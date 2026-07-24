"""
测试套件模块
"""
from .parser_suite import parser_suite
from .analyzer_suite import analyzer_suite
from .codegen_suite import codegen_suite
from .integration_suite import integration_suite

__all__ = ['parser_suite', 'analyzer_suite', 'codegen_suite', 'integration_suite']
