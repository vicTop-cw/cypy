"""编译性能基准测试"""

import os
import sys
import time
import tempfile
import shutil
import unittest


class TestCompilationBenchmark(unittest.TestCase):
    """编译性能基准测试"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.output_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        try:
            shutil.rmtree(self.temp_dir)
            shutil.rmtree(self.output_dir)
        except PermissionError:
            pass
    
    def _create_test_file(self, name: str, complexity: str = "simple") -> str:
        """创建测试文件"""
        filepath = os.path.join(self.temp_dir, f"{name}.cypy")
        
        if complexity == "simple":
            content = """
def add(x: int, y: int) -> int:
    return x + y

def multiply(x: int, y: int) -> int:
    return x * y
"""
        elif complexity == "medium":
            content = """
struct Point:
    x: int
    y: int

enum Color:
    RED
    GREEN
    BLUE

def calculate_distance(p1: Point, p2: Point) -> float:
    dx = p1.x - p2.x
    dy = p1.y - p2.y
    return (dx * dx + dy * dy) ** 0.5

def process_points(points: list) -> float:
    total = 0.0
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            total += calculate_distance(points[i], points[j])
    return total
"""
        elif complexity == "complex":
            content = """
struct Node:
    value: int
    left: Node
    right: Node

def fibonacci(n: int) -> int:
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

def factorial(n: int) -> int:
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result

class Calculator:
    def __init__(self):
        self.result: int = 0
    
    def add(self, x: int) -> int:
        self.result += x
        return self.result
    
    def multiply(self, x: int) -> int:
        self.result *= x
        return self.result
    
    def reset(self):
        self.result = 0

def process_tree(root: Node) -> int:
    if root is None:
        return 0
    return root.value + process_tree(root.left) + process_tree(root.right)

def generate_test_data(count: int) -> list:
    data = []
    for i in range(count):
        data.append(i * 2 + 1)
    return data
"""
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        
        return filepath
    
    def test_transpile_performance_simple(self):
        """测试简单代码的转译性能"""
        from cypy_hook.hook import CypyHook
        
        hook = CypyHook()
        hook.set_output_dir(self.output_dir)
        
        # 创建简单测试文件
        test_file = self._create_test_file("simple_test", "simple")
        
        # 多次运行取平均值
        times = []
        for _ in range(5):
            start = time.time()
            result = hook.transpile_file(test_file, incremental=False)
            elapsed = time.time() - start
            self.assertTrue(result.success)
            times.append(elapsed)
        
        avg_time = sum(times) / len(times)
        print(f"Simple transpile average time: {avg_time:.4f}s")
        
        # 验证性能（简单代码应该在合理时间内完成）
        self.assertLess(avg_time, 1.0, "Transpile took too long")
    
    def test_transpile_performance_medium(self):
        """测试中等复杂度代码的转译性能"""
        from cypy_hook.hook import CypyHook
        
        hook = CypyHook()
        hook.set_output_dir(self.output_dir)
        
        # 创建中等复杂度测试文件
        test_file = self._create_test_file("medium_test", "medium")
        
        # 多次运行取平均值
        times = []
        for _ in range(3):
            start = time.time()
            result = hook.transpile_file(test_file, incremental=False)
            elapsed = time.time() - start
            self.assertTrue(result.success)
            times.append(elapsed)
        
        avg_time = sum(times) / len(times)
        print(f"Medium transpile average time: {avg_time:.4f}s")
        
        # 验证性能
        self.assertLess(avg_time, 2.0, "Transpile took too long")
    
    def test_incremental_compilation_performance(self):
        """测试增量编译功能（验证增量编译正常工作）"""
        from cypy_hook.hook import CypyHook
        
        hook = CypyHook()
        hook.set_output_dir(self.output_dir)
        
        # 创建测试文件
        test_file = os.path.join(self.temp_dir, "incremental_test.cypy")
        with open(test_file, "w", encoding="utf-8") as f:
            # 添加多个重复的函数定义来增加编译时间
            for i in range(20):
                f.write(f"def func_{i}(x: int) -> int:\n")
                f.write(f"    return x * {i}\n")
                f.write(f"def calc_{i}(a: int, b: int) -> int:\n")
                f.write(f"    return a + b + {i}\n")
        
        # 测试增量编译功能正常工作
        result1 = hook.transpile_file(test_file, incremental=True)
        self.assertTrue(result1.success)
        
        # 再次编译（验证重复编译不会出错）
        result2 = hook.transpile_file(test_file, incremental=True)
        self.assertTrue(result2.success)
        
        # 验证生成的Cython代码相同
        self.assertEqual(result1.cython_code, result2.cython_code)
        
        print("Incremental compilation test passed - functionality verified")
    
    def test_compile_to_pyd_performance(self):
        """测试编译为.pyd文件的性能"""
        from cypy_hook.hook import CypyHook
        
        hook = CypyHook()
        hook.set_output_dir(self.output_dir)
        
        # 创建简单测试文件
        test_file = self._create_test_file("pyd_test", "simple")
        
        start = time.time()
        result = hook.compile_to_pyd(test_file)
        elapsed = time.time() - start
        
        print(f"Compile to .pyd time: {elapsed:.4f}s")
        
        self.assertTrue(result.success)
        self.assertIsNotNone(result.pyd_path)
    
    def test_cache_hit_performance(self):
        """测试缓存命中时的性能"""
        from cypy_hook.hook import CypyHook
        
        hook = CypyHook()
        hook.set_output_dir(self.output_dir)
        
        # 创建测试文件
        test_file = self._create_test_file("cache_test", "medium")
        
        # 第一次编译
        result1 = hook.transpile_file(test_file, incremental=True)
        self.assertTrue(result1.success)
        
        # 第二次编译（应该命中缓存）
        start = time.time()
        result2 = hook.transpile_file(test_file, incremental=True)
        cache_time = time.time() - start
        
        print(f"Cache hit time: {cache_time:.4f}s")
        
        # 缓存命中应该非常快
        self.assertLess(cache_time, 0.5)


class TestASTPerformance(unittest.TestCase):
    """AST处理性能测试"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        try:
            shutil.rmtree(self.temp_dir)
        except PermissionError:
            pass
    
    def _create_large_ast_file(self, func_count: int = 10) -> str:
        """创建包含大量函数定义的测试文件"""
        filepath = os.path.join(self.temp_dir, "large_ast.cypy")
        
        content = ""
        for i in range(func_count):
            content += f"""
def func_{i}(x: int) -> int:
    result = x
    for j in range(10):
        result += j
    return result

def fast_func_{i}(x: int) -> int:
    return x * 2
"""
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        
        return filepath
    
    def test_parser_performance(self):
        """测试解析器性能"""
        from cypyc.parser.lexer import Lexer
        from cypyc.parser.parser import Parser
        
        # 创建包含多个函数的文件
        test_file = self._create_large_ast_file(20)
        
        with open(test_file, "r", encoding="utf-8") as f:
            source = f.read()
        
        # 多次运行取平均值
        times = []
        for _ in range(5):
            start = time.time()
            lexer = Lexer(source)
            tokens = list(lexer.tokenize())
            parser = Parser(tokens)
            ast = parser.parse()
            elapsed = time.time() - start
            times.append(elapsed)
        
        avg_time = sum(times) / len(times)
        print(f"Parse 20 functions average time: {avg_time:.4f}s")
        
        self.assertLess(avg_time, 1.0)
    
    def test_analyzer_performance(self):
        """测试分析器性能"""
        from cypyc.parser.lexer import Lexer
        from cypyc.parser.parser import Parser
        from cypyc.analyzer.scope_analyzer import ScopeAnalyzer
        from cypyc.analyzer.type_checker import TypeChecker
        
        # 创建包含多个函数的文件
        test_file = self._create_large_ast_file(10)
        
        with open(test_file, "r", encoding="utf-8") as f:
            source = f.read()
        
        # 解析
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()
        
        # 运行分析器
        start = time.time()
        scope_analyzer = ScopeAnalyzer()
        scope_analyzer.analyze(ast)
        
        type_checker = TypeChecker()
        type_checker.check(ast)
        elapsed = time.time() - start
        
        print(f"Analyzer time: {elapsed:.4f}s")
        
        # 确保没有错误
        self.assertEqual(len(scope_analyzer.errors), 0)
        self.assertEqual(len(type_checker.errors), 0)


if __name__ == "__main__":
    unittest.main()
