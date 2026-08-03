"""类型注册表 - 跨模块类型推断的核心数据结构

集中式类型注册表，在项目级编译的第一阶段收集所有模块的导出类型，
供第二阶段类型检查使用，实现模块间类型的正确传递和解析。
"""

from typing import Dict, List, Optional, Set, Any, Tuple
from dataclasses import dataclass, field
from collections import OrderedDict
import os


@dataclass
class TypeExport:
    """单个类型导出信息"""
    name: str
    kind: str  # 'struct', 'class', 'function', 'trait', 'enum', 'type_alias', 'exception', 'comptime_func'
    module: str
    # 可选的详细信息
    return_type: Optional[str] = None
    param_types: Optional[List[str]] = None
    field_types: Optional[Dict[str, str]] = None
    generic_params: Optional[List[str]] = None
    is_exported: bool = True


@dataclass
class ModuleTypeInfo:
    """模块的完整类型导出信息"""
    module_name: str
    file_path: str
    exports: Dict[str, TypeExport] = field(default_factory=dict)
    imports: Dict[str, List[str]] = field(default_factory=dict)  # module -> [names]
    imported_modules: List[str] = field(default_factory=list)
    raw_symbols: Dict[str, Any] = field(default_factory=dict)  # 原始AST节点引用


class TypeRegistry:
    """集中式类型注册表

    负责：
    1. 收集所有模块的导出类型
    2. 提供跨模块类型查询
    3. 管理模块间的可见性和别名
    4. 支持增量更新单个模块的类型信息
    """

    def __init__(self):
        # 模块名 -> 模块类型信息
        self._modules: Dict[str, ModuleTypeInfo] = OrderedDict()
        # 类型名 -> (模块名, 导出信息) 的全局索引
        self._global_type_index: Dict[str, List[Tuple[str, TypeExport]]] = {}
        # 模块别名映射 (from module import name as alias)
        self._aliases: Dict[str, Dict[str, str]] = {}  # module -> {alias: original_name}
        # 模块可见性：哪些模块导出了哪些类型
        self._visibility: Dict[str, Set[str]] = {}  # module -> set(exported_type_names)

    def register_module(self, module_name: str, file_path: str) -> ModuleTypeInfo:
        """注册一个新模块，返回其 ModuleTypeInfo"""
        if module_name not in self._modules:
            self._modules[module_name] = ModuleTypeInfo(
                module_name=module_name,
                file_path=file_path,
            )
        return self._modules[module_name]

    def add_export(self, module_name: str, export: TypeExport) -> None:
        """添加一个类型导出到指定模块"""
        if module_name not in self._modules:
            self.register_module(module_name, "")

        mod_info = self._modules[module_name]
        mod_info.exports[export.name] = export

        # 更新全局索引
        if export.name not in self._global_type_index:
            self._global_type_index[export.name] = []
        self._global_type_index[export.name].append((module_name, export))

        # 更新可见性
        if module_name not in self._visibility:
            self._visibility[module_name] = set()
        if export.is_exported:
            self._visibility[module_name].add(export.name)

    def add_import(self, importer_module: str, target_module: str, names: List[str]) -> None:
        """记录模块间的导入关系"""
        if importer_module not in self._modules:
            self.register_module(importer_module, "")

        mod_info = self._modules[importer_module]
        if target_module not in mod_info.imports:
            mod_info.imports[target_module] = []
        mod_info.imports[target_module].extend(names)

        if target_module not in mod_info.imported_modules:
            mod_info.imported_modules.append(target_module)

    def add_alias(self, module_name: str, alias: str, original_name: str) -> None:
        """添加导入别名"""
        if module_name not in self._aliases:
            self._aliases[module_name] = {}
        self._aliases[module_name][alias] = original_name

    def resolve_type(self, type_name: str, current_module: str,
                     search_scope: Optional[List[str]] = None) -> Optional[TypeExport]:
        """解析类型引用

        按以下优先级搜索：
        1. 当前模块的导出
        2. 当前模块导入的模块中，按导入顺序
        3. 全局类型索引（最后匹配）
        """
        # 1. 当前模块自身导出
        if current_module in self._modules:
            mod_info = self._modules[current_module]
            if type_name in mod_info.exports:
                return mod_info.exports[type_name]

            # 检查别名
            if current_module in self._aliases:
                aliases = self._aliases[current_module]
                if type_name in aliases:
                    original = aliases[type_name]
                    if original in mod_info.exports:
                        return mod_info.exports[original]

        # 2. 从导入的模块中查找
        if current_module in self._modules:
            mod_info = self._modules[current_module]
            for imported_mod in mod_info.imported_modules:
                if imported_mod in self._modules:
                    imported_exports = self._modules[imported_mod].exports
                    # 检查是否显式导入了该名称
                    if imported_mod in mod_info.imports:
                        imported_names = mod_info.imports[imported_mod]
                        if type_name in imported_names and type_name in imported_exports:
                            return imported_exports[type_name]
                    # 检查别名
                    if imported_mod in self._aliases:
                        if type_name in self._aliases[imported_mod]:
                            original = self._aliases[imported_mod][type_name]
                            if original in imported_exports:
                                return imported_exports[original]

        # 3. 全局索引（最后匹配，可能不精确）
        if type_name in self._global_type_index:
            entries = self._global_type_index[type_name]
            if entries:
                # 优先返回 search_scope 中的模块
                if search_scope:
                    for module_name, export in entries:
                        if module_name in search_scope:
                            return export
                # 否则返回第一个
                return entries[0][1]

        return None

    def resolve_type_in_module(self, type_name: str, module_name: str) -> Optional[TypeExport]:
        """在指定模块中解析类型"""
        if module_name in self._modules:
            mod_info = self._modules[module_name]
            if type_name in mod_info.exports:
                return mod_info.exports[type_name]
        return None

    def get_module_exports(self, module_name: str) -> Dict[str, TypeExport]:
        """获取模块的所有导出"""
        if module_name in self._modules:
            return self._modules[module_name].exports
        return {}

    def get_module_info(self, module_name: str) -> Optional[ModuleTypeInfo]:
        """获取模块的完整类型信息"""
        return self._modules.get(module_name)

    def get_all_modules(self) -> List[str]:
        """获取所有已注册的模块名"""
        return list(self._modules.keys())

    def get_imported_modules(self, module_name: str) -> List[str]:
        """获取模块导入的所有模块"""
        if module_name in self._modules:
            return self._modules[module_name].imported_modules
        return []

    def get_affected_types(self, changed_module: str) -> Set[str]:
        """获取因某个模块变更而受影响的所有类型"""
        affected = set()

        # 获取变更模块的所有导出
        if changed_module in self._modules:
            mod_info = self._modules[changed_module]
            affected.update(mod_info.exports.keys())

        # 查找依赖于该模块的其他模块
        for mod_name, mod_info in self._modules.items():
            if changed_module in mod_info.imported_modules:
                # 该模块导入了变更模块，标记其使用的类型为受影响
                if changed_module in mod_info.imports:
                    affected.update(mod_info.imports[changed_module])

        return affected

    def invalidate_module(self, module_name: str) -> None:
        """使模块的类型信息失效（用于增量更新）"""
        if module_name in self._modules:
            mod_info = self._modules[module_name]
            # 从全局索引中移除该模块的导出
            for type_name, export in mod_info.exports.items():
                if type_name in self._global_type_index:
                    self._global_type_index[type_name] = [
                        (m, e) for m, e in self._global_type_index[type_name]
                        if m != module_name
                    ]
                    if not self._global_type_index[type_name]:
                        del self._global_type_index[type_name]

            # 清空模块导出
            mod_info.exports.clear()
            mod_info.imports.clear()
            mod_info.imported_modules.clear()

    def clear_module(self, module_name: str) -> None:
        """完全清除模块的所有信息"""
        self.invalidate_module(module_name)
        if module_name in self._modules:
            del self._modules[module_name]
        if module_name in self._aliases:
            del self._aliases[module_name]
        if module_name in self._visibility:
            del self._visibility[module_name]

    def clear(self) -> None:
        """清空整个注册表"""
        self._modules.clear()
        self._global_type_index.clear()
        self._aliases.clear()
        self._visibility.clear()

    def get_stats(self) -> Dict[str, int]:
        """获取注册表统计信息"""
        total_exports = sum(
            len(mod.exports) for mod in self._modules.values()
        )
        total_types = len(self._global_type_index)
        return {
            'modules': len(self._modules),
            'total_exports': total_exports,
            'unique_type_names': total_types,
        }

    def __repr__(self) -> str:
        lines = [f"TypeRegistry ({len(self._modules)} modules):"]
        for mod_name, mod_info in self._modules.items():
            exports = list(mod_info.exports.keys())
            imports = mod_info.imported_modules
            lines.append(f"  {mod_name}: exports={exports}, imports={imports}")
        return "\n".join(lines)
