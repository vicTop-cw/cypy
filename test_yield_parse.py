from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser

code = """
def generate_numbers(n: int):
    for i in range(n):
        yield i
"""

lexer = Lexer(code)
tokens = list(lexer.tokenize())
print("Tokens:")
for t in tokens:
    print(f"  {t.type}: '{t.value}'")

parser = Parser(tokens)
ast = parser.parse()
print("\nAST:")
print(ast)

if ast.body:
    func_def = ast.body[0]
    print(f"\nFunction body: {func_def.body}")
    for stmt in func_def.body:
        print(f"  Stmt: {stmt.kind}")
        if stmt.kind == 'ForStmt':
            print(f"    ForStmt body: {stmt.body}")
            for inner_stmt in stmt.body:
                print(f"      Inner Stmt: {inner_stmt.kind}")
