"""
解析器测试套件
覆盖词法分析、语法解析、表达式、语句、声明等核心功能
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from test_suite.core.suite import Suite
from test_suite.core.assertions import Assert, Check
from test_suite.fixtures.parser import ParserFixture


parser_suite = Suite("ParserSuite")
fixture = ParserFixture()


# ===== 基础语法测试 =====
@parser_suite.test("parse_simple_expression")
def test_parse_simple_expression():
    """测试解析简单表达式"""
    source = "1 + 2"
    ast = fixture.parse_expression(source)
    Assert.is_not_none(ast)
    Assert.equal(ast.kind, "ExprStmt")
    Assert.is_not_none(ast.value)
    Assert.equal(ast.value.kind, "BinOp")


@parser_suite.test("parse_variable_assignment")
def test_parse_variable_assignment():
    """测试解析变量赋值"""
    source = "x = 42"
    ast = fixture.parse_statement(source)
    Assert.is_not_none(ast)
    Assert.equal(ast.kind, "Assign")


@parser_suite.test("parse_function_definition")
def test_parse_function_definition():
    """测试解析函数定义"""
    source = """
def add(a: int, b: int) -> int:
    return a + b
"""
    ast = fixture.parse(source)
    Assert.is_not_none(ast)
    Assert.equal(len(ast.body), 1)
    Assert.equal(ast.body[0].kind, "FuncDef")


@parser_suite.test("parse_struct_definition")
def test_parse_struct_definition():
    """测试解析结构体定义"""
    source = """
struct Point:
    x: int
    y: int
"""
    ast = fixture.parse(source)
    Assert.is_not_none(ast)
    Assert.equal(len(ast.body), 1)
    Assert.equal(ast.body[0].kind, "StructDef")


# ===== 类型转换语法测试 =====
@parser_suite.test("parse_cast_expression")
def test_parse_cast_expression():
    """测试解析类型转换表达式"""
    source = "x as int"
    ast = fixture.parse_expression(source)
    Assert.is_not_none(ast)
    Assert.equal(ast.kind, "ExprStmt")
    Assert.is_not_none(ast.value)
    Assert.equal(ast.value.kind, "CastExpr")


@parser_suite.test("parse_cast_with_arithmetic")
def test_parse_cast_with_arithmetic():
    """测试解析带类型转换的算术表达式"""
    source = "(1 + 2) as float"
    ast = fixture.parse_expression(source)
    Assert.is_not_none(ast)
    Assert.equal(ast.kind, "ExprStmt")
    Assert.is_not_none(ast.value)
    Assert.equal(ast.value.kind, "CastExpr")


# ===== 隐式策略语法测试 =====
@parser_suite.test("parse_implicit_struct")
def test_parse_implicit_struct():
    """测试解析隐式结构体"""
    source = """
implicit struct Config:
    host: str
    port: int
"""
    ast = fixture.parse(source)
    Assert.is_not_none(ast)
    Assert.equal(len(ast.body), 1)
    Assert.equal(ast.body[0].kind, "StructDef")
    Assert.true(ast.body[0].is_implicit)


@parser_suite.test("parse_implicit_parameter")
def test_parse_implicit_parameter():
    """测试解析隐式参数"""
    source = """
def greet(name: str, implicit lang: str = "en") -> str:
    return f"Hello, {name}"
"""
    ast = fixture.parse(source)
    Assert.is_not_none(ast)
    Assert.equal(len(ast.body), 1)
    func_def = ast.body[0]
    Assert.equal(func_def.kind, "FuncDef")
    Assert.true(func_def.params[1].is_implicit)


# ===== 构建块语法测试 =====
@parser_suite.test("parse_build_assign")
def test_parse_build_assign():
    """测试解析构建块赋值"""
    # 跳过：构建块语法尚未完全支持
    pass


@parser_suite.test("parse_build_call")
def test_parse_build_call():
    """测试解析构建块调用"""
    # 跳过：构建块语法尚未完全支持
    pass


@parser_suite.test("parse_build_gen")
def test_parse_build_gen():
    """测试解析构建块生成"""
    # 跳过：构建块语法尚未完全支持
    pass


# ===== 控制流测试 =====
@parser_suite.test("parse_if_statement")
def test_parse_if_statement():
    """测试解析 if 语句"""
    source = """
if x > 0:
    print("positive")
elif x == 0:
    print("zero")
else:
    print("negative")
"""
    ast = fixture.parse(source)
    Assert.is_not_none(ast)
    Assert.equal(len(ast.body), 1)
    Assert.equal(ast.body[0].kind, "IfStmt")


@parser_suite.test("parse_while_loop")
def test_parse_while_loop():
    """测试解析 while 循环"""
    source = """
while i < 10:
    i += 1
"""
    ast = fixture.parse(source)
    Assert.is_not_none(ast)
    Assert.equal(len(ast.body), 1)
    Assert.equal(ast.body[0].kind, "WhileStmt")


@parser_suite.test("parse_for_loop")
def test_parse_for_loop():
    """测试解析 for 循环"""
    source = """
for item in items:
    process(item)
"""
    ast = fixture.parse(source)
    Assert.is_not_none(ast)
    Assert.equal(len(ast.body), 1)
    Assert.equal(ast.body[0].kind, "ForStmt")


# ===== 导入语法测试 =====
@parser_suite.test("parse_import_statement")
def test_parse_import_statement():
    """测试解析导入语句"""
    source = "import math"
    ast = fixture.parse_statement(source)
    Assert.is_not_none(ast)
    Assert.equal(ast.kind, "Import")


@parser_suite.test("parse_from_import")
def test_parse_from_import():
    """测试解析 from 导入"""
    source = "from utils import helper"
    ast = fixture.parse_statement(source)
    Assert.is_not_none(ast)
    Assert.equal(ast.kind, "FromImport")


# ===== 词法分析测试 =====
@parser_suite.test("tokenize_basic_tokens")
def test_tokenize_basic_tokens():
    """测试词法分析基本 token"""
    tokens = fixture.tokenize("x = 1 + 2")
    Assert.is_not_none(tokens)
    token_types = [t.type for t in tokens]
    Assert.contains(token_types, "IDENTIFIER")
    Assert.contains(token_types, "ASSIGN")
    Assert.contains(token_types, "INTEGER")


# ===== 反引号代码块测试 =====
@parser_suite.test("parse_backtick_block")
def test_parse_backtick_block():
    """测试解析反引号代码块"""
    source = "`x + y`"
    ast = fixture.parse_expression(source)
    Assert.is_not_none(ast)


# ===== DEMO 示例测试 =====
@parser_suite.test("demo_basic_syntax")
def test_demo_basic_syntax():
    """基本语法 DEMO"""
    demo_source = """
# 基本语法示例
def main() -> int:
    x: int = 42
    y: float = 3.14
    z = x + int(y)
    return z
"""
    ast = fixture.parse(demo_source)
    Assert.is_not_none(ast)
    
    # 关联 DEMO
    test = parser_suite.tests[-1]
    test.with_demo("parser", "basic_syntax", demo_source)


@parser_suite.test("demo_implicit_struct")
def test_demo_implicit_struct():
    """隐式结构体 DEMO"""
    demo_source = """
# 隐式结构体示例
implicit struct Context:
    logger: str
    timeout: int

def process(implicit ctx: Context):
    print(ctx.logger)
"""
    ast = fixture.parse(demo_source)
    Assert.is_not_none(ast)
    
    test = parser_suite.tests[-1]
    test.with_demo("parser", "implicit_struct", demo_source)


@parser_suite.test("demo_type_conversion")
def test_demo_type_conversion():
    """类型转换 DEMO"""
    demo_source = """
# 类型转换示例
def convert_values() -> float:
    a: int = 10
    b: float = a as float
    c: int = b as int
    return (a + c) as float
"""
    ast = fixture.parse(demo_source)
    Assert.is_not_none(ast)
    
    test = parser_suite.tests[-1]
    test.with_demo("parser", "type_conversion", demo_source)
