import asyncio
import time
from typing import Any
from redis.asyncio import Redis

class TelegramRateLimiter:
    """
    Implements sliding window rate limiting using Redis.
    
    Telegram global limits:
    - 30 messages/second global
    - 20 messages/minute per chat (groups)
    - 1 message/second per chat (broadcast)
    """
    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self.global_limit = 25  # messages/second (conservative)
        self.per_chat_limit = 1  # messages/second per chat for broadcast
        self.global_key = "rate_limit:telegram:global"
    
    async def acquire(self) -> None:
        """Alias used by broadcast worker."""
        await self.acquire_global()

    async def acquire_global(self) -> None:
        """Wait until global rate limit allows a send. Uses Redis atomic counter."""
        while True:
            current_time = int(time.time())
            key = f"{self.global_key}:{current_time}"
            
            async with self.redis.pipeline(transaction=True) as pipe:
                pipe.incr(key)
                pipe.expire(key, 2)
                results = await pipe.execute()
                
            count = results[0]
            if count <= self.global_limit:
                return
            
            # Wait until the next second
            await asyncio.sleep(1.0 - (time.time() - current_time))
    
    async def acquire_per_chat(self, chat_id: int) -> None:
        """Per-chat rate limiting for broadcast."""
        while True:
            current_time = int(time.time())
            key = f"rate_limit:telegram:chat:{chat_id}:{current_time}"
            
            async with self.redis.pipeline(transaction=True) as pipe:
                pipe.incr(key)
                pipe.expire(key, 2)
                results = await pipe.execute()
                
            count = results[0]
            if count <= self.per_chat_limit:
                return
                
            await asyncio.sleep(1.0 - (time.time() - current_time))
    
    async def handle_retry_after(self, retry_after: int) -> None:
        """Sleep for retry_after + jitter seconds."""
        jitter = 0.5
        await asyncio.sleep(retry_after + jitter)


class UserCommandThrottler:
    """
    Per-user command throttling using Redis.
    Default: 30 commands per minute per user.
    """
    def __init__(self, redis_client: Redis, limit: int = 30, window: int = 60):
        self.redis = redis_client
        self.limit = limit
        self.window = window
    
    async def is_allowed(self, user_id: int) -> bool:
        """Returns True if user is within rate limit."""
        current_time = int(time.time())
        window_start = current_time - self.window
        key = f"throttle:user:{user_id}"
        
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zadd(key, {str(current_time): current_time})
            pipe.zcard(key)
            pipe.expire(key, self.window)
            results = await pipe.execute()
            
        count = results[2]
        return count <= self.limit
    
    async def get_remaining(self, user_id: int) -> int:
        """Returns remaining allowed commands."""
        current_time = int(time.time())
        window_start = current_time - self.window
        key = f"throttle:user:{user_id}"
        
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zcard(key)
            results = await pipe.execute()
            
        count = results[1]
        return max(0, self.limit - count)
