import unittest
import subprocess
import tempfile
import os
import sys
import shutil
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.analyzer.type_checker import TypeChecker
from cypyc.codegen.cython_generator import CythonGenerator
from cypyc.codegen.setup_generator import SetupGenerator


class ByteDiffRunner:
    """字节级差异测试运行器 - 对比 Cypy 编译结果与 CPython 执行结果"""
    
    def __init__(self, temp_dir=None):
        self.temp_dir = temp_dir or tempfile.mkdtemp(prefix="cypy_byte_diff_")
        self._cleanup_files = []
    
    def cleanup(self):
        """清理临时文件"""
        for f in self._cleanup_files:
            try:
                os.remove(f)
            except:
                pass
        try:
            shutil.rmtree(self.temp_dir)
        except:
            pass
    
    def _compile_cypy_to_cython(self, cypy_source: str, module_name: str) -> str:
        """将 Cypy 源代码编译为 Cython 代码"""
        lexer = Lexer(cypy_source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        
        type_checker = TypeChecker()
        type_checker.check(ast)
        if type_checker.errors:
            raise ValueError(f"Type errors: {type_checker.errors}")
        
        generator = CythonGenerator()
        cython_code = generator.generate(ast)
        
        return cython_code
    
    def _write_cython_module(self, cython_code: str, module_name: str) -> str:
        """将 Cython 代码写入文件"""
        pyx_path = os.path.join(self.temp_dir, f"{module_name}.pyx")
        with open(pyx_path, 'w', encoding='utf-8') as f:
            f.write(cython_code)
        self._cleanup_files.append(pyx_path)
        return pyx_path
    
    def _write_setup_py(self, module_name: str) -> str:
        """生成 setup.py 文件"""
        setup_path = os.path.join(self.temp_dir, "setup.py")
        setup_generator = SetupGenerator()
        setup_generator.set_module_name(module_name)
        setup_generator.add_source(f"{module_name}.pyx")
        setup_code = setup_generator.generate()
        with open(setup_path, 'w', encoding='utf-8') as f:
            f.write(setup_code)
        self._cleanup_files.append(setup_path)
        return setup_path
    
    def _build_cython_module(self, module_name: str):
        """构建 Cython 模块"""
        setup_path = self._write_setup_py(module_name)
        original_dir = os.getcwd()
        try:
            os.chdir(self.temp_dir)
            result = subprocess.run(
                [sys.executable, setup_path, "build_ext", "--inplace"],
                capture_output=True,
                text=True,
                timeout=120
            )
            if result.returncode != 0:
                raise RuntimeError(f"Cython build failed:\n{result.stderr}")
        finally:
            os.chdir(original_dir)
        
        # 将 .pyd 文件复制到临时目录根目录
        for root, dirs, files in os.walk(self.temp_dir):
            for f in files:
                if f.endswith('.pyd') or f.endswith('.so'):
                    src_path = os.path.join(root, f)
                    dst_path = os.path.join(self.temp_dir, f)
                    if src_path != dst_path:
                        shutil.copy2(src_path, dst_path)
    
    def _run_cypy_code(self, cypy_source: str, module_name: str) -> str:
        """运行 Cypy 编译后的代码"""
        cython_code = self._compile_cypy_to_cython(cypy_source, module_name)
        self._write_cython_module(cython_code, module_name)
        self._build_cython_module(module_name)
        
        # 创建测试脚本
        test_script = f"""
import sys
sys.path.insert(0, r'{self.temp_dir}')
import {module_name}
# 执行模块中的主逻辑
if hasattr({module_name}, '__main__'):
    {module_name}.__main__()
"""
        result = subprocess.run(
            [sys.executable, "-c", test_script],
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.stdout.strip()
    
    def _run_python_code(self, python_source: str) -> str:
        """运行等效的 Python 代码"""
        result = subprocess.run(
            [sys.executable, "-c", python_source],
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.stdout.strip()
    
    def compare(self, cypy_source: str, python_source: str, module_name: str = "test_module") -> dict:
        """对比 Cypy 和 Python 代码的执行结果"""
        cypy_output = self._run_cypy_code(cypy_source, module_name)
        python_output = self._run_python_code(python_source)
        
        return {
            'cypy_output': cypy_output,
            'python_output': python_output,
            'match': cypy_output == python_output
        }


class TestByteDiffRunner(unittest.TestCase):
    """测试字节级差异测试运行器"""
    
    def setUp(self):
        self.runner = ByteDiffRunner()
    
    def tearDown(self):
        self.runner.cleanup()
    
    def test_simple_addition(self):
        """测试简单加法运算"""
        cypy_source = """
def add(x: int, y: int) -> int:
    return x + y

print(add(3, 5))
"""
        python_source = """
def add(x, y):
    return x + y

print(add(3, 5))
"""
        result = self.runner.compare(cypy_source, python_source)
        self.assertTrue(result['match'], f"Mismatch: Cypy='{result['cypy_output']}', Python='{result['python_output']}'")
    
    def test_string_concatenation(self):
        """测试字符串拼接"""
        cypy_source = """
def greet(name: str) -> str:
    return "Hello, " + name

print(greet("World"))
"""
        python_source = """
def greet(name):
    return "Hello, " + name

print(greet("World"))
"""
        result = self.runner.compare(cypy_source, python_source)
        self.assertTrue(result['match'], f"Mismatch: Cypy='{result['cypy_output']}', Python='{result['python_output']}'")
    
    def test_loop(self):
        """测试循环"""
        cypy_source = """
def sum_range(n: int) -> int:
    total = 0
    for i in range(n):
        total += i
    return total

print(sum_range(5))
"""
        python_source = """
def sum_range(n):
    total = 0
    for i in range(n):
        total += i
    return total

print(sum_range(5))
"""
        result = self.runner.compare(cypy_source, python_source)
        self.assertTrue(result['match'], f"Mismatch: Cypy='{result['cypy_output']}', Python='{result['python_output']}'")


if __name__ == "__main__":
    unittest.main()