# 并发编程教程

## 概述

Cypy 提供了多种并发编程方式，包括协程（`go`）、线程（`spawn`）和异步函数。本教程将介绍如何使用这些特性编写高性能并发代码。

## 协程（go 关键字）

### 基本用法

`go` 关键字用于创建轻量级协程，基于 Python 的 `asyncio`：

```cypy
async def fetch_data(url: str) -> str:
    # 模拟网络请求
    import asyncio
    await asyncio.sleep(1)
    return f"Data from {url}"

async def main():
    # 使用 go 创建协程任务
    let task1 = go fetch_data("https://api.example.com/data1")
    let task2 = go fetch_data("https://api.example.com/data2")
    
    # 等待结果
    let result1 = await task1
    let result2 = await task2
    
    print(result1)
    print(result2)
```

### 块形式

```cypy
async def run_concurrent():
    let results = []
    
    go:
        # 协程块
        await asyncio.sleep(0.5)
        results.append("Task 1 completed")
    
    go:
        await asyncio.sleep(0.3)
        results.append("Task 2 completed")
    
    # 等待所有协程完成
    await asyncio.sleep(1)
    print(results)
```

### 并行执行多个任务

```cypy
async def parallel_tasks():
    urls = [
        "https://api.example.com/1",
        "https://api.example.com/2",
        "https://api.example.com/3",
    ]
    
    # 创建多个协程
    let tasks = [go fetch_data(url) for url in urls]
    
    # 等待所有任务完成
    let results = await asyncio.gather(*tasks)
    print(results)
```

## 线程（spawn 关键字）

### 基本用法

`spawn` 关键字用于创建线程，基于 Python 的 `threading`：

```cypy
def heavy_computation(data: list<int>) -> int:
    # 模拟耗时计算
    return sum(x * x for x in data)

def main():
    # 使用 spawn 创建线程
    let thread = spawn heavy_computation([1, 2, 3, 4, 5])
    
    # 主线程可以继续执行其他任务
    print("Main thread continues...")
    
    # 等待线程完成（可选）
    thread.join()
```

### 块形式

```cypy
def thread_blocks():
    let counter = 0
    
    spawn:
        # 线程块
        for _ in range(1000):
            counter += 1
    
    spawn:
        for _ in range(1000):
            counter += 1
    
    # 等待线程完成
    import time
    time.sleep(0.1)
    print(f"Counter: {counter}")
```

### 线程安全

```cypy
import threading

def thread_safe_counter():
    lock = threading.Lock()
    counter = 0
    
    def increment():
        nonlocal counter
        with lock:
            for _ in range(10000):
                counter += 1
    
    spawn increment()
    spawn increment()
    
    import time
    time.sleep(0.5)
    print(f"Thread-safe counter: {counter}")
```

## 异步函数

### async/await 语法

```cypy
async def async_add(a: int, b: int) -> int:
    await asyncio.sleep(0.1)
    return a + b

async def async_workflow():
    # 顺序执行
    let result1 = await async_add(1, 2)
    let result2 = await async_add(result1, 3)
    print(f"Result: {result2}")
```

### 异步生成器

```cypy
async def async_generator(n: int):
    for i in range(n):
        await asyncio.sleep(0.1)
        yield i

async def consume_generator():
    async for value in async_generator(5):
        print(f"Received: {value}")
```

### 异步上下文管理器

```cypy
class AsyncResource:
    async def __aenter__(self):
        print("Acquiring resource")
        return self
    
    async def __aexit__(self, exc_type, exc, tb):
        print("Releasing resource")

async def use_resource():
    async with AsyncResource():
        print("Using resource")
```

## 并发模式

### 生产者-消费者模式

```cypy
import asyncio
from collections import deque

async def producer(queue: asyncio.Queue):
    for i in range(10):
        await queue.put(i)
        await asyncio.sleep(0.1)
    await queue.put(None)  # 结束标记

async def consumer(queue: asyncio.Queue):
    while True:
        item = await queue.get()
        if item is None:
            break
        print(f"Consumed: {item}")
        queue.task_done()

async def producer_consumer():
    queue = asyncio.Queue()
    
    go producer(queue)
    go consumer(queue)
    
    await queue.join()
```

### 任务池模式

```cypy
async def task_pool():
    async def worker(task_id: int):
        await asyncio.sleep(0.2)
        return f"Task {task_id} completed"
    
    # 创建任务池
    tasks = [go worker(i) for i in range(5)]
    
    # 处理结果
    for task in asyncio.as_completed(tasks):
        result = await task
        print(result)
```

### 超时控制

```cypy
async def timeout_example():
    async def long_running_task():
        await asyncio.sleep(5)
        return "Done"
    
    try:
        result = await asyncio.wait_for(long_running_task(), timeout=2)
        print(result)
    except asyncio.TimeoutError:
        print("Task timed out")
```

## 性能对比

### 同步 vs 异步 vs 线程

```cypy
import time

def sync_work():
    """同步执行"""
    start = time.time()
    for _ in range(10):
        time.sleep(0.1)
    end = time.time()
    print(f"Sync: {end - start:.2f}s")

async def async_work():
    """异步执行"""
    start = time.time()
    tasks = [go asyncio.sleep(0.1) for _ in range(10)]
    await asyncio.gather(*tasks)
    end = time.time()
    print(f"Async: {end - start:.2f}s")

def threaded_work():
    """线程执行"""
    start = time.time()
    threads = [spawn time.sleep(0.1) for _ in range(10)]
    for t in threads:
        t.join()
    end = time.time()
    print(f"Threaded: {end - start:.2f}s")
```

## 最佳实践

### 1. 使用 go 进行 I/O 密集型操作

```cypy
# 好的做法：I/O 密集型使用协程
async def fetch_multiple(urls: list<str>) -> list<str>:
    tasks = [go fetch_data(url) for url in urls]
    return await asyncio.gather(*tasks)

# 避免：I/O 密集型使用线程
def fetch_with_threads(urls: list<str>) -> list<str>:
    results = []
    def fetch(url):
        results.append(requests.get(url).text)
    threads = [spawn fetch(url) for url in urls]
    for t in threads:
        t.join()
    return results
```

### 2. 使用 spawn 进行 CPU 密集型操作

```cypy
# 好的做法：CPU 密集型使用线程
def process_large_data(data: list<int>) -> int:
    return sum(complex_calculation(x) for x in data)

def parallel_process(data_chunks: list<list<int>>) -> int:
    results = []
    def process(chunk):
        results.append(process_large_data(chunk))
    threads = [spawn process(chunk) for chunk in data_chunks]
    for t in threads:
        t.join()
    return sum(results)

# 避免：CPU 密集型使用协程（会阻塞事件循环）
async def slow_process(data: list<int>) -> int:
    return sum(complex_calculation(x) for x in data)
```

### 3. 使用 defer 进行资源清理

```cypy
async def safe_resource():
    connection = await create_connection()
    
    defer:
        await connection.close()
    
    # 使用 connection...
```

### 4. 避免阻塞事件循环

```cypy
async def mixed_work():
    # CPU 密集型操作在线程池中执行
    loop = asyncio.get_event_loop()
    cpu_result = await loop.run_in_executor(None, heavy_computation)
    
    # I/O 操作使用协程
    io_result = await fetch_data("https://api.example.com")
    
    return cpu_result, io_result
```

## 错误处理

### 协程错误处理

```cypy
async def error_handling():
    async def risky_task():
        await asyncio.sleep(0.1)
        raise ValueError("Something went wrong")
    
    try:
        result = await risky_task()
    except ValueError as e:
        print(f"Caught error: {e}")
```

### 多个任务的错误处理

```cypy
async def multiple_errors():
    async def task1():
        await asyncio.sleep(0.1)
        raise RuntimeError("Task 1 failed")
    
    async def task2():
        await asyncio.sleep(0.2)
        return "Task 2 succeeded"
    
    tasks = [go task1(), go task2()]
    
    # 收集所有结果（包括错误）
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"Task {i} failed: {result}")
        else:
            print(f"Task {i} succeeded: {result}")
```

## 与 Python 的对比

| 特性 | Python | Cypy |
|------|--------|------|
| 协程创建 | `asyncio.create_task()` | `go` |
| 线程创建 | `threading.Thread()` | `spawn` |
| 异步函数 | `async def` | `async def` |
| 块形式 | 无 | `go:` / `spawn:` |
| 语法简洁性 | 繁琐 | 简洁 |

## 高级技巧

### 自定义事件循环

```cypy
def custom_event_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(main())
    finally:
        loop.close()
```

### 并发限制

```cypy
async def limited_concurrency(urls: list<str>, max_concurrent: int = 5):
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def fetch_with_limit(url: str):
        async with semaphore:
            return await fetch_data(url)
    
    tasks = [go fetch_with_limit(url) for url in urls]
    return await asyncio.gather(*tasks)
```

### 进度追踪

```cypy
async def track_progress(total: int):
    progress = 0
    
    async def task(i: int):
        nonlocal progress
        await asyncio.sleep(0.1)
        progress += 1
        print(f"Progress: {progress}/{total}")
    
    tasks = [go task(i) for i in range(total)]
    await asyncio.gather(*tasks)
```
