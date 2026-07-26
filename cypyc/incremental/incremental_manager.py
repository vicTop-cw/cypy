"""增量编译管理器 - 管理增量编译决策"""

import os
import json
import hashlib
import time
from typing import Dict, Set, Optional, Any, Tuple, List
from dataclasses import dataclass
from cypyc.parser.parser import ASTNode
from cypyc.analyzer.scope_analyzer import Scope
from .ast_differ import ASTDiffer
from .dependency_graph import DependencyGraph


@dataclass
class CompilationCacheEntry:
    """编译缓存条目"""
    ast: Optional[ASTNode] = None
    scope_table: Optional[Scope] = None
    cython_code: Optional[str] = None
    timestamp: float = 0.0
    definitions_hash: str = ""


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


class IncrementalCompiler:
    """增量编译管理器"""
    
    def __init__(self, cache_dir: str = None):
        """初始化增量编译器"""
        self._cache_dir = cache_dir or self._get_default_cache_dir()
        self._compilation_cache: Dict[str, CompilationCacheEntry] = {}
        self._ast_differ = ASTDiffer()
        self._dependency_graph = DependencyGraph()
        self._file_cache_index: Dict[str, str] = {}  # file_path -> cache_key
        
        # 确保缓存目录存在
        os.makedirs(self._cache_dir, exist_ok=True)
    
    def _get_default_cache_dir(self) -> str:
        """获取默认缓存目录"""
        return os.path.join(os.path.expanduser("~"), ".cypy", "incremental_cache")
    
    def _compute_file_key(self, source_path: str) -> str:
        """计算文件的唯一标识"""
        return hashlib.sha256(os.path.abspath(source_path).encode()).hexdigest()[:16]
    
    def _compute_definitions_key(self, ast: ASTNode) -> str:
        """计算AST中所有定义的哈希值"""
        from cypyc.parser.parser import FuncDef, StructDef, EnumDef, TypeAlias, ExceptionDef, TraitDef
        
        content = []
        if hasattr(ast, 'body'):
            for stmt in ast.body:
                if isinstance(stmt, (FuncDef, StructDef, EnumDef, TypeAlias, ExceptionDef, TraitDef)):
                    content.append(f"{stmt.kind}:{stmt.name}")
        
        return hashlib.md5('|'.join(sorted(content)).encode()).hexdigest()
    
    def _load_cache(self, source_path: str) -> Optional[CompilationCacheEntry]:
        """加载文件的编译缓存"""
        file_key = self._compute_file_key(source_path)
        cache_path = os.path.join(self._cache_dir, f"{file_key}.json")
        
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                
                # 缓存过期检查（7天）
                if time.time() - cache_data.get('timestamp', 0) > 7 * 24 * 60 * 60:
                    return None
                
                return CompilationCacheEntry(
                    timestamp=cache_data.get('timestamp', 0),
                    definitions_hash=cache_data.get('definitions_hash', ""),
                )
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
        }
        
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2)
    
    def analyze_changes(self, source_path: str, new_ast: ASTNode) -> IncrementalResult:
        """分析源代码变更，返回增量编译结果"""
        # 加载旧缓存
        old_cache = self._load_cache(source_path)
        
        # 计算新的定义哈希
        new_definitions_hash = self._compute_definitions_key(new_ast)
        
        # 如果缓存中没有旧数据或定义哈希相同，直接返回不需要重新编译
        if old_cache and old_cache.definitions_hash == new_definitions_hash:
            return IncrementalResult(
                need_recompile=False,
                affected_definitions=set(),
                reused_definitions=self._dependency_graph.get_all_definitions(),
                changed_definitions=set(),
                added_definitions=set(),
                removed_definitions=set(),
                cache_hit=True
            )
        
        # 构建新的依赖图
        self._dependency_graph.build_from_ast(new_ast)
        
        # 如果没有旧AST，所有定义都是新增的
        if not old_cache:
            all_defs = self._dependency_graph.get_all_definitions()
            return IncrementalResult(
                need_recompile=True,
                affected_definitions=all_defs,
                reused_definitions=set(),
                changed_definitions=set(),
                added_definitions=all_defs,
                removed_definitions=set(),
                cache_hit=False
            )
        
        # 使用AST差异比较器分析变更
        # 这里需要获取旧AST进行比较，当前简化版本使用定义哈希变化来判断
        # 在实际应用中，可以从缓存中加载旧AST进行更精确的比较
        
        # 简化版本：假设定义哈希变化意味着所有定义都可能受影响
        all_defs = self._dependency_graph.get_all_definitions()
        
        return IncrementalResult(
            need_recompile=True,
            affected_definitions=all_defs,
            reused_definitions=set(),
            changed_definitions=all_defs,
            added_definitions=all_defs,
            removed_definitions=set(),
            cache_hit=False
        )
    
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
    
    def update_cache(self, source_path: str, ast: ASTNode, cython_code: str = "") -> None:
        """更新编译缓存"""
        entry = CompilationCacheEntry(
            ast=ast,
            cython_code=cython_code,
            timestamp=time.time(),
            definitions_hash=self._compute_definitions_key(ast),
        )
        
        # 保存到文件缓存
        self._save_cache(source_path, entry)
        
        # 保存到内存缓存
        file_key = self._compute_file_key(source_path)
        self._compilation_cache[file_key] = entry
        self._file_cache_index[source_path] = file_key
    
    def invalidate_cache(self, source_path: str) -> None:
        """使文件的缓存失效"""
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