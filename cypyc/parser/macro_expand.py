"""宏展开模块 - 参考 lang-zone 设计

宏在编译期展开，操作Token流。
支持的语法：
- macro name(ts: Tokens)->Tokens = ...  - 宏定义
- @name! 或 @name!(args...)             - 宏调用
- f```...```                           - 插值代码块（支持 $name 和 $(expr)）
- r```...```                           - 原始代码块（不插值）
- ```...```                            - 普通代码块
"""

import re
from typing import List, Dict, Any, Optional
from cypyc.parser.parser import ASTNode, MacroDef, MacroCall, BacktickBlock, ComptimeStmt


class MacroExpander:
    """宏展开器 - 在编译期展开宏调用"""
    
    def __init__(self):
        self.macros: Dict[str, MacroDef] = {}  # 宏名称 -> 宏定义
        self.expanded_tokens: List[str] = []   # 展开后的token流
    
    def collect_macros(self, node: ASTNode) -> None:
        """收集所有宏定义"""
        if hasattr(node, 'kind') and node.kind == 'MacroDef':
            # 宏名称加上!后缀作为调用名
            macro_name = node.name + "!"
            self.macros[macro_name] = node
        
        # 递归收集子节点中的宏定义
        if hasattr(node, '__dict__'):
            for value in node.__dict__.values():
                if isinstance(value, ASTNode):
                    self.collect_macros(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, ASTNode):
                            self.collect_macros(item)
    
    def expand_macros(self, node: ASTNode) -> ASTNode:
        """展开所有宏调用"""
        return self._expand_node(node)
    
    def _expand_node(self, node: ASTNode) -> ASTNode:
        """递归展开节点中的宏调用"""
        if hasattr(node, 'kind'):
            # 处理宏调用
            if node.kind == 'MacroCall':
                expanded = self._expand_macro_call(node)
                # 如果展开结果是列表，标记为需要展开到父列表中
                if isinstance(expanded, list):
                    node._expanded_list = expanded
                    return node
                return expanded
            
            # 处理编译期求值中的宏
            if node.kind == 'ComptimeStmt':
                node.expr = self._expand_node(node.expr)
                return node
        
        # 递归处理子节点
        if hasattr(node, '__dict__'):
            for key, value in node.__dict__.items():
                if isinstance(value, ASTNode):
                    new_value = self._expand_node(value)
                    setattr(node, key, new_value)
                elif isinstance(value, list):
                    new_list = []
                    for item in value:
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
    
    def _expand_macro_call(self, macro_call: MacroCall) -> ASTNode:
        """展开单个宏调用"""
        macro_name = macro_call.name
        
        if macro_name not in self.macros:
            # 宏未定义，保留原调用
            return macro_call
        
        macro_def = self.macros[macro_name]
        
        # 获取宏参数
        args = macro_call.args
        
        # 构建参数映射：参数名 -> 参数表达式的字符串表示
        param_map = {}
        for i, arg in enumerate(args):
            if i < len(macro_def.params):
                param_name = macro_def.params[i]
                # 如果是字典格式的参数（带类型注解），提取名称
                if isinstance(param_name, dict):
                    param_name = param_name.get('name', f'arg_{i}')
                param_map[param_name] = self._ast_to_string(arg)
        
        # 展开宏体中的反引号代码块
        expanded_body = []
        for stmt in macro_def.body:
            expanded_stmt = self._expand_backtick_blocks(stmt, param_map)
            expanded_body.append(expanded_stmt)
        
        # 返回展开后的语句列表（直接返回列表，由调用方处理）
        # 注意：_parse_block 返回的是 List[ASTNode]，不是 Suite 节点
        return expanded_body
    
    def _expand_backtick_blocks(self, node: ASTNode, param_map: Dict[str, str]) -> ASTNode:
        """展开节点中的反引号代码块"""
        if hasattr(node, 'kind') and node.kind == 'BacktickBlock':
            return self._expand_backtick_block(node, param_map)
        
        # 递归处理子节点
        if hasattr(node, '__dict__'):
            for key, value in node.__dict__.items():
                if isinstance(value, ASTNode):
                    new_value = self._expand_backtick_blocks(value, param_map)
                    setattr(node, key, new_value)
                elif isinstance(value, list):
                    new_list = []
                    for item in value:
                        if isinstance(item, ASTNode):
                            new_list.append(self._expand_backtick_blocks(item, param_map))
                        else:
                            new_list.append(item)
                    setattr(node, key, new_list)
        
        return node
    
    def _expand_backtick_block(self, block: BacktickBlock, param_map: Dict[str, str]) -> ASTNode:
        """展开单个反引号代码块
        
        根据前缀类型处理：
        - None: 普通代码块，不插值
        - 'f': 插值代码块，支持 $name 和 $(expr)
        - 'r': 原始代码块，不插值，不展开宏
        """
        content = block.content
        
        if block.prefix == 'r':
            # 原始代码块，不处理
            return block
        
        if block.prefix == 'f':
            # 插值代码块：替换 $name 和 $(expr)
            content = self._expand_f_string(content, param_map)
        
        # 返回新的BacktickBlock
        return BacktickBlock(content, block.prefix, block.line, block.col)
    
    def _expand_f_string(self, content: str, param_map: Dict[str, str]) -> str:
        """展开f代码块中的插值
        
        支持：
        - $name      -> 替换为参数名对应的表达式字符串
        - $(expr)    -> 保持表达式不变（作为代码片段）
        - $$         -> 转义为单个 $
        """
        # 先处理 $$ 转义
        content = content.replace('$$', '__DOLLAR_ESCAPE__')
        
        # 处理 $(expr) 形式（保持表达式不变）
        def replace_expr(match):
            expr = match.group(1)
            return f'({expr})'
        
        content = re.sub(r'\$\((.*?)\)', replace_expr, content)
        
        # 处理 $name 形式
        def replace_name(match):
            name = match.group(1)
            # 在参数映射中查找对应的参数
            if name in param_map:
                return param_map[name]
            # 如果找不到，保持原样
            return f'${name}'
        
        content = re.sub(r'\$(\w+)', replace_name, content)
        
        # 还原 $$ 转义
        content = content.replace('__DOLLAR_ESCAPE__', '$')
        
        return content
    
    def _ast_to_string(self, node) -> str:
        """将AST节点转换为字符串表示
        
        这个方法将AST节点递归转换为源代码字符串形式，
        用于宏展开时的参数插值。
        """
        if node is None:
            return 'None'
        
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
            left = self._ast_to_string(node.left)
            right = self._ast_to_string(node.right)
            return f'({left} {node.op} {right})'
        
        # 处理一元操作
        if hasattr(node, 'kind') and node.kind == 'UnaryOp':
            operand = self._ast_to_string(node.operand)
            return f'{node.op}{operand}'
        
        # 处理函数调用
        if hasattr(node, 'kind') and node.kind == 'Call':
            func = self._ast_to_string(node.func)
            args = ', '.join(self._ast_to_string(arg) for arg in node.args)
            return f'{func}({args})'
        
        # 处理属性访问
        if hasattr(node, 'kind') and node.kind == 'Attribute':
            value = self._ast_to_string(node.value)
            return f'{value}.{node.attr}'
        
        # 处理下标访问
        if hasattr(node, 'kind') and node.kind == 'Subscript':
            value = self._ast_to_string(node.value)
            slice_val = self._ast_to_string(node.slice)
            return f'{value}[{slice_val}]'
        
        # 处理其他节点类型
        if hasattr(node, '__str__'):
            return str(node)
        
        return repr(node)
    
    def expand_all(self, ast: ASTNode) -> ASTNode:
        """完整的宏展开流程：收集 -> 展开"""
        # 第一步：收集所有宏定义
        self.collect_macros(ast)
        
        # 第二步：展开所有宏调用
        expanded_ast = self.expand_macros(ast)
        
        return expanded_ast


# 简化的宏展开函数
def expand_macros(ast: ASTNode) -> ASTNode:
    """展开AST中的所有宏调用"""
    expander = MacroExpander()
    return expander.expand_all(ast)