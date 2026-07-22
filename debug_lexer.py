from cypyc.parser.lexer import Lexer

source = 'def allocate() -> int*:'
lexer = Lexer(source)
tokens = list(lexer.tokenize())
print('Tokens:')
for t in tokens:
    print(f'  {t.type} "{t.value}" at {t.line}:{t.col}')
