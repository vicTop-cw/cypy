"""模块依赖图 - 追踪项目中模块间的导入依赖关系

支持：
1. 从 AST 构建模块依赖图
2. 拓扑排序确定编译顺序
3. 传递依赖分析
4. 循环依赖检测
"""

from typing import Dict, Set, List, Optional, Tuple
from collections import deque
from dataclasses import dataclass


@dataclass
class ModuleNode:
    """模块节点信息"""
    name: str
    file_path: str
    dependencies: Set[str] = None  # 该模块依赖的其他模块
    dependents: Set[str] = None    # 依赖该模块的其他模块

    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = set()
        if self.dependents is None:
            self.dependents = set()


class ModuleDependencyGraph:
    """模块依赖图

    用于：
    - 分析项目中模块间的导入关系
    - 确定编译顺序（拓扑排序）
    - 检测循环依赖
    - 计算增量编译时的受影响模块集合
    """

    def __init__(self):
        self._nodes: Dict[str, ModuleNode] = {}
        self._file_to_module: Dict[str, str] = {}  # file_path -> module_name
        self._cycles: List[List[str]] = []  # 检测到的循环依赖

    def add_module(self, module_name: str, file_path: str) -> ModuleNode:
        """添加模块节点"""
        if module_name not in self._nodes:
            self._nodes[module_name] = ModuleNode(
                name=module_name,
                file_path=file_path,
            )
        self._file_to_module[file_path] = module_name
        return self._nodes[module_name]

    def add_dependency(self, from_module: str, to_module: str) -> None:
        """添加模块间的依赖关系 (from_module 依赖 to_module)"""
        if from_module not in self._nodes:
            self.add_module(from_module, "")
        if to_module not in self._nodes:
            self.add_module(to_module, "")

        self._nodes[from_module].dependencies.add(to_module)
        self._nodes[to_module].dependents.add(from_module)

    def get_module(self, module_name: str) -> Optional[ModuleNode]:
        """获取模块节点"""
        return self._nodes.get(module_name)

    def get_module_by_path(self, file_path: str) -> Optional[str]:
        """根据文件路径获取模块名"""
        return self._file_to_module.get(file_path)

    def get_dependencies(self, module_name: str) -> Set[str]:
        """获取模块的所有依赖"""
        if module_name in self._nodes:
            return self._nodes[module_name].dependencies
        return set()

    def get_dependents(self, module_name: str) -> Set[str]:
        """获取依赖该模块的所有模块"""
        if module_name in self._nodes:
            return self._nodes[module_name].dependents
        return set()

    def get_transitive_dependencies(self, module_name: str) -> Set[str]:
        """获取模块的传递依赖（所有间接依赖）"""
        visited = set()
        queue = deque([module_name])

        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)

            for dep in self.get_dependencies(current):
                if dep not in visited:
                    queue.append(dep)

        visited.discard(module_name)
        return visited

    def get_transitive_dependents(self, module_name: str) -> Set[str]:
        """获取传递依赖该模块的所有模块"""
        visited = set()
        queue = deque([module_name])

        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)

            for dep in self.get_dependents(current):
                if dep not in visited:
                    queue.append(dep)

        visited.discard(module_name)
        return visited

    def get_affected_modules(self, changed_modules: Set[str]) -> Set[str]:
        """获取因指定模块变更而受影响的所有模块"""
        affected = set(changed_modules)
        for mod in changed_modules:
            affected.update(self.get_transitive_dependents(mod))
        return affected

    def topological_sort(self) -> Tuple[List[str], List[List[str]]]:
        """拓扑排序，返回 (排序后的模块列表, 循环依赖列表)

        算法：Kahn's 算法
        返回：(sorted_modules, cycles)
        """
        in_degree: Dict[str, int] = {}
        for name in self._nodes:
            in_degree[name] = 0

        for name, node in self._nodes.items():
            for dep in node.dependencies:
                if dep in in_degree:
                    pass  # dep -> name 的依赖关系意味着 name 依赖 dep

        # 重新计算入度（模块的依赖数 = 入度）
        in_degree = {name: len(node.dependencies) for name, node in self._nodes.items()}

        # Kahn's 算法
        queue = deque([name for name, degree in in_degree.items() if degree == 0])
        sorted_modules = []

        while queue:
            current = queue.popleft()
            sorted_modules.append(current)

            # 对于依赖当前模块的节点（当前模块的 dependents），减少其入度
            for dependent in self._nodes[current].dependents:
                if dependent in in_degree:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)

        # 检测循环
        cycles = []
        if len(sorted_modules) != len(self._nodes):
            remaining = set(self._nodes.keys()) - set(sorted_modules)
            cycles = self._detect_cycles(remaining)

        return sorted_modules, cycles

    def _detect_cycles(self, remaining: Set[str]) -> List[List[str]]:
        """检测循环依赖"""
        cycles_found = []
        visited = set()
        rec_stack = set()

        def dfs(node: str, path: List[str]):
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for dep in self._nodes[node].dependencies:
                if dep not in remaining:
                    continue
                if dep not in visited:
                    dfs(dep, path)
                elif dep in rec_stack:
                    # 找到循环
                    cycle_start = path.index(dep)
                    cycle = path[cycle_start:] + [dep]
                    cycles_found.append(cycle)

            path.pop()
            rec_stack.discard(node)

        for node in remaining:
            if node not in visited:
                dfs(node, [])

        return cycles_found

    def get_compilation_order(self) -> List[str]:
        """获取推荐的编译顺序（拓扑排序，跳过循环中的模块）"""
        sorted_modules, cycles = self.topological_sort()
        if cycles:
            # 警告：存在循环依赖，循环内的模块可能无法正确编译
            cycle_modules = set()
            for cycle in cycles:
                cycle_modules.update(cycle)
            # 将循环依赖的模块放在最后（按名排序：`set` 的迭代序随进程字符串哈希
            # 种子变化，直接 extend 会让同一张图给出不同推荐序）
            ordered = [m for m in sorted_modules if m not in cycle_modules]
            ordered.extend(sorted(cycle_modules))
            return ordered
        return sorted_modules

    def get_all_modules(self) -> List[str]:
        """获取所有模块名"""
        return list(self._nodes.keys())

    def get_module_count(self) -> int:
        """获取模块数量"""
        return len(self._nodes)

    def is_empty(self) -> bool:
        """检查是否为空图"""
        return len(self._nodes) == 0

    def clear(self) -> None:
        """清空依赖图"""
        self._nodes.clear()
        self._file_to_module.clear()
        self._cycles.clear()

    def remove_module(self, module_name: str) -> None:
        """移除模块及其所有连接"""
        if module_name in self._nodes:
            node = self._nodes[module_name]
            # 从其他模块的依赖列表中移除
            for dep in node.dependencies:
                if dep in self._nodes:
                    self._nodes[dep].dependents.discard(module_name)
            for dependent in node.dependents:
                if dependent in self._nodes:
                    self._nodes[dependent].dependencies.discard(module_name)
            # 从文件映射中移除
            self._file_to_module = {
                k: v for k, v in self._file_to_module.items()
                if v != module_name
            }
            del self._nodes[module_name]

    def get_cycles(self) -> List[List[str]]:
        """获取检测到的循环依赖"""
        if not self._cycles:
            _, self._cycles = self.topological_sort()
        return self._cycles

    def has_cycle(self) -> bool:
        """检查是否存在循环依赖"""
        _, cycles = self.topological_sort()
        return len(cycles) > 0

    def __repr__(self) -> str:
        lines = [f"ModuleDependencyGraph ({len(self._nodes)} modules):"]
        for name, node in sorted(self._nodes.items()):
            deps = ", ".join(sorted(node.dependencies)) or "(none)"
            lines.append(f"  {name} -> [{deps}]")
        return "\n".join(lines)
