# 并发

## Cypy 并发关键字

### `spawn` 和 `go` 关键字

Cypy 提供了 `spawn` 和 `go` 两个关键字用于并发编程：

| 关键字 | 当前实现 | 用途 |
|--------|----------|------|
| `spawn` | 生成 `threading.Thread` | 创建线程，立即启动 |
| `go` | 生成 `asyncio.create_task` | 创建异步协程，需要 asyncio 事件循环 |

```python
# spawn 语句 - 块形式（线程）
spawn:
    print("Running in thread")
    # 执行任务

# go 语句 - 块形式（协程）
go:
    print("Running in coroutine")
    # 执行任务

# spawn 语句 - 调用形式
def worker():
    print("Worker running")

spawn worker()  # 创建线程

# go 语句 - 调用形式
async def async_worker():
    print("Async worker running")

go async_worker()  # 创建协程
```

### 使用注意

- `spawn` 创建的线程在后台运行，与主线程并行执行
- `go` 创建的协程需要在 asyncio 事件循环中运行（如在 `asyncio.run()` 内）
- `go` 适用于 I/O 密集型任务，`spawn` 适用于 CPU 密集型任务

## 线程

### 基本线程

```python
import threading

# 创建线程
def worker(name: str):
    print(f"Worker {name} started")
    # 执行任务
    print(f"Worker {name} finished")

let t1: threading.Thread = threading.Thread(target=worker, args=("A",))
let t2: threading.Thread = threading.Thread(target=worker, args=("B",))

# 启动线程
t1.start()
t2.start()

# 等待线程完成
t1.join()
t2.join()
```

### 线程池

```python
from concurrent.futures import ThreadPoolExecutor

# 使用线程池
def process_item(item: int) -> int:
    return item * 2

let items: list<int> = [1, 2, 3, 4, 5]

with ThreadPoolExecutor(max_workers=3) as executor:
    results = list(executor.map(process_item, items))
    print(results)  # [2, 4, 6, 8, 10]
```

## 进程

### 基本进程

```python
import multiprocessing

# 创建进程
def worker(name: str):
    print(f"Worker {name} started")
    # 执行任务
    print(f"Worker {name} finished")

let p1: multiprocessing.Process = multiprocessing.Process(target=worker, args=("A",))
let p2: multiprocessing.Process = multiprocessing.Process(target=worker, args=("B",))

# 启动进程
p1.start()
p2.start()

# 等待进程完成
p1.join()
p2.join()
```

### 进程池

```python
from concurrent.futures import ProcessPoolExecutor

# 使用进程池
def compute_factorial(n: int) -> int:
    let result: int = 1
    for i in range(1, n + 1):
        result *= i
    return result

let numbers: list<int> = [5, 6, 7, 8]

with ProcessPoolExecutor(max_workers=2) as executor:
    results = list(executor.map(compute_factorial, numbers))
    print(results)  # [120, 720, 5040, 40320]
```

## 异步编程

### async/await

```python
import asyncio

# 异步函数
async def fetch_data(url: str) -> str:
    # 模拟网络请求
    await asyncio.sleep(1)
    return f"Data from {url}"

async def main():
    # 并发执行多个异步任务
    let task1 = asyncio.create_task(fetch_data("https://example.com"))
    let task2 = asyncio.create_task(fetch_data("https://api.example.com"))
    
    # 等待所有任务完成
    let results = await asyncio.gather(task1, task2)
    print(results)

# 运行异步程序
asyncio.run(main())
```

### 异步上下文管理器

```python
# 异步上下文管理器
class AsyncResource:
    async def __aenter__(self):
        print("Acquiring resource")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        print("Releasing resource")

async def use_resource():
    async with AsyncResource():
        print("Using resource")
```

## 协程

### 基本协程

```python
# 使用 yield 实现协程
def coroutine():
    let value = yield "Start"
    print(f"Received: {value}")
    yield "Middle"
    yield "End"

# 使用协程
let co = coroutine()
print(next(co))      # "Start"
print(co.send(42))  # "Received: 42", "Middle"
print(next(co))      # "End"
```

### 协程调度

```python
# 简单协程调度器
def scheduler(coroutines):
    let tasks = list(coroutines)
    while tasks:
        for co in tasks[:]:
            try:
                next(co)
            except StopIteration:
                tasks.remove(co)

# 使用调度器
def task1():
    for i in range(3):
        print(f"Task 1: {i}")
        yield

def task2():
    for i in range(3):
        print(f"Task 2: {i}")
        yield

scheduler([task1(), task2()])
```

## 并发特性

| 特性 | 说明 |
|------|------|
| **线程** | `threading` 模块，共享内存 |
| **进程** | `multiprocessing` 模块，独立内存 |
| **线程池** | `ThreadPoolExecutor` |
| **进程池** | `ProcessPoolExecutor` |
| **异步编程** | `async/await`，单线程并发 |
| **协程** | `yield` 实现，轻量级并发 |