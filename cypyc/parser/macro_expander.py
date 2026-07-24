"""宏展开器：在编译期展开宏调用

参考 lang-zone 的宏系统设计：
- 宏在编译期展开，操作 Token 流
- 支持反引号代码块 ```...``` 用于代码捕获
- 支持插值形式 f```...```，其中 $() 会被替换
- 支持原始形式 r```...```，不插值不展开宏

展开流程：
1. 遍历 AST，收集所有宏定义
2. 遍历 AST，找到所有宏调用
3. 根据宏定义展开宏调用，生成新的 AST 节点
4. 递归处理展开后的代码，支持嵌套宏展开
"""

import re
from typing import Dict, List, Any, Optional
from .parser import ASTNode, Module, MacroDef, MacroCall, Name, Constant, BacktickBlock


class MacroExpander:
    """宏展开器"""
    
    def __init__(self):
        self.macros: Dict[str, MacroDef] = {}  # 宏定义缓存
        self.expanding: Dict[str, bool] = {}   # 防止递归展开
        self.expansion_count = 0               # 展开次数计数器
    
    def collect_macros(self, node: ASTNode) -> None:
        """收集所有宏定义"""
        if isinstance(node, MacroDef):
            self.macros[node.name] = node
        
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
            return self._expand_macro_call(node)
        
        # 处理其他节点的子节点
        for key, child in list(node.__dict__.items()):
            if isinstance(child, ASTNode):
                new_child = self._expand_node(child)
                setattr(node, key, new_child)
            elif isinstance(child, list):
                new_list = []
                for item in child:
                    if isinstance(item, ASTNode):
                        new_list.append(self._expand_node(item))
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
        
        # 检查宏是否存在
        if macro_name not in self.macros:
            raise ValueError(f"Undefined macro '{macro_name}' at line {macro_call.line}")
        
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
        
        # 处理插值形式 f```...```
        if prefix == 'f':
            content = self._substitute_interpolations(content, args, params)
        
        # 重新解析代码块内容
        from .lexer import Lexer
        from .parser import Parser
        
        lexer = Lexer(content)
        tokens = lexer.tokenize()
        
        # 过滤掉 EOF token，因为这是代码块不是完整文件
        tokens = [t for t in tokens if t.type != 'EOF']
        
        parser = Parser(tokens, is_backtick_block=True)
        ast = parser.parse_expression()
        
        return ast
    
    def _substitute_interpolations(self, content: str, args: List[Any], params: List[dict]) -> str:
        """替换反引号代码块中的插值表达式
        
        插值语法：$(expr) 或 $name
        
        Args:
            content: 代码块内容
            args: 宏调用参数
            params: 宏定义参数列表
            
        Returns:
            替换后的内容
        """
        # 建立参数映射
        param_map = {}
        for i, param in enumerate(params):
            if i < len(args):
                param_map[param['name']] = args[i]
        
        # 替换 $(expr) 形式的插值
        def replace_interpolation(match):
            expr_str = match.group(1).strip()
            
            # 检查是否是参数名
            if expr_str in param_map:
                arg = param_map[expr_str]
                return self._arg_to_code(arg)
            
            # 否则尝试作为表达式处理
            return expr_str
        
        # 处理 $(expr) 形式
        content = re.sub(r'\$\(([^)]+)\)', replace_interpolation, content)
        
        # 处理 $name 形式（简单变量插值）
        for param_name, arg in param_map.items():
            content = content.replace(f'${param_name}', self._arg_to_code(arg))
        
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
        # 简单实现：使用节点的kind和属性生成代码
        if node.kind == "BinOp":
            left = self._ast_to_code(node.left)
            right = self._ast_to_code(node.right)
            op = node.op
            return f"({left} {op} {right})"
        elif node.kind == "Call":
            func = self._ast_to_code(node.func)
            args = ", ".join(self._ast_to_code(arg) for arg in node.args)
            return f"{func}({args})"
        elif node.kind == "Constant":
            if isinstance(node.value, str):
                return f'"{node.value}"'
            else:
                return str(node.value)
        elif node.kind == "Name":
            return node.id
        elif node.kind == "UnaryOp":
            operand = self._ast_to_code(node.operand)
            return f"{node.op}{operand}"
        else:
            # 默认返回节点描述
            return str(node)


def expand_macros(ast: ASTNode) -> ASTNode:
    """展开AST中的所有宏调用
    
    Args:
        ast: AST节点
        
    Returns:
        展开后的AST节点
    """
    expander = MacroExpander()
    return expander.expand(ast)
