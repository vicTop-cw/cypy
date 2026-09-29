# tenacity — Cypy 复刻（复刻库压测 · Phase 4 装饰器+泛型+异常）

将 Python `tenacity` 重试库的核心子集移植到 Cypy，用于压测编译器在
**带参装饰器工厂 / 嵌套函数 / 闭包捕获 / 异常层级 / try-except / while 循环
/ 可变变量 / 逻辑运算符** 等路径上的正确性。

## 移植内容（子集）

- `RetryError(Exception)` —— 重试耗尽异常
- `Attempt` struct —— 单次尝试快照（`number / has_exception / exception`）
- `StopAfterAttempt` struct —— 达到最大次数即停止
- `WaitFixed` struct —— 固定等待时长
- `RetryIfExceptionType` struct —— 发生异常时继续重试
- `Retrying` struct —— 重试引擎（`call(fn)` 循环调用、按策略决定继续/抛出）
- `retry(...)` 装饰器工厂 —— 返回包裹目标函数的闭包

## 压测方式

```powershell
# 仅类型检查
python -m cypyc build Find_BUG/tenacity --check-only
# 完整构建（生成可运行 .pyd）
python -m cypyc build Find_BUG/tenacity
```

自动化回归见 `tests/test_find_bug_tenacity.py`（编译 + 运行时执行重试逻辑）。

## 由此暴露并修复的编译器缺陷

| Bug | 说明 | 状态 |
|-----|------|------|
| BUG-010 | `a and not b` 解析失败（`_parse_bitwise_and` 误吞逻辑 `and`） | ✅ Fixed |
| BUG-019 | `obj.attr = v` 属性赋值右侧丢失（被当表达式语句） | ✅ Fixed |
| BUG-020 | 显式 `__init__` 的结构体生成重复构造器 | ✅ Fixed |
| BUG-021 | `&&`/`||` 生成非法 Cython（未归一化为 `and`/`or`） | ✅ Fixed |

详见根目录 `Find_BUG/BUGS.md`。
