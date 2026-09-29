"""AST 差异比较器 - 识别定义级别的变化"""

import hashlib
from typing import Any, Dict, Iterator, List, Set, Tuple
from cypyc.parser.parser import ASTNode, FuncDef, StructDef, EnumDef, TypeAlias, ExceptionDef, TraitDef

# 结构性摘要中必须忽略的属性：纯格式化（上方插入空行、缩进变化、列偏移）只移动
# line/col，不改变语义；把它们计入哈希会让"重排格式"被误判为需要重编译。
_POSITION_ATTRS = frozenset({'line', 'col'})

# 摘要中单独处理或作为节点头输出的属性
_HEADER_ATTRS = frozenset({'kind'}) | _POSITION_ATTRS

# 显式栈的指令类型（避免递归：代价与节点数成正比，且不受解释器递归上限约束）
_ENTER = 0
_EMIT = 1
_CLOSE = 2

_SCALAR_TYPES = (str, int, float, bool, bytes, type(None))


def _token(tag: bytes, text: str) -> bytes:
    """长度前缀编码，保证片段拼接不会产生歧义（'ab'+'c' 不会与 'a'+'bc' 冲突）"""
    raw = text.encode('utf-8', 'backslashreplace')
    return tag + b':' + str(len(raw)).encode('ascii') + b':' + raw


def _literal_token(value: Any) -> bytes:
    """字面量载荷：带类型标记，避免 1 / True / '1' 摘要相同"""
    return _token(b'v', '%s:%r' % (type(value).__name__, value))


def _canonical_fragments(root: Any) -> Iterator[bytes]:
    """按确定顺序产出节点的规范化结构片段：kind + 字面量/字段载荷 + 全部子节点。

    - 排除 line/col（见 _POSITION_ATTRS）
    - 子节点按属性名排序遍历，兄弟节点按原顺序遍历 -> 同一棵树总是得到同一串片段
    - 迭代（显式栈）实现：每个节点常数次入栈，代价 O(节点数)，与深度无关
    """
    stack: List[Tuple[int, Any]] = [(_ENTER, root)]
    push = stack.append
    pop = stack.pop

    while stack:
        op, value = pop()

        if op == _EMIT:
            yield value
            continue
        if op == _CLOSE:
            yield b')'
            continue

        if isinstance(value, ASTNode):
            fields = getattr(value, '__dict__', None)
            if not fields:
                # 极端情况（__slots__ 等）：退回公开属性枚举
                fields = {
                    name: getattr(value, name, None)
                    for name in dir(value)
                    if not name.startswith('_') and not callable(getattr(value, name, None))
                }
            kind = value.kind if isinstance(getattr(value, 'kind', None), str) else type(value).__name__
            push((_CLOSE, None))
            push((_EMIT, _token(b'n', kind)))
            names = sorted(name for name in fields if name not in _HEADER_ATTRS)
            for name in reversed(names):
                push((_ENTER, getattr(value, name, None)))
                push((_EMIT, _token(b'a', name)))

        elif isinstance(value, (list, tuple)):
            push((_CLOSE, None))
            push((_EMIT, _token(b'l', '%s%d' % (type(value).__name__, len(value)))))
            for item in reversed(value):
                push((_ENTER, item))

        elif isinstance(value, dict):
            keys = sorted(value.keys(), key=repr)
            push((_CLOSE, None))
            push((_EMIT, _token(b'd', str(len(keys)))))
            for key in reversed(keys):
                push((_ENTER, value[key]))
                push((_ENTER, key))

        elif isinstance(value, (set, frozenset)):
            items = sorted(value, key=repr)
            push((_CLOSE, None))
            push((_EMIT, _token(b's', str(len(items)))))
            for item in reversed(items):
                push((_ENTER, item))

        elif isinstance(value, _SCALAR_TYPES):
            yield _literal_token(value)

        else:
            # 未知载荷：退化到 "类型名 + str()"，仍然可复现（不含内存地址）
            yield _token(b'o', '%s:%s' % (type(value).__name__, value))


class ASTDiffer:
    """AST 差异比较器"""

    def __init__(self):
        self.changed_definitions: Set[str] = set()
        self.added_definitions: Set[str] = set()
        self.removed_definitions: Set[str] = set()

    def _compute_definition_hash(self, node: ASTNode) -> str:
        """计算定义节点的哈希值

        摘要递归覆盖整棵子树（函数体、字段、变体取值、别名目标、方法体、装饰器、
        泛型参数与约束……），因此行号不变的原地表达式改写同样会改变哈希。
        """
        content: List[str] = []

        if isinstance(node, FuncDef):
            content.append(f"func:{node.name}")
            content.append(f"params:{len(node.params)}")
            for param in node.params:
                content.append(f"param:{param.name}:{self._type_to_str(getattr(param, 'type_annotation', None))}")
            content.append(f"return:{self._type_to_str(node.return_type)}")

        elif isinstance(node, StructDef):
            content.append(f"struct:{node.name}")
            content.append(f"generics:{','.join(node.generic_params)}")
            content.append(f"fields:{len(node.fields)}")
            for field in node.fields:
                if hasattr(field, 'name'):
                    content.append(f"field:{field.name}:{self._type_to_str(getattr(field, 'type_annotation', None))}")

        elif isinstance(node, EnumDef):
            content.append(f"enum:{node.name}")
            content.append(f"variants:{len(node.variants)}")
            for variant in node.variants:
                content.append(f"variant:{variant.name}")

        elif isinstance(node, TypeAlias):
            content.append(f"alias:{node.name}")

        elif isinstance(node, ExceptionDef):
            content.append(f"exception:{node.name}")
            content.append(f"base:{self._type_to_str(node.base_type)}")

        elif isinstance(node, TraitDef):
            content.append(f"trait:{node.name}")
            content.append(f"methods:{len(node.methods)}")

        # 结构摘要：与上面可读的类型头一起参与最终哈希
        content.append(f"digest:{self._node_to_hash(node)}")

        return hashlib.blake2b('|'.join(content).encode('utf-8'), digest_size=16).hexdigest()

    def _type_to_str(self, type_node: Any) -> str:
        """将类型节点转换为字符串（不含任何位置信息）

        注意：ASTNode.__repr__ 只输出 `kind(line=..., col=...)`，对 GenericType /
        UnionType 这类注解直接 str() 会把行号泄漏进定义哈希，使"纯格式化"被误判为
        语义变化；这里退化为位置无关的结构摘要。
        """
        if type_node is None:
            return "None"
        if isinstance(type_node, str):
            return type_node
        identifier = getattr(type_node, 'id', None)
        if isinstance(identifier, str):
            return identifier
        if isinstance(type_node, ASTNode):
            value = getattr(type_node, 'value', None)
            if isinstance(value, (str, int, float, bool)):
                return str(value)
            return self._node_to_hash(type_node)
        if hasattr(type_node, 'value'):
            return str(type_node.value)
        return str(type_node)

    def _node_to_hash(self, node: Any) -> str:
        """将节点转换为哈希字符串（递归结构摘要）

        使用 hashlib 而非内置 hash()：内置 hash 受 PYTHONHASHSEED 随机化，
        而该摘要会随增量缓存持久化，必须跨进程/跨运行稳定。
        """
        if node is None:
            return "None"
        digest = hashlib.blake2b(digest_size=16)
        for fragment in _canonical_fragments(node):
            digest.update(fragment)
        return digest.hexdigest()

    def _extract_definitions(self, ast: Any) -> Dict[str, Any]:
        """从 AST 中提取所有顶层定义"""
        definitions = {}

        if hasattr(ast, 'body'):
            for stmt in ast.body:
                if isinstance(stmt, (FuncDef, StructDef, EnumDef, TypeAlias, ExceptionDef, TraitDef)):
                    definitions[stmt.name] = stmt

        return definitions

    def compare(self, old_ast: Any, new_ast: Any) -> bool:
        """比较两个 AST，返回是否有变化"""
        # IncrementalCompiler 长期复用同一个 ASTDiffer 实例
        # （incremental_manager.py:59 创建，:340 调用，:361-363 读取结果），
        # 每次比较都必须清空上一轮的状态，否则旧的 changed_definitions 会被重放，
        # need_recompile 恒为 True、reused_definitions 恒为空。
        self.changed_definitions = set()
        self.added_definitions = set()
        self.removed_definitions = set()

        old_defs = self._extract_definitions(old_ast)
        new_defs = self._extract_definitions(new_ast)

        old_names = set(old_defs.keys())
        new_names = set(new_defs.keys())

        # 新增的定义
        self.added_definitions = new_names - old_names
        # 删除的定义
        self.removed_definitions = old_names - new_names

        # 检查变化的定义
        for name in old_names & new_names:
            old_hash = self._compute_definition_hash(old_defs[name])
            new_hash = self._compute_definition_hash(new_defs[name])
            if old_hash != new_hash:
                self.changed_definitions.add(name)

        return len(self.changed_definitions) > 0 or len(self.added_definitions) > 0 or len(self.removed_definitions) > 0

    def get_changed_definitions(self) -> Set[str]:
        """获取所有变化的定义名称（包括新增和修改）"""
        return self.changed_definitions | self.added_definitions

    def get_removed_definitions(self) -> Set[str]:
        """获取所有删除的定义名称"""
        return self.removed_definitions

    def is_changed(self, name: str) -> bool:
        """检查指定名称的定义是否发生变化"""
        return name in self.changed_definitions or name in self.added_definitions
