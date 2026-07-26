# 异常处理

## 异常类型

### 内置异常

```python
# Python 内置异常
try:
    let result = 10 / 0
except ZeroDivisionError:
    pass

try:
    let value = int("not a number")
except ValueError:
    pass

try:
    let items = [1, 2, 3]
    let item = items[10]
except IndexError:
    pass
```

### 自定义异常

```python
# 自定义异常类型
class CustomError(Exception):
    pass

class ValidationError(Exception):
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message

# 使用自定义异常
def validate_user(user: dict[str, object]):
    if "name" not in user:
        raise ValidationError(field="name", message="Name is required")
    if len(str(user["name"])) < 3:
        raise ValidationError(field="name", message="Name must be at least 3 characters")
```

## 异常处理语法

### try-except

```python
# 基本异常处理
try:
    process_data()
except Exception as e:
    print(f"An error occurred: {e}")
```

### 多个异常

```python
# 处理多种异常类型
try:
    load_config()
except FileNotFoundError:
    print("Config file not found")
except PermissionError:
    print("Permission denied")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## 抛出异常

### raise 语句

```python
# 抛出异常
def divide(a: float, b: float) -> float:
    if b == 0:
        raise ZeroDivisionError("Cannot divide by zero")
    return a / b

# 抛出自定义异常
def login(username: str, password: str):
    if not username:
        raise ValueError("Username cannot be empty")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
```

### 重新抛出异常

```python
# 捕获并重新抛出
try:
    process()
except Exception as e:
    log_error(e)
    raise  # 重新抛出原异常
```

## 异常链

### from 语法

```python
# 异常链
try:
    open_file("data.txt")
except FileNotFoundError as e:
    raise RuntimeError("Failed to load data") from e

# 无异常链
try:
    open_file("data.txt")
except FileNotFoundError:
    raise RuntimeError("Failed to load data") from None
```

## 异常处理最佳实践

### 具体异常优先

```python
# 优先捕获具体异常
try:
    parse_json(data)
except ValueError:
    print("Invalid JSON format")
except KeyError:
    print("Missing required field")
except Exception:
    print("Unexpected error")  # 最后捕获通用异常
```

### 资源清理

```python
# 使用 finally 清理资源
def process_file(path: str):
    let file = None
    try:
        file = open(path, "r")
        return file.read()
    except IOError:
        print("Failed to read file")
        return ""
    finally:
        if file:
            file.close()
```

## 异常特性

| 特性 | 说明 |
|------|------|
| **内置异常** | 继承 Python 内置异常体系 |
| **自定义异常** | 支持自定义异常类型 |
| **异常字段** | 自定义异常可以有字段 |
| **raise** | 抛出异常 |
| **异常链** | `from` 语法链接异常 |
| **try-except-finally** | 完整的异常处理结构 |