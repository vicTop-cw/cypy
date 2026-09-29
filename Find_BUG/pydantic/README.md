# Cypy 版 Pydantic（核心子集端口）

把 Pydantic 的核心能力用 Cypy 语法复刻一份，放进 `Find_BUG/pydantic/`，
目的是**压测 `cypyc` 编译器**——真实库移植最容易撞出编译器的缺陷。
（编译器 bug 由另一个 agent 同步在修，本目录先产出合规的 cypyc 源码，后续统一编译验证。）

## 已复刻的能力

| Pydantic 概念 | Cypy 端口实现 |
|---|---|
| `BaseModel` | `class BaseModel`（`base_model.cypy`） |
| `Field(...)` / 字段约束 | `Field()` 工厂 + `FieldInfo`（`fields.cypy`）：`min_length` / `max_length` / `ge` / `le` / `pattern` |
| `ValidationError` | `class ValidationError(Exception)`（`errors.cypy`），携带 `errors` 列表 |
| 类型强转 | str / int / float / bool 的宽松强转（`validation.cypy`） |
| 嵌套模型 | `Field(type_name="Address")` + 模型注册表递归校验（`registry.cypy`） |
| `list[Model]` | `List("Tag")`（`type_name="list"` + `item_type`） |
| `field_validator` | `_custom_validate(self, name, value)` 钩子 + `match/case`（见 `User`） |
| 构造 / 序列化 | `Model(**data)`（`**kwargs`）、`model_dump()`、`model_validate(dict)` |

## 目录结构

```
pydantic/
├── errors.cypy        # ValidationError
├── fields.cypy        # FieldInfo + Field() / List()
├── registry.cypy      # 模型注册表
├── validation.cypy    # 强转 + 约束检查内核
├── base_model.cypy    # BaseModel 基类
├── models.cypy        # 示例模型 Address / Tag / User（含嵌套 + list + 自定义校验）
├── BUGS.md            # 编译/运行期发现的 cypyc bug 记录
└── README.md          # 本文件
```

## 与真实 Pydantic 的偏差（v1 有意为之）

1. **字段声明用显式 `fields()` 而非类体注解**：不依赖运行时 `__annotations__` 自省（cypyc 当前是否暴露未验证），最稳。
2. **`pattern` 仅做子串包含**：未接正则引擎，验证阶段再决定是否上 `re`。
3. **`model_dump()` 对嵌套模型/列表返回原始对象**：未递归 dump（v1 简化）。
4. **可变为默认（如 `[]`）在实例间共享**：未做防御性拷贝。
5. **自定义校验走 `_custom_validate` 钩子**而非 `@field_validator` 装饰器（装饰器语法已支持，验证阶段可再改）。

## 忠实端口（选项 B：专门压编译器）

除上面保守版（v1，`BaseModel` + 显式 `fields()`）外，本目录还放了一版**忠实端口**，
刻意用 pydantic 最黑魔法的写法，逼 cypyc 暴露缺陷。基类叫 `Model`（不与 v1 的 `BaseModel` 重名），
示例类加 `F` 前缀避免与 v1 的 `User/Tag/Address` 冲突。

| 文件 | 压测的 cypyc 特性 |
|---|---|
| `model_faithful.cypy` | `class Model<T>` 泛型基类；`__init_subclass__` + `cls.__annotations__` 自省；`getattr`/`hasattr`/`__getattr__`；`model_config` 类属性 |
| `validators_faithful.cypy` | `@field_validator` / `@model_validator` 装饰器工厂 + 闭包捕获 |
| `examples_faithful.cypy` | 类体 `Field()` 注解；`Model<Self>` 自引用泛型；`class Foo<T>` 泛型；`data: T`；`list<T>`/`list<str>` 参数化注解；`str \| None` Union 注解；`Enum` 字段；装饰器应用到方法；返回注解引用本类 |

> 这些写法大概率当前 cypyc 还编译不了——**这正是要找的 bug**。撞到的填 `BUGS.md`。

## 后续编译验证

```powershell
# 先类型检查（快，找类型 bug）
cypyc build Find_BUG/pydantic --check-only
# 再全量生成 .pyx 并编译（找 codegen bug）
cypyc build Find_BUG/pydantic
```

遇到的 cypyc 缺陷统一记到 `BUGS.md`。
