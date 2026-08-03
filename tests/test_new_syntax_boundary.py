"""
新语法边界场景测试
- name~ 方法调用
- ^: 嵌套构建块
- ~: 复杂表达式
- name~ 与默认参数混合
"""
import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.codegen.cython_generator import CythonGenerator


class TestNameArgBoundary:
    """name~ 命名参数边界场景"""

    def test_named_arg_in_method_call(self):
        """name~ 在方法调用 obj.method(name~) 中"""
        source = '''
obj.method(name~, value~)
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        assert "name=name" in result
        assert "value=value" in result

    def test_named_arg_mixed_with_default(self):
        """name~ 与位置参数混合使用"""
        source = '''
func(1, name~, 2, value~)
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        assert "1" in result
        assert "name=name" in result
        assert "2" in result
        assert "value=value" in result

    def test_named_arg_in_build_block(self):
        """name~ 在构建块的函数调用中"""
        source = '''
result = get_user ~:
    validate(name~, age~)
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        assert "name=name" in result
        assert "age=age" in result

    def test_named_arg_multiple_sugar(self):
        """多个 name~ 在复杂函数调用中"""
        source = '''
create_point(x~, y~, z~)
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        assert "x=x" in result
        assert "y=y" in result
        assert "z=z" in result


class TestIndexBuildBlockBoundary:
    """^: 索引构建块边界场景"""

    def test_index_build_block_in_assignment(self):
        """^: 在赋值语句中"""
        source = '''
result = data ^:
    transform(x)
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

    def test_index_build_block_with_named_arg(self):
        """^: 构建块中使用 name~"""
        source = '''
result = list ^:
    process(item~)
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        assert "[-1]" in result
        assert "item=item" in result

    def test_index_build_block_multiline(self):
        """^: 多行构建块"""
        source = '''
result = numbers ^:
    transform(a)
    validate(b)
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        assert "[-1]" in result


class TestDeParenthesisBoundary:
    """~: 去括号边界场景"""

    def test_deparens_in_nested_call(self):
        """~: 在嵌套调用中 (单表达式直接传递)"""
        source = '''
outer(inner ~:
    process(data)
)
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        # 单表达式 ~: 直接传递值 (无 lambda)
        assert "process(data)" in result

    def test_deparens_chained(self):
        """~: 链式调用 (单表达式直接传递)"""
        source = '''
result = first ~:
    step1(data)
result2 = result ~:
    step2(data)
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        # 单表达式 ~: 直接传递值
        assert "step1(data)" in result
        assert "step2(data)" in result

    def test_deparens_with_named_arg(self):
        """~: 去括号中使用 name~"""
        source = '''
result = func ~:
    action(item~, value~)
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        # 单表达式 ~: 直接传递值
        assert "action(" in result
        assert "item=item" in result
        assert "value=value" in result

    def test_deparens_complex_expression(self):
        """~: 在复杂表达式中 (单表达式直接传递)"""
        source = '''
result = compute(x) ~:
    validate(y)
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        # 单表达式 ~: 直接传递值
        assert "validate(y)" in result


class TestCrossFeatureIntegration:
    """跨特性集成测试"""

    def test_named_arg_and_index_block(self):
        """name~ 和 ^: 组合"""
        source = '''
result = data ^:
    process(item~, key~)
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        assert "[-1]" in result
        assert "item=item" in result
        assert "key=key" in result

    def test_named_arg_deparens_and_index(self):
        """三个新特性组合"""
        source = '''
result = source ~:
    data ^:
        transform(item~)
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        # ^: 索引构建块保留 [-1]
        assert "[-1]" in result
        # name~ 语法糖保留
        assert "item=item" in result
        # ~: 单表达式直接传递 (无 lambda)
        assert "data[" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
