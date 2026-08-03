"""测试提取器模式（参考Scala的unapply）以及优先级系统"""

import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser, ExtractorPattern, Pattern, Constant
from cypyc.codegen.cython_generator import CythonGenerator


def test_extractor_pattern_simple():
    """测试简单提取器模式 case Email(user, domain):"""
    source = '''match email:
    case Email(user, domain):
        print(user, domain)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert match_stmt.kind == "MatchStmt"
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, ExtractorPattern)
    assert pattern.type_name == "Email"
    assert len(pattern.args) == 2
    assert pattern.args[0].name == "user"
    assert pattern.args[1].name == "domain"


def test_extractor_pattern_with_constants():
    """测试提取器模式带常量 case Email("admin", domain):"""
    source = '''match email:
    case Email("admin", domain):
        print(domain)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    match_stmt = ast.body[0]
    pattern = match_stmt.cases[0].pattern
    
    assert isinstance(pattern, ExtractorPattern)
    assert isinstance(pattern.args[0], Constant)
    assert pattern.args[0].value == "admin"
    assert isinstance(pattern.args[1], Pattern)
    assert pattern.args[1].name == "domain"


def test_extractor_pattern_nested():
    """测试嵌套提取器模式 case Point(Point(x, y), z):"""
    source = '''match data:
    case Point(Point(x, y), z):
        print(x, y, z)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    match_stmt = ast.body[0]
    pattern = match_stmt.cases[0].pattern
    
    assert isinstance(pattern, ExtractorPattern)
    assert pattern.type_name == "Point"
    assert len(pattern.args) == 2
    
    # 第一个参数是嵌套的提取器模式
    inner_pattern = pattern.args[0]
    assert isinstance(inner_pattern, ExtractorPattern)
    assert inner_pattern.type_name == "Point"


def test_extractor_pattern_with_or():
    """测试提取器模式与OR模式组合"""
    source = '''match email:
    case Email("admin", _) | Email("root", _):
        print("Admin email")'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    match_stmt = ast.body[0]
    pattern = match_stmt.cases[0].pattern
    
    assert isinstance(pattern, dict)
    assert "or" in pattern
    assert len(pattern["or"]) == 2
    
    for p in pattern["or"]:
        assert isinstance(p, ExtractorPattern)
        assert p.type_name == "Email"


def test_extractor_pattern_with_conditional():
    """测试提取器模式带条件 case Email(user, domain) if len(user) > 5:"""
    source = '''match email:
    case Email(user, domain) if len(user) > 5:
        print(user)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    match_stmt = ast.body[0]
    pattern = match_stmt.cases[0].pattern
    
    assert isinstance(pattern, dict)
    assert "pattern" in pattern
    assert "condition" in pattern
    
    extractor_pattern = pattern["pattern"]
    assert isinstance(extractor_pattern, ExtractorPattern)
    assert extractor_pattern.type_name == "Email"


def test_extractor_pattern_with_as():
    """测试提取器模式带 as 绑定 case Email(user, domain) as e:"""
    source = '''match email:
    case Email(user, domain) as e:
        print(e, user, domain)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    match_stmt = ast.body[0]
    pattern = match_stmt.cases[0].pattern
    
    from cypyc.parser.parser import AsPattern
    assert isinstance(pattern, AsPattern)
    assert pattern.name == "e"
    
    inner_pattern = pattern.pattern
    assert isinstance(inner_pattern, ExtractorPattern)
    assert inner_pattern.type_name == "Email"


def test_extractor_pattern_empty_args():
    """测试空参数提取器模式 case Empty():"""
    source = '''match result:
    case Empty():
        print("No result")'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    match_stmt = ast.body[0]
    pattern = match_stmt.cases[0].pattern
    
    assert isinstance(pattern, ExtractorPattern)
    assert pattern.type_name == "Empty"
    assert len(pattern.args) == 0


def test_extractor_pattern_scope_analysis():
    """测试提取器模式的作用域分析"""
    from cypyc.analyzer.scope_analyzer import ScopeAnalyzer
    
    source = '''struct Email:
    address: str

def test_match(obj):
    match obj:
        case Email(user, domain):
            print(user, domain)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    analyzer = ScopeAnalyzer()
    root_scope = analyzer.analyze(ast)
    
    assert not analyzer.errors
    
    # 验证变量 user 和 domain 在函数作用域中可访问
    # 通过检查分析器没有错误来验证作用域分析正确


def test_extractor_pattern_type_checker():
    """测试提取器模式的类型检查"""
    from cypyc.analyzer.type_checker import TypeChecker
    
    source = '''struct Email:
    address: str
    
def test_match(email):
    match email:
        case Email(user, domain):
            print(user, domain)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    checker = TypeChecker()
    checker.check(ast)
    
    assert not checker.errors


def test_extractor_pattern_codegen():
    """测试提取器模式的代码生成（验证优先级调度逻辑）"""
    from cypyc.codegen.cython_generator import CythonGenerator
    
    source = '''def test_match(email):
    match email:
        case Email(user, domain):
            print(user, domain)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    codegen = CythonGenerator()
    code = codegen.generate(ast)
    
    # 验证生成的代码包含优先级调度逻辑
    assert "__unapply__" in code
    assert "__unapply_seq__" in code
    assert "__unwarp__" in code
    assert "__match_args__" in code


# ==================== 范围模式测试 ====================

def test_range_pattern_integer():
    """测试整数范围模式 case 1..10:"""
    source = '''match value:
    case 1..10:
        print("small")'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    match_stmt = ast.body[0]
    pattern = match_stmt.cases[0].pattern
    
    from cypyc.parser.parser import RangePattern
    assert isinstance(pattern, RangePattern)
    assert pattern.lower.value == 1
    assert pattern.upper.value == 10


def test_range_pattern_float():
    """测试浮点数范围模式 case 1.5..10.5:"""
    source = '''match value:
    case 1.5..10.5:
        print("medium")'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    match_stmt = ast.body[0]
    pattern = match_stmt.cases[0].pattern
    
    from cypyc.parser.parser import RangePattern
    assert isinstance(pattern, RangePattern)
    assert pattern.lower.value == 1.5
    assert pattern.upper.value == 10.5


def test_range_pattern_codegen():
    """测试范围模式的代码生成"""
    from cypyc.codegen.cython_generator import CythonGenerator
    
    source = '''def test_range(x):
    match x:
        case 1..10:
            return "small"'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    codegen = CythonGenerator()
    code = codegen.generate(ast)
    
    # 验证范围模式转换为守卫条件
    assert "1 <= _ < 10" in code


def test_range_pattern_with_conditional():
    """测试范围模式带条件 case 1..10 if x % 2 == 0:"""
    source = '''match value:
    case 1..10 if value % 2 == 0:
        print("even")'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    match_stmt = ast.body[0]
    pattern = match_stmt.cases[0].pattern
    
    assert isinstance(pattern, dict)
    assert "pattern" in pattern
    assert "condition" in pattern
    
    from cypyc.parser.parser import RangePattern
    assert isinstance(pattern["pattern"], RangePattern)


# ==================== match 表达式测试 ====================

def test_match_expr_simple():
    """测试 match 表达式作为返回值"""
    source = '''def classify(x):
    return match x:
        case 1: "one"
        case 2: "two"
        case _: "other"
'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    from cypyc.parser.parser import MatchExpr
    return_stmt = ast.body[0].body[0]
    assert isinstance(return_stmt.value, MatchExpr)


def test_match_expr_range_pattern():
    """测试 match 表达式带范围模式"""
    source = '''def classify(x):
    return match x:
        case 1..10: "small"
        case 10..100: "medium"
        case _: "large"
'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    codegen = CythonGenerator()
    code = codegen.generate(ast)
    
    # 验证生成的代码包含三元运算符
    assert "if 1 <= _match_subject < 10" in code
    assert "if 10 <= _match_subject < 100" in code


def test_match_expr_with_conditional():
    """测试 match 表达式带条件"""
    source = '''def check(x):
    return match x:
        case x if x > 0: "positive"
        case x if x < 0: "negative"
        case _: "zero"
'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    codegen = CythonGenerator()
    code = codegen.generate(ast)
    
    assert "positive" in code
    assert "negative" in code


# ==================== 解构绑定测试 ====================

def test_let_tuple_destructuring():
    """测试 let 语句中的元组解构绑定"""
    source = '''def test():
    let (x, y) = (1, 2)
    print(x + y)
'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    let_stmt = ast.body[0].body[0]
    assert isinstance(let_stmt.name, list)
    assert len(let_stmt.name) == 2


def test_let_list_destructuring():
    """测试 let 语句中的列表解构绑定"""
    source = '''def test():
    let [a, b, *rest] = [1, 2, 3, 4]
    print(a, b, rest)
'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    let_stmt = ast.body[0].body[0]
    from cypyc.parser.parser import ArrayPattern
    assert isinstance(let_stmt.name, ArrayPattern)
    assert let_stmt.name.rest_name == "rest"


def test_let_dict_destructuring():
    """测试 let 语句中的字典解构绑定（仅测试解析）"""
    source = '''def test():
    let {"name": n, "age": a} = get_person()
    print(n, a)
'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    let_stmt = ast.body[0].body[0]
    from cypyc.parser.parser import DictPattern
    assert isinstance(let_stmt.name, DictPattern)
    assert len(let_stmt.name.pairs) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])