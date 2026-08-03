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
4. 递归处理展开后的代码，支持嵌套宏展开
5. 插值后的反引号代码块重新解析为真实 AST 节点
"""

import re
from typing import Dict, List, Any, Optional
from .parser import ASTNode, Module, MacroDef, MacroCall, Name, Constant, BacktickBlock, ComptimeStmt
from .lexer import Lexer
from .parser import Parser


class MacroExpander:
    """宏展开器"""
    
    def __init__(self):
        self.macros: Dict[str, MacroDef] = {}  # 宏定义缓存
        self.expanding: Dict[str, bool] = {}   # 防止递归展开
        self.expansion_count = 0               # 展开次数计数器
    
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
                        # 如果节点被标记为需要展开到列表中
                        if hasattr(expanded_item, '_expanded_list'):
                            new_list.extend(expanded_item._expanded_list)
                        else:
                            new_list.append(expanded_item)
                    else:
                        new_list.append(item)
                setattr(node, key, new_list)
        
        return node
    
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
            return self._apply_macro(macro_def, macro_call.args)
        finally:
            del self.expanding[macro_name]
    
    def _apply_macro(self, macro_def: MacroDef, args: List[Any]) -> Any:
        """应用宏定义到参数
        
        Args:
            macro_def: 宏定义
            args: 宏调用参数
            
        Returns:
            展开后的 AST 节点
        """
        # 处理反引号代码块的插值
        expanded_body = []
        
        for stmt in macro_def.body:
            expanded_stmt = self._interpolate_backtick(stmt, args, macro_def.params)
            if expanded_stmt:
                expanded_body.append(expanded_stmt)
        
        # 如果只有一个语句，直接返回该语句
        if len(expanded_body) == 1:
            return expanded_body[0]
        
        # 否则返回语句列表（需要在调用处处理）
        return expanded_body
    
    def _interpolate_backtick(self, node: ASTNode, args: List[Any], params: List[dict]) -> Any:
        """处理反引号代码块的插值
        
        Args:
            node: AST 节点
            args: 宏调用参数
            params: 宏定义参数列表
            
        Returns:
            插值后的 AST 节点
        """
        if isinstance(node, BacktickBlock):
            return self._process_backtick_block(node, args, params)
        
        # 递归处理子节点
        for key, child in list(node.__dict__.items()):
            if isinstance(child, ASTNode):
                new_child = self._interpolate_backtick(child, args, params)
                setattr(node, key, new_child)
            elif isinstance(child, list):
                new_list = []
                for item in child:
                    if isinstance(item, ASTNode):
                        new_list.append(self._interpolate_backtick(item, args, params))
                    else:
                        new_list.append(item)
                setattr(node, key, new_list)
        
        return node
    
    def _process_backtick_block(self, block: BacktickBlock, args: List[Any], params: List[dict]) -> Any:
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
        if prefix == 'r':
            return block
        
        # 处理插值形式 f```...```
        if prefix == 'f':
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
            
            parser = Parser(tokens)
            module = parser.parse()
            
            # 如果只有一个语句，直接返回
            if len(module.body) == 1:
                return module.body[0]
            
            # 否则返回语句列表
            return module.body
        except Exception as e:
            # 解析失败时返回原始代码块作为降级
            return BacktickBlock(code, '', line, col)
    
    def _substitute_interpolations(self, content: str, args: List[Any], params: List[dict]) -> str:
        """替换反引号代码块中的插值表达式
        
        插值语法：$(expr) 或 $name
        支持 $$ 转义为单个 $
        
        Args:
            content: 代码块内容
            args: 宏调用参数
            params: 宏定义参数列表
            
        Returns:
            替换后的内容
        """
        # 先处理 $$ 转义
        content = content.replace('$$', '__DOLLAR_ESCAPE__')
        
        # 建立参数映射
        param_map = {}
        for i, param in enumerate(params):
            if i < len(args):
                param_name = param.get('name', f'arg_{i}')
                param_map[param_name] = args[i]
        
        # 替换 $(expr) 形式的插值
        def replace_interpolation(match):
            expr_str = match.group(1).strip()
            
            # 检查是否是参数名
            if expr_str in param_map:
                arg = param_map[expr_str]
                return self._arg_to_code(arg)
            
            # 否则尝试作为表达式处理
            return f'({expr_str})'
        
        # 处理 $(expr) 形式
        content = re.sub(r'\$\(([^)]+)\)', replace_interpolation, content)
        
        # 处理 $name 形式（简单变量插值）
        def replace_name(match):
            name = match.group(1)
            if name in param_map:
                return self._arg_to_code(param_map[name])
            return f'${name}'
        
        content = re.sub(r'\$(\w+)', replace_name, content)
        
        # 还原 $$ 转义
        content = content.replace('__DOLLAR_ESCAPE__', '$')
        
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
                return f'"{arg.value}"'
            elif isinstance(arg.value, bool):
                return 'true' if arg.value else 'false'
            else:
                return str(arg.value)
        elif isinstance(arg, Name):
            return arg.id
        elif isinstance(arg, ASTNode):
            # 对于复杂节点，返回其代码表示
            return self._ast_to_code(arg)
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
        if hasattr(node, 'kind') and node.kind == 'Constant':
            if isinstance(node.value, str):
                return f'"{node.value}"'
            elif isinstance(node.value, bool):
                return 'true' if node.value else 'false'
            return str(node.value)
        
        # 处理名称
        if hasattr(node, 'kind') and node.kind == 'Name':
            return node.id
        
        # 处理二元操作
        if hasattr(node, 'kind') and node.kind == 'BinOp':
            left = self._ast_to_code(node.left)
            right = self._ast_to_code(node.right)
            return f'({left} {node.op} {right})'
        
        # 处理一元操作
        if hasattr(node, 'kind') and node.kind == 'UnaryOp':
            operand = self._ast_to_code(node.operand)
            return f'{node.op}{operand}'
        
        # 处理函数调用
        if hasattr(node, 'kind') and node.kind == 'Call':
            func = self._ast_to_code(node.func)
            args = ', '.join(self._ast_to_code(arg) for arg in node.args)
            return f'{func}({args})'
        
        # 处理属性访问
        if hasattr(node, 'kind') and node.kind == 'Attribute':
            value = self._ast_to_code(node.value)
            return f'{value}.{node.attr}'
        
        # 处理下标访问
        if hasattr(node, 'kind') and node.kind == 'Subscript':
            value = self._ast_to_code(node.value)
            slice_val = self._ast_to_code(node.slice)
            return f'{value}[{slice_val}]'
        
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
