from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import InsertOne
from pymongo.errors import BulkWriteError, DuplicateKeyError

class BroadcastRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db['broadcast_jobs']
        self.recipients_collection = db['broadcast_recipients']

    async def create_job(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        if 'created_at' not in job_data:
            job_data['created_at'] = datetime.now(timezone.utc)
        if 'status' not in job_data:
            job_data['status'] = 'pending'
        # Normalize: callers may pass job_id or _id — store as _id
        if '_id' not in job_data and 'job_id' in job_data:
            job_data['_id'] = job_data.pop('job_id')
        await self.collection.insert_one(job_data)
        return job_data

    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        return await self.collection.find_one({"_id": job_id})

    async def get_jobs_by_owner(self, owner_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        cursor = self.collection.find({"owner_id": owner_id}).sort("created_at", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_running_jobs(self) -> List[Dict[str, Any]]:
        cursor = self.collection.find({"status": "running"}).sort("created_at", 1)
        return await cursor.to_list(length=None)

    async def update_job_status(self, job_id: str, status: str, extra: Dict[str, Any] = None) -> bool:
        if extra is None:
            extra = {}
        
        update_data = {"status": status, "updated_at": datetime.now(timezone.utc)}
        update_data.update(extra)
        
        result = await self.collection.update_one(
            {"_id": job_id},
            {"$set": update_data}
        )
        return result.modified_count > 0

    async def update_job_progress(self, job_id: str, processed: int, sent: int, failed: int) -> bool:
        result = await self.collection.update_one(
            {"_id": job_id},
            {"$inc": {
                "processed_count": processed,
                "sent_count": sent,
                "failed_count": failed,
                "progress": sent,
            }, "$set": {"updated_at": datetime.now(timezone.utc)}}
        )
        return result.modified_count > 0

    async def set_job_total_recipients(self, job_id: str, total: int) -> bool:
        result = await self.collection.update_one(
            {"_id": job_id},
            {"$set": {"total_recipients": total, "updated_at": datetime.now(timezone.utc)}}
        )
        return result.modified_count > 0

    async def mark_job_completed(self, job_id: str) -> bool:
        return await self.update_job_status(
            job_id, "completed", {"completed_at": datetime.now(timezone.utc)}
        )

    # --- Recipients ---
    async def add_recipient(self, job_id: str, user_id: int) -> bool:
        try:
            await self.recipients_collection.insert_one({
                "job_id": job_id,
                "user_id": user_id,
                "status": "pending",
                "created_at": datetime.now(timezone.utc)
            })
            return True
        except DuplicateKeyError:
            return False

    async def add_recipients_bulk(self, job_id: str, user_ids: List[int]) -> int:
        if not user_ids:
            return 0
            
        now = datetime.now(timezone.utc)
        requests = [
            InsertOne({
                "job_id": job_id,
                "user_id": uid,
                "status": "pending",
                "created_at": now
            }) for uid in user_ids
        ]
        
        try:
            result = await self.recipients_collection.bulk_write(requests, ordered=False)
            return result.inserted_count
        except BulkWriteError as e:
            return e.details['nInserted']

    async def get_pending_recipients(self, job_id: str, skip: int, limit: int) -> List[Dict[str, Any]]:
        cursor = self.recipients_collection.find({
            "job_id": job_id,
            "status": "pending"
        }).sort("user_id", 1).skip(skip).limit(limit)
        return await cursor.to_list(length=limit)

    async def mark_recipient_sent(self, job_id: str, user_id: int) -> bool:
        result = await self.recipients_collection.update_one(
            {"job_id": job_id, "user_id": user_id},
            {"$set": {"status": "sent", "sent_at": datetime.now(timezone.utc)}}
        )
        return result.modified_count > 0

    async def mark_recipient_failed(self, job_id: str, user_id: int, reason: str) -> bool:
        result = await self.recipients_collection.update_one(
            {"job_id": job_id, "user_id": user_id},
            {"$set": {"status": "failed", "error_reason": reason, "failed_at": datetime.now(timezone.utc)}}
        )
        return result.modified_count > 0

    async def count_recipients(self, job_id: str, status: Optional[str] = None) -> int:
        query = {"job_id": job_id}
        if status:
            query["status"] = status
        return await self.recipients_collection.count_documents(query)

    async def get_distinct_user_ids_for_chats(self, chat_ids: List[int]) -> List[int]:
        join_requests = self.collection.database['join_requests']
        pipeline = [
            {"$match": {"chat_id": {"$in": chat_ids}, "status": "approved"}},
            {"$group": {"_id": "$user_id"}}
        ]
        cursor = join_requests.aggregate(pipeline)
        users = await cursor.to_list(length=None)
        return [u["_id"] for u in users]

    async def populate_recipients_from_chats(
        self, job_id: str, chat_ids: List[int], deduplicate: bool = True
    ) -> int:
        join_requests = self.collection.database['join_requests']
        
        match_stage = {"$match": {"chat_id": {"$in": chat_ids}, "status": "approved"}}
        group_stage = {"$group": {"_id": "$user_id"}}
        
        pipeline = [match_stage, group_stage]
        
        cursor = join_requests.aggregate(pipeline)
        
        total_inserted = 0
        batch = []
        now = datetime.now(timezone.utc)
        
        async for doc in cursor:
            user_id = doc["_id"]
            batch.append(InsertOne({
                "job_id": job_id,
                "user_id": user_id,
                "status": "pending",
                "created_at": now
            }))
            
            if len(batch) >= 1000:
                try:
                    res = await self.recipients_collection.bulk_write(batch, ordered=False)
                    total_inserted += res.inserted_count
                except BulkWriteError as e:
                    total_inserted += e.details['nInserted']
                batch = []
                
        if batch:
            try:
                res = await self.recipients_collection.bulk_write(batch, ordered=False)
                total_inserted += res.inserted_count
            except BulkWriteError as e:
                total_inserted += e.details['nInserted']
                
        return total_inserted
