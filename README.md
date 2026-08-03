# Cypy

A Python-like language that compiles to Cython.

## Features

- **Python Compatibility**: Partial Python syntax compatibility
- **Gradual Typing**: Annotated variables use static types, unannotated fall back to `object`
- **Compile-time Checking**: `cypyc` transpiler catches type errors early
- **Cython Backend**: Compiles to Cython for high-performance C code
- **Modern Syntax**: Pattern matching, enum, struct, trait, let/var, and more
- **Concurrency**: `go` keyword for coroutines, `spawn` for threads
- **Pipe Operator**: `|>` for function chaining
- **List Comprehensions**: Full support with nested loops and conditions

## Quick Start

```bash
# Install dependencies
pip install -e .

# Transpile a Cypy file
cypyc input.cypy

# Transpile and compile
cypyc --compile input.cypy

# Type check only
cypyc --check input.cypy
```

## Syntax Examples

### Structs
```python
struct Point:
    x: float
    y: float
    
    def distance(self, other: Point) -> float:
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2) ** 0.5
```

### Pattern Matching
```python
match value:
    case 1:
        return "one"
    case (a, b):
        return f"tuple: {a}, {b}"
    case _:
        return "other"
```

### Enum
```python
enum Color:
    Red
    Green
    Blue

def process_color(c: Color) -> int:
    match c:
        case Color.Red:
            return 1
        case _:
            return 0
```

### Let/Var Variables
```python
let x: int = 10  # Immutable, cannot be reassigned
var y: int = 20  # Mutable, can be reassigned
```

### Pipe Operator
```python
let result = 5 |> double |> square  # equivalent to square(double(5))
```

### Go (Coroutines) and Spawn (Threads)
```python
let task = go fetch_data(url)  # asyncio.create_task
let thread = spawn heavy_computation()  # threading.Thread
```

### List Comprehensions
```python
let squares = [x ** 2 for x in range(10) if x % 2 == 0]
```

## Documentation

- [SYNTAX_IMPLEMENTATION_STATUS.md](SYNTAX_IMPLEMENTATION_STATUS.md) - 语法实现状态报告
- [SYNTAX/00-introduction.md](SYNTAX/00-introduction.md) - 语言介绍
- [SYNTAX/01-basic-types.md](SYNTAX/01-basic-types.md) - 基础类型
- [SYNTAX/02-type-annotations.md](SYNTAX/02-type-annotations.md) - 类型注解
- [SYNTAX/05-struct.md](SYNTAX/05-struct.md) - 结构体
- [SYNTAX/06-enum.md](SYNTAX/06-enum.md) - 枚举
- [SYNTAX/07-trait-impl.md](SYNTAX/07-trait-impl.md) - 特质系统
- [SYNTAX/09-functions.md](SYNTAX/09-functions.md) - 函数
- [SYNTAX/10-variables.md](SYNTAX/10-variables.md) - 变量
- [SYNTAX/20-concurrency.md](SYNTAX/20-concurrency.md) - 并发
- [SYNTAX/23-compilation.md](SYNTAX/23-compilation.md) - 编译系统

## Project-Level Compilation

```bash
# Build entire project with cross-module type inference
cypyc build <project_directory>

# Build with specific entry point
cypyc build <project_directory> --entry main

# Type check only
cypyc build <project_directory> --check-only
```

## Examples

Explore the [examples/](examples/) directory for code examples:

- [basic_types.cypy](examples/basic_types.cypy) - Basic types and type conversion
- [control_flow.cypy](examples/control_flow.cypy) - Control flow statements
- [functions.cypy](examples/functions.cypy) - Functions and pipe operator
- [struct_enum.cypy](examples/struct_enum.cypy) - Structs and enums
- [concurrency.cypy](examples/concurrency.cypy) - Coroutines and threads
- [list_comprehension.cypy](examples/list_comprehension.cypy) - List comprehensions

## Testing

```bash
python scripts/run_tests.py
```

## License

MIT
