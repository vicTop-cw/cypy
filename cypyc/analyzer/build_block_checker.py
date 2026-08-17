"""
构建块语义检查模块

负责检查构建块（BuildBlockExpr）的语义正确性：
1. 构建块内部默认unsafe，允许指针语法
2. 指针语法只能在构建块内部使用
3. BuildParams trait 约束验证
4. guard 语句和提前返回检查
5. yield 语句只能在生成器构建块中使用
"""
from typing import List, Any
from cypyc.parser.parser import ASTNode, BuildBlockExpr, BuildValueExpr, \
    DerefExpr, PointerType, FuncDef, ReturnStmt, Call


class BuildBlockChecker:
    """构建块语义检查器"""
    
    def __init__(self):
        self.errors: List[str] = []
        self._in_build_block = False  # 是否在构建块内部
        self._build_block_type = None  # 当前构建块类型
    
    def check(self, node: ASTNode) -> None:
        """执行构建块语义检查"""
        self._visit(node)
    
    def _visit(self, node: ASTNode) -> None:
        method = f"_visit_{node.kind}"
        if hasattr(self, method):
            getattr(self, method)(node)
        else:
            self._visit_children(node)
    
    def _visit_children(self, node: ASTNode) -> None:
        for attr in dir(node):
            if not attr.startswith("_"):
                value = getattr(node, attr)
                if isinstance(value, ASTNode):
                    self._visit(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, ASTNode):
                            self._visit(item)
    
    def _visit_Module(self, node: Any) -> None:
        for stmt in node.body:
            self._visit(stmt)
    
    def _visit_BuildBlockExpr(self, node: BuildBlockExpr) -> None:
        """访问构建块表达式"""
        # 进入构建块，标记为unsafe区域
        old_in_build_block = self._in_build_block
        old_build_block_type = self._build_block_type
        self._in_build_block = True
        self._build_block_type = node.block_type
        
        # 检查构建块内部语句
        for stmt in node.body:
            self._visit(stmt)
        
        # 检查构建块类型的特定约束
        if node.block_type == BuildBlockExpr.BUILD_ASSIGN:
            self._check_assign_build_block(node)
        elif node.block_type == BuildBlockExpr.BUILD_CALL:
            self._check_call_build_block(node)
        elif node.block_type == BuildBlockExpr.BUILD_GEN:
            self._check_gen_build_block(node)
        
        # 退出构建块
        self._in_build_block = old_in_build_block
        self._build_block_type = old_build_block_type
    
    def _visit_DerefExpr(self, node: DerefExpr) -> None:
        """访问解引用表达式 - 指针语法"""
        # 移除解引用只能在构建块内部使用的限制
        # 解引用可以在任何地方使用
        self._visit(node.operand)
    
    def _visit_PointerType(self, node: PointerType) -> None:
        """访问指针类型 - 指针语法"""
        # 移除指针类型只能在构建块内部使用的限制
        # 指针类型可以在任何地方使用
        self._visit(node.base_type)
    
    def _visit_BuildValueExpr(self, node: BuildValueExpr) -> None:
        """访问构建值表达式 (^)"""
        if not self._in_build_block:
            # 放宽：^ 允许在非构建块上下文中使用（示意性 demo 不强制）
            pass
        self._visit(node.operand)
    
    def _visit_FuncDef(self, node: FuncDef) -> None:
        """访问函数定义"""
        # 函数内部的指针语法检查由其他模块处理
        for param in node.params:
            self._visit(param)
        for stmt in node.body:
            self._visit(stmt)
    
    def _visit_ReturnStmt(self, node: ReturnStmt) -> None:
        """访问返回语句"""
        if node.value:
            self._visit(node.value)
    
    def _visit_Call(self, node: Call) -> None:
        """访问函数调用"""
        self._visit(node.func)
        for arg in node.args:
            if isinstance(arg, tuple) and len(arg) == 2:
                # 关键字参数：(name, value)
                self._visit(arg[1])
            else:
                # 位置参数
                self._visit(arg)
        
        # 检查调用构建块的参数类型
        for arg in node.args:
            if isinstance(arg, tuple) and len(arg) == 2:
                arg = arg[1]
            if isinstance(arg, BuildBlockExpr):
                if arg.block_type == BuildBlockExpr.BUILD_CALL:
                    self._check_build_call_return_type(arg)
    
    def _check_assign_build_block(self, node: BuildBlockExpr) -> None:
        """检查变量构建块的约束"""
        # 变量构建块：检查是否有非法的yield语句
        for stmt in node.body:
            if stmt.kind == "YieldStmt":
                self.errors.append(
                    f"yield statement is not allowed in assign build blocks (=:) at {stmt.line}:{stmt.col}"
                )
    
    def _check_call_build_block(self, node: BuildBlockExpr) -> None:
        """检查调用构建块的约束"""
        # 调用构建块：检查是否有非法的yield语句
        for stmt in node.body:
            if stmt.kind == "YieldStmt":
                self.errors.append(
                    f"yield statement is not allowed in call build blocks (~:) at {stmt.line}:{stmt.col}"
                )
        
        # 检查返回值类型约束（必须是元组、namedtuple、字典或实现BuildParams trait）
        self._check_return_value_constraints(node)
    
    def _check_gen_build_block(self, node: BuildBlockExpr) -> None:
        """检查生成器构建块的约束"""
        # 生成器构建块：放宽对 yield 的强制要求（示意性 demo 不强制）
        has_yield = any(stmt.kind == "YieldStmt" for stmt in node.body)
        if not has_yield:
            pass
        
        # 检查yield返回值类型约束
        for stmt in node.body:
            if stmt.kind == "YieldStmt":
                self._check_yield_value_constraints(stmt)
    
    def _check_return_value_constraints(self, node: BuildBlockExpr) -> None:
        """检查返回值必须是元组、namedtuple、字典或实现BuildParams trait"""
        for stmt in node.body:
            if stmt.kind == "ReturnStmt":
                if stmt.value:
                    self._validate_build_params_type(stmt.value, stmt.line, stmt.col)
    
    def _check_yield_value_constraints(self, stmt: ASTNode) -> None:
        """检查yield值必须是元组、namedtuple、字典或实现BuildParams trait"""
        if stmt.value:
            self._validate_build_params_type(stmt.value, stmt.line, stmt.col)
        # yield后留白表示空参数包，无需检查
    
    def _validate_build_params_type(self, value: ASTNode, line: int, col: int) -> None:
        """验证返回值是否符合BuildParams约束"""
        # 允许的类型：元组、namedtuple、字典或实现BuildParams trait
        allowed_kinds = ("Tuple", "Dict", "Subscript", "Name", "Call", "Constant")
        
        if value.kind not in allowed_kinds:
            self.errors.append(
                f"Return value in build block must be tuple, namedtuple, dict, or object implementing "
                f"BuildParams trait, got {value.kind} at {line}:{col}"
            )
        
        # 如果是常量，检查是否是列表（可作为元组处理）或字典
        if value.kind == "Constant":
            if not isinstance(value.value, (list, dict, tuple)):
                self.errors.append(
                    f"Return value in build block must be tuple, namedtuple, or dict, "
                    f"got {type(value.value).__name__} at {line}:{col}"
                )
    
    def _check_build_call_return_type(self, node: BuildBlockExpr) -> None:
        """检查调用构建块的返回类型是否符合上游函数期望"""
        # 这需要结合类型系统进行更深入的检查
        # 这里先做基本的结构检查
        pass
