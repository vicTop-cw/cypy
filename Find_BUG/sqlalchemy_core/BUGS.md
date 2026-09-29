# sqlalchemy_core 复刻发现的编译器 Bug

本目录复刻 SQLAlchemy Core 表达式层时暴露的缺陷，详细根因与修复见根目录 `../BUGS.md`。

| Bug | 严重度 | 状态 | 触发代码 |
|-----|--------|------|----------|
| BUG-022 | High | ✅ Fixed | `def __init__(self, name: str, table: str = ""):` 默认值丢失 |
| BUG-023 | High | ⚠️ Workaround | `a == 5 & b > 18`（trait 包装器不转发运算符）/ `isinstance(o, ClauseElement)` 恒假 |

## 最小复现

```cypy
# BUG-022
struct Point:
    x: int
    y: int
    def __init__(self, x: int, y: int = 0):
        self.x = x
        self.y = y
# Point(x=5) 报“需要 2 个位置参数，只给了 1 个”

# BUG-023
trait ClauseElement:
    def compile(self) -> str
struct Column:
    def __eq__(self, other) -> ClauseElement:   # 返回 trait 类型
        return _BinaryExpression(self, "=", other)
# (col == 5) 得到 trait 包装器，对其做 & 失败
```

## 工作副本规避方式

- 运算符方法返回**具体类型**（`_BinaryExpression`）而非 trait，避免链式运算经过包装器。
- `isinstance` 判断用具体节点类型（`isinstance(o, _BinaryExpression)` 等），不用 `isinstance(o, Trait)`。
