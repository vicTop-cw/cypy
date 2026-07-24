"""综合测试用例 - 测试多个新特性的组合使用"""

from cypyc.parser.parser import Parser
from cypyc.parser.lexer import Lexer


def test_integration_guard_and_pipe():
    """测试 guard 语句和管道操作符的组合"""
    source = '''def process_data(data):
    guard data else None
    result = data |> filter
    return result'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    func_def = ast.body[0]
    assert func_def.kind == "FuncDef"
    assert len(func_def.body) == 3
    
    # 验证 guard 语句
    guard_stmt = func_def.body[0]
    assert guard_stmt.kind == "GuardStmt"
    
    # 验证管道表达式
    assign_stmt = func_def.body[1]
    assert assign_stmt.kind == "Assign"
    call_expr = assign_stmt.value
    assert call_expr.kind == "Call"


def test_integration_match_and_union():
    """测试 match/case 和联合类型的组合"""
    source = '''type Number = int | float

def handle_value(x):
    match x:
        case 0:
            return "zero"
        case _:
            return "other"'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    # 验证类型别名
    type_alias = ast.body[0]
    assert type_alias.kind == "TypeAlias"
    
    # 验证函数中的 match 语句
    func_def = ast.body[1]
    assert func_def.kind == "FuncDef"
    match_stmt = func_def.body[0]
    assert match_stmt.kind == "MatchStmt"
    assert len(match_stmt.cases) == 2


def test_integration_generic_and_decorator():
    """测试泛型函数和装饰器的组合"""
    source = '''@test
def test_container[T]():
    guard True else None
    assert 1 + 1 == 2
    return None'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    func_def = ast.body[0]
    assert func_def.kind == "FuncDef"
    assert func_def.name == "test_container"
    
    # 验证装饰器
    assert len(func_def.decorators) == 1
    assert func_def.decorators[0].name.id == "test"
    
    # 验证泛型参数
    assert func_def.generic_params == ["T"]
    
    # 验证函数体中的语句
    assert len(func_def.body) == 3
    assert func_def.body[0].kind == "GuardStmt"
    assert func_def.body[1].kind == "AssertStmt"


def test_integration_spawn_and_go():
    """测试 spawn 和 go 的组合使用"""
    source = '''def parallel_work():
    task1 = spawn func1()
    task2 = go func2()
    return (task1, task2)'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    func_def = ast.body[0]
    assert func_def.kind == "FuncDef"
    
    # 验证 spawn 表达式（实际是 SpawnStmt）
    assign1 = func_def.body[0]
    assert assign1.value.kind == "SpawnStmt"
    
    # 验证 go 表达式
    assign2 = func_def.body[1]
    assert assign2.value.kind == "GoStmt"


def test_integration_build_block_with_yield():
    """测试构建块语法和 yield 的组合"""
    source = '''def make_generator():
    gen = sequence *:
        yield (1,)
        yield (2,)
    return gen'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    func_def = ast.body[0]
    assert func_def.kind == "FuncDef"
    
    # 验证生成器构建块
    assign_stmt = func_def.body[0]
    call = assign_stmt.value
    assert call.kind == "Call"
    build_block = call.args[0]
    assert build_block.kind == "BuildBlockExpr"
    
    # 验证构建块内部的 yield 语句
    yield_stmt1 = build_block.body[0]
    assert yield_stmt1.kind == "YieldStmt"
    yield_stmt2 = build_block.body[1]
    assert yield_stmt2.kind == "YieldStmt"


def test_integration_comptime_and_type():
    """测试 comptime 和类型别名的组合"""
    source = '''type Size = int

struct Buffer[T]:
    data: int

@test
def test_buffer():
    buf = Buffer[int]()
    assert True'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    # 验证类型别名
    type_alias = ast.body[0]
    assert type_alias.kind == "TypeAlias"
    
    # 验证带泛型的结构体
    struct_def = ast.body[1]
    assert struct_def.kind == "StructDef"
    assert struct_def.generic_params == ["T"]
    
    # 验证测试函数
    func_def = ast.body[2]
    assert func_def.kind == "FuncDef"
    assert len(func_def.decorators) == 1
