"""
解析器测试夹具
提供解析源码、表达式、语句的便捷方法
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from cypyc.parser import Lexer, Parser, Preprocessor
from cypyc.parser.parser import ASTNode, Module


class ParserFixture:
    def __init__(self):
        self.lexer = None
        self.parser = None
    
    def parse(self, source: str) -> ASTNode:
        """
        解析完整源码为 AST
        
        :param source: Cypy 源代码
        :return: AST 节点
        """
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        return parser.parse()
    
    def parse_expression(self, expr: str) -> ASTNode:
        """
        解析单个表达式
        
        :param expr: 表达式字符串
        :return: 表达式 AST 节点
        """
        # 添加换行确保表达式被正确解析
        source = f"{expr}\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        
        if isinstance(ast, Module) and ast.body:
            return ast.body[0]
        return ast
    
    def parse_statement(self, stmt: str) -> ASTNode:
        """
        解析单个语句
        
        :param stmt: 语句字符串
        :return: 语句 AST 节点
        """
        source = f"{stmt}\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        
        if isinstance(ast, Module) and ast.body:
            return ast.body[0]
        return ast
    
    def parse_file(self, file_path: str) -> ASTNode:
        """
        解析文件内容
        
        :param file_path: 文件路径
        :return: AST 节点
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            source = f.read()
        return self.parse(source)
    
    def tokenize(self, source: str):
        """
        词法分析，返回 token 列表
        
        :param source: 源代码
        :return: token 列表
        """
        lexer = Lexer(source)
        return list(lexer.tokenize())
    
    def preprocess(self, source: str) -> str:
        """
        预处理源码
        
        :param source: 源代码
        :return: 预处理后的代码
        """
        preprocessor = Preprocessor()
        # Preprocessor 暴露的是 process()（曾误写为 preprocess()，AttributeError 会让
        # 这条夹具路径从未真正跑到预处理器，从而失去覆盖）
        return preprocessor.process(source)
    
    def parse_with_errors(self, source: str):
        """
        解析并捕获错误
        
        :param source: 源代码
        :return: (ast, errors) 元组
        """
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        
        try:
            ast = parser.parse()
            errors = []
        except Exception as e:
            ast = None
            errors = [str(e)]
        
        return ast, errors
