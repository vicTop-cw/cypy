"""测试模式匹配的切片模式（.. 和 ..var）以及类型模式"""

import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser, SlicePattern, TypePattern, Constant, Attribute, Name


def test_slice_pattern_trailing():
    """测试末尾切片模式 [x, ..]"""
    source = '''match lst:
    case [x, ..]:
        print(x)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert match_stmt.kind == "MatchStmt"
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert hasattr(pattern, 'kind') and pattern.kind == "ArrayPattern"
    assert len(pattern.elements) == 2
    
    # 第一个元素应该是变量模式
    assert hasattr(pattern.elements[0], 'kind') and pattern.elements[0].kind == "Pattern"
    assert pattern.elements[0].name == "x"
    
    # 第二个元素应该是切片模式（无变量名）
    assert isinstance(pattern.elements[1], SlicePattern)
    assert pattern.elements[1].name is None


def test_slice_pattern_leading():
    """测试开头切片模式 [.., x]"""
    source = '''match lst:
    case [.., x]:
        print(x)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert hasattr(pattern, 'kind') and pattern.kind == "ArrayPattern"
    assert len(pattern.elements) == 2
    
    # 第一个元素应该是切片模式（无变量名）
    assert isinstance(pattern.elements[0], SlicePattern)
    assert pattern.elements[0].name is None
    
    # 第二个元素应该是变量模式
    assert hasattr(pattern.elements[1], 'kind') and pattern.elements[1].kind == "Pattern"
    assert pattern.elements[1].name == "x"


def test_slice_pattern_with_var():
    """测试带变量绑定的切片模式 [x, ..rest, y]"""
    source = '''match lst:
    case [x, ..rest, y]:
        print(x, rest, y)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert hasattr(pattern, 'kind') and pattern.kind == "ArrayPattern"
    assert len(pattern.elements) == 3
    
    # 第一个元素应该是变量模式
    assert hasattr(pattern.elements[0], 'kind') and pattern.elements[0].kind == "Pattern"
    assert pattern.elements[0].name == "x"
    
    # 第二个元素应该是切片模式（绑定到 rest）
    assert isinstance(pattern.elements[1], SlicePattern)
    assert pattern.elements[1].name == "rest"
    
    # 第三个元素应该是变量模式
    assert hasattr(pattern.elements[2], 'kind') and pattern.elements[2].kind == "Pattern"
    assert pattern.elements[2].name == "y"


def test_slice_pattern_only():
    """测试单独的切片模式 [..]"""
    source = '''match lst:
    case [..]:
        print("any list")'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert hasattr(pattern, 'kind') and pattern.kind == "ArrayPattern"
    assert len(pattern.elements) == 1
    
    # 唯一元素应该是切片模式（无变量名）
    assert isinstance(pattern.elements[0], SlicePattern)
    assert pattern.elements[0].name is None


def test_slice_pattern_only_with_var():
    """测试单独带变量的切片模式 [..rest]"""
    source = '''match lst:
    case [..rest]:
        print(rest)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert hasattr(pattern, 'kind') and pattern.kind == "ArrayPattern"
    assert len(pattern.elements) == 1
    
    # 唯一元素应该是切片模式（绑定到 rest）
    assert isinstance(pattern.elements[0], SlicePattern)
    assert pattern.elements[0].name == "rest"


def test_slice_pattern_mixed():
    """测试混合模式 [a, b, ..rest, c, d]"""
    source = '''match lst:
    case [a, b, ..rest, c, d]:
        print(a, b, rest, c, d)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert hasattr(pattern, 'kind') and pattern.kind == "ArrayPattern"
    assert len(pattern.elements) == 5
    
    # 验证各个元素类型
    assert hasattr(pattern.elements[0], 'kind') and pattern.elements[0].kind == "Pattern"
    assert pattern.elements[0].name == "a"
    assert hasattr(pattern.elements[1], 'kind') and pattern.elements[1].kind == "Pattern"
    assert pattern.elements[1].name == "b"
    assert isinstance(pattern.elements[2], SlicePattern)
    assert pattern.elements[2].name == "rest"
    assert hasattr(pattern.elements[3], 'kind') and pattern.elements[3].kind == "Pattern"
    assert pattern.elements[3].name == "c"
    assert hasattr(pattern.elements[4], 'kind') and pattern.elements[4].kind == "Pattern"
    assert pattern.elements[4].name == "d"


def test_slice_pattern_codegen():
    """测试切片模式的代码生成"""
    from cypyc.codegen.cython_generator import CythonGenerator
    
    source = '''def test_match(lst):
    match lst:
        case [x, ..]:
            return x
        case [.., x]:
            return x
        case [x, ..rest, y]:
            return (x, rest, y)
        case [..]:
            return "any"
        case [..rest]:
            return rest'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    generator = CythonGenerator()
    code = generator.generate(ast)
    
    assert "case [x, *_]:" in code
    assert "case [*_, x]:" in code
    assert "case [x, *rest, y]:" in code
    assert "case [*_]:" in code
    assert "case [*rest]:" in code


def test_conditional_pattern_variable():
    """测试变量模式带条件 case x if x > 0:"""
    source = '''match value:
    case x if x > 0:
        print(x)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert match_stmt.kind == "MatchStmt"
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, dict)
    assert "pattern" in pattern
    assert "condition" in pattern
    assert hasattr(pattern["pattern"], 'kind') and pattern["pattern"].kind == "Pattern"
    assert pattern["pattern"].name == "x"
    assert hasattr(pattern["condition"], 'kind') and pattern["condition"].kind == "BinOp"
    assert pattern["condition"].op == ">"


def test_conditional_pattern_tuple():
    """测试元组模式带条件 case x, y if x + y > 0:"""
    source = '''match pair:
    case x, y if x + y > 0:
        print(x, y)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, dict)
    assert "pattern" in pattern
    assert "condition" in pattern
    assert isinstance(pattern["pattern"], list)
    assert len(pattern["pattern"]) == 2
    assert pattern["pattern"][0].name == "x"
    assert pattern["pattern"][1].name == "y"


def test_conditional_pattern_array():
    """测试数组模式带条件 case [x, ..] if len(x) > 0:"""
    source = '''match lst:
    case [x, ..] if x > 0:
        print(x)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, dict)
    assert "pattern" in pattern
    assert "condition" in pattern
    assert hasattr(pattern["pattern"], 'kind') and pattern["pattern"].kind == "ArrayPattern"


def test_conditional_pattern_struct():
    """测试结构体模式带条件 case Point { x } if x > 0:"""
    source = '''match point:
    case Point { x } if x > 0:
        print(x)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, dict)
    assert "pattern" in pattern
    assert "condition" in pattern
    assert hasattr(pattern["pattern"], 'kind') and pattern["pattern"].kind == "StructPattern"
    assert pattern["pattern"].struct_name == "Point"


def test_conditional_pattern_codegen():
    """测试带条件模式的代码生成"""
    from cypyc.codegen.cython_generator import CythonGenerator
    
    source = '''def test_match(value):
    match value:
        case x if x > 0:
            return x
        case x, y if x + y > 0:
            return (x, y)
        case [x, ..] if x > 0:
            return x
        case Point { x } if x > 0:
            return x'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    generator = CythonGenerator()
    code = generator.generate(ast)
    
    assert "case x if x > 0:" in code
    assert "case (x, y) if x + y > 0:" in code
    assert "case [x, *_] if x > 0:" in code
    assert "case Point(x=x) if x > 0:" in code


def test_nested_struct_pattern_direct():
    """测试直接嵌套结构体模式 - case Point { x: Point { y: pyy } }"""
    from cypyc.parser.parser import StructPattern
    
    source = '''match point:
    case Point { x: Point { y: pyy } }:
        print(pyy)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert match_stmt.kind == "MatchStmt"
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, StructPattern)
    assert pattern.struct_name == "Point"
    assert len(pattern.fields) == 1
    
    field_name, field_pattern = pattern.fields[0]
    assert field_name == "x"
    assert isinstance(field_pattern, StructPattern)
    assert field_pattern.struct_name == "Point"
    assert len(field_pattern.fields) == 1
    
    nested_field_name, nested_pattern = field_pattern.fields[0]
    assert nested_field_name == "y"
    assert nested_pattern.name == "pyy"


def test_nested_struct_pattern_multi_level():
    """测试多层嵌套结构体模式 - case Outer { inner: Inner { value: v } }"""
    from cypyc.parser.parser import StructPattern
    
    source = '''match obj:
    case Outer { inner: Inner { value: v } }:
        print(v)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, StructPattern)
    assert pattern.struct_name == "Outer"
    assert len(pattern.fields) == 1
    
    field_name, field_pattern = pattern.fields[0]
    assert field_name == "inner"
    assert isinstance(field_pattern, StructPattern)
    assert field_pattern.struct_name == "Inner"
    assert len(field_pattern.fields) == 1
    
    nested_field_name, nested_pattern = field_pattern.fields[0]
    assert nested_field_name == "value"
    assert nested_pattern.name == "v"


def test_nested_struct_pattern_deep():
    """测试深层嵌套结构体模式 - case Point { x: Point { y: Point { z: deep } } }"""
    from cypyc.parser.parser import StructPattern
    
    source = '''match p:
    case Point { x: Point { y: Point { z: deep } } }:
        print(deep)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, StructPattern)
    assert pattern.struct_name == "Point"
    
    field_name, field_pattern = pattern.fields[0]
    assert field_name == "x"
    assert isinstance(field_pattern, StructPattern)
    
    nested_field_name, nested_pattern = field_pattern.fields[0]
    assert nested_field_name == "y"
    assert isinstance(nested_pattern, StructPattern)
    
    deep_field_name, deep_pattern = nested_pattern.fields[0]
    assert deep_field_name == "z"
    assert deep_pattern.name == "deep"


def test_nested_struct_pattern_with_array():
    """测试结构体中嵌套数组模式 - case Point { x: [Point { y: p1 }, Point { y: p2 }] }"""
    from cypyc.parser.parser import StructPattern, ArrayPattern
    
    source = '''match p:
    case Point { x: [Point { y: p1 }, Point { y: p2 }] }:
        print(p1, p2)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, StructPattern)
    assert pattern.struct_name == "Point"
    assert len(pattern.fields) == 1
    
    field_name, field_pattern = pattern.fields[0]
    assert field_name == "x"
    assert isinstance(field_pattern, ArrayPattern)
    assert len(field_pattern.elements) == 2
    
    for i, element in enumerate(field_pattern.elements):
        assert isinstance(element, StructPattern)
        assert element.struct_name == "Point"
        assert len(element.fields) == 1
        nested_field_name, nested_pattern = element.fields[0]
        assert nested_field_name == "y"
        assert nested_pattern.name == f"p{i+1}"


def test_nested_struct_pattern_codegen():
    """测试嵌套结构体模式的代码生成"""
    from cypyc.codegen.cython_generator import CythonGenerator
    
    source = '''struct Point:
    x: int
    y: int

struct Outer:
    inner: int

struct Inner:
    value: int

def test_match(p):
    match p:
        case Point { x: Point { y: pyy } }:
            return pyy
        case Outer { inner: Inner { value: v } }:
            return v
        case Point { x: Point { y: Point { z: deep } } }:
            return deep
        case Point { x: [Point { y: p1 }, Point { y: p2 }] }:
            return (p1, p2)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    generator = CythonGenerator()
    code = generator.generate(ast)
    
    assert "case Point(x=Point(y=pyy)):" in code
    assert "case Outer(inner=Inner(value=v)):" in code
    assert "case Point(x=Point(y=Point(z=deep))):" in code
    assert "case Point(x=[Point(y=p1), Point(y=p2)]):" in code


def test_nested_struct_pattern_mixed_with_simple():
    """测试嵌套结构体模式与简单字段混合"""
    from cypyc.parser.parser import StructPattern
    
    source = '''match p:
    case Point { x: Point { y: py }, z }:
        print(py, z)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, StructPattern)
    assert pattern.struct_name == "Point"
    assert len(pattern.fields) == 2
    
    field_name_0, field_pattern_0 = pattern.fields[0]
    assert field_name_0 == "x"
    assert isinstance(field_pattern_0, StructPattern)
    
    field_name_1, field_pattern_1 = pattern.fields[1]
    assert field_name_1 == "z"
    assert field_pattern_1.name == "z"


def test_literal_or_pattern_integer():
    """测试多个整数常量的 OR 模式 - case 1 | 2 | 3:"""
    source = '''match value:
    case 1 | 2 | 3:
        print("one of 1, 2, 3")'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert match_stmt.kind == "MatchStmt"
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, dict)
    assert "or" in pattern
    assert len(pattern["or"]) == 3
    
    for p, expected in zip(pattern["or"], [1, 2, 3]):
        assert isinstance(p, Constant)
        assert p.value == expected


def test_literal_or_pattern_string():
    """测试多个字符串常量的 OR 模式 - case "a" | "b":"""
    source = '''match value:
    case "a" | "b":
        print("one of a or b")'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, dict)
    assert "or" in pattern
    assert len(pattern["or"]) == 2
    
    for p, expected in zip(pattern["or"], ["a", "b"]):
        assert isinstance(p, Constant)
        assert p.value == expected


def test_literal_or_pattern_float():
    """测试多个浮点数常量的 OR 模式 - case 1.0 | 2.0:"""
    source = '''match value:
    case 1.0 | 2.0:
        print("one of 1.0 or 2.0")'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, dict)
    assert "or" in pattern
    assert len(pattern["or"]) == 2
    
    for p, expected in zip(pattern["or"], [1.0, 2.0]):
        assert isinstance(p, Constant)
        assert p.value == expected


def test_literal_or_pattern_bool():
    """测试布尔常量的 OR 模式 - case True | False:"""
    source = '''match value:
    case True | False:
        print("boolean")'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, dict)
    assert "or" in pattern
    assert len(pattern["or"]) == 2
    
    for p, expected in zip(pattern["or"], [True, False]):
        assert isinstance(p, Constant)
        assert p.value == expected


def test_literal_or_pattern_codegen():
    """测试字面量 OR 模式的代码生成"""
    from cypyc.codegen.cython_generator import CythonGenerator
    
    source = '''def test_match(value):
    match value:
        case 1 | 2 | 3:
            return "int"
        case "a" | "b":
            return "str"
        case 1.0 | 2.0:
            return "float"
        case True | False:
            return "bool"'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    generator = CythonGenerator()
    code = generator.generate(ast)
    
    assert "case 1 | 2 | 3:" in code
    assert 'case "a" | "b":' in code
    assert "case 1.0 | 2.0:" in code
    assert "case True | False:" in code


def test_literal_or_pattern_existing_functionality():
    """确保现有 OR 模式功能不受影响"""
    from cypyc.codegen.cython_generator import CythonGenerator
    
    source = '''def test_match(obj):
    match obj:
        case [x, ..] | [y, z]:
            return x
        case Point { x } | Point { y }:
            return x'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    generator = CythonGenerator()
    code = generator.generate(ast)
    
    assert "case [x, *_] | [y, z]:" in code


# 命名常量模式测试用例

def test_attribute_pattern_enum():
    """测试枚举常量模式 - case Color.Red:"""
    source = '''match color:
    case Color.Red:
        print("red")'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert match_stmt.kind == "MatchStmt"
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, Attribute)
    assert isinstance(pattern.value, Name)
    assert pattern.value.id == "Color"
    assert pattern.attr == "Red"


def test_attribute_pattern_class_constant():
    """测试类常量模式 - case SomeClass.CONSTANT:"""
    source = '''match value:
    case SomeClass.CONSTANT:
        print("constant")'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert match_stmt.kind == "MatchStmt"
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, Attribute)
    assert isinstance(pattern.value, Name)
    assert pattern.value.id == "SomeClass"
    assert pattern.attr == "CONSTANT"


def test_attribute_pattern_module_constant():
    """测试模块常量模式 - case module.CONST:"""
    source = '''match value:
    case module.CONST:
        print("module constant")'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert match_stmt.kind == "MatchStmt"
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, Attribute)
    assert isinstance(pattern.value, Name)
    assert pattern.value.id == "module"
    assert pattern.attr == "CONST"


def test_attribute_pattern_chain():
    """测试链式属性访问模式 - case module.Class.CONSTANT:"""
    source = '''match value:
    case module.Class.CONSTANT:
        print("chained")'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert match_stmt.kind == "MatchStmt"
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, Attribute)
    assert pattern.attr == "CONSTANT"
    assert isinstance(pattern.value, Attribute)
    assert pattern.value.attr == "Class"
    assert isinstance(pattern.value.value, Name)
    assert pattern.value.value.id == "module"


def test_attribute_pattern_or():
    """测试多个命名常量的 OR 模式 - case Color.Red | Color.Green:"""
    source = '''match color:
    case Color.Red | Color.Green:
        print("primary")'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert match_stmt.kind == "MatchStmt"
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, dict)
    assert "or" in pattern
    assert len(pattern["or"]) == 2
    
    for p in pattern["or"]:
        assert isinstance(p, Attribute)
        assert isinstance(p.value, Name)
        assert p.value.id == "Color"
        assert p.attr in ("Red", "Green")


def test_attribute_pattern_or_mixed():
    """测试命名常量与字面量的混合 OR 模式"""
    source = '''match value:
    case Color.Red | 0 | "default":
        print("mixed")'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert match_stmt.kind == "MatchStmt"
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, dict)
    assert "or" in pattern
    assert len(pattern["or"]) == 3
    
    assert isinstance(pattern["or"][0], Attribute)
    assert isinstance(pattern["or"][1], Constant)
    assert pattern["or"][1].value == 0
    assert isinstance(pattern["or"][2], Constant)
    assert pattern["or"][2].value == "default"


def test_attribute_pattern_codegen():
    """测试命名常量模式的代码生成"""
    from cypyc.codegen.cython_generator import CythonGenerator
    
    source = '''def test_match(color):
    match color:
        case Color.Red:
            return "red"
        case SomeClass.CONSTANT:
            return "constant"
        case module.CONST:
            return "module"
        case module.Class.VALUE:
            return "chained"
        case Color.Red | Color.Green:
            return "primary"
        case Color.Red | 0 | "default":
            return "mixed"'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    generator = CythonGenerator()
    code = generator.generate(ast)
    
    assert "case Color.Red:" in code
    assert "case SomeClass.CONSTANT:" in code
    assert "case module.CONST:" in code
    assert "case module.Class.VALUE:" in code
    assert "case Color.Red | Color.Green:" in code
    assert 'case Color.Red | 0 | "default":' in code


def test_attribute_pattern_with_conditional():
    """测试命名常量模式带条件"""
    source = '''match color:
    case Color.Red if brightness > 50:
        print("bright red")'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert match_stmt.kind == "MatchStmt"
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, dict)
    assert "pattern" in pattern
    assert "condition" in pattern
    assert isinstance(pattern["pattern"], Attribute)
    assert pattern["pattern"].attr == "Red"


def test_attribute_pattern_codegen_with_conditional():
    """测试命名常量模式带条件的代码生成"""
    from cypyc.codegen.cython_generator import CythonGenerator
    
    source = '''def test_match(color, brightness):
    match color:
        case Color.Red if brightness > 50:
            return "bright red"'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    generator = CythonGenerator()
    code = generator.generate(ast)
    
    assert "case Color.Red if brightness > 50:" in code


def test_attribute_pattern_existing_functionality():
    """确保现有属性访问功能不受影响"""
    from cypyc.codegen.cython_generator import CythonGenerator
    
    source = '''def test(obj):
    x = obj.attr1.attr2
    match obj.attr:
        case 1:
            return True'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    generator = CythonGenerator()
    code = generator.generate(ast)
    
    assert "x = obj.attr1.attr2" in code
    assert "case 1:" in code


# 类型模式测试用例

def test_type_pattern_int():
    """测试基本类型模式 - case int x:"""
    source = '''match value:
    case int x:
        print(x)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert match_stmt.kind == "MatchStmt"
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, TypePattern)
    assert pattern.type_name == "int"
    assert pattern.name == "x"


def test_type_pattern_str():
    """测试字符串类型模式 - case str s:"""
    source = '''match value:
    case str s:
        print(s)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, TypePattern)
    assert pattern.type_name == "str"
    assert pattern.name == "s"


def test_type_pattern_float():
    """测试浮点数类型模式 - case float f:"""
    source = '''match value:
    case float f:
        print(f)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, TypePattern)
    assert pattern.type_name == "float"
    assert pattern.name == "f"


def test_type_pattern_custom():
    """测试自定义类型模式 - case Point p:"""
    source = '''struct Point:
    x: int
    y: int

def test_match(obj):
    match obj:
        case Point p:
            print(p.x, p.y)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 2
    func_def = ast.body[1]
    assert func_def.kind == "FuncDef"
    
    match_stmt = func_def.body[0]
    assert match_stmt.kind == "MatchStmt"
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, TypePattern)
    assert pattern.type_name == "Point"
    assert pattern.name == "p"


def test_type_pattern_codegen():
    """测试类型模式的代码生成"""
    from cypyc.codegen.cython_generator import CythonGenerator
    
    source = '''def test_match(obj):
    match obj:
        case int x:
            return x
        case str s:
            return s
        case float f:
            return f
        case Point p:
            return p'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    generator = CythonGenerator()
    code = generator.generate(ast)
    
    assert "case int() as x:" in code
    assert "case str() as s:" in code
    assert "case float() as f:" in code
    assert "case Point() as p:" in code


def test_type_pattern_with_conditional():
    """测试类型模式带条件 - case int x if x > 0:"""
    source = '''match value:
    case int x if x > 0:
        print(x)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, dict)
    assert "pattern" in pattern
    assert "condition" in pattern
    assert isinstance(pattern["pattern"], TypePattern)
    assert pattern["pattern"].type_name == "int"
    assert pattern["pattern"].name == "x"


def test_type_pattern_codegen_with_conditional():
    """测试类型模式带条件的代码生成"""
    from cypyc.codegen.cython_generator import CythonGenerator
    
    source = '''def test_match(obj):
    match obj:
        case int x if x > 0:
            return x'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    generator = CythonGenerator()
    code = generator.generate(ast)
    
    assert "case int() as x if x > 0:" in code


def test_type_pattern_scope_analysis():
    """测试类型模式的作用域分析"""
    from cypyc.analyzer.scope_analyzer import ScopeAnalyzer
    
    source = '''def test_match(obj):
    match obj:
        case int x:
            print(x)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    analyzer = ScopeAnalyzer()
    analyzer.analyze(ast)
    
    assert not analyzer.errors


def test_type_pattern_type_checking():
    """测试类型模式的类型检查"""
    from cypyc.analyzer.type_checker import TypeChecker
    
    source = '''struct Point:
    x: int
    y: int

def test_match(obj):
    match obj:
        case int x:
            return x
        case str s:
            return s
        case Point p:
            return p'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    checker = TypeChecker()
    checker.check(ast)
    
    assert not checker.errors


# As 模式测试用例

def test_as_pattern_tuple():
    """测试元组模式带 as - case (x, y) as point:"""
    from cypyc.parser.parser import AsPattern
    
    source = '''match pair:
    case (x, y) as point:
        print(point)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert match_stmt.kind == "MatchStmt"
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, AsPattern)
    assert pattern.name == "point"
    assert isinstance(pattern.pattern, list)
    assert len(pattern.pattern) == 2
    assert pattern.pattern[0].name == "x"
    assert pattern.pattern[1].name == "y"


def test_as_pattern_array():
    """测试数组模式带 as - case [x, y] as arr:"""
    from cypyc.parser.parser import AsPattern, ArrayPattern
    
    source = '''match lst:
    case [x, y] as arr:
        print(arr)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, AsPattern)
    assert pattern.name == "arr"
    assert isinstance(pattern.pattern, ArrayPattern)
    assert len(pattern.pattern.elements) == 2


def test_as_pattern_struct():
    """测试结构体模式带 as - case Point { x, y } as p:"""
    from cypyc.parser.parser import AsPattern, StructPattern
    
    source = '''match point:
    case Point { x, y } as p:
        print(p)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, AsPattern)
    assert pattern.name == "p"
    assert isinstance(pattern.pattern, StructPattern)
    assert pattern.pattern.struct_name == "Point"


def test_as_pattern_type():
    """测试类型模式带 as - case int x as val:"""
    from cypyc.parser.parser import AsPattern, TypePattern
    
    source = '''match value:
    case int x as val:
        print(val)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, AsPattern)
    assert pattern.name == "val"
    assert isinstance(pattern.pattern, TypePattern)
    assert pattern.pattern.type_name == "int"
    assert pattern.pattern.name == "x"


def test_as_pattern_with_conditional():
    """测试带条件的模式带 as - case x as val if x > 0:"""
    from cypyc.parser.parser import AsPattern
    
    source = '''match value:
    case x as val if x > 0:
        print(val)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, dict)
    assert "condition" in pattern
    assert isinstance(pattern["pattern"], AsPattern)
    assert pattern["pattern"].name == "val"


def test_as_pattern_codegen():
    """测试 as 模式的代码生成"""
    from cypyc.codegen.cython_generator import CythonGenerator
    
    source = '''def test_match(obj):
    match obj:
        case (x, y) as point:
            return point
        case [x, y] as arr:
            return arr
        case Point { x, y } as p:
            return p
        case int x as val:
            return val
        case x as val if x > 0:
            return val'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    generator = CythonGenerator()
    code = generator.generate(ast)
    
    assert "case (x, y) as point:" in code
    assert "case [x, y] as arr:" in code
    assert "case Point(x=x, y=y) as p:" in code
    assert "case int() as x as val:" in code
    assert "case x as val if x > 0:" in code


def test_as_pattern_scope_analysis():
    """测试 as 模式的作用域分析"""
    from cypyc.analyzer.scope_analyzer import ScopeAnalyzer
    
    source = '''def test_match(obj):
    match obj:
        case (x, y) as point:
            print(x, y, point)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    analyzer = ScopeAnalyzer()
    analyzer.analyze(ast)
    
    assert not analyzer.errors


def test_as_pattern_type_checking():
    """测试 as 模式的类型检查"""
    from cypyc.analyzer.type_checker import TypeChecker
    
    source = '''struct Point:
    x: int
    y: int

def test_match(obj):
    match obj:
        case (x, y) as point:
            return point
        case Point { x, y } as p:
            return p'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    checker = TypeChecker()
    checker.check(ast)
    
    assert not checker.errors


# isinstance 类型守卫模式测试用例

def test_isinstance_guard_basic_int():
    """测试基础类型守卫 - case x if isinstance(x, int):"""
    source = '''match value:
    case x if isinstance(x, int):
        print(x)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert match_stmt.kind == "MatchStmt"
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, dict)
    assert "pattern" in pattern
    assert "condition" in pattern
    assert hasattr(pattern["pattern"], 'kind') and pattern["pattern"].kind == "Pattern"
    assert pattern["pattern"].name == "x"
    assert hasattr(pattern["condition"], 'kind') and pattern["condition"].kind == "Call"
    assert pattern["condition"].func.id == "isinstance"


def test_isinstance_guard_str():
    """测试字符串类型守卫 - case x if isinstance(x, str):"""
    source = '''match value:
    case x if isinstance(x, str):
        print(x)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, dict)
    assert "pattern" in pattern
    assert "condition" in pattern
    assert pattern["condition"].func.id == "isinstance"


def test_isinstance_guard_custom_type():
    """测试自定义类型守卫 - case x if isinstance(x, Point):"""
    source = '''struct Point:
    x: int
    y: int

def test_match(obj):
    match obj:
        case x if isinstance(x, Point):
            print(x.x, x.y)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 2
    func_def = ast.body[1]
    assert func_def.kind == "FuncDef"
    
    match_stmt = func_def.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, dict)
    assert "pattern" in pattern
    assert "condition" in pattern
    assert pattern["condition"].func.id == "isinstance"


def test_isinstance_guard_multiple():
    """测试多个类型守卫 - case x, y if isinstance(x, int) and isinstance(y, str):"""
    source = '''match pair:
    case x, y if isinstance(x, int) and isinstance(y, str):
        print(x, y)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, dict)
    assert "pattern" in pattern
    assert "condition" in pattern
    assert isinstance(pattern["pattern"], list)
    assert len(pattern["pattern"]) == 2
    assert hasattr(pattern["condition"], 'kind') and pattern["condition"].kind == "BinOp"
    assert pattern["condition"].op == "and"


def test_isinstance_guard_codegen():
    """测试 isinstance 类型守卫的代码生成"""
    from cypyc.codegen.cython_generator import CythonGenerator
    
    source = '''struct Point:
    x: int
    y: int

def test_match(value):
    match value:
        case x if isinstance(x, int):
            return x
        case x if isinstance(x, str):
            return x
        case x if isinstance(x, Point):
            return x
        case x, y if isinstance(x, int) and isinstance(y, str):
            return (x, y)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    generator = CythonGenerator()
    code = generator.generate(ast)
    
    assert "case x if isinstance(x, int):" in code
    assert "case x if isinstance(x, str):" in code
    assert "case x if isinstance(x, Point):" in code
    assert "case (x, y) if isinstance(x, int) and isinstance(y, str):" in code
    assert "return (x, y)" in code


def test_isinstance_guard_scope_analysis():
    """测试 isinstance 类型守卫的作用域分析"""
    from cypyc.analyzer.scope_analyzer import ScopeAnalyzer
    
    source = '''def test_match(obj):
    match obj:
        case x if isinstance(x, int):
            print(x)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    analyzer = ScopeAnalyzer()
    analyzer.analyze(ast)
    
    assert not analyzer.errors


def test_isinstance_guard_type_checking():
    """测试 isinstance 类型守卫的类型检查"""
    from cypyc.analyzer.type_checker import TypeChecker
    
    source = '''struct Point:
    x: int
    y: int

def test_match(obj):
    match obj:
        case x if isinstance(x, int):
            return x
        case x if isinstance(x, str):
            return x
        case x if isinstance(x, Point):
            return x'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    checker = TypeChecker()
    checker.check(ast)
    
    assert not checker.errors


# 映射模式测试用例

def test_dict_pattern_basic():
    """测试基本字典模式 - case {"name": n, "age": a}:"""
    from cypyc.parser.parser import DictPattern
    
    source = '''match obj:
    case {"name": n, "age": a}:
        print(n, a)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert match_stmt.kind == "MatchStmt"
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, DictPattern)
    assert len(pattern.pairs) == 2
    
    key1, value1 = pattern.pairs[0]
    assert key1.value == "name"
    assert value1.name == "n"
    
    key2, value2 = pattern.pairs[1]
    assert key2.value == "age"
    assert value2.name == "a"


def test_dict_pattern_wildcard():
    """测试字典模式中的通配符 - case {"key": _}:"""
    from cypyc.parser.parser import DictPattern
    
    source = '''match obj:
    case {"key": _}:
        print("has key")'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, DictPattern)
    assert len(pattern.pairs) == 1
    
    key, value = pattern.pairs[0]
    assert key.value == "key"
    assert value.id == "_"


def test_dict_pattern_rest():
    """测试字典模式中的剩余绑定 - case {"key": value, **rest}:"""
    from cypyc.parser.parser import DictPattern
    
    source = '''match obj:
    case {"key": value, **rest}:
        print(value, rest)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, DictPattern)
    assert len(pattern.pairs) == 1
    assert pattern.rest_name == "rest"
    
    key, value = pattern.pairs[0]
    assert key.value == "key"
    assert value.name == "value"


def test_dict_pattern_nested():
    """测试嵌套字典模式 - case {"key": {"nested": value}}:"""
    from cypyc.parser.parser import DictPattern
    
    source = '''match obj:
    case {"key": {"nested": value}}:
        print(value)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, DictPattern)
    assert len(pattern.pairs) == 1
    
    key, value_pattern = pattern.pairs[0]
    assert key.value == "key"
    assert isinstance(value_pattern, DictPattern)
    assert len(value_pattern.pairs) == 1
    
    nested_key, nested_value = value_pattern.pairs[0]
    assert nested_key.value == "nested"
    assert nested_value.name == "value"


def test_dict_pattern_codegen():
    """测试字典模式的代码生成"""
    from cypyc.codegen.cython_generator import CythonGenerator
    
    source = '''def test_match(obj):
    match obj:
        case {"name": n, "age": a}:
            return (n, a)
        case {"key": _}:
            return "has key"
        case {"key": value, **rest}:
            return (value, rest)
        case {"outer": {"inner": v}}:
            return v'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    generator = CythonGenerator()
    code = generator.generate(ast)
    
    assert 'case {"name": n, "age": a}:' in code
    assert 'case {"key": _}:' in code
    assert 'case {"key": value, **rest}:' in code
    assert 'case {"outer": {"inner": v}}:' in code


def test_dict_pattern_scope_analysis():
    """测试字典模式的作用域分析"""
    from cypyc.analyzer.scope_analyzer import ScopeAnalyzer
    
    source = '''def test_match(obj):
    match obj:
        case {"name": n, "age": a}:
            print(n, a)
        case {"key": value, **rest}:
            print(value, rest)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    analyzer = ScopeAnalyzer()
    analyzer.analyze(ast)
    
    assert not analyzer.errors


def test_dict_pattern_type_checking():
    """测试字典模式的类型检查"""
    from cypyc.analyzer.type_checker import TypeChecker
    
    source = '''def test_match(obj):
    match obj:
        case {"name": n, "age": a}:
            return (n, a)
        case {"key": value, **rest}:
            return rest'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    checker = TypeChecker()
    checker.check(ast)
    
    assert not checker.errors


def test_dict_pattern_empty():
    """测试空字典模式 - case {}:"""
    from cypyc.parser.parser import DictPattern
    
    source = '''match obj:
    case {}:
        print("empty dict")'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, DictPattern)
    assert len(pattern.pairs) == 0
    assert pattern.rest_name is None


def test_dict_pattern_only_rest():
    """测试仅剩余绑定的字典模式 - case **rest:"""
    from cypyc.parser.parser import DictPattern
    
    source = '''match obj:
    case **rest:
        print(rest)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, DictPattern)
    assert len(pattern.pairs) == 0
    assert pattern.rest_name == "rest"


def test_dict_pattern_mixed_with_conditional():
    """测试字典模式带条件 - case {"name": n} if n == "test":"""
    source = '''match obj:
    case {"name": n} if n == "test":
        print(n)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, dict)
    assert "pattern" in pattern
    assert "condition" in pattern
    
    from cypyc.parser.parser import DictPattern
    assert isinstance(pattern["pattern"], DictPattern)


def test_dict_pattern_codegen_with_conditional():
    """测试字典模式带条件的代码生成"""
    from cypyc.codegen.cython_generator import CythonGenerator
    
    source = '''def test_match(obj):
    match obj:
        case {"name": n} if n == "test":
            return n'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    generator = CythonGenerator()
    code = generator.generate(ast)
    
    assert 'case {"name": n} if n == "test":' in code


if __name__ == "__main__":
    pytest.main([__file__, "-v"])