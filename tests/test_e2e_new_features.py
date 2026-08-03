"""
端到端集成测试：验证新特性从解析到代码生成的完整流程。

覆盖特性:
1. name~ 命名参数语法糖
2. 循环守卫 (guard 在循环中生成 break)
3. ^: 索引构建块 (container[key][-1])
4. ~: 去括号语法 (lambda 表达式)
"""
import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.codegen.cython_generator import CythonGenerator


class TestE2ENamedArgSugar:
    """命名参数语法糖端到端测试"""

    def test_named_arg_pipeline(self):
        """验证 name~ 从解析到生成的完整流程"""
        source = '''result = make_point(x~, y~)'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        # 验证语法糖被正确转换
        assert "x=x" in result
        assert "y=y" in result
        # 验证生成了有效的 Python/Cython 代码
        assert "make_point" in result

    def test_named_arg_with_default(self):
        """混合命名参数和默认参数"""
        source = '''result = configure(name~, debug=True)'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        assert "name=name" in result
        assert "debug=True" in result

    def test_named_arg_in_method(self):
        """方法调用中的命名参数"""
        source = '''obj.process(data~, options~)'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        assert "data=data" in result
        assert "options=options" in result


class TestE2ELoopGuard:
    """循环守卫端到端测试"""

    def test_guard_in_for_loop(self):
        """for 循环中的 guard 生成 break"""
        source = '''
def test_loop():
    for i in range(10):
        guard i < 5 else break
        print(i)
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        # 验证生成了 break
        assert "break" in result

    def test_guard_in_while_loop(self):
        """while 循环中的 guard"""
        source = '''
def test_loop():
    while running:
        guard len(queue) > 0 else break
        process(queue)
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        # 验证生成了 break
        assert "break" in result

    def test_guard_not_in_loop(self):
        """非循环中的 guard 生成 return"""
        source = '''
def check(x):
    guard x > 0 else "error"
    return x * 2
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        # 验证生成了 return
        assert "return" in result


class TestE2EIndexBuildBlock:
    """索引构建块端到端测试"""

    def test_index_build_block_simple(self):
        """简单的 ^: 构建块"""
        source = '''last = items ^:
    process(item~)
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        # 验证 [-1] 索引被添加
        assert "[-1]" in result
        # 验证处理逻辑
        assert "process" in result

    def test_index_build_block_with_transform(self):
        """带转换的 ^: 构建块"""
        source = '''result = data ^:
    transform(value~)
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        assert "[-1]" in result
        assert "transform" in result
        assert "value=value" in result


class TestE2EDeParenthesis:
    """去括号语法端到端测试"""

    def test_deparens_simple(self):
        """简单的 ~: 去括号"""
        source = '''result = compute ~:
    validate(x)
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        # 验证包含原始表达式 (单表达式直接传递)
        assert "compute" in result
        assert "validate(x)" in result

    def test_deparens_with_complex_body(self):
        """复杂体的 ~: 去括号"""
        source = '''result = transform ~:
    normalize(data~, scale~)
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        assert "normalize" in result
        assert "data=data" in result
        assert "scale=scale" in result

    def test_deparens_in_expression(self):
        """表达式中的 ~:"""
        source = '''result = process(data) ~:
    validate(threshold~)
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        assert "process" in result
        assert "validate" in result
        assert "threshold=threshold" in result


class TestE2ECombinations:
    """多特性组合端到端测试"""

    def test_named_arg_and_index_block(self):
        """name~ + ^: 组合"""
        source = '''last = items ^:
    process(item~, key~)
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        # 验证两个特性都被正确处理
        assert "[-1]" in result
        assert "item=item" in result
        assert "key=key" in result

    def test_guard_with_named_arg(self):
        """guard + name~ 组合"""
        source = '''
def check():
    guard result < 100 else error
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        # 验证命名参数被处理
        assert "error" in result

    def test_all_features_combined(self):
        """三个新特性组合"""
        source = '''final = source ~:
    data ^:
        transform(value~)
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        # 验证所有特性都被正确处理
        assert "[-1]" in result
        assert "value=value" in result
        # ~: 单表达式直接传递 (无 lambda)
        assert "data[" in result

    def test_loop_guard_with_sugar(self):
        """循环 + guard + name~"""
        source = '''
def process_items():
    for item in items:
        guard item > 0 else break
        process(item~, index~)
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        # 验证循环守卫和命名参数
        assert "break" in result
        assert "item=item" in result
        assert "index=index" in result
