"""Bridge代码生成器：将Cypy AST转换为C代码并编译为.pyd文件

这个模块提供了一个与CythonGenerator兼容的接口，
但使用cypy_bridge.compiler.CCodeGenerator生成C代码，
并直接编译为Python扩展模块(.pyd)。

设计目的：
1. 与CythonGenerator保持相同的接口，方便在cypyc中切换使用
2. 支持直接编译为.pyd文件，无需中间的Cython编译步骤
3. 作为移除Cython依赖的核心组件
"""

import os
from typing import Any, List, Optional
from cypyc.parser.parser import (
    ASTNode, Module, FuncDef, LetStmt, ReturnStmt, IfStmt, ForStmt, WhileStmt,
    BinOp, UnaryOp, Call, Name, Constant, Attribute, Subscript, StructDef,
    StructField, EnumDef, EnumVariant, DeferStmt, DerefExpr, PointerType,
    GenericType, TraitDef, ImplStmt, MetaBlock
)


class BridgeGenerator:
    """Bridge代码生成器：生成C代码并编译为.pyd文件"""
    
    def __init__(self):
        self.indent = 0
        self.output = []
        self.module_name = ""
        self._compiler = None  # 延迟导入以避免循环依赖
        self._code_generator = None  # 缓存CCodeGenerator实例
    
    def _get_compiler(self):
        """延迟导入compiler以避免循环依赖"""
        if self._compiler is None:
            from cypy_bridge.compiler import BridgeCompiler
            self._compiler = BridgeCompiler()
        return self._compiler
    
    def _get_code_generator(self):
        """延迟导入CCodeGenerator并缓存实例"""
        if self._code_generator is None:
            from cypy_bridge.compiler import CCodeGenerator
            self._code_generator = CCodeGenerator()
        return self._code_generator
    
    def generate(self, node: ASTNode, module_name: str = "cypy_module") -> str:
        """生成C代码并编译为.pyd文件
        
        Args:
            node: Cypy AST节点（通常是Module）
            module_name: 模块名称，用于生成.pyd文件名
            
        Returns:
            生成的C代码字符串
        """
        self.module_name = module_name
        
        # 每次生成使用新的CCodeGenerator实例，避免状态累积问题
        from cypy_bridge.compiler import CCodeGenerator
        generator = CCodeGenerator()
        generator.module_name = module_name
        c_code = generator.generate(node, module_name)
        
        self.output = c_code.split('\n')
        return c_code
    
    def generate_and_compile(self, node: ASTNode, module_name: str = "cypy_module", 
                            output_dir: str = None, use_cache: bool = True) -> str:
        """生成C代码并编译为.pyd文件
        
        Args:
            node: Cypy AST节点（通常是Module）
            module_name: 模块名称，用于生成.pyd文件名
            output_dir: 输出目录
            use_cache: 是否使用缓存（默认True）
            
        Returns:
            生成的.pyd文件路径
        """
        compiler = self._get_compiler()
        c_code = self.generate(node, module_name)
        result = compiler.compile_c_code(c_code, module_name, output_dir, use_cache)
        
        if result.success:
            return result.output_path
        else:
            raise RuntimeError(f"Bridge compilation failed: {result.error}")
    
    def _visit(self, node: ASTNode) -> None:
        """访问AST节点（兼容CythonGenerator接口）"""
        # 实际实现委托给CCodeGenerator
        pass
    
    def _visit_children(self, node: ASTNode) -> None:
        """访问子节点（兼容CythonGenerator接口）"""
        pass
    
    def _write(self, text: str) -> None:
        """写入代码行（兼容CythonGenerator接口）"""
        if text:
            self.output.append("    " * self.indent + text)
    
    def _detect_libc_usage(self, node: ASTNode) -> None:
        """检测C标准库使用（兼容CythonGenerator接口）"""
        pass


class BridgeCodegenAdapter:
    """适配器：让cypyc CLI可以无缝切换到bridge编译器"""
    
    def __init__(self):
        self.generator = BridgeGenerator()
    
    def transpile(self, source_code: str, module_name: str = "cypy_module") -> str:
        """将Cypy源代码转换为C代码"""
        from cypyc.parser.lexer import Lexer
        from cypyc.parser.parser import Parser
        from cypyc.parser.macro_expander import expand_macros
        
        lexer = Lexer(source_code)
        tokens = lexer.tokenize()
        parser = Parser(tokens)
        ast = parser.parse()
        
        # 在编译前展开宏
        ast = expand_macros(ast)
        
        return self.generator.generate(ast, module_name)
    
    def compile(self, source_code: str, module_name: str = "cypy_module", 
                output_dir: str = None, use_cache: bool = True) -> str:
        """将Cypy源代码编译为.pyd文件
        
        Args:
            source_code: Cypy源代码
            module_name: 模块名称
            output_dir: 输出目录
            use_cache: 是否使用缓存（默认True）
        
        Returns:
            .pyd文件路径
        """
        from cypyc.parser.lexer import Lexer
        from cypyc.parser.parser import Parser
        from cypyc.parser.macro_expander import expand_macros
        
        lexer = Lexer(source_code)
        tokens = lexer.tokenize()
        parser = Parser(tokens)
        ast = parser.parse()
        
        # 在编译前展开宏
        ast = expand_macros(ast)
        
        return self.generator.generate_and_compile(ast, module_name, output_dir, use_cache)
    
    def transpile_file(self, source_path: str) -> str:
        """将Cypy源文件转换为C代码"""
        with open(source_path, 'r', encoding='utf-8') as f:
            source_code = f.read()
        
        module_name = os.path.basename(source_path)
        if module_name.endswith('.cypy'):
            module_name = module_name[:-5]
        elif module_name.endswith('.py'):
            module_name = module_name[:-3]
        
        return self.transpile(source_code, module_name)
    
    def compile_file(self, source_path: str, output_dir: str = None) -> str:
        """编译Cypy源文件为.pyd文件"""
        with open(source_path, 'r', encoding='utf-8') as f:
            source_code = f.read()
        
        module_name = os.path.basename(source_path)
        if module_name.endswith('.cypy'):
            module_name = module_name[:-5]
        elif module_name.endswith('.py'):
            module_name = module_name[:-3]
        
        return self.compile(source_code, module_name, output_dir)


# 兼容接口：提供与CythonGenerator相同的API
def create_bridge_generator() -> BridgeGenerator:
    """创建BridgeGenerator实例（工厂函数）"""
    return BridgeGenerator()


def create_codegen_adapter() -> BridgeCodegenAdapter:
    """创建BridgeCodegenAdapter实例（工厂函数）"""
    return BridgeCodegenAdapter()


__all__ = [
    'BridgeGenerator',
    'BridgeCodegenAdapter',
    'create_bridge_generator',
    'create_codegen_adapter',
]
