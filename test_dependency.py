import tempfile
import os
import sys

tmpdir = tempfile.mkdtemp()
sys.path.insert(0, '.')
sys.path.insert(0, tmpdir)

from cypy_hook.hook import CypyHook

hook = CypyHook()
hook.set_output_dir(tmpdir)

# Create base module
f1 = os.path.join(tmpdir, 'e2e_base.cypy')
with open(f1, 'w', encoding='utf-8') as f:
    f.write('def get_constant() -> int:\n')
    f.write('    return 42\n')

result1 = hook.compile_to_pyd(f1)
print('Base success:', result1.success, result1.errors)

# Create dependency module
f2 = os.path.join(tmpdir, 'e2e_dep.cypy')
with open(f2, 'w', encoding='utf-8') as f:
    f.write('from e2e_base import get_constant\n')
    f.write('def use_constant() -> int:\n')
    f.write('    return get_constant() * 2\n')

result2 = hook.compile_to_pyd(f2)
print('Dep success:', result2.success, result2.errors)
