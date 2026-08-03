# 宏系统

## 当前实现状态

Cypy 支持编译期宏定义和调用。宏在编译时展开，生成代码。

### 宏定义语法

```python
# 基本宏定义
macro name(ts: Tokens) -> Tokens =
    body

# 示例：定义一个简单的宏
macro double(ts: Tokens) =
    pass  # 宏体在编译期执行
```

### 宏调用

```python
# 宏调用（使用宏名）
let result = double!(x)
```

### 代码生成

宏定义生成的 Cython 代码：

```python
# Cypy 源码
macro double(ts: Tokens) =
    pass

# 生成的 Cython 代码
# macro double - compile-time macro
def _macro_double(ts):
    # Macro body evaluated at compile time
    pass  # Macro expansion happens during parsing
```

### 反引号代码块插值

宏系统支持反引号代码块 `\`\`\`...\`\`\`` 的插值功能：

```python
# 使用 f``` 进行插值
macro create_function(name):
    f```
    def ${name}():
        print("Hello from ${name}")
    ```

# 使用宏
create_function!("greet")
```

## 实现说明

当前版本的宏系统实现：

1. **宏定义**：`MacroDef` AST 节点存储宏名称、参数列表（字符串）和宏体（AST 节点列表）
2. **宏调用**：`MacroCall` AST 节点存储宏名称和调用参数
3. **宏展开**：`MacroExpander` 类处理宏展开，但只支持反引号代码块的插值，不支持完整的宏体展开
4. **代码生成**：当前代码生成器不处理 `MacroDef` 和 `MacroCall`，宏调用会被保留在生成的代码中

## 未实现的功能

以下功能是文档中描述但当前未实现的：

| 功能 | 状态 |
|------|------|
| 宏模板 `def name![params](body)` | 未实现 |
| `@name!` 装饰器形式的宏调用 | 未实现 |
| `expr`、`block` 等参数类型 | 未实现 |
| 类型安全宏 | 未实现 |
| 宏嵌套和组合 | 未实现 |
| 宏体的完整编译期展开 | 未实现 |

## 宏特性

| 特性 | 说明 |
|------|------|
| **宏定义** | 支持简单的宏定义语法 |
| **宏调用** | 支持带 `!` 后缀的宏调用 |
| **反引号插值** | 支持 `f\`\`\`` 形式的代码块插值 |
| **编译期展开** | 部分实现，仅处理反引号代码块 |
| **完整功能** | 规划中，当前未实现 |