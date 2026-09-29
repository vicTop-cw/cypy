"""宏展开器：在编译期展开宏调用

参考 lang-zone 的宏系统设计：
- 宏在编译期展开，操作 Token 流
- 支持反引号代码块 ```...``` 用于代码捕获
- 支持插值形式 f```...```，其中 $() 会被替换
- 支持原始形式 r```...```，不插值不展开宏
- 支持 $$ 转义为单个 $

展开流程：
1. 遍历 AST，收集所有宏定义
2. 遍历 AST，找到所有宏调用
3. 根据宏定义展开宏调用，生成新的 AST 节点
4. 对展开结果继续展开（递归），因此支持嵌套宏与多级宏链 a -> b -> c；
   展开守卫 self.expanding 在递归期间仍然持有，真正的自引用/互相引用抛 ValueError
5. 插值后的反引号代码块重新解析为真实 AST 节点

实现约束（2026-Q3 审计 T0r61.2.2）：
- 实参渲染统一走 preprocessor.serialize_string_literal：已解码的字符串必须重新
  转义并保留 f 前缀，否则含引号/反斜杠/换行的实参会产出无法解析的代码，
  并被 _reparse_code() 的降级分支静默丢掉整条语句。
- 插值在词法单元层面进行（preprocessor.iter_code_chunks）：注释与双引号/三引号
  字符串里的 $name 不再被插值；$(expr) 与 $name 合并在一次扫描中完成，
  已插入的实参文本不会被再次扫描。单引号字符串仍参与插值以兼容既有模板写法
  （tests/test_macro_expansion.py::test_backtick_macro_multistmt_not_dropped）。
- name!(...)（无 @ 前缀，解析成 Call(Name('name!'))）也按宏调用展开；
  不带 '!' 的 name(...) 仍留给代码生成的字符串模板宏路径，避免误伤 macro dbl(ts)。
"""

import re
import copy
import sys
from typing import Dict, List, Any, Optional
from .parser import (
    ASTNode,
    Module,
    MacroDef,
    MacroCall,
    Name,
    Constant,
    BacktickBlock,
    ComptimeStmt,
    ExprStmt,
    Call,
)
from .lexer import Lexer
from .parser import Parser
from .preprocessor import iter_code_chunks, serialize_string_literal

# 出于历史兼容，宏体中的单引号字符串字面量仍参与 $ 插值
# （tests/test_macro_expansion.py::test_backtick_macro_multistmt_not_dropped 依赖
#   print('twice: $input') 这种模板写法）；
# 双引号/三引号字面量与注释被视为不透明文本，其中的 $name 不再被插值。
_SINGLE_QUOTED_RE = re.compile(r"^[A-Za-z]{0,2}'")


def _interpolable_chunk(is_code: bool, chunk: str) -> bool:
    """该词法单元是否参与 $ 插值。"""
    if is_code:
        return True
    if chunk.startswith("'''") or chunk.startswith('"""'):
        return False
    return bool(_SINGLE_QUOTED_RE.match(chunk))


class MacroExpander:
    """宏展开器"""

    def __init__(self):
        self.macros: Dict[str, MacroDef] = {}  # 宏定义缓存
        self.expanding: Dict[str, bool] = {}  # 防止递归展开
        self.expansion_count = 0  # 展开次数计数器

    def collect_macros(self, node: ASTNode) -> None:
        """收集所有宏定义"""
        if isinstance(node, MacroDef):
            # 宏名称加上!后缀作为调用名（兼容 macro_expand.py 的风格）
            macro_name = node.name + "!" if not node.name.endswith("!") else node.name
            self.macros[macro_name] = node

        # 遍历所有属性，查找子节点
        for key, child in list(node.__dict__.items()):
            if isinstance(child, ASTNode):
                self.collect_macros(child)
            elif isinstance(child, list):
                for item in child:
                    if isinstance(item, ASTNode):
                        self.collect_macros(item)

    def expand(self, node: ASTNode) -> Any:
        """展开 AST 中的所有宏调用

        Args:
            node: AST 节点

        Returns:
            展开后的 AST 节点
        """
        # 首先收集所有宏定义
        self.collect_macros(node)

        # 然后展开宏调用
        return self._expand_node(node)

    def _expand_node(self, node: ASTNode) -> Any:
        """递归展开单个节点"""
        if node is None:
            return None

        # 处理宏调用
        if isinstance(node, MacroCall):
            expanded = self._expand_macro_call(node)
            # 如果展开结果是列表，标记为需要展开到父列表中
            if isinstance(expanded, list):
                node._expanded_list = expanded
                return node
            return expanded

        # inner!(...) 形态（没有 @ 前缀）会被解析成 Call(Name('inner!'))，
        # 同样是一次宏调用；只有带 '!' 的名字才按宏处理，
        # 无 '!' 的 name(...) 留给代码生成的字符串模板宏路径。
        implicit = self._implicit_macro_call(node)
        if implicit is not None:
            expanded = self._expand_macro_call(implicit)
            if isinstance(expanded, list):
                node._expanded_list = expanded
                return node
            return expanded

        # 编译期反引号宏（体含 BacktickBlock）在展开后即完成使命，
        # 不应再以运行时函数形式残留于输出；字符串模板宏（无 BacktickBlock）
        # 保留，交由 CythonGenerator 继续处理。
        if isinstance(node, MacroDef):
            if self._is_backtick_macro(node):
                return None
            return node

        # 处理编译期求值中的宏
        if isinstance(node, ComptimeStmt):
            node.expr = self._expand_node(node.expr)
            return node

        # 处理其他节点的子节点
        for key, child in list(node.__dict__.items()):
            if isinstance(child, ASTNode):
                new_child = self._expand_node(child)
                setattr(node, key, new_child)
            elif isinstance(child, list):
                new_list = []
                for item in child:
                    if isinstance(item, ASTNode):
                        expanded_item = self._expand_node(item)
                        # 被剔除的节点（如反引号宏定义）直接跳过
                        if expanded_item is None:
                            continue
                        # 如果节点被标记为需要展开到列表中
                        if hasattr(expanded_item, "_expanded_list"):
                            new_list.extend(expanded_item._expanded_list)
                        elif isinstance(expanded_item, list):
                            new_list.extend(expanded_item)
                        else:
                            new_list.append(expanded_item)
                    else:
                        new_list.append(item)
                setattr(node, key, new_list)

        return node

    def _implicit_macro_call(self, node: ASTNode) -> Optional[MacroCall]:
        """把 ``name!(...)``（解析为 Call(Name('name!'))）还原成 MacroCall，未知宏返回 None。"""
        if not isinstance(node, Call):
            return None
        func = getattr(node, "func", None)
        name = getattr(func, "id", None)
        # 只认显式带 '!' 的调用形态；self.macros 的键统一带 '!' 后缀
        if not isinstance(name, str) or name not in self.macros:
            return None
        return MacroCall(
            name,
            list(getattr(node, "args", []) or []),
            getattr(node, "line", 0),
            getattr(node, "col", 0),
        )

    @staticmethod
    def _is_backtick_macro(macro_def: MacroDef) -> bool:
        """判断宏是否为编译期反引号宏（宏体含 BacktickBlock）"""
        for stmt in getattr(macro_def, "body", []) or []:
            if isinstance(stmt, BacktickBlock):
                return True
            val = getattr(stmt, "value", None)
            if isinstance(val, BacktickBlock):
                return True
        return False

    def _expand_macro_call(self, macro_call: MacroCall) -> Any:
        """展开单个宏调用

        Args:
            macro_call: 宏调用节点

        Returns:
            展开后的 AST 节点或节点列表
        """
        macro_name = macro_call.name

        # 检查宏是否存在（支持带!和不带!的名称）
        if macro_name not in self.macros:
            # 尝试添加!后缀查找
            alt_name = macro_name + "!"
            if alt_name in self.macros:
                macro_name = alt_name
            else:
                # 宏未定义，保留原调用
                return macro_call

        # 防止递归展开
        if macro_name in self.expanding:
            raise ValueError(f"Recursive macro expansion detected for '{macro_name}'")

        self.expanding[macro_name] = True

        try:
            macro_def = self.macros[macro_name]
            expanded = self._apply_macro(macro_def, macro_call.args)
            # 对展开结果继续展开：宏体里的嵌套宏（@inner!() 与 inner!()）
            # 在这里被解析掉。仍然持有 expanding 守卫，因此真正的自引用宏
            # （a -> a）以及互相引用（a -> b -> a）都会抛出 ValueError，而不是无限递归。
            return self._expand_expanded(expanded)
        finally:
            del self.expanding[macro_name]

    def _expand_expanded(self, expanded: Any) -> Any:
        """递归展开一次宏调用的产物（单节点或语句列表）。"""
        if isinstance(expanded, list):
            statements: List[Any] = []
            for item in expanded:
                statements.extend(self._expand_to_statements(item))
            return statements
        if isinstance(expanded, ASTNode):
            return self._expand_node(expanded)
        return expanded

    def _expand_to_statements(self, item: Any) -> List[Any]:
        """展开一个语句，并把多语句结果扁平化。"""
        if not isinstance(item, ASTNode):
            return [item]
        result = self._expand_node(item)
        if result is None:
            return []
        if isinstance(result, list):
            return result
        if hasattr(result, "_expanded_list"):
            return list(result._expanded_list)
        return [result]

    def _apply_macro(self, macro_def: MacroDef, args: List[Any]) -> Any:
        """应用宏定义到参数

        Args:
            macro_def: 宏定义
            args: 宏调用参数

        Returns:
            展开后的 AST 节点（单条语句）或节点列表（多条语句）
        """
        # 处理反引号代码块的插值，并将展开结果扁平化为语句列表
        expanded_stmts: List[Any] = []

        # 深拷贝宏定义体后再插值：避免多次调用同一宏时共享的宏定义体被
        # 原地改写，导致后续调用复用前一次调用的插值结果（见 _interpolate_backtick）
        body = copy.deepcopy(macro_def.body)

        for stmt in body:
            result = self._interpolate_backtick(stmt, args, macro_def.params)
            if result is None:
                continue
            if isinstance(result, list):
                expanded_stmts.extend(result)
            else:
                expanded_stmts.append(result)

        # 如果只有一个语句，直接返回该语句（保持单节点语义）
        if len(expanded_stmts) == 1:
            return expanded_stmts[0]

        # 否则返回语句列表（由调用处的父级列表负责展开）
        return expanded_stmts

    def _interpolate_backtick(self, node: ASTNode, args: List[Any], params: List[dict]) -> Any:
        """处理反引号代码块的插值

        反引号块（含 f 前缀的内联代码块）会被重新解析为真实 AST 节点；
        当块内展开出多条语句时，直接以列表形式返回，交由上层扁平化，
        避免出现 “把语句列表塞进单个表达式语句” 导致代码生成时整段丢失的问题。

        Args:
            node: AST 节点
            args: 宏调用参数
            params: 宏定义参数列表

        Returns:
            插值后的单个 AST 节点，或节点列表（多语句时）
        """
        if isinstance(node, BacktickBlock):
            return self._process_backtick_block(node, args, params)

        if isinstance(node, ExprStmt):
            val = node.value
            if isinstance(val, BacktickBlock):
                # 反引号块可能展开为多语句，直接返回（供上层扁平化）；
                # 同时原地替换 node.value，使共享的宏定义体不再保留 BacktickBlock
                # （保持与历史行为一致：展开后宏定义体中的反引号块被替换为真实节点）
                result = self._process_backtick_block(val, args, params)
                node.value = result
                return result
            new_val = self._interpolate_backtick(val, args, params)
            if isinstance(new_val, list):
                return new_val
            node.value = new_val
            return node

        # 递归处理其它节点的子节点（含列表字段），保持多语句扁平化
        for key, child in list(node.__dict__.items()):
            if isinstance(child, ASTNode):
                new_child = self._interpolate_backtick(child, args, params)
                setattr(node, key, new_child)
            elif isinstance(child, list):
                new_list = []
                for item in child:
                    if isinstance(item, ASTNode):
                        new_item = self._interpolate_backtick(item, args, params)
                        if new_item is None:
                            continue
                        if isinstance(new_item, list):
                            new_list.extend(new_item)
                        else:
                            new_list.append(new_item)
                    else:
                        new_list.append(item)
                setattr(node, key, new_list)

        return node

    def _process_backtick_block(
        self, block: BacktickBlock, args: List[Any], params: List[dict]
    ) -> Any:
        """处理反引号代码块

        Args:
            block: 反引号代码块节点
            args: 宏调用参数
            params: 宏定义参数列表

        Returns:
            处理后的 AST 节点（重新解析后的代码）
        """
        content = block.content
        prefix = block.prefix

        # 原始代码块，不处理
        if prefix == "r":
            return block

        # 处理插值形式 f```...```
        if prefix == "f":
            content = self._substitute_interpolations(content, args, params)

        # 将插值后的代码重新解析为真实的 AST 节点
        # 这样下游的作用域分析、类型检查和代码生成才能正确处理
        return self._reparse_code(content, block.line, block.col)

    def _reparse_code(self, code: str, line: int = 1, col: int = 1) -> Any:
        """将代码字符串重新解析为 AST 节点

        Args:
            code: 代码字符串
            line: 起始行号（用于错误报告）
            col: 起始列号（用于错误报告）

        Returns:
            解析后的 AST 节点或节点列表
        """
        try:
            lexer = Lexer(code)
            tokens = lexer.tokenize()

            parser = Parser(tokens, body_scope=True)
            module = parser.parse()

            # 如果只有一个语句，直接返回
            if len(module.body) == 1:
                return module.body[0]

            # 否则返回语句列表
            return module.body
        except Exception as e:
            # 解析失败时返回原始代码块作为降级。
            # 注意：这条降级路径会让整条宏调用语句从输出里消失，所以实参渲染必须
            # 产出可解析的字面量（见 preprocessor.serialize_string_literal）。
            print(
                f"[cypy][warn] 宏展开后的代码块无法解析，按原样保留（该语句可能从输出中消失）"
                f": 行 {line} 列 {col}: {code!r} ({e})",
                file=sys.stderr,
            )
            return BacktickBlock(code, "", line, col)

    def _substitute_interpolations(self, content: str, args: List[Any], params: List[dict]) -> str:
        """替换反引号代码块中的插值表达式

        插值语法：$(expr) 或 $name
        支持 $$ 转义为单个 $

        替换在词法单元上进行：注释与（双引号/三引号）字符串字面量中的 ``$name``
        是普通文本，不再被插值；同时 ``$(...)`` 与 ``$name`` 在一次扫描内完成，
        已插入的实参文本不会被再次扫描（旧实现的两遍 re.sub 会把
        ``print($(x))`` + 实参 ``"a$x"`` 二次插值成不可解析的代码）。

        Args:
            content: 代码块内容
            args: 宏调用参数
            params: 宏定义参数列表

        Returns:
            替换后的内容
        """
        # 先处理 $$ 转义
        content = content.replace("$$", "__DOLLAR_ESCAPE__")

        # 建立参数映射
        param_map = {}
        for i, param in enumerate(params):
            if i < len(args):
                param_name = param.get("name", f"arg_{i}")
                param_map[param_name] = args[i]

        def replace_interpolation(match):
            if match.group(1) is not None:
                expr_str = match.group(1).strip()

                # 检查是否是参数名
                if expr_str in param_map:
                    return self._arg_to_code(param_map[expr_str])

                # 否则尝试作为表达式处理
                return f"({expr_str})"

            name = match.group(2)
            if name in param_map:
                return self._arg_to_code(param_map[name])
            return f"${name}"

        # 单个正则一次扫描：$(expr) 与 $name 互不重扫
        interpolation_re = re.compile(r"\$\(([^)]+)\)|\$(\w+)")

        pieces = []
        for is_code, chunk in iter_code_chunks(content):
            if _interpolable_chunk(is_code, chunk):
                pieces.append(interpolation_re.sub(replace_interpolation, chunk))
            else:
                pieces.append(chunk)
        content = "".join(pieces)

        # 还原 $$ 转义
        content = content.replace("__DOLLAR_ESCAPE__", "$")

        return content

    def _arg_to_code(self, arg: Any) -> str:
        """将宏参数转换为代码字符串

        Args:
            arg: 宏参数（AST节点）

        Returns:
            代码字符串
        """
        if isinstance(arg, Constant):
            if isinstance(arg.value, str):
                # value 是已解码的文本，必须重新转义并保留 f 前缀，
                # 否则含引号/反斜杠/换行的实参会产出无法解析的代码
                return serialize_string_literal(arg.value, getattr(arg, "prefix", None))
            elif isinstance(arg.value, bool):
                return "true" if arg.value else "false"
            else:
                return str(arg.value)
        elif isinstance(arg, Name):
            return arg.id
        elif isinstance(arg, ASTNode):
            # 对于复杂节点，返回其代码表示
            return self._ast_to_code(arg)
        elif isinstance(arg, str):
            # 裸字符串实参同样要按字面量序列化，否则 "a,b" 会展开成两个参数
            return serialize_string_literal(arg)
        else:
            return str(arg)

    def _ast_to_code(self, node: ASTNode) -> str:
        """将AST节点转换为代码字符串

        Args:
            node: AST节点

        Returns:
            代码字符串
        """
        # 处理常量
        if hasattr(node, "kind") and node.kind == "Constant":
            if isinstance(node.value, str):
                # 与 _arg_to_code 共用同一个字面量序列化器：重新转义 + 保留 f 前缀
                return serialize_string_literal(node.value, getattr(node, "prefix", None))
            elif isinstance(node.value, bool):
                return "true" if node.value else "false"
            return str(node.value)

        # 处理名称
        if hasattr(node, "kind") and node.kind == "Name":
            return node.id

        # 处理二元操作
        if hasattr(node, "kind") and node.kind == "BinOp":
            left = self._ast_to_code(node.left)
            right = self._ast_to_code(node.right)
            return f"({left} {node.op} {right})"

        # 处理一元操作
        if hasattr(node, "kind") and node.kind == "UnaryOp":
            operand = self._ast_to_code(node.operand)
            return f"{node.op}{operand}"

        # 处理函数调用
        if hasattr(node, "kind") and node.kind == "Call":
            func = self._ast_to_code(node.func)
            args = ", ".join(self._ast_to_code(arg) for arg in node.args)
            return f"{func}({args})"

        # 处理属性访问
        if hasattr(node, "kind") and node.kind == "Attribute":
            value = self._ast_to_code(node.value)
            return f"{value}.{node.attr}"

        # 处理下标访问
        if hasattr(node, "kind") and node.kind == "Subscript":
            value = self._ast_to_code(node.value)
            slice_val = self._ast_to_code(node.slice)
            return f"{value}[{slice_val}]"

        # 默认返回节点描述
        return str(node)

    def expand_all(self, ast: ASTNode) -> ASTNode:
        """完整的宏展开流程：收集 -> 展开（兼容 macro_expand.py 的接口）"""
        return self.expand(ast)


def expand_macros(ast: ASTNode) -> ASTNode:
    """展开AST中的所有宏调用

    Args:
        ast: AST节点

    Returns:
        展开后的AST节点
    """
    expander = MacroExpander()
    return expander.expand(ast)
