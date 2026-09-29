# Cypy 版 Pydantic — 编译器 Bug 记录（Find_BUG/pydantic）

> 本目录用于压测 `cypyc`。移植过程中撞到的**编译器缺陷**统一记在这里，
> 由负责修编译器的 agent 跟进。每条包含：现象 / 最小复现 / 期望行为 / 实际行为。

## 待验证项（编译通过前先列出来，便于对照）

- [ ] `**kwargs` 形参注解 `**data: dict<str, object>` 的 codegen 是否正确
- [ ] `class` 实例字段在 `__init__` 中动态赋值（`self._values = {}`）是否支持
- [ ] `isinstance(value, dict/list/int/...)` 对内置类型的 codegen
- [ ] `int(value)` / `float(value)` / `str(value)` 强转调用
- [ ] `match name: case "email":` 字符串字面量匹配
- [ ] `dict.get(key, default)` 带默认值的 codegen
- [ ] 模块级 `var REGISTRY: dict<str, object> = {}` 全局可变状态
- [ ] 跨模块 import 链路：models -> base_model -> validation -> registry / fields / errors
- [ ] 在 `object` 上动态调用 `.model_validate(...)`（注册表取出的类）

## 选项 B 忠实端口待验证项（高优先级 / 大概率有坑）

- [ ] 泛型类定义 `class Model<T>` / `class FResponse<T>(Model<T>)` 的 codegen
- [ ] 泛型自引用应用 `class FUser(Model<FUser>)`、`class FTree(Model<FTree>)`
- [ ] 字段类型用泛型参 `data: T`
- [ ] 参数化注解 `list<str>` / `list<Tree>`（cypyc 用 `<>` 而非 `[]`）
- [ ] Union 注解 `str | None` 作为字段类型
- [ ] 类体注解 `id: int` / `name: str = Field(...)` 是否生成类属性
- [ ] `__init_subclass__(cls)` 隐式回调 + `cls.__annotations__` 运行时自省
- [ ] `getattr(cls, name, None)` / `hasattr(cls, "model_config")` 动态属性
- [ ] `__getattr__(self, name)` dunder 方法（让 `self.age` 生效）
- [ ] `@field_validator("email")` / `@model_validator(mode="after")` 装饰器应用到方法 + 闭包捕获
- [ ] 装饰器工厂返回装饰器、闭包捕获 `*fields` / `mode`
- [ ] `Enum` 字段强转（`color: FColor = FColor.RED` -> 校验时 string->enum）
- [ ] `model_config = {"extra": "forbid"}` 类属性 + 读取
- [ ] 方法返回注解引用本类 `-> FUser`（前向引用）
- [ ] 类体 `Field()` 默认值如何被 `__init_subclass__` 读到（pydantic 用类命名空间，cypyc 未必有）

## 已发现 Bug

（暂无 —— 待 `cypyc build Find_BUG/pydantic --check-only` 跑起来后填充）
