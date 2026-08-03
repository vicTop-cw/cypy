"""编译期求值器：在编译时计算常量表达式和函数

参考 lang-zone 的 comptime 设计：
- comptime: expr          - 单行形式，编译期计算表达式
- comptime:               - 块形式，编译期执行代码块
- comptime def            - 编译期函数定义

求值规则：
1. 支持基本算术运算（+、-、*、/、%、**）
2. 支持比较运算（==、!=、<、>、<=、>=）
3. 支持逻辑运算（and、or、not）
4. 支持位运算（&、|、^、~、<<、>>）
5. 支持字符串操作（+、*、upper、lower、replace、split、join 等）
6. 支持列表操作（append、extend、insert、remove、sort、reverse 等）
7. 支持常量表达式和字面量
8. 支持丰富的内置函数调用（len、abs、round、min、max、sum、range 等）
9. 支持编译期函数调用（comptime def）
10. 支持语句执行（LetStmt、ReturnStmt、IfStmt、ForStmt、WhileStmt）
11. 支持条件编译（if comptime）
12. 支持范围操作（range）

不支持：
- 运行时函数调用
- 复杂的副作用操作
"""

import ast
import logging
from typing import Any, Optional, Dict, List, Set
from cypyc.parser.parser import ASTNode, Constant, BinOp, UnaryOp, Call, Name, LetStmt, ReturnStmt, IfStmt, Param, ComptimeFuncDef, ForStmt, WhileStmt, Assign, ExprStmt


class ComptimeEvaluator:
    """编译期求值器"""
    
    def __init__(self):
        self.constants: Dict[str, Any] = {}  # 常量映射 {name: value}
        self.functions: Dict[str, ComptimeFuncDef] = {}  # 编译期函数 {name: ComptimeFuncDef}
        self.scope_stack: List[Dict[str, Any]] = []  # 作用域栈
        self.recursion_depth = 0  # 递归深度计数器
        self.max_recursion_depth = 10000  # 最大递归深度（编译期函数需要较大的深度）
        self.loop_limit = 100000  # 循环执行次数上限
    
    def register_function(self, func_def: ComptimeFuncDef) -> None:
        """注册编译期函数"""
        self.functions[func_def.name] = func_def
    
    def push_scope(self, scope_vars: Dict[str, Any] = None) -> None:
        """压入新作用域"""
        self.scope_stack.append(scope_vars or {})
    
    def pop_scope(self) -> None:
        """弹出当前作用域"""
        if self.scope_stack:
            self.scope_stack.pop()
    
    def get_variable(self, name: str) -> Any:
        """从作用域链中获取变量值"""
        # 从内到外查找
        for scope in reversed(self.scope_stack):
            if name in scope:
                return scope[name]
        # 检查全局常量
        if name in self.constants:
            return self.constants[name]
        raise ValueError(f"Undefined variable '{name}' at compile time")
    
    def set_variable(self, name: str, value: Any) -> None:
        """设置变量值（在当前作用域）"""
        if self.scope_stack:
            self.scope_stack[-1][name] = value
        else:
            self.constants[name] = value
    
    def _evaluate_module(self, node: ASTNode) -> Any:
        """求值 Module 节点
        
        Args:
            node: Module 节点
            
        Returns:
            求值结果
        """
        # 先注册编译期函数
        for stmt in node.body:
            if hasattr(stmt, 'name') and hasattr(stmt, 'params') and hasattr(stmt, 'body'):
                # 这是一个 ComptimeFuncDef
                self.functions[stmt.name] = stmt
        
        # 然后执行编译期语句
        for stmt in node.body:
            if hasattr(stmt, 'expr'):
                # 这是一个 ComptimeStmt
                return self._evaluate_comptime_stmt(stmt)
        
        return None
    
    def _evaluate_comptime_stmt(self, node: ASTNode) -> Any:
        """求值 ComptimeStmt 节点
        
        Args:
            node: ComptimeStmt 节点
            
        Returns:
            求值结果
        """
        # 压入主作用域
        self.push_scope()
        
        # 求值表达式/语句
        result = self.evaluate(node.expr)
        
        self.pop_scope()
        return result
    
    def evaluate(self, node: ASTNode) -> Any:
        """求值 AST 节点
        
        Args:
            node: AST 节点
            
        Returns:
            求值结果（Python 值）
        """
        # 处理 Module 节点
        if hasattr(node, 'body') and isinstance(node.body, list):
            return self._evaluate_module(node)
        
        # 处理 ComptimeStmt 节点
        if hasattr(node, 'expr'):
            return self._evaluate_comptime_stmt(node)
        
        if isinstance(node, Constant):
            return node.value
        
        if isinstance(node, BinOp):
            left_val = self.evaluate(node.left)
            right_val = self.evaluate(node.right)
            return self._evaluate_bin_op(node.op, left_val, right_val)
        
        if isinstance(node, UnaryOp):
            operand_val = self.evaluate(node.operand)
            return self._evaluate_unary_op(node.op, operand_val)
        
        if isinstance(node, Call):
            func_name = self._get_func_name(node.func)
            args = [self.evaluate(arg) for arg in node.args]
            return self._evaluate_call(func_name, args)
        
        if isinstance(node, Name):
            # 处理内置常量
            if node.id == 'True':
                return True
            if node.id == 'False':
                return False
            if node.id == 'None':
                return None
            return self.get_variable(node.id)
        
        # 处理列表字面量
        if hasattr(node, 'elts') and isinstance(node.elts, list):
            return [self.evaluate(elt) for elt in node.elts]
        
        # 处理属性访问（用于方法调用如 str.upper()）
        if hasattr(node, 'value') and hasattr(node, 'attr'):
            obj_val = self.evaluate(node.value)
            return self._evaluate_attribute_access(obj_val, node.attr)
        
        # 处理语句（块形式）
        if isinstance(node, list):
            return self._evaluate_statements(node)
        
        raise ValueError(f"Cannot evaluate expression at compile time: {node.kind}")
    
    def _evaluate_attribute_access(self, obj: Any, attr: str) -> Any:
        """求值属性访问（用于方法调用）
        
        Args:
            obj: 对象值
            attr: 属性名
            
        Returns:
            属性值（通常是方法引用）
        """
        # 字符串方法
        if isinstance(obj, str):
            str_methods = {
                'upper': lambda: obj.upper(),
                'lower': lambda: obj.lower(),
                'capitalize': lambda: obj.capitalize(),
                'title': lambda: obj.title(),
                'strip': lambda: obj.strip(),
                'lstrip': lambda: obj.lstrip(),
                'rstrip': lambda: obj.rstrip(),
                'replace': lambda old, new, count=-1: obj.replace(old, new, count),
                'split': lambda sep=None, maxsplit=-1: obj.split(sep, maxsplit),
                'startswith': lambda prefix: obj.startswith(prefix),
                'endswith': lambda suffix: obj.endswith(suffix),
                'contains': lambda sub: sub in obj,
                'concat': lambda other: obj + other,
                'repeat': lambda n: obj * n,
            }
            if attr in str_methods:
                return str_methods[attr]
        
        # 列表方法
        if isinstance(obj, list):
            list_methods = {
                'append': lambda item: obj.append(item) or None,
                'extend': lambda items: obj.extend(items) or None,
                'insert': lambda index, item: obj.insert(index, item) or None,
                'remove': lambda item: obj.remove(item) or None,
                'pop': lambda index=-1: obj.pop(index),
                'sort': lambda key=None, reverse=False: obj.sort(key=key, reverse=reverse) or None,
                'reverse': lambda: obj.reverse() or None,
                'count': lambda item: obj.count(item),
                'index': lambda item: obj.index(item),
                'contains': lambda item: item in obj,
                'length': lambda: len(obj),
                'map': lambda func: list(map(func, obj)),
                'filter': lambda func: list(filter(func, obj)),
                'reduce': lambda func, initial=None: self._reduce_list(func, obj, initial),
            }
            if attr in list_methods:
                return list_methods[attr]
        
        # 整数方法
        if isinstance(obj, int):
            int_methods = {
                'to_float': lambda: float(obj),
                'to_str': lambda: str(obj),
                'abs': lambda: abs(obj),
                'sqrt': lambda: obj ** 0.5,
                'is_even': lambda: obj % 2 == 0,
                'is_odd': lambda: obj % 2 != 0,
            }
            if attr in int_methods:
                return int_methods[attr]
        
        # 浮点数方法
        if isinstance(obj, float):
            float_methods = {
                'to_int': lambda: int(obj),
                'to_str': lambda: str(obj),
                'round': lambda ndigits=0: round(obj, ndigits),
                'abs': lambda: abs(obj),
                'ceil': lambda: __import__('math').ceil(obj),
                'floor': lambda: __import__('math').floor(obj),
                'is_integer': lambda: obj.is_integer(),
            }
            if attr in float_methods:
                return float_methods[attr]
        
        # 布尔方法
        if isinstance(obj, bool):
            bool_methods = {
                'to_int': lambda: int(obj),
                'to_str': lambda: str(obj),
            }
            if attr in bool_methods:
                return bool_methods[attr]
        
        raise ValueError(f"Unknown attribute '{attr}' for type {type(obj).__name__} at compile time")
    
    def _reduce_list(self, func, items, initial=None):
        """实现列表 reduce 操作"""
        result = initial
        for item in items:
            if result is None:
                result = item
            else:
                result = func(result, item)
        return result
    
    def _evaluate_statements(self, stmts: List[ASTNode]) -> Any:
        """求值语句列表
        
        Args:
            stmts: 语句列表
            
        Returns:
            最后一个语句的求值结果（如果有 return）
        """
        result = None
        for stmt in stmts:
            result = self._evaluate_statement(stmt)
            # 如果遇到 ReturnStmt、IfStmt 或循环返回了值，立即返回
            if result is not None and isinstance(stmt, (ReturnStmt, IfStmt, ForStmt, WhileStmt)):
                return result
        return result
    
    def _evaluate_statement(self, stmt: ASTNode) -> Any:
        """求值单个语句
        
        Args:
            stmt: 语句节点
            
        Returns:
            求值结果
        """
        if isinstance(stmt, LetStmt):
            value = self.evaluate(stmt.value)
            self.set_variable(stmt.name, value)
            return value
        
        if isinstance(stmt, Assign):
            # 处理赋值语句（解析器用 Assign 表示 `x = expr`）
            value = self.evaluate(stmt.value)
            target_name = stmt.target.id if hasattr(stmt.target, 'id') else str(stmt.target)
            self.set_variable(target_name, value)
            return value
        
        if isinstance(stmt, ExprStmt):
            # 处理表达式语句（用于获取表达式值作为最终结果）
            return self.evaluate(stmt.value)
        
        if isinstance(stmt, ReturnStmt):
            if stmt.value is not None:
                return self.evaluate(stmt.value)
            return None
        
        if isinstance(stmt, IfStmt):
            return self._evaluate_if_statement(stmt)
        
        if isinstance(stmt, ForStmt):
            return self._evaluate_for_statement(stmt)
        
        if isinstance(stmt, WhileStmt):
            return self._evaluate_while_statement(stmt)
        
        # 忽略其他语句类型（如 PassStmt）
        return None
    
    def _evaluate_if_statement(self, stmt: IfStmt) -> Any:
        """求值 if 语句
        
        Args:
            stmt: IfStmt 节点
            
        Returns:
            被执行分支的求值结果
        """
        cond_value = self.evaluate(stmt.test)
        
        if cond_value:
            return self._evaluate_statements(stmt.body)
        elif stmt.orelse:
            return self._evaluate_statements(stmt.orelse)
        return None
    
    def _evaluate_for_statement(self, stmt: ForStmt) -> Any:
        """求值 for 循环语句
        
        Args:
            stmt: ForStmt 节点
            
        Returns:
            循环最后一次迭代的结果
        """
        # 求值迭代对象
        iter_value = self.evaluate(stmt.iter)
        
        # 获取循环变量名
        target_name = stmt.target.id if hasattr(stmt.target, 'id') else str(stmt.target)
        
        # 压入新作用域
        self.push_scope()
        
        result = None
        count = 0
        for item in iter_value:
            # 循环次数限制
            if count >= self.loop_limit:
                raise ValueError(f"Comptime loop exceeded limit ({self.loop_limit} iterations)")
            count += 1
            
            # 设置循环变量
            self.set_variable(target_name, item)
            
            # 执行循环体
            result = self._evaluate_statements(stmt.body)
        
        self.pop_scope()
        return result
    
    def _evaluate_while_statement(self, stmt: WhileStmt) -> Any:
        """求值 while 循环语句
        
        Args:
            stmt: WhileStmt 节点
            
        Returns:
            循环最后一次迭代的结果
        """
        # 压入新作用域
        self.push_scope()
        
        result = None
        count = 0
        while True:
            # 循环次数限制
            if count >= self.loop_limit:
                raise ValueError(f"Comptime loop exceeded limit ({self.loop_limit} iterations)")
            count += 1
            
            # 求值条件
            cond_value = self.evaluate(stmt.test)
            if not cond_value:
                break
            
            # 执行循环体
            result = self._evaluate_statements(stmt.body)
        
        self.pop_scope()
        return result
    
    def _get_func_name(self, func_node: ASTNode) -> str:
        """获取函数名称"""
        if isinstance(func_node, Name):
            return func_node.id
        if hasattr(func_node, 'id'):
            return func_node.id
        return str(func_node)
    
    def _evaluate_bin_op(self, op: str, left: Any, right: Any) -> Any:
        """求值二元操作"""
        # 算术运算
        if op == '+':
            return left + right
        if op == '-':
            return left - right
        if op == '*':
            return left * right
        if op == '/':
            return left / right
        if op == '%':
            return left % right
        if op == '**':
            return left ** right
        
        # 比较运算
        if op == '==':
            return left == right
        if op == '!=':
            return left != right
        if op == '<':
            return left < right
        if op == '>':
            return left > right
        if op == '<=':
            return left <= right
        if op == '>=':
            return left >= right
        
        # 逻辑运算
        if op == 'and':
            return left and right
        if op == 'or':
            return left or right
        
        # 位运算
        if op == '&':
            return left & right
        if op == '|':
            return left | right
        if op == '^':
            return left ^ right
        if op == '<<':
            return left << right
        if op == '>>':
            return left >> right
        
        raise ValueError(f"Unknown binary operator: {op}")
    
    def _evaluate_unary_op(self, op: str, operand: Any) -> Any:
        """求值一元操作"""
        if op == 'not' or op == 'NOT':
            return not operand
        if op == '-' or op == 'MINUS':
            return -operand
        if op == '+' or op == 'PLUS':
            return +operand
        if op == '~' or op == 'BIT_NOT':
            return ~operand
        
        raise ValueError(f"Unknown unary operator: {op}")
    
    def _evaluate_call(self, func_name: str, args: list) -> Any:
        """求值函数调用（包含编译期函数和内置函数）"""
        # 检查是否是编译期函数（包括递归调用）
        if func_name in self.functions:
            return self._call_comptime_function(func_name, args)
        
        # 支持的内置函数（基本类型转换和数学运算）
        builtin_funcs = {
            'len': len,
            'abs': abs,
            'round': round,
            'min': min,
            'max': max,
            'sum': sum,
            'pow': pow,
            'str': str,
            'int': int,
            'float': float,
            'bool': bool,
            'chr': chr,
            'ord': ord,
            'hex': hex,
            'oct': oct,
            'bin': bin,
            'repr': repr,
            'hash': hash,
            # 列表/元组/字典构造
            'list': list,
            'tuple': tuple,
            'dict': dict,
            'set': set,
            # 数学函数
            'sqrt': lambda x: x ** 0.5,
            'ceil': lambda x: __import__('math').ceil(x),
            'floor': lambda x: __import__('math').floor(x),
            'log': lambda x, base=None: __import__('math').log(x) if base is None else __import__('math').log(x, base),
            'exp': lambda x: __import__('math').exp(x),
            'sin': lambda x: __import__('math').sin(x),
            'cos': lambda x: __import__('math').cos(x),
            'tan': lambda x: __import__('math').tan(x),
            # 字符串函数
            'concat': lambda *args: ''.join(str(a) for a in args),
            'join': lambda sep, items: sep.join(items),
            'repeat': lambda s, n: s * n,
            'replace': lambda s, old, new, count=-1: s.replace(old, new, count),
            'split': lambda s, sep=None: s.split(sep),
            # 列表函数
            'range': lambda start, stop=None, step=1: self._range_func(start, stop, step),
            'map': lambda func, iterable: list(map(func, iterable)),
            'filter': lambda func, iterable: list(filter(func, iterable)),
            'reduce': lambda func, iterable, initial=None: self._reduce_list(func, iterable, initial),
            'sorted': lambda iterable, key=None, reverse=False: sorted(iterable, key=key, reverse=reverse),
            'reversed': lambda seq: list(reversed(seq)),
            'enumerate': lambda iterable: list(enumerate(iterable)),
            'zip': lambda *args: list(zip(*args)),
        }
        
        if func_name in builtin_funcs:
            return builtin_funcs[func_name](*args)
        
        # 处理方法调用（通过属性访问后的调用）
        # 这种情况会在 _evaluate_attribute_access 中处理
        
        raise ValueError(f"Cannot call function '{func_name}' at compile time")
    
    def _range_func(self, start: int, stop: int = None, step: int = 1) -> List[int]:
        """实现 range 函数"""
        if stop is None:
            return list(range(start))
        return list(range(start, stop, step))
    
    def _call_comptime_function(self, func_name: str, args: list) -> Any:
        """调用编译期函数"""
        func_def = self.functions[func_name]
        
        # 递归深度检查
        self.recursion_depth += 1
        if self.recursion_depth > self.max_recursion_depth:
            self.recursion_depth -= 1
            raise ValueError(f"Recursion depth exceeded for function '{func_name}'")
        
        try:
            # 创建函数作用域，绑定参数
            param_scope = {}
            for i, param in enumerate(func_def.params):
                if i < len(args):
                    param_scope[param.name] = args[i]
            
            # 将函数名添加到作用域中，支持递归调用
            param_scope[func_name] = lambda *call_args: self._call_comptime_function(func_name, call_args)
            
            # 压入作用域并执行
            self.push_scope(param_scope)
            result = self._evaluate_statements(func_def.body)
            self.pop_scope()
            
            return result
        finally:
            self.recursion_depth -= 1
    
    def _evaluate_builtin_constant(self, name: str) -> Any:
        """求值内置常量"""
        builtin_constants = {
            'True': True,
            'False': False,
            'None': None,
            '__name__': '__main__',
        }
        
        if name in builtin_constants:
            return builtin_constants[name]
        
        raise ValueError(f"Unknown constant '{name}' at compile time")


# 配置日志记录器
_comptime_logger = logging.getLogger('cypyc.comptime')

def evaluate_comptime(node: ASTNode, evaluator: Optional[ComptimeEvaluator] = None) -> Optional[Any]:
    """编译期求值入口函数
    
    Args:
        node: AST 节点
        evaluator: 可选的求值器实例（用于共享函数注册）
        
    Returns:
        求值结果，如果无法求值返回 None
    """
    if evaluator is None:
        evaluator = ComptimeEvaluator()
    
    try:
        return evaluator.evaluate(node)
    except (ValueError, TypeError, ZeroDivisionError) as e:
        # 记录警告日志，便于调试
        _comptime_logger.warning(f"Comptime evaluation failed: {e}")
        return None


def register_comptime_functions(ast: ASTNode, evaluator: ComptimeEvaluator) -> None:
    """从 AST 中收集并注册所有编译期函数
    
    Args:
        ast: AST 节点
        evaluator: 编译期求值器
    """
    if isinstance(ast, ComptimeFuncDef):
        evaluator.register_function(ast)
    
    for attr in dir(ast):
        if not attr.startswith("_"):
            value = getattr(ast, attr)
            if isinstance(value, ASTNode):
                register_comptime_functions(value, evaluator)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, ASTNode):
                        register_comptime_functions(item, evaluator)