from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.analyzer.scope_analyzer import ScopeAnalyzer
from cypyc.analyzer.type_checker import TypeChecker
from cypyc.codegen.cython_generator import CythonGenerator

code = """
def generate_numbers(n: int):
    for i in range(n):
        yield i
"""

# Lexer
lexer = Lexer(code)
tokens = list(lexer.tokenize())

# Parser
parser = Parser(tokens)
ast = parser.parse()

# Scope analyzer
scope_analyzer = ScopeAnalyzer()
scope = scope_analyzer.analyze(ast)

# Type checker
type_checker = TypeChecker()
type_checker.check(ast)

# Code generator
generator = CythonGenerator()

# Check is_generator
func_def = ast.body[0]
is_generator = generator._check_is_generator(func_def.body)
print(f"is_generator: {is_generator}")
print(f"Function body: {func_def.body}")
for stmt in func_def.body:
    print(f"  Stmt: {stmt.kind}")
    if hasattr(stmt, 'body'):
        print(f"    Body: {stmt.body}")
        for inner in stmt.body:
            print(f"      Inner: {inner.kind}")

# Generate code
result = generator.generate(ast)
print(f"\nGenerated code:\n{result}")
