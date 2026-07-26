"""增量编译管理器 - 管理增量编译决策"""

import os
import json
import hashlib
import time
from typing import Dict, Set, Optional, Any, Tuple, List
from dataclasses import dataclass
from collections import OrderedDict
from cypyc.parser.parser import ASTNode
from cypyc.analyzer.scope_analyzer import Scope
from .ast_differ import ASTDiffer
from .dependency_graph import DependencyGraph

# 内存缓存配置
MAX_CACHE_ENTRIES = 100  # 最大内存缓存条目数
MAX_CACHE_AGE_HOURS = 24  # 最大缓存有效期（小时）


@dataclass
class CompilationCacheEntry:
    """编译缓存条目"""
    ast: Optional[ASTNode] = None
    scope_table: Optional[Scope] = None
    cython_code: Optional[str] = None
    timestamp: float = 0.0
    definitions_hash: str = ""
    file_hash: str = ""
    file_mtime: float = 0.0
    pyd_path: Optional[str] = None
    imported_modules: List[str] = None
    
    def __post_init__(self):
        if self.imported_modules is None:
            self.imported_modules = []


@dataclass
class IncrementalResult:
    """增量编译结果"""
    need_recompile: bool
    affected_definitions: Set[str]
    reused_definitions: Set[str]
    changed_definitions: Set[str]
    added_definitions: Set[str]
    removed_definitions: Set[str]
    cache_hit: bool = False
    cache_reason: str = ""


class IncrementalCompiler:
    """增量编译管理器"""
    
    def __init__(self, cache_dir: str = None):
        """初始化增量编译器"""
        self._cache_dir = cache_dir or self._get_default_cache_dir()
        # 使用OrderedDict实现LRU缓存
        self._compilation_cache: OrderedDict[str, CompilationCacheEntry] = OrderedDict()
        self._ast_differ = ASTDiffer()
        self._dependency_graph = DependencyGraph()
        self._file_cache_index: Dict[str, str] = {}  # file_path -> cache_key
        self._cross_module_dependencies: Dict[str, Set[str]] = {}  # file -> set(dependent_files)
        
        # 确保缓存目录存在
        os.makedirs(self._cache_dir, exist_ok=True)
    
    def _get_default_cache_dir(self) -> str:
        """获取默认缓存目录"""
        return os.path.join(os.path.expanduser("~"), ".cypy", "incremental_cache")
    
    def _trim_cache(self) -> None:
        """修剪内存缓存，保持在最大条目数以内"""
        # 移除过期的缓存
        now = time.time()
        expired_keys = []
        for key, entry in self._compilation_cache.items():
            if now - entry.timestamp > MAX_CACHE_AGE_HOURS * 3600:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._compilation_cache[key]
        
        # 移除超出最大条目数的旧缓存（LRU策略）
        while len(self._compilation_cache) > MAX_CACHE_ENTRIES:
            self._compilation_cache.popitem(last=False)
    
    def _touch_cache_entry(self, file_key: str) -> None:
        """将缓存条目标记为最近使用（LRU更新）"""
        if file_key in self._compilation_cache:
            entry = self._compilation_cache.pop(file_key)
            self._compilation_cache[file_key] = entry
    
    def _compute_file_key(self, source_path: str) -> str:
        """计算文件的唯一标识"""
        return hashlib.sha256(os.path.abspath(source_path).encode()).hexdigest()[:16]
    
    def _compute_file_hash(self, source_path: str) -> str:
        """计算文件内容的SHA256哈希"""
        with open(source_path, "rb") as f:
            content = f.read()
        return hashlib.sha256(content).hexdigest()
    
    def _compute_definitions_key(self, ast: ASTNode) -> str:
        """计算AST中所有定义的哈希值"""
        from cypyc.parser.parser import FuncDef, StructDef, EnumDef, TypeAlias, ExceptionDef, TraitDef
        
        content = []
        if hasattr(ast, 'body'):
            for stmt in ast.body:
                if isinstance(stmt, (FuncDef, StructDef, EnumDef, TypeAlias, ExceptionDef, TraitDef)):
                    content.append(f"{stmt.kind}:{stmt.name}")
        
        return hashlib.md5('|'.join(sorted(content)).encode()).hexdigest()
    
    def _extract_imported_modules(self, ast: ASTNode) -> List[str]:
        """从AST中提取导入的模块名称"""
        from cypyc.parser.parser import ImportStmt, ImportFromStmt
        
        imports = []
        if hasattr(ast, 'body'):
            for stmt in ast.body:
                if isinstance(stmt, ImportStmt):
                    for alias in stmt.names:
                        imports.append(alias.name)
                elif isinstance(stmt, ImportFromStmt):
                    if stmt.module:
                        imports.append(stmt.module)
        
        return imports
    
    def _load_cache(self, source_path: str) -> Optional[CompilationCacheEntry]:
        """加载文件的编译缓存（优先内存缓存）"""
        file_key = self._compute_file_key(source_path)
        
        # 优先检查内存缓存
        if file_key in self._compilation_cache:
            entry = self._compilation_cache[file_key]
            
            # 检查内存缓存是否过期
            if time.time() - entry.timestamp <= MAX_CACHE_AGE_HOURS * 3600:
                # 更新LRU顺序
                self._touch_cache_entry(file_key)
                return entry
            
            # 内存缓存过期，删除
            del self._compilation_cache[file_key]
            if source_path in self._file_cache_index:
                del self._file_cache_index[source_path]
        
        # 检查文件缓存
        cache_path = os.path.join(self._cache_dir, f"{file_key}.json")
        
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                
                # 缓存过期检查
                if time.time() - cache_data.get('timestamp', 0) > MAX_CACHE_AGE_HOURS * 3600:
                    return None
                
                entry = CompilationCacheEntry(
                    timestamp=cache_data.get('timestamp', 0),
                    definitions_hash=cache_data.get('definitions_hash', ""),
                    file_hash=cache_data.get('file_hash', ""),
                    file_mtime=cache_data.get('file_mtime', 0),
                    pyd_path=cache_data.get('pyd_path'),
                    imported_modules=cache_data.get('imported_modules', []),
                )
                
                # 加载到内存缓存
                self._compilation_cache[file_key] = entry
                self._file_cache_index[source_path] = file_key
                self._touch_cache_entry(file_key)
                
                return entry
            except (json.JSONDecodeError, IOError):
                return None
        
        return None
    
    def _save_cache(self, source_path: str, entry: CompilationCacheEntry) -> None:
        """保存文件的编译缓存"""
        file_key = self._compute_file_key(source_path)
        cache_path = os.path.join(self._cache_dir, f"{file_key}.json")
        
        cache_data = {
            'timestamp': entry.timestamp,
            'definitions_hash': entry.definitions_hash,
            'file_hash': entry.file_hash,
            'file_mtime': entry.file_mtime,
            'pyd_path': entry.pyd_path,
            'imported_modules': entry.imported_modules,
        }
        
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2)
    
    def analyze_changes(self, source_path: str, new_ast: ASTNode) -> IncrementalResult:
        """分析源代码变更，返回增量编译结果"""
        # 加载旧缓存
        old_cache = self._load_cache(source_path)
        
        # 获取当前文件状态
        current_file_hash = self._compute_file_hash(source_path)
        current_mtime = os.path.getmtime(source_path)
        
        # 计算新的定义哈希
        new_definitions_hash = self._compute_definitions_key(new_ast)
        
        # 检查缓存有效性（多重检查）
        if old_cache:
            # 检查文件哈希是否匹配
            if old_cache.file_hash != current_file_hash:
                reason = "文件内容哈希不匹配"
            # 检查文件修改时间是否匹配
            elif abs(old_cache.file_mtime - current_mtime) > 1e-9:
                reason = "文件修改时间变化"
            # 检查定义哈希是否匹配
            elif old_cache.definitions_hash != new_definitions_hash:
                reason = "定义哈希变化"
            # 检查.pyd文件是否存在
            elif old_cache.pyd_path and not os.path.exists(old_cache.pyd_path):
                reason = "缓存的.pyd文件不存在"
            # 检查依赖模块是否发生变化
            elif self._check_imported_modules_changed(old_cache.imported_modules):
                reason = "依赖模块发生变化"
            else:
                # 缓存完全有效
                self._dependency_graph.build_from_ast(new_ast)
                return IncrementalResult(
                    need_recompile=False,
                    affected_definitions=set(),
                    reused_definitions=self._dependency_graph.get_all_definitions(),
                    changed_definitions=set(),
                    added_definitions=set(),
                    removed_definitions=set(),
                    cache_hit=True,
                    cache_reason="缓存完全匹配"
                )
        else:
            reason = "无缓存数据"
        
        # 构建新的依赖图
        self._dependency_graph.build_from_ast(new_ast)
        
        # 如果没有旧缓存，所有定义都是新增的
        if not old_cache:
            all_defs = self._dependency_graph.get_all_definitions()
            return IncrementalResult(
                need_recompile=True,
                affected_definitions=all_defs,
                reused_definitions=set(),
                changed_definitions=set(),
                added_definitions=all_defs,
                removed_definitions=set(),
                cache_hit=False,
                cache_reason=reason
            )
        
        # 使用AST差异比较器分析变更（如果有旧AST可用）
        # 当前简化版本使用定义哈希变化来判断，但提供更详细的原因
        
        all_defs = self._dependency_graph.get_all_definitions()
        
        return IncrementalResult(
            need_recompile=True,
            affected_definitions=all_defs,
            reused_definitions=set(),
            changed_definitions=all_defs,
            added_definitions=all_defs,
            removed_definitions=set(),
            cache_hit=False,
            cache_reason=reason
        )
    
    def _check_imported_modules_changed(self, imported_modules: List[str]) -> bool:
        """检查导入的模块是否发生变化"""
        for module_name in imported_modules:
            # 尝试找到模块对应的文件
            module_file = self._find_module_file(module_name)
            if module_file and os.path.exists(module_file):
                # 检查模块的缓存是否失效
                if not self.is_cached(module_file):
                    return True
        return False
    
    def _find_module_file(self, module_name: str) -> Optional[str]:
        """尝试找到模块对应的文件"""
        import sys
        for path in sys.path:
            # 尝试不同的扩展名
            for ext in ['.cypy', '.py', '.pyx']:
                module_path = os.path.join(path, module_name.replace('.', os.sep) + ext)
                if os.path.exists(module_path):
                    return module_path
            # 尝试包
            pkg_path = os.path.join(path, module_name.replace('.', os.sep), '__init__.py')
            if os.path.exists(pkg_path):
                return pkg_path
        return None
    
    def analyze_changes_with_old_ast(self, old_ast: ASTNode, new_ast: ASTNode) -> IncrementalResult:
        """使用新旧AST进行精确的增量编译分析"""
        # 使用AST差异比较器
        has_changes = self._ast_differ.compare(old_ast, new_ast)
        
        if not has_changes:
            # 没有变化，所有定义都可以复用
            self._dependency_graph.build_from_ast(new_ast)
            all_defs = self._dependency_graph.get_all_definitions()
            
            return IncrementalResult(
                need_recompile=False,
                affected_definitions=set(),
                reused_definitions=all_defs,
                changed_definitions=set(),
                added_definitions=set(),
                removed_definitions=set(),
                cache_hit=True
            )
        
        # 构建新的依赖图
        self._dependency_graph.build_from_ast(new_ast)
        
        # 获取变化的定义
        changed_definitions = self._ast_differ.get_changed_definitions()
        added_definitions = self._ast_differ.added_definitions
        removed_definitions = self._ast_differ.removed_definitions
        
        # 获取受影响的定义（包括传递依赖）
        affected_definitions = self._dependency_graph.get_affected_definitions(changed_definitions)
        
        # 获取可以复用的定义
        all_defs = self._dependency_graph.get_all_definitions()
        reused_definitions = all_defs - affected_definitions
        
        return IncrementalResult(
            need_recompile=True,
            affected_definitions=affected_definitions,
            reused_definitions=reused_definitions,
            changed_definitions=changed_definitions,
            added_definitions=added_definitions,
            removed_definitions=removed_definitions,
            cache_hit=False
        )
    
    def update_cache(self, source_path: str, ast: ASTNode, cython_code: str = "", pyd_path: str = "") -> None:
        """更新编译缓存"""
        entry = CompilationCacheEntry(
            ast=ast,
            cython_code=cython_code,
            timestamp=time.time(),
            definitions_hash=self._compute_definitions_key(ast),
            file_hash=self._compute_file_hash(source_path),
            file_mtime=os.path.getmtime(source_path),
            pyd_path=pyd_path,
            imported_modules=self._extract_imported_modules(ast),
        )
        
        # 保存到文件缓存
        self._save_cache(source_path, entry)
        
        # 保存到内存缓存（LRU策略）
        file_key = self._compute_file_key(source_path)
        
        # 如果已存在，先删除再添加以更新LRU顺序
        if file_key in self._compilation_cache:
            del self._compilation_cache[file_key]
        
        self._compilation_cache[file_key] = entry
        self._file_cache_index[source_path] = file_key
        
        # 更新跨模块依赖
        self._update_cross_module_dependencies(source_path, entry.imported_modules)
        
        # 修剪缓存
        self._trim_cache()
    
    def _update_cross_module_dependencies(self, source_path: str, imported_modules: List[str]) -> None:
        """更新跨模块依赖关系"""
        # 清除旧的依赖记录
        if source_path in self._cross_module_dependencies:
            del self._cross_module_dependencies[source_path]
        
        # 添加新的依赖记录
        if imported_modules:
            self._cross_module_dependencies[source_path] = set()
            for module_name in imported_modules:
                module_file = self._find_module_file(module_name)
                if module_file:
                    self._cross_module_dependencies[source_path].add(module_file)
    
    def invalidate_cache(self, source_path: str, cascade: bool = True) -> None:
        """使文件的缓存失效
        
        参数：
            source_path: 源文件路径
            cascade: 是否级联失效依赖此文件的其他文件
        """
        file_key = self._compute_file_key(source_path)
        
        # 删除文件缓存
        cache_path = os.path.join(self._cache_dir, f"{file_key}.json")
        if os.path.exists(cache_path):
            os.remove(cache_path)
        
        # 删除内存缓存
        if file_key in self._compilation_cache:
            del self._compilation_cache[file_key]
        if source_path in self._file_cache_index:
            del self._file_cache_index[source_path]
        
        # 级联失效依赖此文件的其他文件
        if cascade:
            self._cascade_invalidate(source_path)
    
    def _cascade_invalidate(self, changed_file: str) -> None:
        """级联失效依赖指定文件的所有文件"""
        for source_path, dependencies in self._cross_module_dependencies.items():
            if changed_file in dependencies:
                self.invalidate_cache(source_path, cascade=False)
    
    def clear_cache(self) -> None:
        """清空所有缓存"""
        # 清空文件缓存
        if os.path.exists(self._cache_dir):
            for filename in os.listdir(self._cache_dir):
                if filename.endswith('.json'):
                    os.remove(os.path.join(self._cache_dir, filename))
        
        # 清空内存缓存
        self._compilation_cache.clear()
        self._file_cache_index.clear()
        self._dependency_graph.clear()
    
    def get_dependency_graph(self) -> DependencyGraph:
        """获取依赖图"""
        return self._dependency_graph
    
    def get_ast_differ(self) -> ASTDiffer:
        """获取AST差异比较器"""
        return self._ast_differ
    
    def is_cached(self, source_path: str) -> bool:
        """检查文件是否有有效的缓存"""
        file_key = self._compute_file_key(source_path)
        return file_key in self._compilation_cache or os.path.exists(
            os.path.join(self._cache_dir, f"{file_key}.json")
        )
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        return {
            'cache_dir': self._cache_dir,
            'cached_files': len(self._compilation_cache),
            'file_cache_count': len([f for f in os.listdir(self._cache_dir) if f.endswith('.json')]),
            'dependency_graph_size': len(self._dependency_graph.get_all_definitions()),
        }