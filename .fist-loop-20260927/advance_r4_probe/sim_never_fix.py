"""Simulate the one-line analyzer fix (teach _visit_Name about Never) and
measure: does the CLI pipeline then succeed, and is codegen output unchanged?"""
import sys, io, os
sys.path.insert(0, os.getcwd())
import cypyc.analyzer.type_checker as tc
from cypyc.parser.parser import Name

_orig = tc.TypeChecker._visit_Name
NEVER = {'Never', 'never'}

def patched(self, node):
    if isinstance(node, Name) and getattr(node, 'id', None) in NEVER:
        return tc.Type('Never')
    return _orig(self, node)

tc.TypeChecker._visit_Name = patched

from cypyc.cli import main
for f in sys.argv[1:]:
    print('====', f)
    rc = main(['transpile', f, '-o', '.fist-loop-20260927/advance_r4_probe/sim_out'])
    print('rc=', rc)
    p = '.fist-loop-20260927/advance_r4_probe/sim_out/' + os.path.basename(f).replace('.cypy', '.pyx')
    if os.path.exists(p):
        for i, line in enumerate(open(p, encoding='utf-8').read().splitlines(), 1):
            if 'NoReturn' in line or 'def ' in line:
                print(f'  pyx:{i}: {line}')
