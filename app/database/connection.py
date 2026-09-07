from motor.motor_asyncio import AsyncIOMotorClient
import pymongo
import logging

class DatabaseManager:
    def __init__(self):
        self.client: AsyncIOMotorClient | None = None
        self.db = None

    async def connect(self, mongo_uri: str = None, db_name: str = None, *, settings=None):
        if settings is not None:
            mongo_uri = mongo_uri or settings.mongodb_uri
            db_name = db_name or settings.mongodb_database
        if not mongo_uri or not db_name:
            raise ValueError("mongo_uri and db_name are required")
        self.client = AsyncIOMotorClient(
            mongo_uri,
            maxPoolSize=50,
            serverSelectionTimeoutMS=5000
        )
        self.db = self.client[db_name]
        
    async def disconnect(self):
        if self.client:
            self.client.close()
            
    async def create_indexes(self):
        if self.db is None:
            return
            
        try:
            # users
            await self.db.users.create_index("telegram_id", unique=True)
            await self.db.users.create_index("status")
            await self.db.users.create_index("created_at")
            await self.db.users.create_index("chat_ids")
            
            # chats
            await self.db.chats.create_index("chat_id", unique=True)
            await self.db.chats.create_index("status")
            await self.db.chats.create_index("type")
            
            # chat_admins
            await self.db.chat_admins.create_index([("chat_id", pymongo.ASCENDING), ("user_id", pymongo.ASCENDING)], unique=True)
            await self.db.chat_admins.create_index("chat_id")
            
            # chat_settings
            await self.db.chat_settings.create_index("chat_id", unique=True)
            
            # join_requests
            await self.db.join_requests.create_index(
                [("chat_id", pymongo.ASCENDING), ("user_id", pymongo.ASCENDING)],
                unique=True,
                partialFilterExpression={"status": {"$in": ["pending", "scheduled"]}}
            )
            await self.db.join_requests.create_index([("status", pymongo.ASCENDING), ("scheduled_at", pymongo.ASCENDING)])
            await self.db.join_requests.create_index([("chat_id", pymongo.ASCENDING), ("created_at", pymongo.ASCENDING)])
            
            # user_chat_relationships
            await self.db.user_chat_relationships.create_index([("user_id", pymongo.ASCENDING), ("chat_id", pymongo.ASCENDING)], unique=True)
            await self.db.user_chat_relationships.create_index("user_id")
            await self.db.user_chat_relationships.create_index("chat_id")
            
            # broadcast_jobs
            await self.db.broadcast_jobs.create_index([("status", pymongo.ASCENDING), ("created_at", pymongo.ASCENDING)])
            await self.db.broadcast_jobs.create_index("owner_id")
            
            # broadcast_recipients
            await self.db.broadcast_recipients.create_index([("job_id", pymongo.ASCENDING), ("user_id", pymongo.ASCENDING)], unique=True)
            await self.db.broadcast_recipients.create_index([("job_id", pymongo.ASCENDING), ("status", pymongo.ASCENDING)])
            
            # subscriptions
            await self.db.subscriptions.create_index([("user_id", pymongo.ASCENDING), ("status", pymongo.ASCENDING)])
            await self.db.subscriptions.create_index("expiry_date", expireAfterSeconds=0)
            
            # plans
            await self.db.plans.create_index("plan_id", unique=True)
            
            # admin_actions
            await self.db.admin_actions.create_index("user_id")
            await self.db.admin_actions.create_index("created_at", expireAfterSeconds=90*24*60*60)  # 90 days
            
            # system_logs
            await self.db.system_logs.create_index("level")
            await self.db.system_logs.create_index("created_at", expireAfterSeconds=30*24*60*60)  # 30 days
            
        except Exception as e:
            logging.error(f"Error creating indexes: {e}")

db_manager = DatabaseManager()

def get_db():
    return db_manager.db
