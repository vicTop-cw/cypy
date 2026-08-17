from typing import Iterator, List, Optional, Any, Tuple, Dict
import hashlib
import os
from .lexer import Token, TokenType


class StopExpressionParsing(Exception):
    """用于在匹配表达式中停止表达式解析的异常"""
    pass


# AST缓存全局实例
class ASTCache:
    """AST解析结果缓存 - 避免重复解析相同的源代码"""
    
    def __init__(self):
        self._cache: Dict[str, Any] = {}  # hash -> (ast, timestamp)
        self._source_map: Dict[str, str] = {}  # source_path -> hash
        self._max_size = 100  # 最大缓存条目数
    
    def _compute_hash(self, source: str) -> str:
        """计算源代码的SHA256哈希"""
        return hashlib.sha256(source.encode()).hexdigest()
    
    def get(self, source: str, source_path: str = "") -> Optional[Any]:
        """获取缓存的AST"""
        source_hash = self._compute_hash(source)
        
        # 如果有路径，检查路径对应的哈希是否一致
        if source_path and source_path in self._source_map:
            if self._source_map[source_path] != source_hash:
                return None
        
        if source_hash in self._cache:
            ast, _ = self._cache[source_hash]
            return ast
        
        return None
    
    def set(self, source: str, ast: Any, source_path: str = "") -> None:
        """设置缓存的AST"""
        source_hash = self._compute_hash(source)
        
        # 如果缓存已满，移除最旧的条目
        if len(self._cache) >= self._max_size:
            # 找到最早的条目
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]
        
        self._cache[source_hash] = (ast, os.times()[4])
        
        if source_path:
            self._source_map[source_path] = source_hash
    
    def invalidate(self, source_path: str) -> None:
        """使指定路径的缓存失效"""
        if source_path in self._source_map:
            source_hash = self._source_map[source_path]
            if source_hash in self._cache:
                del self._cache[source_hash]
            del self._source_map[source_path]
    
    def clear(self) -> None:
        """清空所有缓存"""
        self._cache.clear()
        self._source_map.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        return {
            'cache_size': len(self._cache),
            'max_size': self._max_size,
            'source_count': len(self._source_map),
        }


# 全局AST缓存实例
_global_ast_cache = ASTCache()


def get_ast_cache() -> ASTCache:
    """获取全局AST缓存实例"""
    return _global_ast_cache


class ASTNode:
    def __init__(self, kind: str, line: int = 0, col: int = 0):
        self.kind = kind
        self.line = line
        self.col = col

    def __repr__(self) -> str:
        return f"{self.kind}(line={self.line}, col={self.col})"


class Module(ASTNode):
    def __init__(self, body: List[ASTNode], line: int = 0, col: int = 0):
        super().__init__("Module", line, col)
        self.body = body


class Import(ASTNode):
    def __init__(self, module: str, alias: Optional[str] = None, line: int = 0, col: int = 0):
        super().__init__("Import", line, col)
        self.module = module
        self.alias = alias


class FromImport(ASTNode):
    def __init__(self, module: str, names: List[str], line: int = 0, col: int = 0):
        super().__init__("FromImport", line, col)
        self.module = module
        self.names = names


class StructDef(ASTNode):
    def __init__(self, name: str, fields: List[Any], generic_params: List[str] = None, generic_constraints: Dict[str, Any] = None, line: int = 0, col: int = 0, methods: List[Any] = None, decorators: List[Any] = None):
        super().__init__("StructDef", line, col)
        self.name = name
        self.fields = fields
        self.generic_params = generic_params or []
        self.generic_constraints = generic_constraints or {}
        self.methods = methods or []
        self.decorators = decorators or []


class StructField(ASTNode):
    def __init__(self, name: str, type_annotation: Optional[Any], mutable: bool = False, default_value: Optional[Any] = None, line: int = 0, col: int = 0):
        super().__init__("StructField", line, col)
        self.name = name
        self.type_annotation = type_annotation
        self.mutable = mutable
        self.default_value = default_value


class EnumDef(ASTNode):
    def __init__(self, name: str, variants: List[Any], line: int = 0, col: int = 0):
        super().__init__("EnumDef", line, col)
        self.name = name
        self.variants = variants


class EnumVariant(ASTNode):
    def __init__(self, name: str, value: Optional[Any] = None, line: int = 0, col: int = 0):
        super().__init__("EnumVariant", line, col)
        self.name = name
        self.value = value


class TraitDef(ASTNode):
    def __init__(self, name: str, methods: List[Any], generic_params: List[str] = None, super_traits: List[Any] = None, line: int = 0, col: int = 0):
        super().__init__("TraitDef", line, col)
        self.name = name
        self.methods = methods
        self.generic_params = generic_params or []
        self.super_traits = super_traits or []


class TypeClassDef(ASTNode):
    """TypeClass 定义节点 - 对标 Rust trait / Scala Type Class"""
    def __init__(self, name: str, methods: List[Any], generic_params: List[str] = None, generic_constraints: Dict[str, Any] = None, line: int = 0, col: int = 0):
        super().__init__("TypeClassDef", line, col)
        self.name = name
        self.methods = methods  # 方法签名列表
        self.generic_params = generic_params or []  # 泛型参数
        self.generic_constraints = generic_constraints or {}  # 泛型约束


class TypeClassImpl(ASTNode):
    """TypeClass 实现节点 - 对标 Rust impl Trait for Type"""
    def __init__(self, typeclass_name: str, target_type: str, methods: List[Any], generic_params: List[str] = None, line: int = 0, col: int = 0):
        super().__init__("TypeClassImpl", line, col)
        self.typeclass_name = typeclass_name  # 实现的 TypeClass 名称
        self.target_type = target_type  # 被实现的目标类型
        self.methods = methods  # 方法实现列表
        self.generic_params = generic_params or []  # 泛型参数


class ExceptionDef(ASTNode):
    """自定义异常类型定义"""
    def __init__(self, name: str, base_type: Optional[Any] = None, fields: List[Any] = None, line: int = 0, col: int = 0):
        super().__init__("ExceptionDef", line, col)
        self.name = name
        self.base_type = base_type  # 父异常类型，默认为 Exception
        self.fields = fields or []


class SuiteDef(ASTNode):
    """测试套件定义 - 参照 lang-zone/hermes 设计"""
    def __init__(self, name: str, body: List[ASTNode], line: int = 0, col: int = 0):
        super().__init__("SuiteDef", line, col)
        self.name = name
        self.body = body


class TestDef(ASTNode):
    """测试用例定义 - 参照 lang-zone/hermes 设计"""
    def __init__(self, name: str, body: List[ASTNode], line: int = 0, col: int = 0):
        super().__init__("TestDef", line, col)
        self.name = name
        self.body = body


class SetupStmt(ASTNode):
    """测试套件初始化块"""
    def __init__(self, body: List[ASTNode], line: int = 0, col: int = 0):
        super().__init__("SetupStmt", line, col)
        self.body = body


class TeardownStmt(ASTNode):
    """测试套件清理块"""
    def __init__(self, body: List[ASTNode], line: int = 0, col: int = 0):
        super().__init__("TeardownStmt", line, col)
        self.body = body


class FuncDef(ASTNode):
    def __init__(self, name: str, params: List[Any], return_type: Optional[Any], body: List[ASTNode], generic_params: List[str] = None, generic_constraints: Dict[str, Any] = None, decorators: List[Any] = None, is_async: bool = False, params_checker: Optional[str] = None, is_test: bool = False, line: int = 0, col: int = 0):
        super().__init__("FuncDef", line, col)
        self.name = name
        self.params = params
        self.return_type = return_type
        self.body = body
        self.generic_params = generic_params or []
        self.generic_constraints = generic_constraints or {}
        self.decorators = decorators or []
        self.is_async = is_async
        self.params_checker = params_checker  # <checker> 参数检查站名称
        self.is_test = is_test


class Param(ASTNode):
    def __init__(self, name: str, type_annotation: Optional[Any], default_value: Any = None, is_mut: bool = False, is_ref: bool = False, line: int = 0, col: int = 0, is_var_positional: bool = False, is_var_keyword: bool = False, is_dot_separator: bool = False):
        super().__init__("Param", line, col)
        self.name = name
        self.type_annotation = type_annotation
        self.default_value = default_value
        self.is_mut = is_mut
        self.is_ref = is_ref
        self.is_var_positional = is_var_positional  # *args
        self.is_var_keyword = is_var_keyword        # **kwargs
        self.is_dot_separator = is_dot_separator    # .. 分隔符


class ClassDef(ASTNode):
    def __init__(self, name: str, bases: List[Any], body: List[ASTNode], line: int = 0, col: int = 0, is_cdef: bool = False):
        super().__init__("ClassDef", line, col)
        self.name = name
        self.bases = bases
        self.body = body
        self.is_cdef = is_cdef


class TypeAlias(ASTNode):
    def __init__(self, name: str, target: Any, generic_params: List[str] = None, line: int = 0, col: int = 0):
        super().__init__("TypeAlias", line, col)
        self.name = name
        self.target = target
        self.generic_params = generic_params or []


class LetStmt(ASTNode):
    def __init__(self, name: Any, type_annotation: Optional[Any], value: Optional[Any], mutable: bool = False, is_const: bool = False, is_owned: bool = False, line: int = 0, col: int = 0):
        super().__init__("LetStmt", line, col)
        self.name = name  # 可以是字符串（普通变量）或模式（解构绑定）
        self.type_annotation = type_annotation
        self.value = value
        self.mutable = mutable
        self.is_const = is_const
        self.is_owned = is_owned


class DeferStmt(ASTNode):
    def __init__(self, body: List[ASTNode], line: int = 0, col: int = 0):
        super().__init__("DeferStmt", line, col)
        self.body = body


class GuardStmt(ASTNode):
    """守卫表达式语句 - 支持提前终止并隐式返回"""
    def __init__(self, test: Any, orelse: Any, is_let: bool = False, let_target: Any = None, line: int = 0, col: int = 0):
        super().__init__("GuardStmt", line, col)
        self.test = test           # 条件表达式
        self.condition = test      # 条件表达式（别名，用于兼容其他模块）
        self.orelse = orelse       # else 分支（表达式或块）
        self.is_let = is_let       # 是否是 guard let 形式
        self.let_target = let_target  # guard let 的绑定目标


class ReturnStmt(ASTNode):
    def __init__(self, value: Optional[Any], line: int = 0, col: int = 0):
        super().__init__("ReturnStmt", line, col)
        self.value = value


class YieldStmt(ASTNode):
    def __init__(self, value: Optional[Any], is_from: bool = False, line: int = 0, col: int = 0):
        super().__init__("YieldStmt", line, col)
        self.value = value
        self.is_from = is_from


class AwaitExpr(ASTNode):
    """await 表达式 - 等待异步结果"""
    def __init__(self, value: Any, line: int = 0, col: int = 0):
        super().__init__("AwaitExpr", line, col)
        self.value = value


class AssertStmt(ASTNode):
    def __init__(self, test: Any, msg: Optional[Any] = None, line: int = 0, col: int = 0):
        super().__init__("AssertStmt", line, col)
        self.test = test
        self.msg = msg


class Decorator(ASTNode):
    def __init__(self, name: Any, args: Optional[List[Any]] = None, line: int = 0, col: int = 0):
        super().__init__("Decorator", line, col)
        self.name = name
        self.args = args or []


class IfStmt(ASTNode):
    def __init__(self, test: Any, body: List[ASTNode], orelse: Optional[List[ASTNode]] = None, line: int = 0, col: int = 0):
        super().__init__("IfStmt", line, col)
        self.test = test
        self.body = body
        self.orelse = orelse


class MatchStmt(ASTNode):
    """match/case 模式匹配语句"""
    def __init__(self, subject: Any, cases: List[Any], orelse: Optional[List[ASTNode]] = None, line: int = 0, col: int = 0):
        super().__init__("MatchStmt", line, col)
        self.subject = subject  # 匹配的表达式
        self.cases = cases      # case 子句列表
        self.orelse = orelse    # else 分支


class MatchExpr(ASTNode):
    """match/case 模式匹配表达式（返回值）"""
    def __init__(self, subject: Any, cases: List[Any], line: int = 0, col: int = 0):
        super().__init__("MatchExpr", line, col)
        self.subject = subject  # 匹配的表达式
        self.cases = cases      # case 子句列表


class CaseClause(ASTNode):
    """case 子句"""
    def __init__(self, pattern: Any, body: List[ASTNode], line: int = 0, col: int = 0):
        super().__init__("CaseClause", line, col)
        self.pattern = pattern  # 匹配模式
        self.body = body        # case 体


class ForStmt(ASTNode):
    def __init__(self, target: Any, iter: Any, body: List[ASTNode], line: int = 0, col: int = 0):
        super().__init__("ForStmt", line, col)
        self.target = target
        self.iter = iter
        self.body = body


class WhileStmt(ASTNode):
    def __init__(self, test: Any, body: List[ASTNode], line: int = 0, col: int = 0):
        super().__init__("WhileStmt", line, col)
        self.test = test
        self.body = body


class BreakStmt(ASTNode):
    def __init__(self, line: int = 0, col: int = 0):
        super().__init__("BreakStmt", line, col)


class ContinueStmt(ASTNode):
    def __init__(self, line: int = 0, col: int = 0):
        super().__init__("ContinueStmt", line, col)


class DelStmt(ASTNode):
    def __init__(self, targets: List[ASTNode], line: int = 0, col: int = 0):
        super().__init__("DelStmt", line, col)
        self.targets = targets


class GlobalStmt(ASTNode):
    def __init__(self, names: List[str], line: int = 0, col: int = 0):
        super().__init__("GlobalStmt", line, col)
        self.names = names


class NonlocalStmt(ASTNode):
    def __init__(self, names: List[str], line: int = 0, col: int = 0):
        super().__init__("NonlocalStmt", line, col)
        self.names = names


class ExprStmt(ASTNode):
    def __init__(self, value: Any, line: int = 0, col: int = 0):
        super().__init__("ExprStmt", line, col)
        self.value = value


class TryStmt(ASTNode):
    def __init__(self, body: List[ASTNode], handlers: List[Any], orelse: List[ASTNode] = None, line: int = 0, col: int = 0):
        super().__init__("TryStmt", line, col)
        self.body = body
        self.handlers = handlers  # List of (type, name, body) tuples
        self.orelse = orelse or []


class RaiseStmt(ASTNode):
    def __init__(self, exc: Any = None, cause: Any = None, line: int = 0, col: int = 0):
        super().__init__("RaiseStmt", line, col)
        self.exc = exc
        self.cause = cause


class WithStmt(ASTNode):
    def __init__(self, items: List[Any], body: List[ASTNode], line: int = 0, col: int = 0):
        super().__init__("WithStmt", line, col)
        self.items = items  # List of (expr, var) tuples
        self.body = body


class LambdaExpr(ASTNode):
    """Lambda表达式 - 匿名函数"""
    def __init__(self, params: List[Param], body: Any, line: int = 0, col: int = 0):
        super().__init__("LambdaExpr", line, col)
        self.params = params  # List of Param nodes
        self.body = body      # Single expression or block


class ListComp(ASTNode):
    """列表推导式"""
    def __init__(self, elt: Any, generators: List[Any], line: int = 0, col: int = 0):
        super().__init__("ListComp", line, col)
        self.elt = elt        # 元素表达式
        self.generators = generators  # 生成器列表，每个元素是 (target, iter, if_expr) 元组


class Assign(ASTNode):
    def __init__(self, target: Any, value: Any, line: int = 0, col: int = 0):
        super().__init__("Assign", line, col)
        self.target = target
        self.value = value


class BinOp(ASTNode):
    def __init__(self, left: Any, op: str, right: Any, line: int = 0, col: int = 0):
        super().__init__("BinOp", line, col)
        self.left = left
        self.op = op
        self.right = right


class IfExp(ASTNode):
    """三元条件表达式: body if test else orelse"""
    def __init__(self, test: Any, body: Any, orelse: Any, line: int = 0, col: int = 0):
        super().__init__("IfExp", line, col)
        self.test = test
        self.body = body
        self.orelse = orelse


class UnaryOp(ASTNode):
    def __init__(self, op: str, operand: Any, line: int = 0, col: int = 0):
        super().__init__("UnaryOp", line, col)
        self.op = op
        self.operand = operand


class Call(ASTNode):
    def __init__(self, func: Any, args: List[Any], checker: Optional[str] = None, line: int = 0, col: int = 0):
        super().__init__("Call", line, col)
        self.func = func
        self.args = args
        self.checker = checker  # 调用时指定的 <checker> 参数检查站名称


class Attribute(ASTNode):
    def __init__(self, value: Any, attr: str, line: int = 0, col: int = 0):
        super().__init__("Attribute", line, col)
        self.value = value
        self.attr = attr


class Subscript(ASTNode):
    def __init__(self, value: Any, slice: Any, line: int = 0, col: int = 0):
        super().__init__("Subscript", line, col)
        self.value = value
        self.slice = slice


class Name(ASTNode):
    def __init__(self, id: str, line: int = 0, col: int = 0):
        super().__init__("Name", line, col)
        self.id = id


class Pattern(ASTNode):
    """模式绑定 - 在 match case 中绑定变量"""
    def __init__(self, name: str, line: int = 0, col: int = 0):
        super().__init__("Pattern", line, col)
        self.name = name


class SlicePattern(ASTNode):
    """切片模式 - .. 或 ..var 用于列表/元组模式中的剩余元素绑定"""
    def __init__(self, name: Optional[str] = None, line: int = 0, col: int = 0):
        super().__init__("SlicePattern", line, col)
        self.name = name


class ArrayPattern(ASTNode):
    """数组/列表模式 - 在 match case 中匹配数组/列表结构"""
    def __init__(self, elements: List[Any], rest_name: Optional[str] = None, line: int = 0, col: int = 0):
        super().__init__("ArrayPattern", line, col)
        self.elements = elements
        self.rest_name = rest_name  # *rest 剩余绑定


class StructPattern(ASTNode):
    """结构体解构模式 - Point { x, y } 或 Point { x: px, y: py }"""
    def __init__(self, struct_name: str, fields: List[Tuple[str, Any]], has_ellipsis: bool = False, line: int = 0, col: int = 0):
        super().__init__("StructPattern", line, col)
        self.struct_name = struct_name  # 结构体名称
        self.fields = fields             # 字段列表 [(field_name, pattern), ...]
        self.has_ellipsis = has_ellipsis # 是否包含 .. 忽略其他字段


class DictPattern(ASTNode):
    """字典/映射解构模式 - {"key": value, "key2": value2, **rest}"""
    def __init__(self, pairs: List[Tuple[Any, Any]], rest_name: Optional[str] = None, line: int = 0, col: int = 0):
        super().__init__("DictPattern", line, col)
        self.pairs = pairs               # 键值对列表 [(key_pattern, value_pattern), ...]
        self.rest_name = rest_name       # 剩余字段绑定变量名（**rest）


class TypePattern(ASTNode):
    """类型模式 - case int x: 匹配 int 类型并绑定到 x"""
    def __init__(self, type_name: str, name: str, line: int = 0, col: int = 0):
        super().__init__("TypePattern", line, col)
        self.type_name = type_name  # 类型名称（如 int, str, Point）
        self.name = name            # 绑定的变量名


class AsPattern(ASTNode):
    """As模式 - case pattern as name: 将匹配值绑定到变量"""
    def __init__(self, pattern: Any, name: str, line: int = 0, col: int = 0):
        super().__init__("AsPattern", line, col)
        self.pattern = pattern  # 内部模式
        self.name = name        # 绑定的变量名


class ExtractorPattern(ASTNode):
    """提取器模式 - 参考Scala的unapply，如 Email(user, domain)
    优先级：__match_args__ < __unapply__ < __unapply_seq__ < __unwarp__
    """
    def __init__(self, type_name: str, args: List[Any], line: int = 0, col: int = 0):
        super().__init__("ExtractorPattern", line, col)
        self.type_name = type_name  # 类型/提取器名称（如 Email）
        self.args = args            # 提取的参数模式列表 [pattern1, pattern2, ...]


class RangePattern(ASTNode):
    """范围模式 - case 1..10: 匹配范围内的值"""
    def __init__(self, lower: Any, upper: Any, line: int = 0, col: int = 0):
        super().__init__("RangePattern", line, col)
        self.lower = lower  # 下界（包含）
        self.upper = upper  # 上界（不包含）


class PipeExpr(ASTNode):
    """管道表达式 - x |> f 等同于 f(x)"""
    def __init__(self, value: Any, function: Any, line: int = 0, col: int = 0):
        super().__init__("PipeExpr", line, col)
        self.value = value       # 管道左边的值
        self.function = function # 管道右边的函数


class Constant(ASTNode):
    def __init__(self, value: Any, line: int = 0, col: int = 0, prefix: str = None):
        super().__init__("Constant", line, col)
        self.value = value
        self.prefix = prefix


class PointerType(ASTNode):
    def __init__(self, base_type: Any, line: int = 0, col: int = 0):
        super().__init__("PointerType", line, col)
        self.base_type = base_type


class RefType(ASTNode):
    def __init__(self, base_type: Any, line: int = 0, col: int = 0):
        super().__init__("RefType", line, col)
        self.base_type = base_type


class DerefExpr(ASTNode):
    def __init__(self, operand: Any, line: int = 0, col: int = 0):
        super().__init__("DerefExpr", line, col)
        self.operand = operand


class CastExpr(ASTNode):
    """类型转换表达式 - expr as Type"""
    def __init__(self, value: Any, target_type: Any, line: int = 0, col: int = 0):
        super().__init__("CastExpr", line, col)
        self.value = value          # 要转换的值
        self.target_type = target_type  # 目标类型


class GenericType(ASTNode):
    def __init__(self, name: str, args: List[Any], line: int = 0, col: int = 0):
        super().__init__("GenericType", line, col)
        self.name = name
        self.args = args


class UnionType(ASTNode):
    """联合类型 - type Number = int | float"""
    def __init__(self, types: List[Any], line: int = 0, col: int = 0):
        super().__init__("UnionType", line, col)
        self.types = types


class ImplStmt(ASTNode):
    def __init__(self, trait_name: str, trait_generic_args: List[Any], for_type: Any, methods: List[Any], line: int = 0, col: int = 0):
        super().__init__("ImplStmt", line, col)
        self.trait_name = trait_name
        self.trait_generic_args = trait_generic_args or []
        self.for_type = for_type
        self.methods = methods


class MetaBlock(ASTNode):
    def __init__(self, body: List[ASTNode], line: int = 0, col: int = 0):
        super().__init__("MetaBlock", line, col)
        self.body = body


class BuildBlockExpr(ASTNode):
    """构建块表达式 - 闭包无参函数，内部默认unsafe
    
    LZ 语法参考:
    - =: 变量构建块: 创建无参不安全闭包，块体末尾表达式作为返回值
    - ^: 索引构建块: 对容器做索引访问，脱糖为 __getitem__ 调用
    - ~: 调用构建块: 创建带参闭包，块体末尾返回元组/字典，自动拆包传递
    - *: 生成器构建块: 创建生成器闭包
    """
    BUILD_ASSIGN = "assign"    # =: 变量构建块
    BUILD_INDEX = "index"      # ^: 索引构建块 (lz 新增)
    BUILD_CALL = "call"        # ~: 调用构建块
    BUILD_GEN = "generator"    # *: 生成器构建块
    
    def __init__(self, block_type: str, body: List[ASTNode], line: int = 0, col: int = 0):
        super().__init__("BuildBlockExpr", line, col)
        self.block_type = block_type
        self.body = body


class BuildValueExpr(ASTNode):
    """构建值表达式 - 使用 ^ 符号获取构建值"""
    def __init__(self, operand: Any, line: int = 0, col: int = 0):
        super().__init__("BuildValueExpr", line, col)
        self.operand = operand


class DuckRequirement(ASTNode):
    """单个 duck 约束项

    kind 类型:
    - "operator": 操作符约束 (如: a < b -> bool, -a -> Self)
    - "attribute": 属性约束 (如: name: str)
    - "method": 方法约束 (如: len(self) -> int)
    - "reference": 引用约束 (如: Comparable, Container<T>)
    """
    def __init__(self, kind: str, name: str, params: List[str],
                 return_type: Optional[str] = None,
                 line: int = 0, col: int = 0,
                 generic_args: Optional[List[str]] = None,
                 is_unary: bool = False):
        super().__init__("DuckRequirement", line, col)
        self.kind = kind
        self.name = name
        self.params = params
        self.return_type = return_type
        self.generic_args = generic_args or []
        self.is_unary = is_unary


class DuckDef(ASTNode):
    """duck 约束定义
    
    示例:
        duck Comparable:
            a < b -> bool
            a > b -> bool
        
        duck Container[T]:
            add(self, item: T) -> None
            len(self) -> int
    """
    def __init__(self, name: str, type_params: List[str],
                 requirements: List[DuckRequirement], line: int = 0, col: int = 0):
        super().__init__("DuckDef", line, col)
        self.name = name
        self.type_params = type_params
        self.requirements = requirements


class MacroDef(ASTNode):
    """宏定义 - 编译期代码生成函数"""
    def __init__(self, name: str, params: List[str], body: List[ASTNode], line: int = 0, col: int = 0):
        super().__init__("MacroDef", line, col)
        self.name = name
        self.params = params
        self.body = body


class MacroCall(ASTNode):
    """宏调用 - 编译期展开"""
    def __init__(self, name: str, args: List[Any], line: int = 0, col: int = 0):
        super().__init__("MacroCall", line, col)
        self.name = name
        self.args = args


class StructLiteral(ASTNode):
    """结构体字面量 - StructName {field1: value1, field2: value2}"""
    def __init__(self, struct_name: str, fields: List[Tuple[str, Any]], line: int = 0, col: int = 0):
        super().__init__("StructLiteral", line, col)
        self.struct_name = struct_name  # 结构体名称
        self.fields = fields             # 字段列表 [(name, value), ...]


class ComptimeStmt(ASTNode):
    """编译期求值语句 - 在编译时执行并替换为常量"""
    def __init__(self, expr: Any, line: int = 0, col: int = 0):
        super().__init__("ComptimeStmt", line, col)
        self.expr = expr


class ComptimeFuncDef(ASTNode):
    """编译期函数定义 - 在编译时执行的函数"""
    def __init__(self, name: str, params: List[Any], return_type: Optional[Any], body: List[ASTNode], line: int = 0, col: int = 0):
        super().__init__("ComptimeFuncDef", line, col)
        self.name = name
        self.params = params
        self.return_type = return_type
        self.body = body


class BacktickBlock(ASTNode):
    """反引号代码块 - 用于宏中的代码捕获
    语法：
    - ```...```     普通形式（不插值）
    - f```...```    插值形式（支持 $() 插值）
    - r```...```    原始形式（不插值，不展开宏）
    """
    def __init__(self, content: str, prefix: str = None, line: int = 0, col: int = 0):
        super().__init__("BacktickBlock", line, col)
        self.content = content  # 代码块内容（字符串）
        self.prefix = prefix    # None | 'f' | 'r'


class SpawnStmt(ASTNode):
    """并发任务语句 - 在后台执行异步任务"""
    def __init__(self, target: Any, args: List[Any] = None, body: List[ASTNode] = None, line: int = 0, col: int = 0):
        super().__init__("SpawnStmt", line, col)
        self.target = target  # 函数名或表达式
        self.args = args or []  # 调用参数（用于 spawn func(args) 形式）
        self.body = body or []  # 任务体（用于 spawn: 块形式）


class GoStmt(ASTNode):
    """轻量级协程语句 - 创建并启动协程"""
    def __init__(self, target: Any, args: List[Any] = None, body: List[ASTNode] = None, line: int = 0, col: int = 0):
        super().__init__("GoStmt", line, col)
        self.target = target  # 函数名或表达式
        self.args = args or []  # 调用参数（用于 go func(args) 形式）
        self.body = body or []  # 任务体（用于 go: 块形式）


class VecType(ASTNode):
    """SIMD 向量类型 - vec[ElementType; Size]"""
    def __init__(self, element_type: Any, size: int, line: int = 0, col: int = 0):
        super().__init__("VecType", line, col)
        self.element_type = element_type  # 元素类型
        self.size = size  # 向量大小（必须是编译期常量）


class VecLiteral(ASTNode):
    """SIMD 向量字面量 - vec![value; Size] 或 vec![v1, v2, ...]"""
    def __init__(self, elements: List[Any], size: Optional[int] = None, line: int = 0, col: int = 0):
        super().__init__("VecLiteral", line, col)
        self.elements = elements  # 元素列表
        self.size = size  # 如果是重复形式，size 指定重复次数


class DictLiteral(ASTNode):
    """字典字面量 - {key: value, key2: value2, ...}"""
    def __init__(self, pairs: List[Tuple[Any, Any]], line: int = 0, col: int = 0):
        super().__init__("DictLiteral", line, col)
        self.pairs = pairs


class Parser:
    def __init__(self, tokens: Iterator[Token]):
        self.tokens = list(tokens)
        self.pos = 0
        self._scope_stack = []  # 作用域跟踪栈，记录当前嵌套深度和类型
        self._in_function = False  # 是否在函数内部（用于defer检查）
        self._in_call_args = False  # 是否在函数调用参数列表中（用于区分独立语句 vs 嵌套调用）
    
    def _push_scope(self, scope_type: str):
        """进入新的作用域"""
        self._scope_stack.append(scope_type)
        if scope_type in ('func', 'method'):
            self._in_function = True
    
    def _pop_scope(self):
        """退出当前作用域"""
        if self._scope_stack:
            scope_type = self._scope_stack.pop()
            if scope_type in ('func', 'method') and not any(s in ('func', 'method') for s in self._scope_stack):
                self._in_function = False
    
    def _is_module_level(self) -> bool:
        """检查是否在模块顶级"""
        return len(self._scope_stack) == 0
    
    def _require_module_level(self, construct_name: str, token: Token):
        """要求必须在模块顶级，否则抛出错误"""
        if not self._is_module_level():
            raise ValueError(f"{construct_name} must be defined at module level, found at {token.line}:{token.col}")
    
    def _require_function_scope(self, construct_name: str, token: Token):
        """要求必须在函数内部，否则抛出错误"""
        if not self._in_function:
            raise ValueError(f"{construct_name} must be used inside a function, found at {token.line}:{token.col}")

    def _current(self) -> Token:
        if self.pos >= len(self.tokens):
            return Token(TokenType.EOF, "", 0, 0)
        return self.tokens[self.pos]

    def _peek(self) -> Optional[Token]:
        if self.pos + 1 < len(self.tokens):
            return self.tokens[self.pos + 1]
        return None
    
    def _peek_ahead(self, n: int) -> Optional[TokenType]:
        """预看第n个token的类型（n=1表示下一个）"""
        if self.pos + n < len(self.tokens):
            return self.tokens[self.pos + n].type
        return None

    def _consume(self, expected_type: Optional[str] = None) -> Token:
        token = self._current()
        if expected_type and token.type != expected_type:
            raise ValueError(f"Expected {expected_type}, got {token.type} at {token.line}:{token.col}")
        self.pos += 1
        return token

    def _expect(self, expected_type: str) -> Token:
        token = self._consume(expected_type)
        return token

    def parse(self) -> Module:
        body = []
        while self._current().type != TokenType.EOF:
            stmt = self._parse_statement()
            if stmt:
                body.append(stmt)
        return Module(body)

    def _parse_statement(self, signature_only: bool = False) -> Optional[ASTNode]:
        token = self._current()
        
        # 解析装饰器列表（注意：@name! 是宏调用，不是装饰器）
        decorators = []
        while token.type == TokenType.AT:
            # 预看：检查下一个token是否表明是宏调用
            next_token = self._peek_ahead(1)
            is_macro_call = False
            if next_token == TokenType.IDENTIFIER:
                # 获取下一个token的实际值
                actual_next = self.tokens[self.pos + 1]
                # 检查是否是宏调用 @name!
                if actual_next.value.endswith('!'):
                    is_macro_call = True
                elif self._peek_ahead(2) == TokenType.BANG:
                    is_macro_call = True
            
            if is_macro_call:
                # 这是宏调用语句，不是装饰器，跳出循环让后续逻辑处理
                break
            
            # 这是装饰器
            decorator = self._parse_decorator()
            decorators.append(decorator)
            token = self._current()
        
        if token.type == TokenType.NEWLINE:
            self._consume()
            return None
        if token.type == TokenType.INDENT:
            self._consume()
            return None
        if token.type == TokenType.DEDENT:
            self._consume()
            return None

        if token.type == TokenType.ASYNC:
            self._consume()
            if self._current().type == TokenType.DEF:
                return self._parse_func_def(decorators, is_async=True, signature_only=signature_only)
            else:
                raise ValueError(f"Unexpected token {self._current().type} after async at {self._current().line}:{self._current().col}")
        if token.type == TokenType.DEF:
            return self._parse_func_def(decorators, signature_only=signature_only)
        if token.type == TokenType.CLASS:
            return self._parse_class_def()
        if token.type == TokenType.STRUCT:
            return self._parse_struct_def(decorators=decorators)
        if token.type == TokenType.ENUM:
            return self._parse_enum_def()
        if token.type == TokenType.TRAIT:
            return self._parse_trait_def()
        if token.type == TokenType.TYPECLASS:
            return self._parse_typeclass_def()
        if token.type == TokenType.IMPL:
            return self._parse_impl_stmt()
        if token.type == TokenType.SUITE:
            return self._parse_suite_stmt()
        if token.type == TokenType.LET:
            return self._parse_let_stmt()
        if token.type == TokenType.MUT:
            return self._parse_mut_stmt()
        if token.type == TokenType.CONST:
            return self._parse_const_stmt()
        if token.type == TokenType.OWNED:
            return self._parse_owned_stmt()
        if token.type == TokenType.TEST:
            # test name: 语法：测试用例（参照 lang-zone/hermes）
            return self._parse_test_stmt()
        if token.type == TokenType.SETUP:
            return self._parse_setup_stmt()
        if token.type == TokenType.TEARDOWN:
            return self._parse_teardown_stmt()
        if token.type == TokenType.IDENTIFIER:
            peek_token = self._peek()
            if peek_token and peek_token.type == TokenType.COLON:
                return self._parse_typed_var()
        if token.type == TokenType.META:
            return self._parse_meta_block()
        if token.type == TokenType.RETURN:
            return self._parse_return_stmt()
        if token.type == TokenType.IF:
            return self._parse_if_stmt()
        if token.type == TokenType.MATCH:
            return self._parse_match_stmt()
        if token.type == TokenType.FOR:
            return self._parse_for_stmt()
        if token.type == TokenType.WHILE:
            return self._parse_while_stmt()
        if token.type == TokenType.BREAK:
            return self._parse_break_stmt()
        if token.type == TokenType.DEL:
            return self._parse_del_stmt()
        if token.type == TokenType.PASS:
            self._consume()
            return ASTNode("PassStmt", self._current().line, self._current().col)
        if token.type == TokenType.GLOBAL:
            return self._parse_global_stmt()
        if token.type == TokenType.NONLOCAL:
            return self._parse_nonlocal_stmt()
        if token.type == TokenType.CONTINUE:
            return self._parse_continue_stmt()
        if token.type == TokenType.DEFER:
            return self._parse_defer_stmt()
        if token.type == TokenType.GUARD:
            return self._parse_guard_stmt()
        if token.type == TokenType.MACRO:
            return self._parse_macro_def()
        if token.type == TokenType.COMPTIME:
            # 检查是否是 comptime def 语法
            if self._peek_ahead(1) == TokenType.DEF:
                return self._parse_comptime_func_def()
            return self._parse_comptime_stmt()
        if token.type == TokenType.SPAWN:
            return self._parse_spawn_stmt()
        if token.type == TokenType.GO:
            return self._parse_go_stmt()
        if token.type == TokenType.YIELD:
            return self._parse_yield_stmt()
        if token.type == TokenType.AT:
            # 宏调用语句：@name! 或 @name!(args...)
            # 注意：Lexer可能将 name! 解析为单个标识符（如果name不是关键字）
            self._consume()
            name_token = self._expect(TokenType.IDENTIFIER)
            name = name_token.value
            # 检查标识符是否以!结尾（Lexer可能合并了!）
            if name.endswith('!'):
                name = name[:-1]
            elif self._current().type == TokenType.BANG:
                # ! 被单独解析
                self._consume()
            # 宏名称加上!后缀表示宏调用
            name += "!"
            args = []
            if self._current().type == TokenType.LPAREN:
                self._consume()
                if self._current().type != TokenType.RPAREN:
                    while True:
                        args.append(self._parse_expression())
                        if self._current().type != TokenType.COMMA:
                            break
                        self._consume()
                self._expect(TokenType.RPAREN)
            if self._current().type == TokenType.NEWLINE:
                self._consume()
            return MacroCall(name, args, token.line, token.col)
        if token.type == TokenType.TRY:
            return self._parse_try_stmt()
        if token.type == TokenType.WITH:
            return self._parse_with_stmt()
        if token.type == TokenType.RAISE:
            return self._parse_raise_stmt()
        if token.type == TokenType.ASSERT:
            return self._parse_assert_stmt()
        if token.type == TokenType.IMPORT:
            return self._parse_import()
        if token.type == TokenType.FROM:
            return self._parse_from_import()
        if token.type == TokenType.TYPE:
            return self._parse_type_alias()

        return self._parse_expr_stmt()

    def _parse_func_def(self, decorators: List[Any] = None, is_async: bool = False, is_test: bool = False, signature_only: bool = False) -> FuncDef:
        # 函数定义统一使用 def 关键字
        self._consume(TokenType.DEF)
        
        # <checker> 参数检查站（可选，在函数名之前）
        params_checker = None
        if self._current().type == TokenType.LT:
            self._consume()  # consume <
            checker_name = self._consume(TokenType.IDENTIFIER).value
            self._expect(TokenType.GT)  # consume >
            params_checker = checker_name
        
        # 函数名可以是 IDENTIFIER 或 TEST（允许使用 test 作为函数名）
        if self._current().type == TokenType.TEST:
            name_token = self._consume(TokenType.TEST)
        else:
            name_token = self._consume(TokenType.IDENTIFIER)
        
        # [generic] 泛型参数（可选，在函数名之后）
        # 统一使用尖括号 <>（与 LZ 语法对齐）
        generic_params = []
        generic_constraints = {}
        if self._current().type == TokenType.LT:
            self._consume()
            if self._current().type == TokenType.GT:
                raise ValueError(f"Generic parameter list cannot be empty at {name_token.line}:{name_token.col}")
            while self._current().type != TokenType.GT:
                param_name = self._consume(TokenType.IDENTIFIER).value
                generic_params.append(param_name)
                # 检查是否有约束
                if self._current().type == TokenType.COLON:
                    self._consume()
                    constraint_type = self._parse_type()
                    generic_constraints[param_name] = constraint_type
                if self._current().type == TokenType.COMMA:
                    self._consume()
            self._consume()
        
        self._expect(TokenType.LPAREN)
        params = self._parse_params()
        self._expect(TokenType.RPAREN)
        return_type = None
        if self._current().type == TokenType.ARROW:
            self._consume()
            return_type = self._parse_type()
        
        # 支持 LZ 风格的 = 函数体语法（兼容 : 语法）
        # def f() = expr  -> 单行函数体
        # def f() =       -> 块函数体（换行后）
        # def f():        -> 原有块函数体语法
        # signature_only 模式（trait/typeclass 方法签名）: 无函数体，body 为空
        is_lz_style = False
        body = []
        if signature_only:
            # 签名模式：检查是否有 body 标记（= 或 :），如果没有则 body 为空
            if self._current().type == TokenType.ASSIGN:
                is_lz_style = True
                self._consume()
                if self._current().type not in (TokenType.INDENT, TokenType.NEWLINE, TokenType.EOF, TokenType.DEDENT):
                    expr = self._parse_expression()
                    self._push_scope("func")
                    body = [ReturnStmt(expr, expr.line, expr.col)]
                    self._pop_scope()
                elif self._current().type in (TokenType.INDENT, TokenType.NEWLINE):
                    self._push_scope("func")
                    body = self._parse_block()
                    self._pop_scope()
            elif self._current().type == TokenType.COLON:
                self._consume()
                self._push_scope("func")
                body = self._parse_block()
                self._pop_scope()
            # 否则 body 保持为空（签名模式）
        elif self._current().type == TokenType.ASSIGN:
            is_lz_style = True
            self._consume()
            # 检查是否是单行函数体（= 后跟表达式）
            # 如果当前 token 是 INDENT、NEWLINE 或 EOF，则是块函数体
            # 否则是单行函数体（表达式）
            if self._current().type not in (TokenType.INDENT, TokenType.NEWLINE, TokenType.EOF):
                # 单行函数体：解析表达式作为 body
                expr = self._parse_expression()
                self._push_scope("func")
                body = [ReturnStmt(expr, expr.line, expr.col)]
                self._pop_scope()
            else:
                # 块函数体：解析缩进块
                self._push_scope("func")
                body = self._parse_block()
                self._pop_scope()
        else:
            # 原有 : 语法
            self._expect(TokenType.COLON)
            self._push_scope("func")
            body = self._parse_block()
            self._pop_scope()
        
        return FuncDef(name_token.value, params, return_type, body, generic_params, generic_constraints, decorators, is_async, params_checker, is_test, name_token.line, name_token.col)

    def _parse_params(self) -> List[Param]:
        params = []
        if self._current().type != TokenType.RPAREN:
            while True:
                # 检查是否是 .. 分隔符
                if self._current().type == TokenType.DOT_DOT:
                    line = self._current().line
                    col = self._current().col
                    self._consume()
                    
                    # .. 可能带类型注解（用于 args/kwargs 类型约束）
                    type_annotation = None
                    if self._current().type == TokenType.COLON:
                        self._consume()
                        type_annotation = self._parse_type()
                    
                    params.append(Param(
                        name="__dot_separator__", 
                        type_annotation=type_annotation, 
                        is_dot_separator=True,
                        line=line, 
                        col=col
                    ))
                    
                    if self._current().type != TokenType.COMMA:
                        # 检查是否是双 .. (.. ..)
                        if self._current().type == TokenType.DOT_DOT:
                            # 第二个 ..
                            line2 = self._current().line
                            col2 = self._current().col
                            self._consume()
                            type_annotation2 = None
                            if self._current().type == TokenType.COLON:
                                self._consume()
                                type_annotation2 = self._parse_type()
                            params.append(Param(
                                name="__dot_separator__", 
                                type_annotation=type_annotation2, 
                                is_dot_separator=True,
                                line=line2, 
                                col=col2
                            ))
                        else:
                            break
                    else:
                        self._consume()
                    continue
                
                is_mut = False
                is_ref = False
                if self._current().type == TokenType.MUT:
                    is_mut = True
                    self._consume()
                
                # 支持 *args 和 **kwargs 语法
                is_var_positional = False
                is_var_keyword = False
                if self._current().type == TokenType.POW:
                    # **kwargs
                    self._consume()
                    is_var_keyword = True
                elif self._current().type == TokenType.MUL:
                    # *args
                    self._consume()
                    is_var_positional = True
                
                name_token = self._consume(TokenType.IDENTIFIER)
                type_annotation = None
                default_value = None
                
                if self._current().type == TokenType.COLON:
                    self._consume()
                    type_annotation = self._parse_type()
                
                # 检查是否是 List<T> 类型（安全收集模式）
                # 如果类型是 List<T>，标记为可变位置参数
                if type_annotation and not is_var_positional and not is_var_keyword:
                    # 处理泛型类型：GenericType(name='List', args=[...])
                    if isinstance(type_annotation, GenericType) and type_annotation.name == 'List':
                        is_var_positional = True
                    # 处理普通名称类型
                    elif hasattr(type_annotation, 'id') and type_annotation.id == 'List':
                        is_var_positional = True
                
                if self._current().type == TokenType.ASSIGN:
                    self._consume()
                    default_value = self._parse_expression()
                
                params.append(Param(
                    name_token.value, 
                    type_annotation, 
                    default_value, 
                    is_mut, 
                    is_ref, 
                    name_token.line, 
                    name_token.col,
                    is_var_positional=is_var_positional,
                    is_var_keyword=is_var_keyword
                ))
                
                if self._current().type != TokenType.COMMA:
                    break
                self._consume()
        return params

    def _parse_class_def(self, is_cdef: bool = False) -> ClassDef:
        self._consume(TokenType.CLASS)
        name_token = self._consume(TokenType.IDENTIFIER)
        bases = []
        # 支持 Python 风格的 class Name(Parent): 语法
        if self._current().type == TokenType.LPAREN:
            self._consume()
            while self._current().type != TokenType.RPAREN:
                bases.append(self._parse_type())
                if self._current().type == TokenType.COMMA:
                    self._consume()
            self._consume()
        # 支持 Cypy 风格的 class Name extends Parent: 语法
        elif self._current().type == TokenType.EXTENDS:
            self._consume()
            bases = self._parse_type_list()
        self._expect(TokenType.COLON)
        self._push_scope("class")
        body = self._parse_block()
        self._pop_scope()
        return ClassDef(name_token.value, bases, body, name_token.line, name_token.col, is_cdef=is_cdef)

    def _parse_struct_def(self, decorators: List[Any] = None) -> StructDef:
        self._consume(TokenType.STRUCT)
        name_token = self._consume(TokenType.IDENTIFIER)
        self._require_module_level("struct", name_token)
        
        generic_params = []
        generic_constraints = {}
        # 统一使用尖括号 <>（与 LZ 语法对齐）
        if self._current().type == TokenType.LT:
            self._consume()
            if self._current().type == TokenType.GT:
                raise ValueError(f"Generic parameter list cannot be empty at {name_token.line}:{name_token.col}")
            while self._current().type != TokenType.GT:
                param_name = self._consume(TokenType.IDENTIFIER).value
                generic_params.append(param_name)
                # 检查是否有约束
                if self._current().type == TokenType.COLON:
                    self._consume()
                    constraint_type = self._parse_type()
                    generic_constraints[param_name] = constraint_type
                if self._current().type == TokenType.COMMA:
                    self._consume()
            self._consume()
        
        self._expect(TokenType.COLON)
        self._expect(TokenType.INDENT)
        fields = []
        methods = []
        while self._current().type not in (TokenType.DEDENT, TokenType.EOF):
            if self._current().type == TokenType.NEWLINE:
                self._consume()
                continue
            # 如果是 DEF，解析为方法
            if self._current().type == TokenType.DEF:
                method = self._parse_func_def()
                methods.append(method)
                continue
            # 跳过 pass 语句
            if self._current().type == TokenType.PASS:
                self._consume()
                continue
            # 否则解析为字段（支持 let 关键字）
            is_let = False
            if self._current().type == TokenType.LET:
                self._consume()
                is_let = True
            field_name_token = self._consume(TokenType.IDENTIFIER)
            type_annotation = None
            default_value = None
            if self._current().type == TokenType.COLON:
                self._consume()
                type_annotation = self._parse_type()
                # 检查是否有默认值
                if self._current().type == TokenType.ASSIGN:
                    self._consume()
                    default_value = self._parse_expression()
            elif self._current().type == TokenType.ASSIGN:
                # 没有类型注解但有默认值
                self._consume()
                default_value = self._parse_expression()
            fields.append(StructField(field_name_token.value, type_annotation, False, default_value, field_name_token.line, field_name_token.col))
            if self._current().type == TokenType.NEWLINE:
                self._consume()
        if self._current().type == TokenType.DEDENT:
            self._consume()
        return StructDef(name_token.value, fields, generic_params, generic_constraints, name_token.line, name_token.col, methods, decorators)

    def _parse_enum_def(self) -> EnumDef:
        self._consume(TokenType.ENUM)
        name_token = self._consume(TokenType.IDENTIFIER)
        self._require_module_level("enum", name_token)
        self._expect(TokenType.COLON)
        self._expect(TokenType.INDENT)
        variants = []
        while self._current().type not in (TokenType.DEDENT, TokenType.EOF):
            if self._current().type == TokenType.NEWLINE:
                self._consume()
                continue
            variant_name_token = self._consume(TokenType.IDENTIFIER)
            value = None
            if self._current().type == TokenType.ASSIGN:
                self._consume()
                value = self._parse_expression()
            variants.append(EnumVariant(variant_name_token.value, value, variant_name_token.line, variant_name_token.col))
            if self._current().type == TokenType.NEWLINE:
                self._consume()
        if self._current().type == TokenType.DEDENT:
            self._consume()
        return EnumDef(name_token.value, variants, name_token.line, name_token.col)

    def _parse_trait_def(self) -> TraitDef:
        self._consume(TokenType.TRAIT)
        name_token = self._consume(TokenType.IDENTIFIER)
        self._require_module_level("trait", name_token)
        
        generic_params = []
        if self._current().type == TokenType.LT:
            self._consume()
            while self._current().type != TokenType.GT:
                param_name = self._consume(TokenType.IDENTIFIER).value
                generic_params.append(param_name)
                if self._current().type == TokenType.COMMA:
                    self._consume()
            self._consume()
        
        super_traits = []
        if self._current().type == TokenType.EXTENDS:
            self._consume()
            super_traits = self._parse_type_list()
        
        self._expect(TokenType.COLON)
        methods = self._parse_block(signature_only=True)
        return TraitDef(name_token.value, methods, generic_params, super_traits, name_token.line, name_token.col)

    def _parse_typeclass_def(self) -> TypeClassDef:
        """解析 TypeClass 定义
        
        语法:
            typeclass TypeClassName:
                def method_name(self) -> return_type
        
        支持泛型:
            typeclass Container<T>:
                def get(self) -> T
                def put(self, value: T) -> None
        """
        self._consume(TokenType.TYPECLASS)
        name_token = self._consume(TokenType.IDENTIFIER)
        self._require_module_level("typeclass", name_token)
        
        generic_params = []
        generic_constraints = {}
        
        # 解析泛型参数
        if self._current().type == TokenType.LT:
            self._consume()
            while self._current().type != TokenType.GT:
                param_name = self._consume(TokenType.IDENTIFIER).value
                generic_params.append(param_name)
                
                # 解析泛型约束 (如 T: BoundType 或 T: A & B)
                if self._current().type == TokenType.COLON:
                    self._consume()
                    constraints = []
                    while self._current().type not in (TokenType.COMMA, TokenType.GT):
                        constraints.append(self._parse_type())
                        if self._current().type == TokenType.AND:
                            self._consume()
                    generic_constraints[param_name] = constraints if len(constraints) > 1 else (constraints[0] if constraints else None)
                
                if self._current().type == TokenType.COMMA:
                    self._consume()
            self._consume()  # 消耗 GT
        
        self._expect(TokenType.COLON)
        methods = self._parse_block(signature_only=True)
        return TypeClassDef(name_token.value, methods, generic_params, generic_constraints, name_token.line, name_token.col)

    def _parse_suite_stmt(self) -> SuiteDef:
        """解析测试套件定义 - 参照 lang-zone/hermes 设计
        
        语法:
            suite SuiteName:
                test test_name:
                    assert ...
                setup:
                    ...
                teardown:
                    ...
        """
        self._consume(TokenType.SUITE)
        name_token = self._consume(TokenType.IDENTIFIER)
        self._require_module_level("suite", name_token)
        
        self._expect(TokenType.COLON)
        
        self._push_scope("suite")
        body = self._parse_block()
        self._pop_scope()
        
        return SuiteDef(name_token.value, body, name_token.line, name_token.col)

    def _parse_test_stmt(self) -> TestDef:
        """解析测试用例定义 - 参照 lang-zone/hermes 设计
        
        语法:
            test test_name:
                assert ...
        """
        self._consume(TokenType.TEST)
        name_token = self._consume(TokenType.IDENTIFIER)
        
        self._expect(TokenType.COLON)
        
        body = self._parse_block()
        
        return TestDef(name_token.value, body, name_token.line, name_token.col)

    def _parse_setup_stmt(self) -> SetupStmt:
        """解析测试套件初始化块"""
        token = self._consume(TokenType.SETUP)
        line = token.line
        col = token.col
        
        self._expect(TokenType.COLON)
        
        body = self._parse_block()
        
        return SetupStmt(body, line, col)

    def _parse_teardown_stmt(self) -> TeardownStmt:
        """解析测试套件清理块"""
        token = self._consume(TokenType.TEARDOWN)
        line = token.line
        col = token.col
        
        self._expect(TokenType.COLON)
        
        body = self._parse_block()
        
        return TeardownStmt(body, line, col)

    def _parse_let_stmt(self) -> LetStmt:
        self._consume(TokenType.LET)
        
        # 支持解构绑定：let (x, y) = ... 或 let [a, b] = ...
        token = self._current()
        if token.type in (TokenType.LPAREN, TokenType.LBRACKET, TokenType.LBRACE):
            # 解析解构模式
            target = self._parse_pattern()
            line, col = token.line, token.col
        else:
            # 普通变量声明
            name_token = self._consume(TokenType.IDENTIFIER)
            target = name_token.value
            line, col = name_token.line, name_token.col
        
        type_annotation = None
        if self._current().type == TokenType.COLON:
            self._consume()
            type_annotation = self._parse_type()
        value = None
        if self._current().type == TokenType.ASSIGN:
            self._consume()
            value = self._parse_expression()
        # 允许 NEWLINE 或 DEDENT（在块末尾时）
        if self._current().type == TokenType.NEWLINE:
            self._consume()
        elif self._current().type == TokenType.DEDENT:
            # 块末尾，不消费DEDENT，留给外层处理
            pass
        else:
            self._expect(TokenType.NEWLINE)
        # let 声明的是不可变变量
        return LetStmt(target, type_annotation, value, False, False, False, line, col)

    def _parse_mut_stmt(self) -> LetStmt:
        self._consume(TokenType.MUT)
        name_token = self._consume(TokenType.IDENTIFIER)
        type_annotation = None
        if self._current().type == TokenType.COLON:
            self._consume()
            type_annotation = self._parse_type()
        value = None
        if self._current().type == TokenType.ASSIGN:
            self._consume()
            value = self._parse_expression()
        # 允许 NEWLINE 或 DEDENT（在块末尾时）
        if self._current().type == TokenType.NEWLINE:
            self._consume()
        elif self._current().type == TokenType.DEDENT:
            # 块末尾，不消费DEDENT，留给外层处理
            pass
        else:
            self._expect(TokenType.NEWLINE)
        return LetStmt(name_token.value, type_annotation, value, True, False, False, name_token.line, name_token.col)

    def _parse_owned_stmt(self) -> LetStmt:
        """解析 owned 声明 - LZ风格的所有权语义，使用弱引用实现"""
        self._consume(TokenType.OWNED)
        name_token = self._consume(TokenType.IDENTIFIER)
        type_annotation = None
        if self._current().type == TokenType.COLON:
            self._consume()
            type_annotation = self._parse_type()
        value = None
        if self._current().type == TokenType.ASSIGN:
            self._consume()
            value = self._parse_expression()
        if self._current().type == TokenType.NEWLINE:
            self._consume()
        elif self._current().type == TokenType.DEDENT:
            pass
        else:
            self._expect(TokenType.NEWLINE)
        return LetStmt(name_token.value, type_annotation, value, True, False, is_owned=True, line=name_token.line, col=name_token.col)

    def _parse_const_stmt(self) -> LetStmt:
        """解析 const 声明 - 编译期常量，值在编译时展开"""
        self._consume(TokenType.CONST)
        name_token = self._consume(TokenType.IDENTIFIER)
        type_annotation = None
        if self._current().type == TokenType.COLON:
            self._consume()
            type_annotation = self._parse_type()
        value = None
        if self._current().type == TokenType.ASSIGN:
            self._consume()
            value = self._parse_expression()
        if self._current().type == TokenType.NEWLINE:
            self._consume()
        # const 声明的是编译期常量（不可变）
        return LetStmt(name_token.value, type_annotation, value, False, is_const=True, is_owned=False, line=name_token.line, col=name_token.col)

    def _parse_typed_var(self, mutable: bool = True) -> LetStmt:
        name_token = self._consume(TokenType.IDENTIFIER)
        self._consume(TokenType.COLON)
        type_annotation = self._parse_type()
        value = None
        if self._current().type == TokenType.ASSIGN:
            self._consume()
            value = self._parse_expression()
        if self._current().type == TokenType.NEWLINE:
            self._consume()
        return LetStmt(name_token.value, type_annotation, value, mutable, is_const=False, is_owned=False, line=name_token.line, col=name_token.col)

    def _parse_return_stmt(self) -> ReturnStmt:
        self._consume(TokenType.RETURN)
        value = None
        if self._current().type not in (TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF):
            value = self._parse_expression()
        if self._current().type == TokenType.NEWLINE:
            self._consume()
        return ReturnStmt(value, self._current().line, self._current().col)

    def _parse_yield_stmt(self) -> YieldStmt:
        self._consume(TokenType.YIELD)
        value = None
        is_from = False
        if self._current().type == TokenType.FROM:
            self._consume()
            is_from = True
            value = self._parse_expression()
        elif self._current().type not in (TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF):
            value = self._parse_expression()
        if self._current().type == TokenType.NEWLINE:
            self._consume()
        return YieldStmt(value, is_from, self._current().line, self._current().col)

    def _parse_assert_stmt(self) -> AssertStmt:
        self._consume(TokenType.ASSERT)
        test = self._parse_expression()
        msg = None
        if self._current().type == TokenType.COMMA:
            self._consume()
            msg = self._parse_expression()
        if self._current().type == TokenType.NEWLINE:
            self._consume()
        return AssertStmt(test, msg, self._current().line, self._current().col)

    def _parse_with_stmt(self) -> WithStmt:
        """解析 with 语句（上下文管理器）
        
        语法：
        with expr as var:
            body
        
        或多上下文：
        with expr1 as var1, expr2 as var2:
            body
        """
        self._consume(TokenType.WITH)
        
        items = []
        while True:
            # 解析上下文表达式（标记 _in_with，避免 `as` 被当作类型转换消费）
            self._in_with = True
            expr = self._parse_expression()
            self._in_with = False
            
            # 可选的 as var
            var = None
            if self._current().type == TokenType.AS:
                self._consume()
                var_token = self._consume(TokenType.IDENTIFIER)
                var = Name(var_token.value, var_token.line, var_token.col)
            
            items.append((expr, var))
            
            # 是否有多个上下文
            if self._current().type != TokenType.COMMA:
                break
            self._consume()
        
        self._expect(TokenType.COLON)
        body = self._parse_block()
        
        return WithStmt(items, body, self._current().line, self._current().col)

    def _parse_decorator(self) -> Decorator:
        self._consume(TokenType.AT)
        
        # 特殊处理关键字作为装饰器
        if self._current().type == TokenType.TEST:
            name_token = self._consume()
            name = Name(name_token.value, name_token.line, name_token.col)
        else:
            name = self._parse_expression()
        
        args = []
        
        # 如果 name 是 Call 节点，参数已经在 Call 节点的 args 中
        if hasattr(name, 'kind') and name.kind == "Call":
            args = name.args
            name = name.func
        elif self._current().type == TokenType.LPAREN:
            # 处理 @decorator(args) 形式
            self._consume()
            while self._current().type != TokenType.RPAREN:
                args.append(self._parse_expression())
                if self._current().type == TokenType.COMMA:
                    self._consume()
            self._consume()  # consume RPAREN
        
        if self._current().type == TokenType.NEWLINE:
            self._consume()
        return Decorator(name, args, self._current().line, self._current().col)

    def _parse_match_stmt(self) -> MatchStmt:
        """解析 match/case 模式匹配语句
        语法：
        match expr:
            case pattern1:
                body1
            case pattern2 if condition:
                body2
            else:
                body_else
        """
        self._consume(TokenType.MATCH)
        subject = self._parse_expression()
        self._expect(TokenType.COLON)
        self._expect(TokenType.INDENT)
        
        cases = []
        orelse = None
        
        while self._current().type not in (TokenType.DEDENT, TokenType.EOF):
            if self._current().type == TokenType.NEWLINE:
                self._consume()
                continue
            
            if self._current().type == TokenType.CASE:
                self._consume()
                pattern = self._parse_pattern_with_or()
                
                # 支持隐式元组模式：case x, y:
                if self._current().type == TokenType.COMMA:
                    patterns = [pattern]
                    while self._current().type == TokenType.COMMA:
                        self._consume()
                        patterns.append(self._parse_pattern_with_or())
                    pattern = patterns
                
                # 支持 case pattern as name 语法
                if self._current().type == TokenType.AS:
                    self._consume()
                    name_token = self._consume(TokenType.IDENTIFIER)
                    pattern = AsPattern(pattern, name_token.value, name_token.line, name_token.col)
                
                # 支持 case pattern if condition 语法
                if self._current().type == TokenType.IF:
                    self._consume()
                    condition = self._parse_expression()
                    # 将条件包装到 pattern 中
                    pattern = {"pattern": pattern, "condition": condition}
                
                self._expect(TokenType.COLON)
                body = self._parse_block()
                cases.append(CaseClause(pattern, body, self._current().line, self._current().col))
            
            elif self._current().type == TokenType.ELSE:
                self._consume()
                self._expect(TokenType.COLON)
                orelse = self._parse_block()
            
            else:
                raise ValueError(f"Unexpected token {self._current().type} in match statement at {self._current().line}:{self._current().col}")
        
        # match 语句的 DEDENT 已经在最后一个 case/else 的 _parse_block 中消费了
        if self._current().type == TokenType.DEDENT:
            self._consume()
        return MatchStmt(subject, cases, orelse, self._current().line, self._current().col)
    
    def _parse_match_expr(self) -> MatchExpr:
        """解析 match 表达式（返回值形式）
        
        match 表达式使用与 match 语句类似的语法，但 case 体是单个表达式：
        match x:
            case 1: "one"
            case 2: "two"
            case _: "other"
        """
        self._consume(TokenType.MATCH)
        subject = self._parse_expression()
        self._expect(TokenType.COLON)
        
        # 匹配表达式必须在一行或缩进块中
        # 处理 INDENT（如果有）和 NEWLINE
        if self._current().type == TokenType.INDENT:
            self._consume()
        if self._current().type == TokenType.NEWLINE:
            self._consume()
        
        cases = []
        
        while self._current().type not in (TokenType.DEDENT, TokenType.EOF, TokenType.RBRACE, TokenType.RPAREN, TokenType.RBRACKET):
            if self._current().type == TokenType.NEWLINE:
                self._consume()
                continue
            
            if self._current().type == TokenType.CASE:
                self._consume()
                pattern = self._parse_pattern_with_or()
                
                # 支持 case pattern if condition 语法
                if self._current().type == TokenType.IF:
                    self._consume()
                    condition = self._parse_expression()
                    pattern = {"pattern": pattern, "condition": condition}
                
                self._expect(TokenType.COLON)
                
                # match 表达式的 case 体是单个表达式
                # 简单处理：直接解析下一个 token，如果是字符串/数字等直接使用
                # 如果是 CASE，则说明上一个 case 没有 body（语法错误，但我们允许空 body）
                body = []
                if self._current().type not in (TokenType.CASE, TokenType.DEDENT, TokenType.EOF):
                    # 设置停止 token，让表达式解析器在 CASE、DEDENT、EOF、换行、return 处停止
                    old_stop_tokens = getattr(self, '_stop_tokens', None)
                    self._stop_tokens = {TokenType.CASE, TokenType.DEDENT, TokenType.EOF,
                                         TokenType.RBRACKET, TokenType.NEWLINE, TokenType.RETURN}
                    try:
                        body_expr = self._parse_simple_expression()
                        body = [body_expr]
                    except StopExpressionParsing:
                        # 遇到停止 token，说明上一个 case 已经结束
                        pass
                    finally:
                        self._stop_tokens = old_stop_tokens
                
                # 如果后面是换行且下一个 token 是 CASE，继续解析
                if self._current().type == TokenType.NEWLINE:
                    self._consume()
                
                cases.append(CaseClause(pattern, body, self._current().line, self._current().col))
            else:
                break
        
        # 消费 case 块结束的 DEDENT（与 match 语句形式一致，避免父级语句块提前结束）
        if self._current().type == TokenType.DEDENT:
            self._consume()
        
        return MatchExpr(subject, cases, self._current().line, self._current().col)
    
    def _parse_pattern(self) -> Any:
        """解析匹配模式"""
        token = self._current()
        
        # **rest 剩余绑定模式（顶层）
        if token.type == TokenType.POW:
            self._consume()
            name_token = self._consume(TokenType.IDENTIFIER)
            return DictPattern([], name_token.value, token.line, token.col)
        
        # 切片模式：.. 或 ..var
        if token.type == TokenType.DOT_DOT:
            self._consume()
            line = token.line
            col = token.col
            # 检查后面是否跟变量名（..var）
            if self._current().type == TokenType.IDENTIFIER:
                name_token = self._consume()
                return SlicePattern(name_token.value, line, col)
            # 单独的 ..（忽略剩余元素）
            return SlicePattern(None, line, col)
        
        # 通配符模式：_
        if token.type == TokenType.IDENTIFIER and token.value == "_":
            self._consume()
            return Name("_", token.line, token.col)
        
        # 常量模式：字面量
        if token.type == TokenType.INTEGER:
            self._consume()
            # 使用 base 0 自动识别进制（0x=十六进制, 0b=二进制, 0o=八进制）
            lower = Constant(int(token.value, 0), token.line, token.col)
            # 检查是否是范围模式：1..10
            if self._current().type == TokenType.DOT_DOT:
                self._consume()
                upper_token = self._current()
                if upper_token.type == TokenType.INTEGER:
                    self._consume()
                    upper = Constant(int(upper_token.value, 0), upper_token.line, upper_token.col)
                    return RangePattern(lower, upper, token.line, token.col)
                elif upper_token.type == TokenType.FLOAT:
                    self._consume()
                    upper = Constant(float(upper_token.value), upper_token.line, upper_token.col)
                    return RangePattern(lower, upper, token.line, token.col)
            return lower
        if token.type == TokenType.FLOAT:
            self._consume()
            lower = Constant(float(token.value), token.line, token.col)
            # 检查是否是范围模式：1.5..10.5
            if self._current().type == TokenType.DOT_DOT:
                self._consume()
                upper_token = self._current()
                if upper_token.type == TokenType.INTEGER:
                    self._consume()
                    upper = Constant(int(upper_token.value, 0), upper_token.line, upper_token.col)
                    return RangePattern(lower, upper, token.line, token.col)
                elif upper_token.type == TokenType.FLOAT:
                    self._consume()
                    upper = Constant(float(upper_token.value), upper_token.line, upper_token.col)
                    return RangePattern(lower, upper, token.line, token.col)
            return lower
        if token.type == TokenType.STRING:
            self._consume()
            # 保留字符串的前缀（如 f-string 的 'f', 'F', 'rf', 'fr'）
            prefix = getattr(token, 'prefix', None)
            if prefix:
                return Constant(token.value, token.line, token.col, prefix=prefix)
            return Constant(token.value, token.line, token.col)
        if token.type == TokenType.TRUE:
            self._consume()
            return Constant(True, token.line, token.col)
        if token.type == TokenType.FALSE:
            self._consume()
            return Constant(False, token.line, token.col)
        
        # 变量模式：标识符（模式绑定）
        if token.type == TokenType.IDENTIFIER:
            self._consume()
            # 如果后面跟着 .，说明是限定名（如 Color.Red），解析为属性访问
            if self._current().type == TokenType.DOT:
                attr_expr = Name(token.value, token.line, token.col)
                while self._current().type == TokenType.DOT:
                    self._consume()
                    attr_name = self._consume(TokenType.IDENTIFIER).value
                    attr_expr = Attribute(
                        value=attr_expr,
                        attr=attr_name,
                        line=token.line,
                        col=token.col
                    )
                return attr_expr
            # 如果后面跟着 {，说明是结构体模式（如 Point { x, y }）
            if self._current().type == TokenType.LBRACE:
                self._consume()
                fields = []
                has_ellipsis = False
                while self._current().type != TokenType.RBRACE:
                    if self._current().type == TokenType.NEWLINE:
                        self._consume()
                        continue
                    if self._current().type == TokenType.DOT_DOT:
                        has_ellipsis = True
                        self._consume()
                        continue
                    if self._current().type == TokenType.COMMA:
                        self._consume()
                        continue
                    
                    field_name_token = self._consume(TokenType.IDENTIFIER)
                    field_name = field_name_token.value
                    
                    # 检查是否是 field: pattern 形式（绑定到自定义变量名）
                    if self._current().type == TokenType.COLON:
                        self._consume()
                        pattern = self._parse_pattern()
                    else:
                        # 默认绑定到同名变量
                        pattern = Pattern(field_name, field_name_token.line, field_name_token.col)
                    
                    fields.append((field_name, pattern))
                    
                    if self._current().type == TokenType.COMMA:
                        self._consume()
                
                self._consume()  # 消费 RBRACE
                return StructPattern(token.value, fields, has_ellipsis, token.line, token.col)
            
            # 检查是否是提取器模式：case TypeName(pattern1, pattern2, ...)
            # 参考Scala的unapply提取器，如 Email(user, domain)
            if self._current().type == TokenType.LPAREN:
                self._consume()
                args = []
                while self._current().type != TokenType.RPAREN:
                    if self._current().type == TokenType.COMMA:
                        self._consume()
                        continue
                    if self._current().type == TokenType.NEWLINE:
                        self._consume()
                        continue
                    # 解析提取器参数（模式）
                    arg_pattern = self._parse_pattern_with_or()
                    args.append(arg_pattern)
                self._consume()  # 消费 RPAREN
                return ExtractorPattern(token.value, args, token.line, token.col)
            
            # 检查是否是类型模式：case TypeName variable:
            # 如果后面跟着另一个标识符，则是类型模式（如 int x, str s, Point p）
            if self._current().type == TokenType.IDENTIFIER:
                name_token = self._consume()
                return TypePattern(token.value, name_token.value, token.line, token.col)
            
            return Pattern(token.value, token.line, token.col)
        
        # 字典模式：{"key": value, "key2": value2, **rest}
        if token.type == TokenType.LBRACE:
            self._consume()
            pairs = []
            rest_name = None
            while self._current().type != TokenType.RBRACE:
                if self._current().type == TokenType.NEWLINE:
                    self._consume()
                    continue
                if self._current().type == TokenType.COMMA:
                    self._consume()
                    continue
                
                # 检查是否是 **rest 剩余绑定
                if self._current().type == TokenType.POW:
                    self._consume()
                    name_token = self._consume(TokenType.IDENTIFIER)
                    rest_name = name_token.value
                    continue
                
                # 解析键（字符串字面量或标识符）
                key = self._parse_pattern()
                
                # 冒号分隔键值
                self._expect(TokenType.COLON)
                
                # 解析值模式
                value = self._parse_pattern()
                
                pairs.append((key, value))
                
                if self._current().type == TokenType.COMMA:
                    self._consume()
            
            self._consume()  # 消费 RBRACE
            return DictPattern(pairs, rest_name, token.line, token.col)
        
        # 列表模式：[pattern1, pattern2, ...]
        if token.type == TokenType.LBRACKET:
            self._consume()
            patterns = []
            rest_name = None
            while self._current().type != TokenType.RBRACKET:
                # 支持 *rest 剩余绑定
                if self._current().type == TokenType.MUL:
                    self._consume()
                    rest_token = self._consume(TokenType.IDENTIFIER)
                    rest_name = rest_token.value
                    # 将 *rest 表示为 SlicePattern 元素，保留其在列表中的位置
                    patterns.append(SlicePattern(rest_token.value, token.line, token.col))
                    # 跳过逗号（如果有）
                    if self._current().type == TokenType.COMMA:
                        self._consume()
                    continue
                patterns.append(self._parse_pattern())
                if self._current().type == TokenType.COMMA:
                    self._consume()
            self._consume()
            return ArrayPattern(patterns, rest_name, token.line, token.col)
        
        # 元组模式：(pattern1, pattern2, ...)
        if token.type == TokenType.LPAREN:
            self._consume()
            patterns = []
            while self._current().type != TokenType.RPAREN:
                patterns.append(self._parse_pattern())
                if self._current().type == TokenType.COMMA:
                    self._consume()
            self._consume()
            return patterns
        
        raise ValueError(f"Unexpected pattern token {token.type} at {token.line}:{token.col}")
    
    def _parse_pattern_with_or(self) -> Any:
        """解析支持 OR 的模式（pattern1 | pattern2 | ...）"""
        left = self._parse_pattern()
        
        # 支持 OR 模式：pattern1 | pattern2 | pattern3
        while self._current().type == TokenType.PIPE:
            self._consume()
            right = self._parse_pattern()
            if isinstance(left, dict) and "or" in left:
                left["or"].append(right)
            else:
                left = {"or": [left, right]}
        
        return left
    
    def _parse_if_stmt(self, is_elif: bool = False) -> IfStmt:
        if not is_elif:
            self._consume(TokenType.IF)
        else:
            self._consume(TokenType.ELIF)
        test = self._parse_expression()
        self._expect(TokenType.COLON)
        self._push_scope("if")
        body = self._parse_block()
        self._pop_scope()
        orelse = None
        if self._current().type == TokenType.ELIF:
            orelse = [self._parse_if_stmt(is_elif=True)]
        elif self._current().type == TokenType.ELSE:
            self._consume()
            self._expect(TokenType.COLON)
            self._push_scope("if")
            orelse = self._parse_block()
            self._pop_scope()
        return IfStmt(test, body, orelse, self._current().line, self._current().col)

    def _parse_for_stmt(self) -> ForStmt:
        self._consume(TokenType.FOR)
        # 使用 _parse_bitwise_or() 来解析目标，避免 IN 运算符的干扰
        target = self._parse_bitwise_or()
        self._expect(TokenType.IN)
        iter = self._parse_expression()
        self._expect(TokenType.COLON)
        self._push_scope("for")
        body = self._parse_block()
        self._pop_scope()
        return ForStmt(target, iter, body, self._current().line, self._current().col)

    def _parse_while_stmt(self) -> WhileStmt:
        self._consume(TokenType.WHILE)
        test = self._parse_expression()
        self._expect(TokenType.COLON)
        self._push_scope("while")
        body = self._parse_block()
        self._pop_scope()
        return WhileStmt(test, body, self._current().line, self._current().col)

    def _parse_break_stmt(self) -> BreakStmt:
        self._consume(TokenType.BREAK)
        if self._current().type == TokenType.NEWLINE:
            self._consume()
        return BreakStmt()

    def _parse_del_stmt(self) -> DelStmt:
        self._consume(TokenType.DEL)
        targets = []
        while True:
            targets.append(self._parse_expression())
            if self._current().type == TokenType.COMMA:
                self._consume()
            else:
                break
        if self._current().type == TokenType.NEWLINE:
            self._consume()
        return DelStmt(targets)

    def _parse_continue_stmt(self) -> ContinueStmt:
        self._consume(TokenType.CONTINUE)
        if self._current().type == TokenType.NEWLINE:
            self._consume()
        return ContinueStmt()

    def _parse_global_stmt(self) -> GlobalStmt:
        token = self._consume(TokenType.GLOBAL)
        names = [self._consume(TokenType.IDENTIFIER).value]
        while self._current().type == TokenType.COMMA:
            self._consume()
            names.append(self._consume(TokenType.IDENTIFIER).value)
        if self._current().type == TokenType.NEWLINE:
            self._consume()
        return GlobalStmt(names, token.line, token.col)

    def _parse_nonlocal_stmt(self) -> NonlocalStmt:
        token = self._consume(TokenType.NONLOCAL)
        names = [self._consume(TokenType.IDENTIFIER).value]
        while self._current().type == TokenType.COMMA:
            self._consume()
            names.append(self._consume(TokenType.IDENTIFIER).value)
        if self._current().type == TokenType.NEWLINE:
            self._consume()
        return NonlocalStmt(names, token.line, token.col)
    
    def _parse_try_stmt(self) -> TryStmt:
        """解析 try/except/finally 语句"""
        self._consume(TokenType.TRY)
        self._expect(TokenType.COLON)
        
        # 解析 try 块
        self._push_scope("try")
        body = self._parse_block()
        self._pop_scope()
        
        # 解析 except 子句
        handlers = []
        while self._current().type == TokenType.EXCEPT:
            self._consume()
            exc_type = None
            exc_name = None
            
            # except [type] [as name]:
            if self._current().type == TokenType.IDENTIFIER:
                parsed = self._parse_expression()
                # `except Type as var` 可能被表达式解析器当作 CastExpr(Type, var) 处理，
                # 这里解包以正确取得异常类型与捕获变量名
                if getattr(parsed, 'kind', None) == 'CastExpr':
                    exc_type = parsed.value
                    tgt = parsed.target_type
                    exc_name = tgt.id if hasattr(tgt, 'id') else tgt
                else:
                    exc_type = parsed
                    if self._current().type == TokenType.AS:
                        self._consume()
                        name_token = self._expect(TokenType.IDENTIFIER)
                        exc_name = name_token.value
            
            self._expect(TokenType.COLON)
            self._push_scope("except")
            except_body = self._parse_block()
            self._pop_scope()
            
            handlers.append((exc_type, exc_name, except_body))
        
        # 解析 finally 子句
        orelse = []
        if self._current().type == TokenType.FINALLY:
            self._consume()
            self._expect(TokenType.COLON)
            self._push_scope("finally")
            orelse = self._parse_block()
            self._pop_scope()
        
        return TryStmt(body, handlers, orelse, self._current().line, self._current().col)
    
    def _parse_raise_stmt(self) -> RaiseStmt:
        """解析 raise 语句"""
        self._consume(TokenType.RAISE)
        exc = None
        cause = None
        
        # 只有当后面不是 NEWLINE/DEDENT/EOF 时才解析表达式
        if self._current().type not in (TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF):
            exc = self._parse_expression()
            # raise exc from cause
            if self._current().type == TokenType.FROM:
                self._consume()
                cause = self._parse_expression()
        
        # 允许 NEWLINE（不消费DEDENT，留给外层处理）
        if self._current().type == TokenType.NEWLINE:
            self._consume()
        
        return RaiseStmt(exc, cause, self._current().line, self._current().col)

    def _parse_defer_stmt(self) -> DeferStmt:
        self._consume(TokenType.DEFER)
        self._require_function_scope("defer", self._current())
        
        # 支持两种形式：
        # 1. defer free(ptr)  - 单行形式
        # 2. defer:          - 块形式
        #       free(ptr)
        if self._current().type == TokenType.COLON:
            self._consume()
            body = self._parse_block()
        else:
            # 单行形式：解析表达式直到换行
            expr = self._parse_expression()
            body = [expr]
            # 消费换行符
            if self._current().type == TokenType.NEWLINE:
                self._consume()
        
        return DeferStmt(body, self._current().line, self._current().col)

    def _parse_guard_stmt(self) -> GuardStmt:
        """解析 guard 守卫表达式语句
        
        支持三种语法形式：
        1. 单行语法：guard cond else expr（无冒号，隐式返回 expr）
        2. 多行语法：guard cond else:\n    expr（有冒号，换行块体）
        3. guard let 绑定：guard let Some(v) = opt else expr
        
        else 后的值隐式返回，不需要 return 关键字
        """
        self._consume(TokenType.GUARD)
        self._require_function_scope("guard", self._current())
        
        is_let = False
        let_target = None
        
        # 检查是否是 guard let 形式
        if self._current().type == TokenType.LET:
            is_let = True
            self._consume()
            # 解析 let 绑定目标
            let_target = self._parse_expression()
            # 期望 = 符号
            self._expect(TokenType.ASSIGN)
        
        # 解析条件表达式
        test = self._parse_expression()
        
        # 期望 else 关键字
        self._expect(TokenType.ELSE)
        
        # 判断是单行还是多行形式
        if self._current().type == TokenType.COLON:
            # 多行形式：else: 换行块体
            self._consume()
            orelse = self._parse_block()
        else:
            # 单行形式：else expr 或 else break/continue/return
            # 检查是否是控制流语句
            if self._current().type == TokenType.BREAK:
                self._consume()
                orelse = BreakStmt(self._current().line, self._current().col)
            elif self._current().type == TokenType.CONTINUE:
                self._consume()
                orelse = ContinueStmt(self._current().line, self._current().col)
            elif self._current().type == TokenType.RETURN:
                self._consume()
                # return 可能有返回值
                if self._current().type not in [TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF]:
                    return_value = self._parse_expression()
                    orelse = ReturnStmt(return_value, self._current().line, self._current().col)
                else:
                    orelse = ReturnStmt(None, self._current().line, self._current().col)
            else:
                # 普通表达式
                orelse = self._parse_expression()
            
            # 消费换行符
            if self._current().type == TokenType.NEWLINE:
                self._consume()
        
        return GuardStmt(test, orelse, is_let, let_target, self._current().line, self._current().col)

    def _type_node_to_str(self, node) -> str:
        """将类型 AST 节点转换为源文本形式，如 GenericType(Wrapper, [T]) -> 'Wrapper<T>'"""
        if isinstance(node, str):
            return node
        if isinstance(node, Name):
            return node.id
        if hasattr(node, 'kind') and node.kind == 'GenericType':
            args = ', '.join(self._type_node_to_str(a) for a in getattr(node, 'args', []))
            return f"{getattr(node, 'name', '?')}<{args}>"
        return str(node)

    def _parse_impl_stmt(self) -> Any:
        """解析 impl 语句 - 支持 trait 实现和 TypeClass 实现
        
        语法:
            # Trait 实现
            impl TraitName for TypeName:
                ...
            
            # TypeClass 实现
            impl typeclass TypeClassName for TypeName:
                ...
        """
        self._consume(TokenType.IMPL)
        
        # 检查是否是 TypeClass 实现
        if self._current().type == TokenType.TYPECLASS:
            self._consume()  # 消耗 typeclass 关键字
            typeclass_name_token = self._consume(TokenType.IDENTIFIER)
            self._require_module_level("impl typeclass", typeclass_name_token)
            
            # 解析 TypeClass 泛型参数
            generic_params = []
            if self._current().type == TokenType.LT:
                self._consume()
                while self._current().type != TokenType.GT:
                    param_name = self._consume(TokenType.IDENTIFIER).value
                    generic_params.append(param_name)
                    if self._current().type == TokenType.COMMA:
                        self._consume()
                self._consume()
            
            # 消耗 for 关键字
            if self._current().type == TokenType.FOR_KW or self._current().type == TokenType.FOR:
                self._consume()
            
            # 解析目标类型（支持泛型，如 Box<T>）
            target_type_node = self._parse_type()
            # 提取目标类型名称（保留泛型参数，如 Wrapper<T>）
            target_type_name = self._type_node_to_str(target_type_node)
            
            self._expect(TokenType.COLON)
            methods = self._parse_block()
            return TypeClassImpl(
                typeclass_name_token.value, 
                target_type_name, 
                methods, 
                generic_params,
                typeclass_name_token.line, 
                typeclass_name_token.col
            )
        
        # 普通的 trait 实现
        trait_name_token = self._consume(TokenType.IDENTIFIER)
        self._require_module_level("impl", trait_name_token)
        
        trait_generic_args = []
        if self._current().type == TokenType.LT:
            self._consume()
            while self._current().type != TokenType.GT:
                trait_generic_args.append(self._parse_type())
                if self._current().type == TokenType.COMMA:
                    self._consume()
            self._consume()
        
        if self._current().type == TokenType.FOR_KW or self._current().type == TokenType.FOR:
            self._consume()
        for_type = self._parse_type()
        self._expect(TokenType.COLON)
        methods = self._parse_block()
        return ImplStmt(trait_name_token.value, trait_generic_args, for_type, methods, trait_name_token.line, trait_name_token.col)

    def _parse_meta_block(self) -> MetaBlock:
        self._consume(TokenType.META)
        self._require_module_level("meta", self._current())
        self._expect(TokenType.COLON)
        body = []
        self._expect(TokenType.INDENT)
        while self._current().type not in (TokenType.DEDENT, TokenType.EOF):
            token = self._current()
            if token.type == TokenType.DUCK:
                body.append(self._parse_duck_def())
            elif token.type == TokenType.NEWLINE:
                self._consume()
            elif token.type == TokenType.PASS:
                self._consume()
            elif token.type in (TokenType.IF, TokenType.CONST, TokenType.DEF,
                               TokenType.LET, TokenType.MUT, TokenType.IDENTIFIER,
                               TokenType.META, TokenType.SETUP, TokenType.TEARDOWN):
                stmt = self._parse_statement()
                if stmt:
                    body.append(stmt)
            else:
                raise ValueError(f"Unexpected token {token.type} in meta block at {token.line}:{token.col}.")
        if self._current().type == TokenType.DEDENT:
            self._consume()
        return MetaBlock(body, 0, 0)

    def _parse_duck_def(self) -> DuckDef:
        """解析 duck 约束定义
        
        语法示例:
            duck Comparable:
                a < b -> bool
                a > b -> bool
            
            duck Container[T]:
                add(self, item: T) -> None
                len(self) -> int
        """
        self._consume(TokenType.DUCK)
        name_token = self._consume(TokenType.IDENTIFIER)

        # 解析可选的类型参数 <T, U>（统一使用尖括号）
        type_params = []
        if self._current().type == TokenType.LT:
            self._consume()  # <
            if self._current().type == TokenType.GT:
                raise ValueError(f"Generic parameter list cannot be empty at {name_token.line}:{name_token.col}")
            type_params.append(self._consume(TokenType.IDENTIFIER).value)
            while self._current().type == TokenType.COMMA:
                self._consume()
                type_params.append(self._consume(TokenType.IDENTIFIER).value)
            self._expect(TokenType.GT)
        
        self._expect(TokenType.COLON)
        self._expect(TokenType.INDENT)
        
        requirements = []
        while self._current().type not in (TokenType.DEDENT, TokenType.EOF):
            if self._current().type == TokenType.NEWLINE:
                self._consume()
                if self._current().type in (TokenType.DEDENT, TokenType.EOF):
                    break
                continue
            requirements.append(self._parse_duck_requirement())
        
        if self._current().type == TokenType.DEDENT:
            self._consume()
        
        return DuckDef(name_token.value, type_params, requirements, name_token.line, name_token.col)

    def _parse_duck_requirement(self) -> DuckRequirement:
        """解析单个约束项
        
        约束类型识别:
        1. 操作符: a < b -> bool, a + b -> Self
        2. 属性: name: str
        3. 方法: len(self) -> int, add(self, item: T) -> None
        4. 引用: Comparable (标识符)
        """
        first_token = self._current()

        # 处理一元操作符: -a -> Self
        if first_token.type == TokenType.MINUS:
            self._consume()  # -
            operand = self._consume(TokenType.IDENTIFIER).value
            return_type = None
            if self._current().type == TokenType.ARROW:
                self._consume()
                return_type = self._parse_simple_type()
            if self._current().type == TokenType.NEWLINE:
                self._consume()
            return DuckRequirement("operator", "-", [operand], return_type,
                                   is_unary=True,
                                   line=first_token.line, col=first_token.col)

        # 先读取第一个标识符
        if first_token.type != TokenType.IDENTIFIER:
            raise ValueError(f"Expected identifier in duck requirement at {first_token.line}:{first_token.col}")
        
        first_name = self._consume(TokenType.IDENTIFIER).value
        
        # 根据下一个 token 判断约束类型
        next_token = self._current()
        
        if next_token.type == TokenType.LPAREN:
            # 方法约束: method_name(params) -> return_type
            self._consume()  # (
            params = self._parse_duck_params()
            self._expect(TokenType.RPAREN)
            return_type = None
            if self._current().type == TokenType.ARROW:
                self._consume()
                return_type = self._parse_simple_type()
            if self._current().type == TokenType.NEWLINE:
                self._consume()
            return DuckRequirement("method", first_name, params, return_type, first_token.line, first_token.col)
        
        elif next_token.type == TokenType.COLON:
            # 属性约束: name: type
            self._consume()  # :
            attr_type = self._parse_simple_type()
            if self._current().type == TokenType.NEWLINE:
                self._consume()
            return DuckRequirement("attribute", first_name, [], attr_type, first_token.line, first_token.col)
        
        elif next_token.type == TokenType.LT:
            # 可能有歧义：Container<T>（引用约束带泛型）或 a < b -> bool（操作符约束）
            # 尝试先解析为引用约束的泛型参数
            saved_pos = self.pos
            try:
                self._consume()  # <
                generic_args = [self._consume(TokenType.IDENTIFIER).value]
                while self._current().type == TokenType.COMMA:
                    self._consume()
                    generic_args.append(self._consume(TokenType.IDENTIFIER).value)
                self._expect(TokenType.GT)
                # 成功解析为引用约束带泛型参数
                if self._current().type == TokenType.NEWLINE:
                    self._consume()
                return DuckRequirement("reference", first_name, [], None,
                                       generic_args=generic_args,
                                       line=first_token.line, col=first_token.col)
            except (ValueError, Exception):
                # 回退，按操作符约束解析
                self.pos = saved_pos

            # 操作符约束: a < b -> bool
            op = self._consume().value
            right_name = self._consume(TokenType.IDENTIFIER).value
            return_type = None
            if self._current().type == TokenType.ARROW:
                self._consume()
                return_type = self._parse_simple_type()
            if self._current().type == TokenType.NEWLINE:
                self._consume()
            return DuckRequirement("operator", op, [first_name, right_name], return_type, first_token.line, first_token.col)

        elif next_token.type in (TokenType.GT, TokenType.LE, TokenType.GE,
                                TokenType.EQ, TokenType.NE, TokenType.PLUS, TokenType.MINUS,
                                TokenType.MUL, TokenType.DIV):
            # 其他操作符约束: a > b -> bool, a + b -> Self, -a -> Self
            op = self._consume().value
            right_name = ""
            is_unary = False
            # 处理 <=> 飞船操作符 (LE + GT)
            if next_token.type == TokenType.LE and self._current().type == TokenType.GT:
                self._consume()
                op = "<=>"
            if next_token.type == TokenType.MINUS and self._current().type != TokenType.IDENTIFIER:
                is_unary = True
            else:
                right_name = self._consume(TokenType.IDENTIFIER).value
            return_type = None
            if self._current().type == TokenType.ARROW:
                self._consume()
                return_type = self._parse_simple_type()
            if self._current().type == TokenType.NEWLINE:
                self._consume()
            return DuckRequirement("operator", op, [first_name, right_name], return_type,
                                   is_unary=is_unary,
                                   line=first_token.line, col=first_token.col)

        elif next_token.type == TokenType.NEWLINE or next_token.type in (TokenType.DEDENT, TokenType.EOF):
            # 引用约束: Comparable (单独一行的标识符)
            if self._current().type == TokenType.NEWLINE:
                self._consume()
            return DuckRequirement("reference", first_name, [], None, first_token.line, first_token.col)
        
        else:
            raise ValueError(f"Unexpected token {next_token.type} in duck requirement at {next_token.line}:{next_token.col}")

    def _parse_duck_params(self) -> List[str]:
        """解析 duck 方法约束的参数列表
        
        格式: self, item: T, index: int
        返回参数名列表
        """
        params = []
        if self._current().type == TokenType.RPAREN:
            return params
        
        params.append(self._consume(TokenType.IDENTIFIER).value)
        # 可选的类型注解
        if self._current().type == TokenType.COLON:
            self._consume()
            self._parse_simple_type()  # 消费类型注解但不存储
        
        while self._current().type == TokenType.COMMA:
            self._consume()
            param_name = self._consume(TokenType.IDENTIFIER).value
            params.append(param_name)
            if self._current().type == TokenType.COLON:
                self._consume()
                self._parse_simple_type()  # 消费类型注解
        
        return params

    def _parse_simple_type(self) -> str:
        """解析简单类型 (用于 duck 约束中的类型注解)

        支持: str, int, bool, float, None, Self, Iterator, etc.
        """
        type_name = self._consume(TokenType.IDENTIFIER).value

        # 可选的泛型参数 <T>（统一使用尖括号）
        if self._current().type == TokenType.LT:
            self._consume()
            type_name += "<"
            type_name += self._consume(TokenType.IDENTIFIER).value
            while self._current().type == TokenType.COMMA:
                self._consume()
                type_name += ", " + self._consume(TokenType.IDENTIFIER).value
            self._expect(TokenType.GT)
            type_name += ">"

        return type_name

    def _parse_import(self) -> Import:
        self._consume(TokenType.IMPORT)
        module = self._parse_identifier()
        alias = None
        if self._current().type == TokenType.AS:
            self._consume()
            alias = self._parse_identifier()
        self._expect(TokenType.NEWLINE)
        return Import(module, alias, self._current().line, self._current().col)

    def _parse_from_import(self) -> FromImport:
        self._consume(TokenType.FROM)
        module = self._parse_identifier()
        self._expect(TokenType.IMPORT)
        names = []
        while self._current().type == TokenType.IDENTIFIER:
            names.append(self._consume().value)
            if self._current().type == TokenType.COMMA:
                self._consume()
            else:
                break
        self._expect(TokenType.NEWLINE)
        return FromImport(module, names, self._current().line, self._current().col)

    def _parse_type_alias(self) -> TypeAlias:
        self._consume(TokenType.TYPE)
        name_token = self._consume(TokenType.IDENTIFIER)
        
        # 支持泛型类型别名：type Maybe<T> = T | None
        # 统一使用尖括号 <>（与 LZ 语法对齐）
        generic_params = []
        if self._current().type == TokenType.LT:
            self._consume()
            # 检查空泛型参数列表
            if self._current().type == TokenType.GT:
                raise ValueError(f"Generic parameter list cannot be empty at {name_token.line}:{name_token.col}")
            while self._current().type != TokenType.GT:
                generic_params.append(self._consume(TokenType.IDENTIFIER).value)
                if self._current().type == TokenType.COMMA:
                    self._consume()
            self._consume()
        
        self._expect(TokenType.ASSIGN)
        target = self._parse_type()
        # 允许单行类型别名没有换行符（最后一行）
        if self._current().type == TokenType.NEWLINE:
            self._consume()
        return TypeAlias(name_token.value, target, generic_params, name_token.line, name_token.col)

    def _is_destructure_target(self, value: Any) -> bool:
        """判断一个表达式节点是否可作为解构赋值/循环的目标（裸元组/列表）"""
        if isinstance(value, (Name, DerefExpr, ArrayPattern)):
            return True
        # 元组/列表字面量在 LHS 上即解构目标，如 (a, b) = ... / [a, b] = ...
        if isinstance(value, Constant) and isinstance(value.value, (tuple, list)):
            return all(
                (isinstance(e, (Name, DerefExpr, ArrayPattern))
                 or (isinstance(e, Constant) and isinstance(e.value, (tuple, list))))
                for e in value.value
            )
        return False

    def _parse_expr_stmt(self) -> ASTNode:
        value = self._parse_expression()
        if self._current().type == TokenType.ASSIGN:
            self._consume()
            right_value = self._parse_expression()
            # 允许 Name、DerefExpr 以及解构目标（元组/列表/数组模式）作为赋值目标
            if self._is_destructure_target(value):
                # 处理赋值右边的构建块语法：x = func ~: block
                if self._current().type == TokenType.BUILD_CALL:
                    self._consume()
                    build_block = self._parse_build_block(BuildBlockExpr.BUILD_CALL)
                    # x = func ~: block 转换为 x = func(build_block)
                    return Assign(value, Call(right_value, [build_block]), value.line, value.col)
                elif self._current().type == TokenType.BUILD_GEN:
                    self._consume()
                    build_block = self._parse_build_block(BuildBlockExpr.BUILD_GEN)
                    # x = func *: block 转换为 x = func(build_block)
                    return Assign(value, Call(right_value, [build_block]), value.line, value.col)
                # 处理赋值右边的索引构建块：x = container ^: key
                elif self._current().type == TokenType.BUILD_INDEX:
                    self._consume()
                    # ^: 块体是单个表达式（key）
                    key_expr = self._parse_single_expr_block()
                    # x = container ^: key 转换为 x = container[key][-1] (取最后一个元素)
                    inner_index = Subscript(right_value, key_expr, value.line, value.col)
                    minus_one = Constant(-1, value.line, value.col)
                    index = Subscript(inner_index, minus_one, value.line, value.col)
                    return Assign(value, index, value.line, value.col)
                # 消费换行符或INDENT（Lexer会在换行后输出INDENT）
                if self._current().type in (TokenType.NEWLINE, TokenType.INDENT):
                    self._consume()
                return Assign(value, right_value, value.line, value.col)
        # 处理复合赋值 (+=, -=, *=, /=, //=, %=, <<=, >>=)
        compound_ops = {
            TokenType.PLUS_ASSIGN: "+",
            TokenType.MINUS_ASSIGN: "-",
            TokenType.MUL_ASSIGN: "*",
            TokenType.DIV_ASSIGN: "/",
            TokenType.FLOORDIV_ASSIGN: "//",
            TokenType.MOD_ASSIGN: "%",
            TokenType.LSHIFT_ASSIGN: "<<",
            TokenType.RSHIFT_ASSIGN: ">>",
        }
        if self._current().type in compound_ops:
            op = compound_ops[self._current().type]
            self._consume()
            right_value = self._parse_expression()
            # 支持 Name 和 Attribute 作为复合赋值目标
            if isinstance(value, (Name, Attribute, Subscript)):
                if self._current().type == TokenType.NEWLINE:
                    self._consume()
                return Assign(value, BinOp(value, op, right_value), value.line, value.col)
        # 处理变量构建块 =:（独立语句形式）
        if self._current().type == TokenType.BUILD_ASSIGN:
            self._consume()
            if isinstance(value, Name):
                build_block = self._parse_build_block(BuildBlockExpr.BUILD_ASSIGN)
                return Assign(value, build_block, value.line, value.col)
            else:
                raise ValueError(f"Left side of =: must be a variable name at {self._current().line}:{self._current().col}")
        # 处理调用构建块 ~:（独立语句形式）
        if self._current().type == TokenType.BUILD_CALL:
            self._consume()
            build_block = self._parse_build_block(BuildBlockExpr.BUILD_CALL)
            if isinstance(value, Name):
                # value ~: block → Assign(value, block) (赋值语义)
                return Assign(value, build_block, value.line, value.col)
            else:
                # (value 已经是 Call 或其他表达式)
                # 链式调用: value ~: block → Call(value, [block])
                return ExprStmt(Call(value, [build_block]), value.line, value.col)
        # 处理索引构建块 ^:（独立语句形式）
        if self._current().type == TokenType.BUILD_INDEX:
            self._consume()
            if isinstance(value, (Name, Attribute, Call)):
                # container ^: key → container[key][-1] (取最后一个元素)
                key_expr = self._parse_single_expr_block()
                inner_subscript = Subscript(value, key_expr, value.line, value.col)
                minus_one = Constant(-1, value.line, value.col)
                subscript = Subscript(inner_subscript, minus_one, value.line, value.col)
                # 包装在 ExprStmt 中，确保代码生成器正确处理
                return ExprStmt(subscript, value.line, value.col)
            else:
                raise ValueError(f"Left side of ^: must be a container expression at {self._current().line}:{self._current().col}")
        # 处理生成器构建块 *:（独立语句形式）
        if self._current().type == TokenType.BUILD_GEN:
            self._consume()
            build_block = self._parse_build_block(BuildBlockExpr.BUILD_GEN)
            if isinstance(value, Name):
                return Assign(value, build_block, value.line, value.col)
            else:
                return ExprStmt(Call(value, [build_block]), value.line, value.col)
        if self._current().type == TokenType.NEWLINE:
            self._consume()
        return ExprStmt(value, value.line, value.col)

    def _parse_expression(self) -> ASTNode:
        expr = self._parse_pipeline_expr()
        # 三元条件表达式: body if test else orelse
        while self._current().type == TokenType.IF:
            line = self._current().line
            col = self._current().col
            self._consume()  # consume IF
            test = self._parse_pipeline_expr()
            self._expect(TokenType.ELSE)
            orelse = self._parse_expression()
            expr = IfExp(test, expr, orelse, line, col)
        return expr

    def _parse_pipe_expr(self) -> ASTNode:
        """解析管道表达式（已废弃，使用 _parse_pipeline_expr）"""
        return self._parse_or_expr()
    
    def _parse_simple_expression(self) -> ASTNode:
        """解析简单表达式（不包含管道和函数调用）"""
        # 设置 skip_pipe 标志并直接调用 _parse_or_expr
        self._skip_pipe = True
        try:
            return self._parse_or_expr()
        finally:
            self._skip_pipe = False

    def _parse_or_expr(self) -> ASTNode:
        left = self._parse_and_expr()
        while self._current().type == TokenType.OR:
            op = self._consume().value
            right = self._parse_and_expr()
            left = BinOp(left, op, right)
        return left

    def _parse_and_expr(self) -> ASTNode:
        left = self._parse_not_expr()
        while self._current().type == TokenType.AND:
            op = self._consume().value
            right = self._parse_not_expr()
            left = BinOp(left, op, right)
        return left

    def _parse_not_expr(self) -> ASTNode:
        if self._current().type == TokenType.NOT:
            op = self._consume().value
            operand = self._parse_not_expr()
            return UnaryOp(op, operand)
        # BANG (!) 也用于逻辑非
        if self._current().type == TokenType.BANG:
            op = self._consume().value
            operand = self._parse_not_expr()
            return UnaryOp(op, operand)
        return self._parse_comparison()

    def _parse_comparison(self) -> ASTNode:
        left = self._parse_bitwise_or()
        while self._current().type in (TokenType.EQ, TokenType.NE, TokenType.LT, TokenType.LE, TokenType.GT, TokenType.GE, TokenType.IN, TokenType.IS, TokenType.NOT):
            if self._current().type == TokenType.NOT:
                # 检查是否是 "not in" 或 "not is" 操作符
                next_type = self._peek_ahead(1)
                if next_type == TokenType.IN:
                    self._consume()  # 消费 NOT
                    self._consume()  # 消费 IN
                    op = "not in"
                    right = self._parse_bitwise_or()
                    left = BinOp(left, op, right)
                    continue
                elif next_type == TokenType.IS:
                    self._consume()  # 消费 NOT
                    self._consume()  # 消费 IS
                    op = "not is"
                    right = self._parse_bitwise_or()
                    left = BinOp(left, op, right)
                    continue
                else:
                    break
            elif self._current().type == TokenType.IS:
                # 检查是否是 "is not" 操作符（Python 标准语法）
                self._consume()  # 消费 IS
                if self._current().type == TokenType.NOT:
                    self._consume()  # 消费 NOT
                    op = "is not"
                else:
                    op = "is"
                right = self._parse_bitwise_or()
                left = BinOp(left, op, right)
                continue
            elif self._current().type == TokenType.IN:
                # 检查是否是 "in" 操作符（单独 in，not in 已在上方处理）
                self._consume()  # 消费 IN
                op = "in"
                right = self._parse_bitwise_or()
                left = BinOp(left, op, right)
                continue
            else:
                op = self._consume().value
                right = self._parse_bitwise_or()
                left = BinOp(left, op, right)
        return left

    def _parse_bitwise_or(self) -> ASTNode:
        left = self._parse_bitwise_and()
        while self._current().type == TokenType.PIPE:
            op = self._consume().value
            right = self._parse_bitwise_and()
            left = BinOp(left, op, right)
        return left

    def _parse_bitwise_and(self) -> ASTNode:
        left = self._parse_shift_expr()
        while self._current().type == TokenType.AND:
            op = self._consume().value
            right = self._parse_shift_expr()
            left = BinOp(left, op, right)
        return left

    def _parse_shift_expr(self) -> ASTNode:
        left = self._parse_additive_expr()
        while self._current().type in (TokenType.LSHIFT, TokenType.RSHIFT):
            op = self._consume().value
            right = self._parse_additive_expr()
            left = BinOp(left, op, right)
        return left

    def _parse_comparison_expr(self) -> ASTNode:
        """解析比较表达式（==, !=, <, >, <=, >=, in, is）"""
        left = self._parse_shift_expr()
        while self._current().type in (TokenType.EQ, TokenType.NE, TokenType.LT, TokenType.GT, TokenType.LE, TokenType.GE, TokenType.IN, TokenType.IS):
            op = self._consume().value
            right = self._parse_shift_expr()
            left = BinOp(left, op, right)
        return left

    def _parse_pipeline_expr(self) -> ASTNode:
        left = self._parse_or_expr()
        while self._current().type == TokenType.PIPE_GT:
            self._consume()
            right = self._parse_call()
            if hasattr(right, 'kind') and right.kind == "Call":
                # right 已经是一个函数调用，将 left 作为第一个参数插入
                right.args.insert(0, left)
                left = right
            else:
                # right 只是一个名称或其他表达式，创建新的调用
                left = Call(right, [left])
        return left

    def _parse_additive_expr(self) -> ASTNode:
        left = self._parse_multiplicative_expr()
        while self._current().type in (TokenType.PLUS, TokenType.MINUS):
            op = self._consume().value
            right = self._parse_multiplicative_expr()
            left = BinOp(left, op, right)
        return left

    def _parse_multiplicative_expr(self) -> ASTNode:
        left = self._parse_unary_expr()
        while self._current().type in (TokenType.MUL, TokenType.DIV, TokenType.MOD, TokenType.FLOORDIV):
            op = self._consume().value
            right = self._parse_unary_expr()
            left = BinOp(left, op, right)
        return left

    def _parse_unary_expr(self) -> ASTNode:
        if self._current().type in (TokenType.PLUS, TokenType.MINUS):
            op = self._consume().value
            operand = self._parse_unary_expr()
            return UnaryOp(op, operand)
        # 支持 DEREF 和 MUL 作为解引用运算符
        if self._current().type in (TokenType.DEREF, TokenType.MUL):
            self._consume()
            operand = self._parse_unary_expr()
            return DerefExpr(operand)
        if self._current().type == TokenType.AWAIT:
            token = self._consume()
            operand = self._parse_unary_expr()
            return AwaitExpr(operand, token.line, token.col)
        return self._parse_cast_expr()

    def _parse_power_expr(self) -> ASTNode:
        base = self._parse_call()
        # 处理后缀构建值操作符 ^
        while self._current().type == TokenType.BUILD_VALUE:
            self._consume()
            base = BuildValueExpr(base)
        while self._current().type == TokenType.POW:
            op = self._consume().value
            exp = self._parse_unary_expr()
            base = BinOp(base, op, exp)
        return base

    def _parse_cast_expr(self) -> ASTNode:
        """解析类型转换表达式 - expr as Type"""
        base = self._parse_power_expr()
        while self._current().type == TokenType.AS:
            # with 语句中的 `expr as var` 的 as 是绑定语法，不是类型转换
            if getattr(self, '_in_with', False):
                break
            self._consume()  # consume AS
            target_type = self._parse_type()
            base = CastExpr(base, target_type, base.line, base.col)
        return base

    def _parse_call(self) -> ASTNode:
        func = self._parse_primary()
        
        # 如果设置了 skip_pipe 标志，只处理括号表达式，不构建函数调用
        if hasattr(self, '_skip_pipe') and self._skip_pipe:
            # 处理括号表达式 (expr)
            if self._current().type == TokenType.LPAREN:
                self._consume()
                inner = self._parse_expression()
                self._expect(TokenType.RPAREN)
                return inner
            return func
        
        # 记录 checker 名称（用于 func<checker>(args) 或 func<checker>[generic](args)）
        checker_name_for_call = None
        
        # 处理函数调用、成员访问、索引等
        while True:
            # 检查是否是 func<checker> 模式
            if self._current().type == TokenType.LT:
                # 查看后面是否是标识符 + >
                next_token = self._peek()
                if next_token and next_token.type == TokenType.IDENTIFIER:
                    # 预看第三个 token 是否是 >
                    peek_gt = self._peek_ahead(2)
                    if peek_gt == TokenType.GT:
                        # 这是 func<checker> 模式
                        self._consume()  # consume <
                        checker_name_for_call = self._consume(TokenType.IDENTIFIER).value
                        self._consume()  # consume >
                        # 继续循环处理后续的 [generic] 或 (args)
                        continue
            
            if self._current().type == TokenType.LPAREN:
                # 处理函数调用
                self._consume()
                # 标记进入函数调用参数列表（用于区分独立语句 vs 嵌套调用中的 ~:）
                old_in_call_args = self._in_call_args
                self._in_call_args = True
                args = []
                kwargs = []
                if self._current().type != TokenType.RPAREN:
                    while True:
                        # 检查是否是命名参数语法糖: name~ (简写为 name=name)
                        # 检查 IDENTIFIER + TILDE 序列
                        if (self._current().type == TokenType.IDENTIFIER and
                            self._peek_ahead(1) == TokenType.TILDE):
                            # name~ 语法糖: 脱糖为 name=name
                            kw_name = self._consume().value  # consume IDENTIFIER
                            self._consume()  # consume TILDE
                            kw_value = Name(kw_name, self._current().line, self._current().col)
                            kwargs.append((kw_name, kw_value))
                        elif self._current().type == TokenType.IDENTIFIER and self._peek_ahead(1) == TokenType.ASSIGN:
                            # 关键字参数：name=value
                            kw_name = self._consume().value
                            self._consume()  # consume ASSIGN
                            kw_value = self._parse_expression()
                            kwargs.append((kw_name, kw_value))
                        else:
                            # 普通位置参数
                            args.append(self._parse_expression())
                        if self._current().type != TokenType.COMMA:
                            break
                        self._consume()
                self._expect(TokenType.RPAREN)
                # 恢复调用参数标志
                self._in_call_args = old_in_call_args
                # 将关键字参数转换为命名参数形式
                all_args = args + kwargs
                func = Call(func, all_args, checker_name_for_call)
            elif self._current().type == TokenType.LBRACKET:
                # 处理索引访问或切片
                self._consume()
                # 检查是否是切片语法 [start:end] 或 [start:end:step]
                if self._current().type == TokenType.COLON:
                    # 无起始索引的切片 [:end] 或 [::step]
                    self._consume()
                    if self._current().type == TokenType.COLON:
                        # [::step] 格式
                        self._consume()
                        step = self._parse_expression()
                        self._expect(TokenType.RBRACKET)
                        func = Subscript(func, {'slice': True, 'start': None, 'end': None, 'step': step})
                    elif self._current().type == TokenType.RBRACKET:
                        # [:] 格式
                        self._consume()
                        func = Subscript(func, {'slice': True, 'start': None, 'end': None, 'step': None})
                    else:
                        end = self._parse_expression()
                        step = None
                        if self._current().type == TokenType.COLON:
                            self._consume()
                            if self._current().type != TokenType.RBRACKET:
                                step = self._parse_expression()
                        self._expect(TokenType.RBRACKET)
                        func = Subscript(func, {'slice': True, 'start': None, 'end': end, 'step': step})
                else:
                    index = self._parse_expression()
                    if self._current().type == TokenType.COLON:
                        # 切片语法 [start:end] 或 [start:end:step]
                        self._consume()
                        if self._current().type == TokenType.RBRACKET:
                            # [start:] 格式
                            self._consume()
                            func = Subscript(func, {'slice': True, 'start': index, 'end': None, 'step': None})
                        elif self._current().type == TokenType.COLON:
                            # [start::step] 格式
                            self._consume()
                            if self._current().type != TokenType.RBRACKET:
                                step = self._parse_expression()
                            else:
                                step = None
                            self._expect(TokenType.RBRACKET)
                            func = Subscript(func, {'slice': True, 'start': index, 'end': None, 'step': step})
                        else:
                            end = self._parse_expression()
                            step = None
                            if self._current().type == TokenType.COLON:
                                self._consume()
                                if self._current().type != TokenType.RBRACKET:
                                    step = self._parse_expression()
                                self._expect(TokenType.RBRACKET)
                            else:
                                self._expect(TokenType.RBRACKET)
                            func = Subscript(func, {'slice': True, 'start': index, 'end': end, 'step': step})
                    else:
                        self._expect(TokenType.RBRACKET)
                        func = Subscript(func, index)
            elif self._current().type == TokenType.DOT:
                # 处理成员访问
                self._consume()
                attr = self._expect(TokenType.IDENTIFIER).value
                func = Attribute(func, attr)
            elif self._current().type == TokenType.PIPE_GT:
                # 遇到管道操作符，停止处理，让 _parse_pipe_expr 处理
                break
            elif self._current().type == TokenType.BUILD_CALL:
                # 如果 func 是简单 Name 且不在函数调用参数中，停止处理，
                # 让 _parse_expr_stmt 处理赋值语义 (result ~: block → Assign(result, block))
                if isinstance(func, Name) and not self._in_call_args:
                    break
                # 处理调用构建块 ~: (链式调用: obj.method ~: block → Call(obj.method, [block]))
                self._consume()
                build_block = self._parse_build_block(BuildBlockExpr.BUILD_CALL)
                func = Call(func, [build_block])
                # 不立即返回，继续循环以支持链式调用和后续操作
            elif self._current().type == TokenType.BUILD_GEN:
                # 如果 func 是简单 Name 且不在函数调用参数中，停止处理，
                # 让 _parse_expr_stmt 处理赋值语义 (result *: block → Assign(result, block))
                if isinstance(func, Name) and not self._in_call_args:
                    break
                # 处理生成器构建块 *: (链式调用)
                self._consume()
                build_block = self._parse_build_block(BuildBlockExpr.BUILD_GEN)
                func = Call(func, [build_block])
                # 不立即返回，继续循环以支持链式调用和后续操作
            elif self._current().type == TokenType.LBRACE and hasattr(func, 'kind') and func.kind == "Name":
                # 处理结构体字面量 StructName {field: value, ...}
                self._consume()
                fields = []
                if self._current().type != TokenType.RBRACE:
                    while True:
                        field_name = self._expect(TokenType.IDENTIFIER).value
                        self._expect(TokenType.COLON)
                        field_value = self._parse_expression()
                        fields.append((field_name, field_value))
                        if self._current().type != TokenType.COMMA:
                            break
                        self._consume()
                self._expect(TokenType.RBRACE)
                return StructLiteral(func.id, fields, func.line, func.col)
            elif self._current().type == TokenType.BANG:
                # 宏调用语法（无 @ 前缀）：name!(args) 或 name！
                self._consume()
                macro_name = func.id if isinstance(func, Name) else getattr(func, 'id', str(func))
                args = []
                if self._current().type == TokenType.LPAREN:
                    self._consume()
                    if self._current().type != TokenType.RPAREN:
                        while True:
                            args.append(self._parse_expression())
                            if self._current().type != TokenType.COMMA:
                                break
                            self._consume()
                    self._expect(TokenType.RPAREN)
                return MacroCall(macro_name, args, func.line, func.col)
            else:
                break
        
        return func

    def _parse_primary(self) -> ASTNode:
        token = self._current()
        # match 表达式（返回值形式）
        if token.type == TokenType.MATCH:
            return self._parse_match_expr()
        if token.type == TokenType.INTEGER:
            self._consume()
            # 使用 base 0 自动识别进制（0x=十六进制, 0b=二进制, 0o=八进制）
            return Constant(int(token.value, 0), token.line, token.col)
        if token.type == TokenType.FLOAT:
            self._consume()
            return Constant(float(token.value), token.line, token.col)
        # 布尔字面量
        if token.type == TokenType.TRUE:
            self._consume()
            return Constant(True, token.line, token.col)
        if token.type == TokenType.FALSE:
            self._consume()
            return Constant(False, token.line, token.col)
        # 支持 type(expr) 作为一等类型表达式
        if token.type == TokenType.TYPE:
            self._consume()
            return Name("type", token.line, token.col)
        if token.type == TokenType.STRING:
            self._consume()
            # 保留字符串的前缀（如 f-string 的 'f', 'F', 'rf', 'fr'）
            prefix = getattr(token, 'prefix', None)
            if prefix:
                return Constant(token.value, token.line, token.col, prefix=prefix)
            return Constant(token.value, token.line, token.col)
        if token.type == TokenType.LAMBDA:
            return self._parse_lambda()
        if token.type == TokenType.BACKTICK_BLOCK:
            # 反引号代码块 - 用于宏中的代码捕获
            content = token.value
            prefix = token.prefix
            self._consume()
            return BacktickBlock(content, prefix, token.line, token.col)
        if token.type == TokenType.IDENTIFIER:
            self._consume()
            return Name(token.value, token.line, token.col)
        if token.type == TokenType.NEVER:
            self._consume()
            return Name("Never", token.line, token.col)
        if token.type == TokenType.LPAREN:
            self._consume()
            # 检查是否是空元组 ()
            if self._current().type == TokenType.RPAREN:
                self._consume()
                return Constant((), token.line, token.col)
            
            # 解析第一个表达式
            first_expr = self._parse_expression()
            
            # 检查是否是元组（后面有逗号）
            if self._current().type == TokenType.COMMA:
                elements = [first_expr]
                while self._current().type == TokenType.COMMA:
                    self._consume()
                    # 如果逗号后面是 RPAREN，说明是单元素元组
                    if self._current().type == TokenType.RPAREN:
                        break
                    elements.append(self._parse_expression())
                self._expect(TokenType.RPAREN)
                return Constant(tuple(elements), token.line, token.col)
            
            # 普通括号表达式
            self._expect(TokenType.RPAREN)
            return first_expr
        if token.type == TokenType.LBRACKET:
            self._consume()
            # 检查是否是列表推导式（包含for关键字）
            if self._current().type != TokenType.RBRACKET:
                # 解析第一个表达式
                first_expr = self._parse_expression()
                
                # 如果后面是for，则是列表推导式
                if self._current().type == TokenType.FOR:
                    generators = []
                    while self._current().type == TokenType.FOR:
                        self._consume()
                        # 解析循环变量（支持标识符或元组解构）
                        if self._current().type == TokenType.LPAREN:
                            # 元组解构：(x, y)
                            self._consume()
                            target_elements = []
                            while self._current().type != TokenType.RPAREN:
                                target_elements.append(self._consume(TokenType.IDENTIFIER).value)
                                if self._current().type == TokenType.COMMA:
                                    self._consume()
                            self._consume()  # consume RPAREN
                            target = tuple(target_elements)
                        else:
                            # 简单标识符
                            target = self._consume(TokenType.IDENTIFIER).value
                        
                        self._expect(TokenType.IN)
                        iter_expr = self._parse_pipeline_expr()
                        
                        # 支持多个 if 条件
                        if_exprs = []
                        while self._current().type == TokenType.IF:
                            self._consume()
                            if_exprs.append(self._parse_or_expr())
                        
                        generators.append((target, iter_expr, if_exprs))
                    
                    self._expect(TokenType.RBRACKET)
                    return ListComp(first_expr, generators, token.line, token.col)
                
                # 普通列表字面量
                elements = [first_expr]
                while self._current().type == TokenType.COMMA:
                    self._consume()
                    elements.append(self._parse_expression())
                self._expect(TokenType.RBRACKET)
                return Constant(elements, token.line, token.col)
            
            # 空列表
            self._expect(TokenType.RBRACKET)
            return Constant([], token.line, token.col)
        if token.type == TokenType.LBRACE:
            self._consume()
            pairs = []
            if self._current().type != TokenType.RBRACE:
                while True:
                    key = self._parse_expression()
                    self._expect(TokenType.COLON)
                    value = self._parse_expression()
                    pairs.append((key, value))
                    if self._current().type != TokenType.COMMA:
                        break
                    self._consume()
            self._expect(TokenType.RBRACE)
            return DictLiteral(pairs, token.line, token.col)
        if token.type == TokenType.SPAWN:
            # 作为表达式使用：task = spawn func()
            self._consume()
            self._require_function_scope("spawn", token)
            target = self._parse_expression()
            if hasattr(target, 'kind') and target.kind == 'Call':
                func_name = target.func
                args = target.args
                return SpawnStmt(func_name, args, [], token.line, token.col)
            else:
                return SpawnStmt(target, [], [], token.line, token.col)
        if token.type == TokenType.GO:
            # 作为表达式使用：task = go func()
            self._consume()
            self._require_function_scope("go", token)
            target = self._parse_expression()
            if hasattr(target, 'kind') and target.kind == 'Call':
                func_name = target.func
                args = target.args
                return GoStmt(func_name, args, [], token.line, token.col)
            else:
                return GoStmt(target, [], [], token.line, token.col)
        if token.type == TokenType.VEC:
            # vec 字面量：vec![value; Size] 或 vec![v1, v2, ...]
            self._consume()
            return self._parse_vec_literal(token)
        if token.type == TokenType.BUILD_CALL:
            # 调用构建块 ~: 作为独立表达式
            self._consume()
            return self._parse_build_block(BuildBlockExpr.BUILD_CALL)
        if token.type == TokenType.BUILD_GEN:
            # 生成器构建块 *: 作为独立表达式
            self._consume()
            return self._parse_build_block(BuildBlockExpr.BUILD_GEN)
        if token.type == TokenType.COMPTIME:
            # comptime: expr 作为表达式使用
            self._consume()
            return self._parse_comptime_stmt(consume_token=False, consume_newline=False)
        if token.type == TokenType.AT:
            # 宏调用：@name! 或 @name!(args...)
            # 注意：Lexer可能将 name! 解析为单个标识符（如果name不是关键字）
            self._consume()
            # 解析宏名称
            name_token = self._expect(TokenType.IDENTIFIER)
            name = name_token.value
            # 检查标识符是否以!结尾（Lexer可能合并了!）
            if name.endswith('!'):
                name = name[:-1]
            elif self._current().type == TokenType.BANG:
                # ! 被单独解析
                self._consume()
            # 宏名称加上!后缀表示宏调用
            name += "!"
            # 解析参数
            args = []
            if self._current().type == TokenType.LPAREN:
                self._consume()
                if self._current().type != TokenType.RPAREN:
                    while True:
                        args.append(self._parse_expression())
                        if self._current().type != TokenType.COMMA:
                            break
                        self._consume()
                self._expect(TokenType.RPAREN)
            return MacroCall(name, args, token.line, token.col)
        # 如果设置了 _stop_tokens 且当前 token 在停止列表中，停止表达式解析
        stop_tokens = getattr(self, '_stop_tokens', None)
        if stop_tokens is not None and token.type in stop_tokens:
            raise StopExpressionParsing()
        raise ValueError(f"Unexpected token {token.type} at {token.line}:{token.col}")

    def _parse_lambda(self) -> LambdaExpr:
        """解析 lambda 表达式
        
        语法：
        lambda params -> body
        
        参数可以有类型注解：
        lambda x: int, y: str -> x + len(y)
        
        示例：
        lambda x -> x * 2
        lambda x, y -> x + y
        lambda x: int -> x * 2
        """
        self._consume(TokenType.LAMBDA)
        
        # 解析参数列表
        params = []
        if self._current().type != TokenType.ARROW:
            while True:
                param = self._parse_param_for_lambda()
                params.append(param)
                
                if self._current().type == TokenType.ARROW:
                    break
                elif self._current().type == TokenType.COMMA:
                    self._consume()
                else:
                    break
        
        self._expect(TokenType.ARROW)
        
        # 解析lambda体（单个表达式）
        body = self._parse_expression()
        
        return LambdaExpr(params, body, self._current().line, self._current().col)
    
    def _parse_param_for_lambda(self) -> Param:
        """解析lambda参数，支持类型注解
        
        语法：
        param_name
        param_name: type
        """
        is_mut = False
        is_ref = False
        
        # 支持 TEST 作为参数名（test 被识别为关键字）
        if self._current().type == TokenType.TEST:
            name_token = self._consume(TokenType.TEST)
        else:
            name_token = self._consume(TokenType.IDENTIFIER)
        
        # 检查是否有类型注解（使用 COLON）
        type_annotation = None
        if self._current().type == TokenType.COLON:
            self._consume()  # 消耗 COLON
            type_annotation = self._parse_type()
        
        return Param(name_token.value, type_annotation, None, is_mut, is_ref, name_token.line, name_token.col)

    def _parse_type(self) -> ASTNode:
        base = self._parse_type_element()
        
        # 支持联合类型：int | float | str
        while self._current().type == TokenType.PIPE:
            self._consume()
            right = self._parse_type_element()
            # 如果已经是联合类型，扩展它
            if isinstance(base, UnionType):
                base.types.append(right)
            else:
                base = UnionType([base, right], base.line, base.col)
        
        return base
    
    def _parse_type_element(self) -> ASTNode:
        """解析单个类型元素（不包括 |）"""
        token = self._current()
        if token.type == TokenType.VEC:
            # vec[ElementType; Size] 类型
            self._consume()
            self._expect(TokenType.LBRACKET)
            element_type = self._parse_type()
            self._expect(TokenType.SEMICOLON)
            size = self._parse_expression()
            self._expect(TokenType.RBRACKET)
            return VecType(element_type, size.value if hasattr(size, 'value') else 4, token.line, token.col)
        
        if token.type == TokenType.MUL:
            # *Type 指针类型 (C 风格)
            self._consume()
            base_type = self._parse_type_element()
            return PointerType(base_type, token.line, token.col)
        
        base = self._parse_primary()
        while self._current().type == TokenType.MUL:
            self._consume()
            base = PointerType(base, base.line, base.col)
        
        # 统一使用尖括号 <>（与 LZ 语法对齐）
        if self._current().type == TokenType.LT:
            self._consume()  # 消费 <

            args = []
            if self._current().type != TokenType.GT:
                while True:
                    args.append(self._parse_type())
                    if self._current().type == TokenType.COMMA:
                        self._consume()
                    else:
                        break
            else:
                raise ValueError(f"Generic type parameter list cannot be empty at {base.line}:{base.col}")

            # 消费 >（处理嵌套泛型 >> 拆分）
            if self._current().type == TokenType.RSHIFT:
                rshift_token = self._consume()
                synthetic_gt = Token(TokenType.GT, ">", rshift_token.line, rshift_token.col)
                self.pos = max(0, self.pos - 1)
                self.tokens[self.pos] = synthetic_gt
            else:
                self._expect(TokenType.GT)
            
            if isinstance(base, Name):
                return GenericType(base.id, args, base.line, base.col)
            else:
                raise ValueError(f"Generic type must be a name at {base.line}:{base.col}")

        # 支持方括号下标泛型（Python 习惯写法）：Name[...]
        # 例如 list[int]、dict[str, int]、Optional[int]、
        #      Callable[[int], str]（首参为类型元组，用 GenericType('tuple', ...) 承载）
        if self._current().type == TokenType.LBRACKET:
            self._consume()
            args = []
            if self._current().type != TokenType.RBRACKET:
                while True:
                    if self._current().type == TokenType.LBRACKET:
                        # Callable[[int, str], bool] 中的参数类型列表
                        self._consume()
                        inner = []
                        while self._current().type != TokenType.RBRACKET:
                            inner.append(self._parse_type())
                            if self._current().type == TokenType.COMMA:
                                self._consume()
                        self._expect(TokenType.RBRACKET)
                        args.append(GenericType('tuple', inner, base.line, base.col))
                    else:
                        args.append(self._parse_type())
                    if self._current().type == TokenType.COMMA:
                        self._consume()
                    else:
                        break
            self._expect(TokenType.RBRACKET)
            if isinstance(base, Name):
                return GenericType(base.id, args, base.line, base.col)
            else:
                raise ValueError(f"Generic type must be a name at {base.line}:{base.col}")
        return base

    def _parse_type_list(self) -> List[ASTNode]:
        types = []
        while self._current().type == TokenType.IDENTIFIER:
            types.append(self._parse_type())
            if self._current().type == TokenType.COMMA:
                self._consume()
            else:
                break
        return types

    def _parse_block(self, signature_only: bool = False) -> List[ASTNode]:
        self._expect(TokenType.INDENT)
        body = []
        while self._current().type not in (TokenType.DEDENT, TokenType.EOF):
            # 跳过空行
            if self._current().type == TokenType.NEWLINE:
                self._consume()
                continue
            # 在调用_parse_statement之前再次检查是否遇到DEDENT
            if self._current().type in (TokenType.DEDENT, TokenType.EOF):
                break
            stmt = self._parse_statement(signature_only=signature_only)
            if stmt:
                body.append(stmt)
        if self._current().type == TokenType.DEDENT:
            self._consume()
            # 消费后面的NEWLINE（如果有的话），以便后续语句可以正确识别
            while self._current().type == TokenType.NEWLINE:
                self._consume()
        return body

    def _parse_build_block(self, block_type: str) -> BuildBlockExpr:
        """解析构建块体 - 内部默认unsafe，允许指针语法"""
        # 构建块后面必须换行并缩进
        if self._current().type == TokenType.NEWLINE:
            self._consume()
        body = self._parse_block()
        return BuildBlockExpr(block_type, body, self._current().line, self._current().col)

    def _parse_single_expr_block(self) -> ASTNode:
        """解析索引构建块 ^: 中的单个表达式
        
        LZ 语法: container ^:
                     key_expr
                 
        块体是一个表达式（key），用于索引访问。
        
        Token 序列: BUILD_INDEX → NEWLINE → INDENT → expr → DEDENT → NEWLINE
        """
        # 消费换行符
        if self._current().type == TokenType.NEWLINE:
            self._consume()
        # 消费 INDENT（缩进增加）
        if self._current().type == TokenType.INDENT:
            self._consume()
        # 消费可能跟随的 NEWLINE（词法分析器在 INDENT 后会生成 NEWLINE）
        if self._current().type == TokenType.NEWLINE:
            self._consume()
        # 解析单个表达式
        expr = self._parse_expression()
        # 消费 DEDENT（取消缩进）
        if self._current().type == TokenType.DEDENT:
            self._consume()
        # 消费后面的 NEWLINE（如果有的话）
        while self._current().type == TokenType.NEWLINE:
            self._consume()
        return expr

    def _parse_identifier(self) -> str:
        token = self._consume(TokenType.IDENTIFIER)
        return token.value
    
    def _parse_macro_def(self) -> MacroDef:
        """解析 macro 宏定义
        语法：macro name(ts: Tokens)-> Tokens = ...
        
        宏在编译期展开，操作Token流。
        参数必须是 ts: Tokens，返回值必须是 Tokens。
        """
        self._consume(TokenType.MACRO)
        
        # 解析宏名称
        name = self._expect(TokenType.IDENTIFIER).value
        
        # 解析参数列表 (ts: Tokens)
        self._expect(TokenType.LPAREN)
        params = []
        if self._current().type != TokenType.RPAREN:
            # 解析参数名和类型
            param_name = self._expect(TokenType.IDENTIFIER).value
            self._expect(TokenType.COLON)
            param_type = self._parse_type()
            params.append({"name": param_name, "type": param_type})
            while self._current().type == TokenType.COMMA:
                self._consume()
                param_name = self._expect(TokenType.IDENTIFIER).value
                self._expect(TokenType.COLON)
                param_type = self._parse_type()
                params.append({"name": param_name, "type": param_type})
        self._expect(TokenType.RPAREN)
        
        # 解析返回类型 -> Tokens
        return_type = None
        if self._current().type == TokenType.ARROW:
            self._consume()
            return_type = self._parse_type()
        
        # 期望等号（lang-zone风格）
        self._expect(TokenType.ASSIGN)
        
        # 解析宏体
        body = self._parse_block()
        
        return MacroDef(name, params, body, self._current().line, self._current().col)
    
    def _parse_comptime_func_def(self) -> ComptimeFuncDef:
        """解析 comptime def 编译期函数定义
        
        语法：
        comptime def func_name(params) -> return_type:
            body...
        
        在编译时执行的函数，不生成运行时代码
        """
        self._consume(TokenType.COMPTIME)
        self._consume(TokenType.DEF)
        
        name_token = self._consume(TokenType.IDENTIFIER)
        
        self._expect(TokenType.LPAREN)
        params = self._parse_params()
        self._expect(TokenType.RPAREN)
        
        return_type = None
        if self._current().type == TokenType.ARROW:
            self._consume()
            return_type = self._parse_type()
        
        self._expect(TokenType.COLON)
        self._push_scope("func")
        body = self._parse_block()
        self._pop_scope()
        
        return ComptimeFuncDef(name_token.value, params, return_type, body, name_token.line, name_token.col)
    
    def _parse_comptime_stmt(self, consume_token: bool = True, consume_newline: bool = True) -> ComptimeStmt:
        """解析 comptime 编译期求值语句
        语法（参考 lang-zone）：
        1. comptime: expr          - 单行形式，编译期计算表达式
        2. comptime:               - 块形式，编译期执行代码块
            body...
        
        在编译时执行表达式并将结果替换为常量
        
        consume_token: 是否消费COMPTIME关键字（当在表达式中调用时已消费）
        consume_newline: 是否消费单行形式后的换行符（当在表达式中调用时不应消费）
        """
        if consume_token:
            self._consume(TokenType.COMPTIME)
        
        # 期望冒号（lang-zone风格）
        self._expect(TokenType.COLON)
        
        # 解析编译期内容（表达式或块）
        if self._current().type == TokenType.NEWLINE:
            # 块形式：comptime: 后跟换行
            self._consume()
            body = self._parse_block()
            expr = body
        elif self._current().type == TokenType.INDENT:
            # 块形式：comptime: 后跟缩进（Lexer可能先输出INDENT再输出NEWLINE）
            body = self._parse_block()
            expr = body
        else:
            # 单行形式：comptime: expr
            expr = self._parse_expression()
        
        # 消费换行符（单行形式，语句模式）
        if consume_newline and hasattr(expr, 'kind') and expr.kind != 'Suite' and self._current().type == TokenType.NEWLINE:
            self._consume()
        
        return ComptimeStmt(expr, self._current().line, self._current().col)
    
    def _parse_spawn_stmt(self) -> SpawnStmt:
        """解析 spawn 并发任务语句
        
        支持两种语法形式：
        1. spawn func(args) - 调用形式，在后台执行函数
        2. spawn:            - 块形式，在后台执行代码块
            body...
        
        返回任务句柄，可以通过 join() 等待完成
        """
        self._consume(TokenType.SPAWN)
        self._require_function_scope("spawn", self._current())
        
        if self._current().type == TokenType.COLON:
            # 块形式：spawn: 换行块体
            self._consume()
            body = self._parse_block()
            return SpawnStmt(None, [], body, self._current().line, self._current().col)
        else:
            # 调用形式：spawn func(args)
            target = self._parse_expression()
            # 如果是函数调用，提取函数名和参数
            if hasattr(target, 'kind') and target.kind == 'Call':
                func_name = target.func
                args = target.args
                return SpawnStmt(func_name, args, [], self._current().line, self._current().col)
            else:
                # 表达式形式
                return SpawnStmt(target, [], [], self._current().line, self._current().col)
    
    def _parse_go_stmt(self) -> GoStmt:
        """解析 go 轻量级协程语句
        
        支持两种语法形式：
        1. go func(args) - 调用形式，创建并启动协程
        2. go:            - 块形式，创建并启动协程块
            body...
        
        go 与 spawn 的区别：go 创建轻量级协程（协程池复用），spawn 创建重量级线程
        """
        self._consume(TokenType.GO)
        self._require_function_scope("go", self._current())
        
        if self._current().type == TokenType.COLON:
            # 块形式：go: 换行块体
            self._consume()
            body = self._parse_block()
            return GoStmt(None, [], body, self._current().line, self._current().col)
        else:
            # 调用形式：go func(args)
            target = self._parse_expression()
            # 如果是函数调用，提取函数名和参数
            if hasattr(target, 'kind') and target.kind == 'Call':
                func_name = target.func
                args = target.args
                return GoStmt(func_name, args, [], self._current().line, self._current().col)
            else:
                # 表达式形式
                return GoStmt(target, [], [], self._current().line, self._current().col)
    
    def _parse_vec_literal(self, token: Token) -> VecLiteral:
        """解析 vec 向量字面量
        
        支持两种语法形式：
        1. vec![v1, v2, v3, v4] - 显式元素列表
        2. vec![value; 4] - 重复值形式
        
        向量大小必须是编译期常量（2, 4, 8, 16）
        """
        # 期望 ! 符号（lexer 中将 ! 识别为 BANG）
        self._expect(TokenType.BANG)
        # 期望 [ 符号
        self._expect(TokenType.LBRACKET)
        
        elements = []
        size = None
        
        # 解析第一个元素
        first_elem = self._parse_expression()
        
        # 检查是重复形式还是列表形式
        if self._current().type == TokenType.SEMICOLON:
            # 重复形式：vec![value; Size]
            self._consume()
            size_token = self._expect(TokenType.INTEGER)
            size = int(size_token.value)
            elements = [first_elem]
        else:
            # 列表形式：vec![v1, v2, ...]
            elements.append(first_elem)
            while self._current().type == TokenType.COMMA:
                self._consume()
                elements.append(self._parse_expression())
        
        # 期望 ] 符号
        self._expect(TokenType.RBRACKET)
        
        # 如果是列表形式，size 就是元素个数
        if size is None:
            size = len(elements)
        
        return VecLiteral(elements, size, token.line, token.col)
