"""
编译器测试夹具
提供编译、运行 Cypy 代码的便捷方法
"""
import os
import sys
import tempfile
import subprocess
from typing import Any, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


class CompilerFixture:
    def __init__(self):
        self.temp_dir = None
        self.output_dir = None
    
    def setup(self):
        """初始化编译环境"""
        self.temp_dir = tempfile.mkdtemp(prefix="cypy_test_")
        self.output_dir = os.path.join(self.temp_dir, "output")
        os.makedirs(self.output_dir, exist_ok=True)
    
    def teardown(self):
        """清理编译环境"""
        import shutil
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.temp_dir = None
        self.output_dir = None
    
    def compile(self, source: str, source_name: str = "test") -> Optional[str]:
        """
        编译 Cypy 源码为 Cython
        
        :param source: Cypy 源代码
        :param source_name: 源文件名称（不含扩展名）
        :return: 生成的 Cython 代码，失败返回 None
        """
        from cypy_hook.hook import CypyHook
        
        if not self.temp_dir:
            self.setup()
        
        source_path = os.path.join(self.temp_dir, f"{source_name}.cypy")
        with open(source_path, 'w', encoding='utf-8') as f:
            f.write(source)
        
        hook = CypyHook()
        hook.set_output_dir(self.output_dir)
        hook.set_verbose(False)
        
        result = hook.transpile_file(source_path)
        
        if result.success:
            return result.cython_code
        return None
    
    def compile_file(self, source_path: str) -> Optional[str]:
        """
        编译 Cypy 文件
        
        :param source_path: 文件路径
        :return: 生成的 Cython 代码，失败返回 None
        """
        from cypy_hook.hook import CypyHook
        
        if not self.temp_dir:
            self.setup()
        
        hook = CypyHook()
        hook.set_output_dir(self.output_dir)
        hook.set_verbose(False)
        
        result = hook.transpile_file(source_path)
        
        if result.success:
            return result.cython_code
        return None
    
    def compile_and_run(self, source: str, source_name: str = "test") -> Any:
        """
        编译并运行，返回执行结果
        
        :param source: Cypy 源代码
        :param source_name: 源文件名称（不含扩展名）
        :return: 执行结果，失败返回 None
        """
        from cypy_hook.hook import CypyHook
        
        if not self.temp_dir:
            self.setup()
        
        source_path = os.path.join(self.temp_dir, f"{source_name}.cypy")
        with open(source_path, 'w', encoding='utf-8') as f:
            f.write(source)
        
        hook = CypyHook()
        hook.set_output_dir(self.output_dir)
        hook.set_verbose(False)
        
        try:
            result, output = hook.run(source_path, "main")
            if result.success:
                return output
        except Exception as e:
            return None
        
        return None
    
    def analyze_only(self, source: str, source_name: str = "test"):
        """
        仅执行静态分析，不生成代码
        
        :param source: Cypy 源代码
        :param source_name: 源文件名称（不含扩展名）
        :return: (success, errors) 元组
        """
        from cypy_hook.hook import CypyHook
        
        if not self.temp_dir:
            self.setup()
        
        source_path = os.path.join(self.temp_dir, f"{source_name}.cypy")
        with open(source_path, 'w', encoding='utf-8') as f:
            f.write(source)
        
        hook = CypyHook()
        hook.set_output_dir(self.output_dir)
        hook.set_verbose(False)
        
        result = hook.transpile_file(source_path)
        
        return result.success, result.errors
    
    def generate_ast(self, source: str) -> Any:
        """
        生成 AST 表示
        
        :param source: Cypy 源代码
        :return: AST 对象
        """
        from cypyc.parser import Lexer, Parser
        
        lexer = Lexer(source)
        parser = Parser(lexer)
        return parser.parse()
    
    def __enter__(self):
        self.setup()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.teardown()
