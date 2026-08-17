"""热重载引擎 - 在不中断应用运行的情况下更新代码"""

import os
import sys
import importlib
import tempfile
import shutil
from typing import Dict, Set, Any, Optional, List, Callable
from dataclasses import dataclass
from .file_monitor import CypyFileMonitor, FileChangeEvent
from .incremental_manager import IncrementalCompiler, IncrementalResult
from .dependency_graph import DependencyGraph


@dataclass
class HotReloadResult:
    """热重载结果"""
    success: bool
    recompiled_modules: List[str]
    updated_modules: List[str]
    affected_definitions: Set[str] = None
    errors: List[str] = None
    state_preserved: bool = False
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.affected_definitions is None:
            self.affected_definitions = set()


class CypyProxyModule:
    """Cypy代理模块 - 解决Windows .pyd文件锁定问题
    
    代理模块模式：创建一个稳定的Python模块作为代理，
    将所有属性访问委托给实际的.pyd模块。当需要热重载时，
    只需更新代理内部的.pyd引用，而不需要卸载模块本身。
    
    优化特性：
    - 属性缓存机制：减少重复属性访问的开销
    - 支持更多类型的状态保存：函数、类、实例等
    - 模块重新导入逻辑优化：避免重复导入
    """
    
    def __init__(self, module_name: str):
        """初始化代理模块"""
        self._module_name = module_name
        self._actual_module = None
        self._state_cache: Dict[str, Any] = {}
        self._attr_cache: Dict[str, Any] = {}
        self._cache_enabled = True
    
    def _set_actual_module(self, actual_module):
        """设置实际的.pyd模块"""
        # 保存当前状态（支持更多类型）
        if self._actual_module is not None:
            self._save_state()
        
        self._actual_module = actual_module
        
        # 恢复状态
        self._restore_state()
        
        # 清空属性缓存（新模块需要重新缓存）
        self._attr_cache.clear()
    
    def _get_actual_module(self):
        """获取实际的.pyd模块"""
        return self._actual_module
    
    def _save_state(self):
        """保存模块状态（支持更多类型）"""
        if self._actual_module is None:
            return
        
        for name in dir(self._actual_module):
            if not name.startswith('_'):
                try:
                    value = getattr(self._actual_module, name)
                    # 保存多种类型：基本类型、函数、类、实例
                    if isinstance(value, (int, float, str, bool, tuple, list, dict, set)):
                        self._state_cache[name] = value
                    elif callable(value) and not isinstance(value, type):
                        # 保存函数和方法引用
                        self._state_cache[name] = value
                    elif isinstance(value, type):
                        # 保存类定义（但不保存类的实例）
                        self._state_cache[name] = value
                except Exception:
                    pass
    
    def _restore_state(self):
        """恢复模块状态"""
        if self._actual_module is None:
            return
        
        for name, value in self._state_cache.items():
            if hasattr(self._actual_module, name):
                try:
                    current_value = getattr(self._actual_module, name)
                    # 只恢复非函数/非类的状态（函数和类应该使用新的定义）
                    if not callable(current_value) and not isinstance(current_value, type):
                        setattr(self._actual_module, name, value)
                except Exception:
                    pass
    
    def _enable_cache(self, enable: bool = True):
        """启用/禁用属性缓存"""
        self._cache_enabled = enable
        if not enable:
            self._attr_cache.clear()
    
    def __getattr__(self, name):
        """委托属性访问给实际模块（带缓存）"""
        if name.startswith('_'):
            return object.__getattribute__(self, name)
        if self._actual_module is None:
            raise AttributeError(f"Module '{self._module_name}' not loaded")
        
        # 使用属性缓存
        if self._cache_enabled and name in self._attr_cache:
            return self._attr_cache[name]
        
        value = getattr(self._actual_module, name)
        
        # 缓存非动态属性
        if self._cache_enabled:
            # 不缓存函数和方法（它们应该从新模块获取）
            if not callable(value) or isinstance(value, type):
                self._attr_cache[name] = value
        
        return value
    
    def __setattr__(self, name, value):
        """委托属性设置给实际模块"""
        if name.startswith('_'):
            object.__setattr__(self, name, value)
        elif self._actual_module is not None:
            setattr(self._actual_module, name, value)
            # 清除该属性的缓存
            if name in self._attr_cache:
                del self._attr_cache[name]
        else:
            # 如果模块尚未加载，保存到状态缓存
            self._state_cache[name] = value
    
    def __dir__(self):
        """返回模块的属性列表"""
        if self._actual_module is not None:
            return dir(self._actual_module)
        return list(self._state_cache.keys())
    
    def __call__(self, *args, **kwargs):
        """支持模块级调用（如果实际模块支持）"""
        if self._actual_module is None:
            raise AttributeError(f"Module '{self._module_name}' not loaded")
        if callable(self._actual_module):
            return self._actual_module(*args, **kwargs)
        raise TypeError(f"Module '{self._module_name}' is not callable")


class HotReloadEngine:
    """热重载引擎"""
    
    def __init__(self, hook, incremental_compiler=None):
        """
        初始化热重载引擎
        
        参数:
            hook: CypyHook实例
            incremental_compiler: IncrementalCompiler实例（可选）
        """
        self._hook = hook
        
        # 使用传入的增量编译器，或从hook中获取
        if incremental_compiler:
            self._incremental_compiler = incremental_compiler
        elif hasattr(hook, '_get_incremental_compiler'):
            self._incremental_compiler = hook._get_incremental_compiler()
        else:
            self._incremental_compiler = IncrementalCompiler()
        
        # 复用hook中的缓存管理器（如果可用）
        if hasattr(hook, '_cache_manager'):
            self._cache_manager = hook._cache_manager
        else:
            from cypy_hook.hook import CypyCacheManager
            self._cache_manager = CypyCacheManager()
        
        # 模块状态缓存: module_name -> {global_name: value}
        self._module_state: Dict[str, Dict[str, Any]] = {}
        # 已加载模块的源文件映射: module_name -> source_path
        self._module_source_map: Dict[str, str] = {}
        # 模块间依赖图: module_name -> set(dependent_module_names)
        self._module_dependencies: Dict[str, Set[str]] = {}
        # 代理模块映射: module_name -> CypyProxyModule
        self._proxy_modules: Dict[str, CypyProxyModule] = {}
        # 监控器实例
        self._monitor: Optional[CypyFileMonitor] = None
        # 热重载回调
        self._on_reload: Optional[Callable[[HotReloadResult], None]] = None
        
    def _save_module_state(self, module_name: str) -> None:
        """保存模块的全局状态"""
        if module_name not in sys.modules:
            return
        
        module = sys.modules[module_name]
        
        # 如果是代理模块，获取实际模块
        if isinstance(module, CypyProxyModule):
            module = module._get_actual_module()
            if module is None:
                return
        
        # 保存模块的全局变量（排除特殊属性）
        state = {}
        for name in dir(module):
            # 排除私有属性和特殊方法
            if not name.startswith('_'):
                try:
                    value = getattr(module, name)
                    # 只保存可序列化的简单类型
                    if isinstance(value, (int, float, str, bool, tuple, list, dict, set)):
                        state[name] = value
                except Exception:
                    pass
        
        self._module_state[module_name] = state
    
    def _restore_module_state(self, module_name: str) -> None:
        """恢复模块的全局状态"""
        if module_name not in sys.modules or module_name not in self._module_state:
            return
        
        module = sys.modules[module_name]
        
        # 如果是代理模块，获取实际模块
        if isinstance(module, CypyProxyModule):
            module = module._get_actual_module()
            if module is None:
                return
        
        state = self._module_state[module_name]
        
        # 恢复保存的全局变量
        for name, value in state.items():
            if not hasattr(module, name) or getattr(module, name) != value:
                try:
                    setattr(module, name, value)
                except Exception:
                    pass
    
    def _get_module_name_from_path(self, source_path: str) -> str:
        """从源文件路径获取模块名称"""
        basename = os.path.basename(source_path)
        if basename.endswith('.cypy'):
            return basename[:-5]
        elif basename.endswith('.py'):
            return basename[:-3]
        return os.path.splitext(basename)[0]
    
    def _compile_and_reload_module(self, source_path: str) -> HotReloadResult:
        """编译并重新加载单个模块（使用代理模式）"""
        module_name = self._get_module_name_from_path(source_path)
        
        # 保存当前状态
        self._save_module_state(module_name)
        
        # 使用临时目录编译（处理Windows文件锁定）
        temp_dir = tempfile.mkdtemp()
        
        try:
            # 编译为.pyd（强制重新编译，跳过增量编译缓存）
            result = self._hook.compile_to_pyd(source_path, output_dir=temp_dir, force_recompile=True)
            
            if not result.success or not result.pyd_path:
                # 恢复状态
                self._restore_module_state(module_name)
                return HotReloadResult(
                    success=False,
                    recompiled_modules=[],
                    updated_modules=[],
                    errors=result.errors,
                    state_preserved=True
                )
            
            # 更新缓存
            if self._cache_manager:
                self._cache_manager.cache_pyd(source_path, result.pyd_path)
            
            # 更新增量编译缓存
            if self._incremental_compiler:
                # 解析新AST来更新依赖图
                from cypyc.parser.lexer import Lexer
                from cypyc.parser.parser import Parser
                
                try:
                    with open(source_path, 'r', encoding='utf-8') as f:
                        source_code = f.read()
                    
                    lexer = Lexer(source_code)
                    new_ast = Parser(lexer.tokenize()).parse()
                    self._incremental_compiler.update_cache(source_path, new_ast)
                except Exception:
                    pass  # 解析失败不影响热重载
            
            # 重新导入模块
            module_dir = os.path.dirname(result.pyd_path)
            if module_dir not in sys.path:
                sys.path.insert(0, module_dir)
            
            try:
                spec = importlib.util.spec_from_file_location(module_name, result.pyd_path)
                if spec and spec.loader:
                    new_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(new_module)
                    
                    # 检查是否已有代理模块
                    if module_name in sys.modules and isinstance(sys.modules[module_name], CypyProxyModule):
                        # 更新代理模块的实际模块引用
                        proxy_module = sys.modules[module_name]
                        proxy_module._set_actual_module(new_module)
                    else:
                        # 创建新的代理模块
                        proxy_module = CypyProxyModule(module_name)
                        proxy_module._set_actual_module(new_module)
                        sys.modules[module_name] = proxy_module
                        self._proxy_modules[module_name] = proxy_module
                    
                    # 恢复状态
                    self._restore_module_state(module_name)
                    
                    # 更新源文件映射
                    self._module_source_map[module_name] = source_path
                    
                    # 清理sys.path
                    if module_dir in sys.path:
                        sys.path.remove(module_dir)
                    
                    # 获取受影响的定义
                    affected_definitions = set()
                    if self._incremental_compiler:
                        dep_graph = self._incremental_compiler.get_dependency_graph()
                        affected_definitions = dep_graph.get_all_definitions()
                    
                    return HotReloadResult(
                        success=True,
                        recompiled_modules=[module_name],
                        updated_modules=[module_name],
                        affected_definitions=affected_definitions,
                        state_preserved=True
                    )
                else:
                    self._restore_module_state(module_name)
                    return HotReloadResult(
                        success=False,
                        recompiled_modules=[],
                        updated_modules=[],
                        errors=[f"Failed to create spec for '{result.pyd_path}'"],
                        state_preserved=True
                    )
            except Exception as e:
                self._restore_module_state(module_name)
                return HotReloadResult(
                    success=False,
                    recompiled_modules=[],
                    updated_modules=[],
                    errors=[f"Failed to reload module '{module_name}': {e}"],
                    state_preserved=True
                )
        
        finally:
            # 清理临时目录（忽略Windows文件锁定错误）
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass
    
    def _find_affected_modules(self, changed_module: str) -> Set[str]:
        """查找所有受变更影响的模块（包括传递依赖）"""
        affected = {changed_module}
        visited = set()
        queue = [changed_module]
        
        while queue:
            current = queue.pop(0)
            
            if current in visited:
                continue
            
            visited.add(current)
            
            # 获取直接依赖于当前模块的模块
            dependents = self._module_dependencies.get(current, set())
            
            for dependent in dependents:
                if dependent not in affected:
                    affected.add(dependent)
                    queue.append(dependent)
        
        return affected
    
    def _analyze_module_dependencies(self, source_path: str, module_name: str) -> None:
        """分析模块的依赖关系"""
        from cypyc.parser.lexer import Lexer
        from cypyc.parser.parser import Parser
        
        try:
            with open(source_path, 'r', encoding='utf-8') as f:
                source_code = f.read()
            
            lexer = Lexer(source_code)
            ast = Parser(lexer.tokenize()).parse()
            
            # 使用增量编译器构建依赖图
            if self._incremental_compiler:
                self._incremental_compiler.analyze_changes(source_path, ast)
                
                # 获取定义级别的依赖图
                dep_graph = self._incremental_compiler.get_dependency_graph()
                
                # 记录模块级别的依赖关系（简化版：基于导入语句）
                if hasattr(ast, 'body'):
                    for stmt in ast.body:
                        if hasattr(stmt, 'kind') and stmt.kind == 'Import':
                            imported_name = getattr(stmt, 'module', '')
                            if imported_name in self._module_source_map:
                                # 添加反向依赖：被导入的模块 -> 当前模块
                                if imported_name not in self._module_dependencies:
                                    self._module_dependencies[imported_name] = set()
                                self._module_dependencies[imported_name].add(module_name)
        except Exception:
            pass  # 解析失败不影响热重载
    
    def _handle_file_changes(self, events: List[FileChangeEvent]) -> None:
        """处理文件变更事件"""
        results = []
        
        for event in events:
            if event.event_type in ('modified', 'created'):
                module_name = self._get_module_name_from_path(event.file_path)
                
                # 分析模块依赖
                self._analyze_module_dependencies(event.file_path, module_name)
                
                # 查找所有受影响的模块
                affected_modules = self._find_affected_modules(module_name)
                
                print(f"[HotReload] File changed: {event.file_path}")
                print(f"[HotReload] Affected modules: {affected_modules}")
                
                # 按依赖顺序重新编译模块（拓扑排序）
                for affected_module in affected_modules:
                    if affected_module in self._module_source_map:
                        source_path = self._module_source_map[affected_module]
                        result = self._compile_and_reload_module(source_path)
                        results.append(result)
                        
                        if result.success:
                            print(f"[HotReload] Successfully reloaded: {affected_module}")
                        else:
                            print(f"[HotReload] Failed to reload {affected_module}:")
                            for error in result.errors:
                                print(f"  - {error}")
                    else:
                        # 如果模块不在跟踪列表中，直接编译
                        result = self._compile_and_reload_module(event.file_path)
                        results.append(result)
                        
                        if result.success:
                            print(f"[HotReload] Successfully reloaded: {event.file_path}")
                        else:
                            print(f"[HotReload] Failed to reload {event.file_path}:")
                            for error in result.errors:
                                print(f"  - {error}")
            elif event.event_type == 'deleted':
                # 文件删除，从状态缓存中移除
                module_name = self._get_module_name_from_path(event.file_path)
                if module_name in self._module_state:
                    del self._module_state[module_name]
                if module_name in self._module_source_map:
                    del self._module_source_map[module_name]
                if module_name in self._module_dependencies:
                    del self._module_dependencies[module_name]
                if module_name in self._proxy_modules:
                    del self._proxy_modules[module_name]
                print(f"[HotReload] Removed module: {event.file_path}")
        
        # 调用回调函数
        if self._on_reload:
            try:
                # 合并结果
                merged_result = HotReloadResult(
                    success=all(r.success for r in results),
                    recompiled_modules=[m for r in results for m in r.recompiled_modules],
                    updated_modules=[m for r in results for m in r.updated_modules],
                    affected_definitions=set.union(*[r.affected_definitions for r in results]),
                    errors=[e for r in results for e in r.errors],
                    state_preserved=all(r.state_preserved for r in results)
                )
                self._on_reload(merged_result)
            except Exception as e:
                print(f"[HotReload] Callback error: {e}")
    
    def start(self, watch_dirs: List[str], on_reload: Optional[Callable[[HotReloadResult], None]] = None):
        """
        启动热重载引擎
        
        参数:
            watch_dirs: 要监控的目录列表
            on_reload: 热重载完成后的回调函数
        """
        self._on_reload = on_reload
        
        # 创建文件监控器
        self._monitor = CypyFileMonitor(
            watch_dirs=watch_dirs,
            callback=self._handle_file_changes,
            debounce_delay=0.5
        )
        
        # 启动监控器
        self._monitor.start()
        
        print(f"[HotReload] Engine started, monitoring {len(watch_dirs)} directories")
    
    def stop(self):
        """停止热重载引擎"""
        if self._monitor:
            self._monitor.stop()
            self._monitor = None
        print("[HotReload] Engine stopped")
    
    def reload_module(self, module_name: str) -> HotReloadResult:
        """
        手动触发模块重载
        
        参数:
            module_name: 模块名称
            
        返回:
            HotReloadResult: 重载结果
        """
        if module_name not in self._module_source_map:
            return HotReloadResult(
                success=False,
                recompiled_modules=[],
                updated_modules=[],
                errors=[f"Module '{module_name}' not tracked by hot reload"]
            )
        
        source_path = self._module_source_map[module_name]
        return self._compile_and_reload_module(source_path)
    
    def get_tracked_modules(self) -> List[str]:
        """获取当前跟踪的模块列表"""
        return list(self._module_source_map.keys())
    
    def get_module_state(self, module_name: str) -> Optional[Dict[str, Any]]:
        """获取指定模块保存的状态"""
        return self._module_state.get(module_name)
    
    def get_module_dependencies(self, module_name: str) -> Set[str]:
        """获取指定模块的依赖模块列表"""
        return self._module_dependencies.get(module_name, set())
    
    def is_proxy_module(self, module_name: str) -> bool:
        """检查模块是否使用代理模式"""
        return module_name in self._proxy_modules
    
    def clear_state(self):
        """清空所有保存的模块状态"""
        self._module_state.clear()
        self._module_source_map.clear()
        self._module_dependencies.clear()
        self._proxy_modules.clear()
    
    def get_dependency_graph(self) -> DependencyGraph:
        """获取依赖图"""
        if self._incremental_compiler:
            return self._incremental_compiler.get_dependency_graph()
        return DependencyGraph()