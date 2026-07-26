# 类定义

## 基本语法

### 简单类

```python
class Person:
    def __init__(self, name: str, age: int):
        self.name = name
        self.age = age
    
    def greet(self) -> str:
        return f"Hello, my name is {self.name}"

# 创建实例
let p: Person = Person(name="Alice", age=30)
print(p.greet())  # "Hello, my name is Alice"
```

### 类成员

```python
class Counter:
    # 类变量
    instances: int = 0
    
    def __init__(self):
        # 实例变量
        self.value: int = 0
        Counter.instances += 1
    
    def increment(self) -> None:
        self.value += 1
    
    @staticmethod
    def get_instance_count() -> int:
        return Counter.instances
    
    @classmethod
    def create_with_value(cls, value: int) -> Counter:
        let c: Counter = cls()
        c.value = value
        return c
```

## 继承

### 单继承

```python
class Animal:
    def __init__(self, name: str):
        self.name = name
    
    def speak(self) -> str:
        return "..."

class Dog(Animal):
    def __init__(self, name: str, breed: str):
        super().__init__(name)
        self.breed = breed
    
    def speak(self) -> str:
        return "Woof!"

# 使用
let dog: Dog = Dog(name="Buddy", breed="Golden Retriever")
print(dog.speak())  # "Woof!"
```

### 多重继承

```python
class Flyable:
    def fly(self) -> str:
        return "Flying..."

class Swimmable:
    def swim(self) -> str:
        return "Swimming..."

class Duck(Animal, Flyable, Swimmable):
    def speak(self) -> str:
        return "Quack!"

let duck: Duck = Duck(name="Donald")
print(duck.speak())  # "Quack!"
print(duck.fly())    # "Flying..."
print(duck.swim())   # "Swimming..."
```

## 方法类型

### 实例方法

```python
class Calculator:
    def add(self, a: int, b: int) -> int:
        return a + b
    
    def multiply(self, a: int, b: int) -> int:
        return a * b
```

### 静态方法

```python
class MathUtils:
    @staticmethod
    def sqrt(x: float) -> float:
        return x ** 0.5
    
    @staticmethod
    def pi() -> float:
        return 3.141592653589793
```

### 类方法

```python
class Factory:
    @classmethod
    def create(cls, type: str) -> object:
        match type:
            case "dog":
                return Dog(name="Generic Dog")
            case "cat":
                return Cat(name="Generic Cat")
            case _:
                raise ValueError(f"Unknown type: {type}")
```

## 魔术方法

### 常见魔术方法

```python
class Vector:
    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y
    
    def __add__(self, other: Vector) -> Vector:
        return Vector(self.x + other.x, self.y + other.y)
    
    def __sub__(self, other: Vector) -> Vector:
        return Vector(self.x - other.x, self.y - other.y)
    
    def __repr__(self) -> str:
        return f"Vector({self.x}, {self.y})"
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Vector):
            return False
        return self.x == other.x and self.y == other.y
```

## 装饰器

### 属性装饰器

```python
class Circle:
    def __init__(self, radius: float):
        self._radius = radius
    
    @property
    def radius(self) -> float:
        return self._radius
    
    @radius.setter
    def radius(self, value: float):
        if value <= 0:
            raise ValueError("Radius must be positive")
        self._radius = value
    
    @property
    def area(self) -> float:
        return 3.14159 * self._radius ** 2
```

## 类特性

| 特性 | 说明 |
|------|------|
| **Python 兼容** | 类语法与 Python 完全兼容 |
| **继承支持** | 支持单继承和多重继承 |
| **静态方法** | `@staticmethod` 装饰器 |
| **类方法** | `@classmethod` 装饰器 |
| **属性装饰器** | `@property` 实现属性访问 |
| **魔术方法** | 支持 `__add__`、`__eq__`、`__repr__` 等 |