"""
循环依赖检测模块 - 借鉴 Julia 的 DFS 着色算法

在 Cypy 中，trait 和 impl 之间可能存在循环依赖：
- A trait 需要 B trait 的实现
- B trait 需要 A trait 的实现

这种循环依赖会导致编译时无限递归或无法确定的类型解析。

本模块使用经典的 DFS 着色算法检测循环依赖：
- WHITE: 未访问
- GRAY: 正在访问（当前路径中）
- BLACK: 已完成访问

当在 DFS 过程中遇到 GRAY 节点时，说明存在循环。
"""
from typing import Dict, List, Set, Tuple, Any
from ..parser.parser import ASTNode, TraitDef, ImplStmt


class CycleDetector:
    """循环依赖检测器"""
    
    WHITE = 0  # 未访问
    GRAY = 1   # 正在访问
    BLACK = 2  # 已完成访问
    
    def __init__(self):
        self._graph: Dict[str, Set[str]] = {}  # 依赖图
        self._node_types: Dict[str, str] = {}  # 节点类型: trait 或 impl
        self._color: Dict[str, int] = {}       # 节点颜色状态
        self._cycle_path: List[str] = []       # 当前循环路径
    
    def analyze(self, ast: ASTNode) -> Tuple[bool, List[str]]:
        """分析 AST，检测循环依赖
        
        返回: (是否存在循环, 循环路径列表)
        """
        # 构建依赖图
        self._build_graph(ast)
        
        # 初始化颜色
        self._color = {node: CycleDetector.WHITE for node in self._graph}
        
        # 对每个节点进行 DFS
        for node in self._graph:
            if self._color[node] == CycleDetector.WHITE:
                if self._dfs(node):
                    return True, self._cycle_path
        
        return False, []
    
    def _build_graph(self, ast: ASTNode):
        """从 AST 构建依赖图"""
        if ast.kind == "Module":
            for stmt in ast.body:
                self._process_statement(stmt)
    
    def _process_statement(self, stmt: ASTNode):
        """处理单个语句，提取依赖关系"""
        if stmt.kind == "TraitDef":
            self._process_trait(stmt)
        elif stmt.kind == "ImplStmt":
            self._process_impl(stmt)
        elif stmt.kind == "StructDef":
            self._process_struct(stmt)
        elif stmt.kind == "EnumDef":
            self._process_enum(stmt)
    
    def _process_trait(self, trait: TraitDef):
        """处理 trait 定义，提取依赖"""
        trait_name = trait.name
        self._ensure_node(trait_name, "trait")
        
        # 检查 trait 的方法参数和返回类型中的类型依赖
        for method in trait.methods:
            if method.kind == "FuncDef":
                # 检查参数类型
                for param in method.params:
                    if param.type_annotation:
                        type_name = self._extract_type_name(param.type_annotation)
                        if type_name:
                            self._add_edge(trait_name, type_name)
                
                # 检查返回类型
                if method.return_type:
                    type_name = self._extract_type_name(method.return_type)
                    if type_name:
                        self._add_edge(trait_name, type_name)
    
    def _process_impl(self, impl: ImplStmt):
        """处理 impl 定义，提取依赖"""
        trait_name = impl.trait_name
        for_type_name = self._extract_type_name(impl.for_type)
        
        # impl 节点标识为 "impl:{trait} for {type}"
        impl_key = f"impl:{trait_name} for {for_type_name}"
        self._ensure_node(impl_key, "impl")
        
        # impl 依赖于 trait 和实现类型
        self._add_edge(impl_key, trait_name)
        self._add_edge(impl_key, for_type_name)
        
        # 检查方法中的类型依赖
        for method in impl.methods:
            if method.kind == "FuncDef":
                for param in method.params:
                    if param.type_annotation:
                        type_name = self._extract_type_name(param.type_annotation)
                        if type_name:
                            self._add_edge(impl_key, type_name)
                if method.return_type:
                    type_name = self._extract_type_name(method.return_type)
                    if type_name:
                        self._add_edge(impl_key, type_name)
    
    def _process_struct(self, struct):
        """处理 struct 定义，提取依赖"""
        struct_name = struct.name
        self._ensure_node(struct_name, "struct")
        
        for field in struct.fields:
            if field.type_annotation:
                type_name = self._extract_type_name(field.type_annotation)
                if type_name:
                    self._add_edge(struct_name, type_name)
    
    def _process_enum(self, enum):
        """处理 enum 定义，提取依赖"""
        enum_name = enum.name
        self._ensure_node(enum_name, "enum")
    
    def _ensure_node(self, name: str, node_type: str):
        """确保节点存在于图中"""
        if name not in self._graph:
            self._graph[name] = set()
        if name not in self._node_types:
            self._node_types[name] = node_type
    
    def _add_edge(self, from_node: str, to_node: str):
        """添加依赖边"""
        self._ensure_node(from_node, "unknown")
        self._ensure_node(to_node, "unknown")
        self._graph[from_node].add(to_node)
    
    def _extract_type_name(self, type_node: ASTNode) -> str:
        """从类型节点中提取类型名称"""
        if type_node is None:
            return ""
        
        if type_node.kind == "Name":
            return type_node.id
        elif type_node.kind == "GenericType":
            return type_node.name
        elif type_node.kind == "PointerType":
            return self._extract_type_name(type_node.base_type)
        elif type_node.kind == "Subscript":
            return self._extract_type_name(type_node.value)
        else:
            return ""
    
    def _dfs(self, node: str) -> bool:
        """深度优先搜索检测循环"""
        self._color[node] = CycleDetector.GRAY
        self._cycle_path.append(node)
        
        for neighbor in self._graph.get(node, []):
            if neighbor not in self._color:
                self._color[neighbor] = CycleDetector.WHITE
            
            if self._color[neighbor] == CycleDetector.WHITE:
                if self._dfs(neighbor):
                    return True
            elif self._color[neighbor] == CycleDetector.GRAY:
                # 找到循环！构造完整的循环路径
                idx = self._cycle_path.index(neighbor)
                self._cycle_path = self._cycle_path[idx:]
                return True
        
        self._color[node] = CycleDetector.BLACK
        if node in self._cycle_path:
            self._cycle_path.remove(node)
        
        return False
    
    def get_dependency_graph(self) -> Dict[str, Set[str]]:
        """获取依赖图"""
        return self._graph
    
    def format_cycle_error(self, cycle_path: List[str]) -> str:
        """格式化循环依赖错误信息"""
        if not cycle_path:
            return ""
        
        lines = ["循环依赖检测错误：发现以下循环依赖链："]
        for i, node in enumerate(cycle_path):
            node_type = self._node_types.get(node, "unknown")
            prefix = "├─" if i < len(cycle_path) - 1 else "└─"
            lines.append(f"{prefix} [{node_type}] {node}")
        
        lines.append("")
        lines.append("建议修复方案：")
        lines.append("1. 移除循环中的一个或多个依赖")
        lines.append("2. 将共同依赖提取为独立的 trait")
        lines.append("3. 使用 trait 继承代替直接实现依赖")
        
        return "\n".join(lines)
