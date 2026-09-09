import asyncio
import random
from typing import Any, Dict
import structlog
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError, TelegramBadRequest, TelegramAPIError
from app.core.logging import get_logger

class BroadcastWorker:
    """
    Persistent worker that sends broadcast messages in batches.
    
    Architecture:
    - Polls MongoDB for broadcast_jobs with status=running
    - Populates broadcast_recipients from join_requests on first run
    - Processes pending recipients in configurable batch sizes
    - Respects Telegram rate limits via TelegramRateLimiter
    - Updates progress counters atomically in MongoDB
    """
    
    def __init__(
        self,
        broadcast_service,
        broadcast_repo,
        telegram_service,
        rate_limiter,
        user_repo=None,
        chat_repo=None,
        batch_size: int = 200,
        poll_interval: int = 10
    ):
        self.broadcast_service = broadcast_service
        self.broadcast_repo = broadcast_repo
        self.telegram_service = telegram_service
        self.rate_limiter = rate_limiter
        self.user_repo = user_repo
        self.chat_repo = chat_repo
        self.batch_size = batch_size
        self.poll_interval = poll_interval
        self.running = False
        self.logger = get_logger('broadcast_worker')
    
    async def start(self) -> None:
        """Main worker loop."""
        self.running = True
        self.logger.info('BROADCAST_WORKER_STARTED', poll_interval=self.poll_interval, batch_size=self.batch_size)
        while self.running:
            try:
                await self._process_running_jobs()
            except Exception as e:
                self.logger.error('BROADCAST_WORKER_ERROR', error=str(e), exc_info=True)
            await asyncio.sleep(self.poll_interval)
    
    async def _process_running_jobs(self) -> None:
        """Find and process all running jobs."""
        jobs = await self.broadcast_repo.get_running_jobs()
        for job in jobs:
            if not self.running:
                break
            await self._process_job(job)
    
    async def _ensure_recipients(self, job: dict) -> bool:
        """Populate broadcast_recipients collection once per job."""
        job_id = str(job['_id'])
        if job.get('recipients_prepared'):
            return True

        target = job.get('target')
        target_id = job.get('target_id')
        owner_id = job.get('owner_id')

        chat_ids: list[int] = []
        if target == 'chat' and target_id:
            chat_ids = [int(target_id)]
        elif target == 'all' and owner_id and self.chat_repo:
            chats = await self.chat_repo.get_by_admin(int(owner_id))
            chat_ids = [c['chat_id'] for c in chats]
        elif target in ('all_users', 'master') and self.user_repo:
            cursor = self.user_repo.collection.find({}, {"telegram_id": 1, "_id": 0})
            docs = await cursor.to_list(length=None)
            user_ids = [d['telegram_id'] for d in docs]
            if user_ids:
                inserted = await self.broadcast_repo.add_recipients_bulk(job_id, user_ids)
                await self.broadcast_repo.collection.update_one(
                    {"_id": job_id},
                    {"$set": {
                        "recipients_prepared": True,
                        "total_recipients": inserted,
                    }},
                )
            return bool(user_ids)

        if not chat_ids:
            return False

        inserted = await self.broadcast_repo.populate_recipients_from_chats(job_id, chat_ids)
        await self.broadcast_repo.collection.update_one(
            {"_id": job_id},
            {"$set": {
                "recipients_prepared": True,
                "total_recipients": inserted,
            }},
        )
        return inserted > 0

    async def _process_job(self, job: dict) -> None:
        """Process one batch of recipients for a job."""
        job_id = str(job['_id'])
        current_job = await self.broadcast_repo.get_job(job_id)
        if not current_job or current_job.get('status') != 'running':
            return

        if not await self._ensure_recipients(current_job):
            await self.broadcast_repo.update_job_status(
                job_id, 'completed', {'completed_at': __import__('datetime').datetime.utcnow()}
            )
            self.logger.info('BROADCAST_JOB_NO_RECIPIENTS', job_id=job_id)
            return

        sent_so_far = await self.broadcast_repo.count_recipients(job_id, 'sent')
        batch = await self.broadcast_repo.get_pending_recipients(job_id, skip=0, limit=self.batch_size)
        if not batch:
            await self.broadcast_repo.update_job_status(
                job_id, 'completed', {'completed_at': __import__('datetime').datetime.utcnow()}
            )
            self.logger.info('BROADCAST_JOB_COMPLETED', job_id=job_id, sent=sent_so_far)
            return

        success_count = 0
        failure_count = 0

        for recipient in batch:
            if not self.running:
                break

            user_id = recipient['user_id']
            success = await self._send_to_recipient(current_job, {'user_id': user_id})
            if success:
                await self.broadcast_repo.mark_recipient_sent(job_id, user_id)
                success_count += 1
            else:
                await self.broadcast_repo.mark_recipient_failed(job_id, user_id, "send_failed")
                failure_count += 1

            await asyncio.sleep(0.04)

        await self.broadcast_repo.update_job_progress(job_id, len(batch), success_count, failure_count)
        self.logger.info(
            'BROADCAST_BATCH_PROCESSED',
            job_id=job_id,
            success=success_count,
            failure=failure_count,
        )
    
    async def _send_to_recipient(self, job: dict, recipient: dict) -> bool:
        """Send broadcast message to one recipient."""
        user_id = recipient['user_id']
        payload = job.get('payload', {})
        max_retries = 3

        for attempt in range(max_retries):
            try:
                await self.rate_limiter.acquire_global()

                bot = self.telegram_service.bot
                msg_type = payload.get('type', 'text')
                text = payload.get('text')
                caption = payload.get('caption')
                parse_mode = payload.get('parse_mode', 'HTML')
                reply_markup = payload.get('reply_markup')

                if msg_type == 'photo':
                    await bot.send_photo(
                        chat_id=user_id, photo=payload['photo'],
                        caption=caption, parse_mode=parse_mode,
                        reply_markup=reply_markup,
                    )
                elif msg_type == 'video':
                    await bot.send_video(
                        chat_id=user_id, video=payload['video'],
                        caption=caption, parse_mode=parse_mode,
                        reply_markup=reply_markup,
                    )
                elif msg_type == 'document':
                    await bot.send_document(
                        chat_id=user_id, document=payload['document'],
                        caption=caption, parse_mode=parse_mode,
                        reply_markup=reply_markup,
                    )
                elif msg_type == 'animation':
                    await bot.send_animation(
                        chat_id=user_id, animation=payload['animation'],
                        caption=caption, parse_mode=parse_mode,
                        reply_markup=reply_markup,
                    )
                else:
                    await bot.send_message(
                        chat_id=user_id, text=text or "(empty)",
                        parse_mode=parse_mode, reply_markup=reply_markup,
                    )

                return True

            except TelegramRetryAfter as e:
                sleep_time = e.retry_after + random.uniform(0.5, 1.5)
                self.logger.warning('RATE_LIMIT_RETRY_AFTER', user_id=user_id, sleep_time=sleep_time)
                await asyncio.sleep(sleep_time)
            except TelegramForbiddenError:
                self.logger.info('USER_BLOCKED_BOT', user_id=user_id)
                return False
            except TelegramBadRequest as e:
                self.logger.warning('BAD_REQUEST', user_id=user_id, error=str(e))
                return False
            except TelegramAPIError as e:
                self.logger.error('TELEGRAM_API_ERROR', user_id=user_id, error=str(e), attempt=attempt)
                await asyncio.sleep(1 * (attempt + 1))
            except Exception as e:
                self.logger.error('UNKNOWN_BROADCAST_ERROR', user_id=user_id, error=str(e), exc_info=True)
                return False

        return False
    
    async def stop(self) -> None:
        self.running = False
        self.logger.info('BROADCAST_WORKER_STOPPED')
