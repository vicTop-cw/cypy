# tenacity 复刻发现的编译器 Bug

本目录复刻 tenacity 时暴露的缺陷，详细根因与修复见根目录 `../BUGS.md`。

| Bug | 严重度 | 状态 | 触发代码 |
|-----|--------|------|----------|
| BUG-010 | Medium | ✅ Fixed | `if a and not b:` / `isinstance(x, int) and not isinstance(x, bool)` |
| BUG-019 | High | ✅ Fixed | `self.x = v` / `o.y = 5`（属性赋值右侧丢失） |
| BUG-020 | High | ✅ Fixed | `struct Attempt:\n  def __init__(self, number): ...`（重复构造器） |
| BUG-021 | Medium | ✅ Fixed | `a && b` / `a || b`（生成非法 Cython） |

## 最小复现

```cypy
# BUG-019
def f(o: object) -> int:
    o.y = 5          # 错误生成裸 o.y
    return 1

# BUG-020
struct Attempt:
    number: int
    has_exception: bool
    def __init__(self, number: int):
        self.number = number
        self.has_exception = False
# 生成两个 def __init__，后者覆盖前者
```
