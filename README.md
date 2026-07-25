# Cypy

A Python-like language that compiles to Cython.

## Features

- **Python Superset**: Any valid Python code is valid Cypy code
- **Gradual Typing**: Annotated variables use static types, unannotated fall back to PyObject
- **Compile-time Checking**: `cypyc` transpiler catches type errors early
- **Cython Backend**: Compiles to Cython for high-performance C code
- **Modern Syntax**: Pattern matching, enum, struct, trait, and more

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

### Build Blocks
```python
# Variable build block
result =:
    x = 10
    y = 20
    x + y  # result = 30
```

## Documentation

See [CYPY_SYNTAX.md](CYPY_SYNTAX.md) for full language specification.

## Testing

```bash
python scripts/run_tests.py
```

## License

MIT
