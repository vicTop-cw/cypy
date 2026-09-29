"""测试新增特性的代码生成"""

from cypyc.parser.parser import Parser
from cypyc.parser.lexer import Lexer
from cypy_bridge.compiler import CCodeGenerator


def test_assert_stmt_codegen():
    """测试 assert 语句代码生成"""
    source = '''def test_assert():
    assert x > 0
    assert y > 0, "y must be positive"'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    codegen = CCodeGenerator()
    c_code = codegen.generate(ast, "test_mod")

    # 验证 assert 语句生成了正确的 C 代码
    assert "if (!((x > 0))) {" in c_code
    assert 'PyErr_SetString(PyExc_AssertionError, "assertion failed");' in c_code
    assert 'PyErr_SetString(PyExc_AssertionError, "y must be positive");' in c_code


def test_match_stmt_codegen():
    """测试 match/case 语句代码生成"""
    source = '''def test_match(x):
    match x:
        case 0:
            return "zero"
        case 1:
            return "one"
        case _:
            return "other"'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    codegen = CCodeGenerator()
    c_code = codegen.generate(ast, "test_mod")

    # 验证 match 语句生成了正确的 if-else 链（整数不再被加引号）
    assert "_match_subject" in c_code
    assert "if (_match_subject == 0)" in c_code
    assert "else if (_match_subject == 1)" in c_code
    assert "else" in c_code


def test_match_with_or_pattern_codegen():
    """测试 match/case OR 模式代码生成"""
    source = '''def test_match_or(x):
    match x:
        case 0 | 1 | 2:
            return "small"
        case _:
            return "large"'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    codegen = CCodeGenerator()
    c_code = codegen.generate(ast, "test_mod")

    # 验证 OR 模式生成了正确的条件表达式
    assert "_match_subject" in c_code
    assert "||" in c_code  # OR 模式使用 ||


def test_match_with_variable_pattern_codegen():
    """测试 match/case 变量模式代码生成"""
    source = '''def test_match_var(x):
    match x:
        case value:
            return value
        case _:
            return None'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    codegen = CCodeGenerator()
    c_code = codegen.generate(ast, "test_mod")

    # 验证变量模式生成了变量绑定
    assert "void* value = _match_subject;" in c_code


def test_struct_with_generic_codegen():
    """测试带泛型参数的结构体代码生成"""
    source = '''struct Container<T>:
    data: int'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    codegen = CCodeGenerator()
    c_code = codegen.generate(ast, "test_mod")

    # 验证泛型结构体生成了正确的名称
    assert "Container_T" in c_code


def test_decorator_codegen():
    """测试装饰器代码生成"""
    source = '''@test
def my_test():
    pass'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    codegen = CCodeGenerator()
    c_code = codegen.generate(ast, "test_mod")

    # 验证装饰器生成了正确的注释标记
    assert "// Register test: my_test" in c_code


def test_decorator_with_args_codegen():
    """测试带参数的装饰器代码生成"""
    source = '''@decorator("arg1", 42)
def my_func():
    pass'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    codegen = CCodeGenerator()
    c_code = codegen.generate(ast, "test_mod")

    # 验证带参数的装饰器生成了正确的注释标记
    assert "// Decorator: decorator" in c_code


def test_type_alias_codegen():
    """测试类型别名代码生成"""
    source = '''type MyInt = int'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    codegen = CCodeGenerator()
    c_code = codegen.generate(ast, "test_mod")

    # 验证类型别名生成了正确的typedef
    assert "typedef int MyInt;" in c_code


def test_union_type_codegen():
    """测试联合类型代码生成"""
    source = '''type Number = int | float'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    codegen = CCodeGenerator()
    c_code = codegen.generate(ast, "test_mod")

    # 验证联合类型生成了tagged union结构体
    assert "typedef struct Number" in c_code
    assert "int tag;" in c_code
    assert "union" in c_code


def test_build_block_call_codegen():
    """测试调用构建块代码生成"""
    source = '''def test_build():
    ~:
        x = 1
        y = 2
        x + y'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    codegen = CCodeGenerator()
    c_code = codegen.generate(ast, "test_mod")

    # 验证构建块生成了正确的代码
    assert "Build block call" in c_code


def test_integer_quoting_fix():
    """测试整数类型修复的全局效果"""
    source = '''def test_int():
    x = 42
    y = x + 1
    return y'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    codegen = CCodeGenerator()
    c_code = codegen.generate(ast, "test_mod")

    # 验证整数不再被加引号
    assert 'x = 42;' in c_code
    assert '"42"' not in c_code


def test_spawn_call_form_codegen():
    """测试 spawn 调用形式的代码生成"""
    source = '''def test_spawn():
    spawn my_task(1, 2)'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    codegen = CCodeGenerator()
    c_code = codegen.generate(ast, "test_mod")

    # 验证 spawn 调用生成了正确的 C 代码
    assert "Spawn: concurrent task execution" in c_code
    assert "PyThread_start_new_thread" in c_code
    assert "my_task" in c_code


def test_spawn_block_form_codegen():
    """测试 spawn 块形式的代码生成"""
    source = '''def test_spawn_block():
    spawn:
        x = 1
        y = 2
        return x + y'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    codegen = CCodeGenerator()
    c_code = codegen.generate(ast, "test_mod")

    # 验证 spawn 块生成了正确的 C 代码
    assert "Spawn: concurrent task execution" in c_code
    assert "_spawn_block_" in c_code


def test_go_call_form_codegen():
    """测试 go 调用形式的代码生成"""
    source = '''def test_go():
    go my_coroutine(3, 4)'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    codegen = CCodeGenerator()
    c_code = codegen.generate(ast, "test_mod")

    # 验证 go 调用生成了正确的 C 代码
    assert "Go: lightweight coroutine execution" in c_code
    assert "PyThread_start_new_thread" in c_code
    assert "my_coroutine" in c_code


def test_go_block_form_codegen():
    """测试 go 块形式的代码生成"""
    source = '''def test_go_block():
    go:
        a = 10
        b = 20
        return a * b'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    codegen = CCodeGenerator()
    c_code = codegen.generate(ast, "test_mod")

    # 验证 go 块生成了正确的 C 代码
    assert "Go: lightweight coroutine execution" in c_code
    assert "_go_block_" in c_code


def test_yield_stmt_codegen():
    """测试 yield 语句代码生成"""
    source = '''def test_yield():
    yield 1
    yield 2
    yield 3'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    codegen = CCodeGenerator()
    c_code = codegen.generate(ast, "test_mod")

    # 验证 yield 生成了迭代器类型和状态机框架
    assert "_test_yield_Generator" in c_code
    assert "PyObject_HEAD" in c_code
    assert "_gen_state" in c_code
    assert "_finished" in c_code
    assert "switch(gen->_gen_state)" in c_code
    assert "case 0:" in c_code
    assert "case 1:" in c_code
    assert "case 2:" in c_code
    assert "case 3:" in c_code
    assert "test_yield_create" in c_code
    assert "test_yield_iter" in c_code
    assert "test_yield_next" in c_code
    assert "test_yield_next_wrapper" in c_code
    assert "PyExc_StopIteration" in c_code


def test_macro_def_codegen():
    """测试 macro 宏定义代码生成（参考 lang-zone 语法）"""
    source = '''macro log_call(ts: Tokens)-> Tokens =
    print("Calling...")
    $(ts)
    print("Done.")'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    codegen = CCodeGenerator()
    c_code = codegen.generate(ast, "test_mod")

    # 验证宏定义生成了正确的 C 代码
    assert "// Macro: log_call" in c_code
    assert "static inline void log_call" in c_code


def test_comptime_expr_codegen():
    """测试 comptime 单行表达式代码生成（参考 lang-zone 语法）"""
    source = '''def test_comptime():
    PI = comptime: 3.141592653589793
    answer = comptime: 40 + 2
    return 0'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    codegen = CCodeGenerator()
    c_code = codegen.generate(ast, "test_mod")

    # 验证 comptime 表达式在编译期被求值
    # comptime: 3.141592653589793 -> 3.141592653589793
    # comptime: 40 + 2 -> 42
    assert "PI = 3.141592653589793;" in c_code
    assert "answer = 42;" in c_code


def test_comptime_block_codegen():
    """测试 comptime 块形式代码生成（参考 lang-zone 语法）"""
    source = '''comptime:
    PI = 3.141592653589793
    ANSWER = 42'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    codegen = CCodeGenerator()
    c_code = codegen.generate(ast, "test_mod")

    # 验证 comptime 块生成了正确的注释标记
    assert "// comptime block:" in c_code


def test_bang_identifier_codegen():
    """测试带!后缀的标识符代码生成（转译期辅助）"""
    source = '''def log!(msg):
    print(msg)

def test_bang():
    x! : int = 9'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    codegen = CCodeGenerator()
    c_code = codegen.generate(ast, "test_mod")

    # 验证带!后缀的标识符被正确处理
    assert "log!" in c_code


def test_comptime_short_circuit_folds_instead_of_degrading_to_comment():
    """OMEGA T0r61.3.2 永久回归：短路后的常量必须真的被折叠
    
    缺陷（comptime_evaluator 的 BinOp 先算两侧再分派）会让 evaluate_comptime() 把
    `False and (1/0)` 判成"不是常量"并返回 None，cython_generator 的
    _visit_ComptimeStmt 于是把整条语句降级成 `# comptime: ...` 注释——语句被静默丢掉。
    """
    from cypyc.codegen.cython_generator import CythonGenerator
    
    source = 'comptime: False and (1/0)\n'
    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()
    
    code = CythonGenerator().generate(ast)
    stripped = [line.strip() for line in code.splitlines()]
    
    assert "False" in stripped, code
    assert not any(line.startswith("# comptime:") for line in stripped), code


def test_comptime_or_short_circuit_folds_to_true():
    """`comptime: True or (1/0)` 折叠成 True，同样不能退化成注释"""
    from cypyc.codegen.cython_generator import CythonGenerator
    
    source = 'comptime: True or (1/0)\n'
    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()
    
    code = CythonGenerator().generate(ast)
    stripped = [line.strip() for line in code.splitlines()]
    
    assert "True" in stripped, code
    assert not any(line.startswith("# comptime:") for line in stripped), code


def test_comptime_arithmetic_still_folds():
    """回归保护：普通算术常量折叠不受短路改动影响（40 + 2 -> 42）"""
    from cypyc.codegen.cython_generator import CythonGenerator
    
    lexer = Lexer('comptime: 40 + 2\n')
    ast = Parser(lexer.tokenize()).parse()
    code = CythonGenerator().generate(ast)
    stripped = [line.strip() for line in code.splitlines()]
    assert "42" in stripped, code
    assert not any(line.startswith("# comptime:") for line in stripped), code
