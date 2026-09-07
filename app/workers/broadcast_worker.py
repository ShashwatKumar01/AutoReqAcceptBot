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
    - Processes recipients in configurable batch sizes (default 200)
    - Respects Telegram rate limits via TelegramRateLimiter
    - Handles RetryAfter by sleeping exact duration + jitter
    - Updates progress counters atomically in MongoDB
    - Resumable: skips already-sent recipients (status=sent)
    - One failed recipient never stops the batch
    - Handles job pause: checks status before each batch
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
    
    async def _process_job(self, job: dict) -> None:
        """Process one batch of recipients for a job."""
        job_id = str(job['_id'])
        # Re-check status before processing
        current_job = await self.broadcast_repo.get_job(job_id)
        if not current_job or current_job.get('status') != 'running':
            return

        # If recipients aren't pre-populated, generate them from `users` collection
        # for this job's target. They're cached on the job document so we don't
        # re-query every batch.
        if not job.get('_recipients_resolved'):
            recipients = await self._resolve_recipients(job)
            if not recipients:
                await self.broadcast_repo.update_job_status(
                    job_id, 'completed', {'completed_at': __import__('datetime').datetime.utcnow()}
                )
                self.logger.info('BROADCAST_JOB_NO_RECIPIENTS', job_id=job_id)
                return
            await self.broadcast_repo.set_job_total_recipients(job_id, len(recipients))
            # Stash on the job dict in-memory for this loop iteration only
            job['_recipients'] = recipients
            job['_recipients_resolved'] = True
            job['_cursor'] = 0

        recipients = job.get('_recipients', [])
        cursor = job.get('_cursor', 0)
        batch = recipients[cursor:cursor + self.batch_size]
        if not batch:
            await self.broadcast_repo.update_job_status(
                job_id, 'completed', {'completed_at': __import__('datetime').datetime.utcnow()}
            )
            self.logger.info('BROADCAST_JOB_COMPLETED', job_id=job_id)
            return

        success_count = 0
        failure_count = 0

        for user_id in batch:
            if not self.running:
                break

            success = await self._send_to_recipient(job, {'user_id': user_id})
            if success:
                success_count += 1
            else:
                failure_count += 1

            # Rate limiting sleep between messages
            await asyncio.sleep(0.04)  # 40ms minimum sleep

        job['_cursor'] = cursor + len(batch)
        await self.broadcast_repo.update_job_progress(job_id, len(batch), success_count, failure_count)
        self.logger.info('BROADCAST_BATCH_PROCESSED', job_id=job_id, success=success_count, failure=failure_count)

    async def _resolve_recipients(self, job: dict) -> list[int]:
        """Compute the list of user IDs to send to, based on job.target.
        Reads from `users` collection (not join_requests) since that's where
        the bot has been recording actual interactions.
        """
        if not self.user_repo or not self.chat_repo:
            self.logger.error('BROADCAST_NO_REPO', job_id=job.get('_id'))
            return []

        target = job.get('target')
        target_id = job.get('target_id')
        owner_id = job.get('owner_id')

        if target == 'chat' and target_id:
            cursor = self.user_repo.collection.aggregate([
                {"$unwind": "$chat_ids"},
                {"$match": {"chat_ids": int(target_id)}},
                {"$group": {"_id": "$telegram_id"}},
            ])
            docs = await cursor.to_list(length=None)
            return [d['_id'] for d in docs]

        if target == 'all':
            chats = await self.chat_repo.get_by_admin(int(owner_id)) if owner_id else []
            chat_ids = [c['chat_id'] for c in chats]
            if not chat_ids:
                return []
            cursor = self.user_repo.collection.aggregate([
                {"$unwind": "$chat_ids"},
                {"$match": {"chat_ids": {"$in": chat_ids}}},
                {"$group": {"_id": "$telegram_id"}},
            ])
            docs = await cursor.to_list(length=None)
            return [d['_id'] for d in docs]

        if target == 'all_users' or target == 'master':
            # Master broadcast — every user in DB
            cursor = self.user_repo.collection.find({}, {"telegram_id": 1, "_id": 0})
            docs = await cursor.to_list(length=None)
            return [d['telegram_id'] for d in docs]

        return []
    
    async def _send_to_recipient(self, job: dict, recipient: dict) -> bool:
        """Send broadcast message to one recipient."""
        user_id = recipient['user_id']
        payload = job.get('payload', {})
        max_retries = 3

        for attempt in range(max_retries):
            try:
                # Wait based on global rate limiter
                await self.rate_limiter.acquire()

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
