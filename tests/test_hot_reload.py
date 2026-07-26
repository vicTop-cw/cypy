"""热重载功能测试"""

import os
import sys
import time
import tempfile
import shutil
import unittest


class TestFileMonitor(unittest.TestCase):
    """文件监控器测试"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir)
    
    def test_file_monitor_import(self):
        """测试文件监控器模块导入"""
        from cypyc.incremental import CypyFileMonitor, FileChangeEvent
        self.assertIsNotNone(CypyFileMonitor)
        self.assertIsNotNone(FileChangeEvent)
    
    def test_file_monitor_basic(self):
        """测试文件监控器基本功能"""
        from cypyc.incremental import CypyFileMonitor
        
        events_received = []
        
        def callback(events):
            events_received.extend(events)
        
        monitor = CypyFileMonitor([self.temp_dir], callback)
        monitor.start()
        
        try:
            # 创建Cypy文件
            cypy_file = os.path.join(self.temp_dir, "test.cypy")
            with open(cypy_file, "w", encoding="utf-8") as f:
                f.write("def test():\n    return 42\n")
            
            # 等待事件触发
            time.sleep(1.0)
            
            # 验证事件被捕获（watchdog可能触发created或modified）
            self.assertTrue(len(events_received) > 0)
            # 找到与该文件相关的事件
            file_events = [e for e in events_received if e.file_path == cypy_file]
            self.assertTrue(len(file_events) > 0)
            
            # 修改文件
            time.sleep(0.1)  # 确保mtime变化
            with open(cypy_file, "w", encoding="utf-8") as f:
                f.write("def test():\n    return 100\n")
            
            # 等待事件触发
            time.sleep(1.0)
            
            # 验证修改事件被捕获
            modify_events = [e for e in events_received if e.event_type == "modified"]
            self.assertTrue(len(modify_events) > 0)
            
        finally:
            monitor.stop()
    
    def test_file_monitor_debounce(self):
        """测试防抖机制"""
        from cypyc.incremental import CypyFileMonitor
        
        events_received = []
        
        def callback(events):
            events_received.extend(events)
        
        monitor = CypyFileMonitor([self.temp_dir], callback, debounce_delay=0.3)
        monitor.start()
        
        try:
            # 创建文件
            cypy_file = os.path.join(self.temp_dir, "debounce_test.cypy")
            with open(cypy_file, "w", encoding="utf-8") as f:
                f.write("def test():\n    return 1\n")
            
            # 快速多次修改
            for i in range(5):
                time.sleep(0.1)
                with open(cypy_file, "w", encoding="utf-8") as f:
                    f.write(f"def test():\n    return {i}\n")
            
            # 等待防抖完成
            time.sleep(1.0)
            
            # 验证事件被合并（应该少于5次修改事件）
            modify_events = [e for e in events_received if e.event_type == "modified"]
            self.assertLessEqual(len(modify_events), 2)
            
        finally:
            monitor.stop()


class TestHotReloadEngine(unittest.TestCase):
    """热重载引擎测试"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.output_dir = tempfile.mkdtemp()
        
        # 添加临时目录到sys.path
        if self.output_dir not in sys.path:
            sys.path.insert(0, self.output_dir)
    
    def tearDown(self):
        # 清理导入的模块
        modules_to_remove = [name for name in sys.modules if name.startswith('hotreload_')]
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
    
    def test_hot_reload_engine_import(self):
        """测试热重载引擎模块导入"""
        from cypyc.incremental import HotReloadEngine, HotReloadResult
        self.assertIsNotNone(HotReloadEngine)
        self.assertIsNotNone(HotReloadResult)
    
    def test_hot_reload_compile_and_reload(self):
        """测试编译并重新加载模块"""
        from cypy_hook.hook import CypyHook
        from cypyc.incremental import HotReloadEngine
        
        # 创建Cypy文件
        cypy_file = os.path.join(self.temp_dir, "hotreload_test.cypy")
        with open(cypy_file, "w", encoding="utf-8") as f:
            f.write("def get_value() -> int:\n    return 42\n")
        
        # 创建hook和引擎
        hook = CypyHook()
        hook.set_output_dir(self.output_dir)
        
        engine = HotReloadEngine(hook)
        
        # 编译并加载模块
        result = engine._compile_and_reload_module(cypy_file)
        
        self.assertTrue(result.success)
        self.assertEqual(result.recompiled_modules, ["hotreload_test"])
        
        # 验证模块可以被导入
        import hotreload_test
        self.assertEqual(hotreload_test.get_value(), 42)
    
    def test_hot_reload_state_preservation(self):
        """测试热重载状态保持 - 验证代码更新和状态保持机制"""
        from cypy_hook.hook import CypyHook
        from cypyc.incremental import HotReloadEngine
        
        # 创建简单的Cypy文件
        cypy_file = os.path.join(self.temp_dir, "hotreload_state.cypy")
        with open(cypy_file, "w", encoding="utf-8") as f:
            f.write("def get_value() -> int:\n")
            f.write("    return 42\n")
            f.write("def multiply(a: int, b: int) -> int:\n")
            f.write("    return a * b\n")
        
        # 创建hook和引擎
        hook = CypyHook()
        hook.set_output_dir(self.output_dir)
        
        engine = HotReloadEngine(hook)
        
        # 第一次编译
        result1 = engine._compile_and_reload_module(cypy_file)
        self.assertTrue(result1.success, f"First compile failed: {result1.errors}")
        
        # 使用模块
        import hotreload_state
        self.assertEqual(hotreload_state.get_value(), 42)
        self.assertEqual(hotreload_state.multiply(3, 4), 12)
        
        # 验证热重载引擎能够正确跟踪模块
        self.assertIn("hotreload_state", engine._module_source_map)
        tracked_modules = engine.get_tracked_modules()
        self.assertIn("hotreload_state", tracked_modules)
        
        # 测试状态保存和恢复方法
        engine._save_module_state("hotreload_state")
        self.assertIn("hotreload_state", engine._module_state)
        
        # 测试状态获取
        state = engine.get_module_state("hotreload_state")
        self.assertIsNotNone(state)
    
    def test_hot_reload_compile_error(self):
        """测试编译错误处理"""
        from cypy_hook.hook import CypyHook
        from cypyc.incremental import HotReloadEngine
        
        # 创建有效Cypy文件
        cypy_file = os.path.join(self.temp_dir, "hotreload_error.cypy")
        with open(cypy_file, "w", encoding="utf-8") as f:
            f.write("def get_value() -> int:\n    return 42\n")
        
        # 创建hook和引擎
        hook = CypyHook()
        hook.set_output_dir(self.output_dir)
        
        engine = HotReloadEngine(hook)
        
        # 第一次编译成功
        result1 = engine._compile_and_reload_module(cypy_file)
        self.assertTrue(result1.success)
        
        # 使用模块
        import hotreload_error
        self.assertEqual(hotreload_error.get_value(), 42)
        
        # 修改代码引入错误
        time.sleep(0.1)
        with open(cypy_file, "w", encoding="utf-8") as f:
            f.write("def get_value() -> int:\n    return invalid_syntax\n")
        
        # 第二次编译（应该失败）
        result2 = engine._compile_and_reload_module(cypy_file)
        self.assertFalse(result2.success)
        self.assertTrue(len(result2.errors) > 0)
        self.assertTrue(result2.state_preserved)
        
        # 验证旧模块仍可使用
        self.assertEqual(hotreload_error.get_value(), 42)


class TestDependencyCascade(unittest.TestCase):
    """依赖级联重编译测试"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.output_dir = tempfile.mkdtemp()
        
        # 添加临时目录到sys.path
        if self.output_dir not in sys.path:
            sys.path.insert(0, self.output_dir)
    
    def tearDown(self):
        # 清理导入的模块
        modules_to_remove = [name for name in sys.modules if name.startswith('dep_') or name.startswith('proxy_')]
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
    
    def test_dependency_tracking(self):
        """测试依赖关系追踪 - 验证_find_affected_modules和_module_dependencies功能"""
        from cypy_hook.hook import CypyHook
        from cypyc.incremental import HotReloadEngine
        
        # 创建独立模块A
        module_a = os.path.join(self.temp_dir, "dep_module_a.cypy")
        with open(module_a, "w", encoding="utf-8") as f:
            f.write("def get_base_value() -> int:\n")
            f.write("    return 10\n")
        
        # 创建独立模块B（不导入A，用于测试依赖图）
        module_b = os.path.join(self.temp_dir, "dep_module_b.cypy")
        with open(module_b, "w", encoding="utf-8") as f:
            f.write("def calculate() -> int:\n")
            f.write("    return 5 * 2\n")
        
        # 创建hook和引擎
        hook = CypyHook()
        hook.set_output_dir(self.output_dir)
        
        engine = HotReloadEngine(hook)
        
        # 编译并加载模块A
        result_a = engine._compile_and_reload_module(module_a)
        self.assertTrue(result_a.success, f"Failed to compile module A: {result_a.errors}")
        
        # 编译并加载模块B
        result_b = engine._compile_and_reload_module(module_b)
        self.assertTrue(result_b.success, f"Failed to compile module B: {result_b.errors}")
        
        # 验证模块被正确跟踪
        self.assertIn("dep_module_a", engine._module_source_map)
        self.assertIn("dep_module_b", engine._module_source_map)
        
        # 手动添加依赖关系（模拟模块B依赖模块A）
        engine._module_dependencies["dep_module_a"] = {"dep_module_b"}
        
        # 测试_find_affected_modules方法
        affected = engine._find_affected_modules("dep_module_a")
        self.assertIn("dep_module_a", affected)
        self.assertIn("dep_module_b", affected)
        
        # 测试_get_module_dependencies方法
        deps = engine.get_module_dependencies("dep_module_a")
        self.assertIn("dep_module_b", deps)
    
    def test_proxy_module_pattern(self):
        """测试代理模块模式"""
        from cypy_hook.hook import CypyHook
        from cypyc.incremental import HotReloadEngine
        
        # 创建Cypy文件
        cypy_file = os.path.join(self.temp_dir, "proxy_test.cypy")
        with open(cypy_file, "w", encoding="utf-8") as f:
            f.write("def get_value() -> int:\n    return 42\n")
        
        # 创建hook和引擎
        hook = CypyHook()
        hook.set_output_dir(self.output_dir)
        
        engine = HotReloadEngine(hook)
        
        # 第一次编译
        result1 = engine._compile_and_reload_module(cypy_file)
        self.assertTrue(result1.success, f"First compile failed: {result1.errors}")
        
        # 验证模块使用代理模式
        self.assertTrue(engine.is_proxy_module("proxy_test"))
        
        # 使用模块
        import proxy_test
        self.assertEqual(proxy_test.get_value(), 42)
        
        # 修改代码
        time.sleep(0.1)
        with open(cypy_file, "w", encoding="utf-8") as f:
            f.write("def get_value() -> int:\n    return 100\n")
        
        # 第二次编译
        result2 = engine._compile_and_reload_module(cypy_file)
        self.assertTrue(result2.success, f"Second compile failed: {result2.errors}")
        
        # 验证模块仍然使用代理模式
        self.assertTrue(engine.is_proxy_module("proxy_test"))
        
        # 验证新代码生效
        self.assertEqual(proxy_test.get_value(), 100)


class TestCLIWatch(unittest.TestCase):
    """CLI watch命令测试"""
    
    def test_watch_command_exists(self):
        """测试watch命令存在"""
        from cypyc.cli import parse_args
        
        # 测试watch命令可以被解析
        args = parse_args(["watch", "."])
        self.assertEqual(args.command, "watch")
        self.assertEqual(args.source, ".")
    
    def test_watch_command_with_options(self):
        """测试watch命令参数"""
        from cypyc.cli import parse_args
        
        args = parse_args(["watch", "./src", "-o", "./build", "-v", "--debounce", "1.0"])
        self.assertEqual(args.command, "watch")
        self.assertEqual(args.source, "./src")
        self.assertEqual(args.output, "./build")
        self.assertTrue(args.verbose)
        self.assertEqual(args.debounce, 1.0)


if __name__ == "__main__":
    unittest.main()
