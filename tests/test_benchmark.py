"""基准测试 - 验证增量编译性能提升"""

import os
import sys
import time
import tempfile
import shutil
import unittest


class TestIncrementalCompilationBenchmark(unittest.TestCase):
    """增量编译性能基准测试"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.output_dir = tempfile.mkdtemp()
        
        # 添加临时目录到sys.path
        if self.output_dir not in sys.path:
            sys.path.insert(0, self.output_dir)
    
    def tearDown(self):
        # 清理导入的模块
        modules_to_remove = [name for name in sys.modules if name.startswith('bench_')]
        for mod_name in modules_to_remove:
            if mod_name in sys.modules:
                del sys.modules[mod_name]
        
        # 清理sys.path
        if self.output_dir in sys.path:
            sys.path.remove(self.output_dir)
        
        # 清理临时目录
        try:
            shutil.rmtree(self.temp_dir)
            shutil.rmtree(self.output_dir)
        except PermissionError:
            pass
    
    def _create_dependency_chain(self, depth: int = 5):
        """创建依赖链（模块A依赖模块B，模块B依赖模块C，依此类推）"""
        files = []
        
        for i in range(depth):
            filename = f"bench_module_{i}.cypy"
            filepath = os.path.join(self.temp_dir, filename)
            
            if i == 0:
                # 最底层模块，不依赖其他模块
                content = f"def compute_{i}(x: int) -> int:\n    return x + {i}\n"
            else:
                # 依赖前一个模块
                content = f"import bench_module_{i-1}\n"
                content += f"def compute_{i}(x: int) -> int:\n"
                content += f"    return bench_module_{i-1}.compute_{i-1}(x) * 2\n"
            
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            
            files.append(filepath)
        
        return files
    
    def _create_independent_modules(self, count: int = 10):
        """创建独立模块（互不依赖）"""
        files = []
        
        for i in range(count):
            filename = f"bench_independent_{i}.cypy"
            filepath = os.path.join(self.temp_dir, filename)
            
            content = f"def process_{i}(value: int) -> int:\n"
            content += f"    result = value\n"
            content += f"    for j in range(100):\n"
            content += f"        result = result * 2 + {i}\n"
            content += f"    return result\n"
            
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            
            files.append(filepath)
        
        return files
    
    def test_incremental_vs_full_compilation_speed(self):
        """测试增量编译与全量编译的速度对比"""
        from cypy_hook.hook import CypyHook
        from cypyc.incremental import HotReloadEngine
        
        # 创建10个独立模块
        modules = self._create_independent_modules(10)
        
        hook = CypyHook()
        hook.set_output_dir(self.output_dir)
        
        # 全量编译时间（第一次编译）
        start_time = time.time()
        for module_path in modules:
            result = hook.compile_to_pyd(module_path, output_dir=self.output_dir)
            self.assertTrue(result.success, f"Failed to compile {module_path}")
        full_compile_time = time.time() - start_time
        
        print(f"[Benchmark] Full compilation time: {full_compile_time:.3f}s")
        
        # 修改其中一个模块
        modified_module = modules[0]
        with open(modified_module, "w", encoding="utf-8") as f:
            f.write("def process_0(value: int) -> int:\n")
            f.write("    result = value\n")
            f.write("    for j in range(101):\n")  # 稍微修改循环次数
            f.write("        result = result * 2 + 0\n")
            f.write("    return result\n")
        
        # 增量编译时间（只编译修改的模块）
        engine = HotReloadEngine(hook)
        
        start_time = time.time()
        result = engine._compile_and_reload_module(modified_module)
        incremental_time = time.time() - start_time
        
        print(f"[Benchmark] Incremental compilation time: {incremental_time:.3f}s")
        
        # 计算性能提升比例
        speedup = full_compile_time / incremental_time if incremental_time > 0 else float('inf')
        
        print(f"[Benchmark] Speedup: {speedup:.2f}x")
        
        # 验证增量编译成功
        self.assertTrue(result.success, f"Incremental compilation failed: {result.errors}")
        
        # 验证性能提升（至少50%）
        # 50%提升意味着增量编译时间应该小于全量编译时间的50%
        self.assertLess(incremental_time, full_compile_time * 0.5,
                        f"Incremental compilation should be at least 50% faster")
    
    def test_dependency_chain_compilation(self):
        """测试依赖链的增量编译 - 验证依赖分析机制"""
        from cypyc.incremental import DependencyGraph
        from cypyc.parser.lexer import Lexer
        from cypyc.parser.parser import Parser
        
        # 创建单个文件包含多个相互依赖的函数
        filepath = os.path.join(self.temp_dir, "bench_dependency.cypy")
        content = """def base_func(x: int) -> int:
    return x * 2

def intermediate_func(x: int) -> int:
    return base_func(x) + 10

def final_func(x: int) -> int:
    return intermediate_func(x) * 3
"""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        
        # 分析依赖关系
        with open(filepath, 'r', encoding='utf-8') as f:
            source_code = f.read()
        
        lexer = Lexer(source_code)
        ast = Parser(lexer.tokenize()).parse()
        
        # 构建依赖图
        dep_graph = DependencyGraph()
        dep_graph.build_from_ast(ast)
        
        # 验证依赖图能够正确识别定义
        definitions = dep_graph.get_all_definitions()
        self.assertIn("base_func", definitions)
        self.assertIn("intermediate_func", definitions)
        self.assertIn("final_func", definitions)
        
        print(f"[Benchmark] Dependency graph analysis completed successfully")
        print(f"[Benchmark] Definitions found: {definitions}")
    
    def test_multiple_file_monitoring(self):
        """测试同时监控多个文件"""
        from cypyc.incremental import CypyFileMonitor
        
        # 创建100个Cypy文件
        for i in range(100):
            filepath = os.path.join(self.temp_dir, f"bench_monitor_{i}.cypy")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"def func_{i}() -> int:\n    return {i}\n")
        
        events_received = []
        
        def callback(events):
            events_received.extend(events)
        
        monitor = CypyFileMonitor([self.temp_dir], callback)
        monitor.start()
        
        try:
            # 验证监控器能够识别所有Cypy文件
            watched_files = monitor.get_watched_files()
            self.assertEqual(len(watched_files), 100)
            
        finally:
            monitor.stop()


if __name__ == "__main__":
    unittest.main()
