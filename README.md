# FastAPIRedisCRUD
FastAPI, MySQL and Redis are the building materials for this To-Do app. It simply operates CRUD to database. When making any POST request through the API, it writes to MySQL and then cache the data in the Redis. Similarly for the UPDATE request. But for GET request, the API returns the data immediately when the data is available in the Redis. If not data available to the Redis then it retrieves from MySQL and cache to Redis again. At last it deletes from both the databases whenever the DELETE API is called.

# Data Flow
![image](https://github.com/tanjimulislam55/FastAPIRedisCRUD/assets/38599881/00d63b46-b3e2-4eb0-a234-1e0a4a4a91da)
