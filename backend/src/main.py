from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
import os
import uvicorn
import aiomysql
import aioredis


class TodoCreate(BaseModel):
    title: str
    description: str


class TodoOut(TodoCreate):
    id: int


class TodoUpdate(BaseModel):
    title: Optional[str]
    description: Optional[str]


redis_pool = None
mysql_pool = None


load_dotenv()


mysql_config = {
    "host": os.environ.get("MYSQL_HOST"),
    "port": int(os.environ.get("MYSQL_PORT", 3306)),
    "user": os.environ.get("MYSQL_USER"),
    "password": os.environ.get("MYSQL_PASSWORD"),
    "db": os.environ.get("MYSQL_DATABASE"),
}

redis_config = {
    "host": os.environ.get("REDIS_HOST"),
    "port": int(os.environ.get("REDIS_PORT", 6379)),
}


async def create_mysql_pool():
    return await aiomysql.create_pool(**mysql_config)


async def get_mysql_pool():
    global mysql_pool
    if not mysql_pool:
        mysql_pool = await create_mysql_pool()
    return mysql_pool


async def create_redis_pool():
    return aioredis.ConnectionPool.from_url(f"redis://{redis_config['host']}:{redis_config['port']}")


async def get_redis_connection():
    global redis_pool
    if not redis_pool:
        redis_pool = await create_redis_pool()
        return aioredis.Redis(connection_pool=redis_pool)
    return aioredis.Redis(connection_pool=redis_pool)


async def create_todo(todo: TodoCreate) -> TodoOut:
    pool = await get_mysql_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            query = "INSERT INTO todos (title, description) VALUES (%s, %s)"
            id = await cur.execute(query, (todo.title, todo.description))
            await conn.commit()
            return TodoOut(id=id, title=todo.title, description=todo.description)


async def get_todo(todo_id: int):
    pool = await get_mysql_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            query = "SELECT * FROM todos WHERE id = %s"
            await cur.execute(query, (todo_id,))
            result = await cur.fetchone()
            if result:
                return TodoOut(**result)


async def update_todo(todo_id: int, todo: TodoUpdate):
    pool = await get_mysql_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            query = "UPDATE todos SET title = %s, description = %s WHERE id = %s"
            await cur.execute(query, (todo.title, todo.description, todo_id))
        await conn.commit()


async def delete_todo(todo_id: int):
    pool = await get_mysql_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            query = "DELETE FROM users WHERE id = %s"
            await cur.execute(query, (todo_id,))
        await conn.commit()


# Redis Caching
async def get_todo_from_cache(todo_id: int):
    redis = await get_redis_connection()
    todo_data = await redis.get(f"todo:{todo_id}")
    if todo_data:
        return TodoOut.parse_raw(todo_data)


async def cache_set(todo: TodoOut):
    redis = await get_redis_connection()
    await redis.set(f"todo:{todo.id}", todo.json().encode("utf-8"))
    value = await redis.get(f"todo:{todo.id}")
    return value


async def cache_delete(key):
    redis = await get_redis_connection()
    await redis.delete(key)


app = FastAPI()


# API Routes
@app.post("/todos/", response_model=TodoOut)
async def create_todo_handler(todo: TodoCreate):
    new_todo = await create_todo(todo)
    cache = await cache_set(new_todo)
    print("cache", cache)
    return new_todo


@app.get("/todos/{todo_id}", response_model=TodoOut)
async def get_todo_handler(todo_id: int):
    cached_todo = await get_todo_from_cache(todo_id)
    if cached_todo:
        return cached_todo
    todo = await get_todo(todo_id)
    if todo:
        await cache_set(todo)
    return todo


@app.put("/todos/{todo_id}", response_model=TodoUpdate)
async def update_todo_handler(todo_id: int, todo: TodoUpdate):
    await update_todo(todo_id, todo)
    await cache_set(TodoOut(id=todo_id, **todo.dict(exclude_unset=True)))
    return todo


@app.delete("/todos/{todo_id}")
async def delete_todo_handler(todo_id: int):
    await delete_todo(todo_id)
    await cache_delete(f"todo:{todo_id}")
    return {"message": "Todo deleted"}


# Event Handlers
@app.on_event("startup")
async def startup_event():
    global mysql_pool, redis_pool
    mysql_pool = await create_mysql_pool()
    redis_pool = await create_redis_pool()


@app.on_event("shutdown")
async def shutdown_event():
    global mysql_pool, redis_pool
    if mysql_pool:
        mysql_pool.close()
        await mysql_pool.wait_closed()
    if redis_pool:
        await redis_pool.wait_closed()


if __name__ == "__main__":
    uvicorn.run("main:app", port=8000, host="127.0.0.1", reload=True)
