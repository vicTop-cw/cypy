#!/usr/bin/env python3
"""OMEGA-verified repro unit T0r61.4.1 / defect 01.

Target: cypy_bridge/compiler.py:1653-1661  (CCodeGenerator._visit_TryStmt)

Claim: try/finally (and try/except) codegen emits FIXED local variable names
``_try_result`` / ``_try_result_obj`` / ``_try_returned`` with no per-block
uniquing (only the goto *label* is uniqued via ``buildblock_counter``).  Two
sibling try blocks in the same function therefore redeclare the same names in
one C scope -> hard "redefinition" compile error; a nested try silently
shadows (and clobbers) the outer block's state because
``current_try_result_var`` is the constant string "_try_result" for every level.

Evidence: real Lexer+Parser+CCodeGenerator output, then a real MSVC
``cl /c`` pass over the emitted C (when cl is on PATH).

Exit codes: 1 = defect REPRODUCED, 0 = not reproduced, 3 = harness error.
Writes only inside Find_BUG/audit_2026q3/scratch/codegen/.
"""
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir))
sys.path.insert(0, REPO)
SCRATCH = os.path.join(HERE, "scratch", "codegen")

if hasattr(sys.stdout, "reconfigure"):                       # console may be GBK
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def z(b):
    """Decode subprocess output and make it print-safe on any console codepage."""
    if isinstance(b, bytes):
        for enc in ("utf-8", "gbk", "cp936"):
            try:
                t = b.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            t = b.decode("utf-8", "replace")
    else:
        t = b or ""
    return t.encode("ascii", "replace").decode("ascii")


from cypyc.parser.lexer import Lexer            # noqa: E402
from cypyc.parser.parser import Parser          # noqa: E402
from cypy_bridge.compiler import CCodeGenerator  # noqa: E402

FIXED_NAMES = ("_try_result", "_try_result_obj", "_try_returned")

SIBLING_SRC = """
def two_sibling_try() -> int:
    try:
        let a: int = 1
    except ValueError as e1:
        let b: int = 2
    finally:
        let c: int = 3

    try:
        let d: int = 4
    except ValueError as e2:
        let f: int = 5
    finally:
        let g: int = 6

    return 0
"""

NESTED_SRC = """
def nested_try() -> int:
    try:
        let a: int = 1
    except BaseException as oe:
        try:
            let b: int = 2
        except ValueError as ie:
            let c: int = 3
        finally:
            let d: int = 4
    finally:
        let e2: int = 5
    return 0
"""


def emit(src, module_name):
    ast = Parser(Lexer(src).tokenize()).parse()
    c = CCodeGenerator().generate(ast, module_name)
    # mechanical shim, unrelated to the audited defect: the bridge emits bare
    # Python exception names as C identifiers (ValueError, BaseException ...).
    # Prepending the alias lets MSVC reach the audited redefinition error
    # instead of stopping on the missing symbol.
    c = c.replace(
        "#include <string.h>",
        "#include <string.h>\n"
        "#define ValueError PyExc_ValueError\n"
        "#define BaseException PyExc_BaseException\n", 1)
    return c


def func_body(c, fname):
    start = c.index("int %s() {" % fname)
    end = c.index("// Python module:", start)
    return c[start:end]


def declarations_in(body):
    """Return {name: [line numbers]} for the fixed try locals in one scope."""
    hits = {}
    for i, line in enumerate(body.splitlines(), 1):
        for n in FIXED_NAMES:
            if re.match(r"\s*(int|PyObject\*)\s+%s\s*=\s*0?NULL?0?;" % re.escape(n), line) or \
               re.match(r"\s*(int|PyObject\*)\s+%s\s*=" % re.escape(n), line):
                hits.setdefault(n, []).append((i, line.strip()))
    return hits


def try_cl_compile(path, tag):
    """Compile the emitted C with MSVC.  Return (available, rc, output)."""
    cl = shutil.which("cl")
    if not cl:
        return False, None, "cl.exe not on PATH"
    import sysconfig
    inc = sysconfig.get_paths()["include"]
    outdir = os.path.dirname(path)
    if not os.path.isdir(inc):
        return False, None, "Python headers not found at %s" % inc
    env = dict(os.environ)
    env["VSLANG"] = "1033"          # force English MSVC diagnostics
    cmd = [cl, "/nologo", "/c", "/I%s" % inc, os.path.basename(path)]
    p = subprocess.run(cmd, cwd=outdir, env=env, capture_output=True, timeout=180)
    raw = (p.stdout or b"") + (p.stderr or b"")
    return True, p.returncode, z(raw)


def main():
    os.makedirs(SCRATCH, exist_ok=True)
    reproduced, notes = [], []

    # ---------------- case A: sibling try blocks ----------------
    cA = emit(SIBLING_SRC, "d01_sibling")
    pathA = os.path.join(SCRATCH, "d01_sibling.c")
    open(pathA, "w", encoding="utf-8", newline="\n").write(cA)
    bodyA = func_body(cA, "two_sibling_try")
    declA = declarations_in(bodyA)

    print("=" * 72)
    print("CASE A - two sibling try/finally in one function (emitted C, %s)" % pathA)
    print("=" * 72)
    labels = [ln.strip() for ln in bodyA.splitlines() if ln.strip().startswith("_try_")]
    print("unique goto labels emitted : %s" % labels)
    dup = {n: v for n, v in declA.items() if len(v) > 1}
    for name in FIXED_NAMES:
        found = declA.get(name, [])
        print("  '%s' declared %d time(s) in one function scope, body line(s) %s"
              % (name, len(found), [ln for ln, _ in found]))
        for ln, text in found:
            print("      line %2d | %s" % (ln, text))
    if dup:
        reproduced.append("sibling try blocks redeclare %s in one function scope"
                          % ", ".join(sorted(dup)))

    ok, rc, out = try_cl_compile(pathA, "sibling")
    print("-" * 72)
    if not ok:
        print("MSVC check skipped: %s" % out)
        notes.append("cl unavailable -> source-level evidence only")
    else:
        print("cl /c %s -> exit %s" % (os.path.basename(pathA), rc))
        diag = [ln for ln in out.splitlines() if "error" in ln.lower() or "C23" in ln or "C20" in ln]
        for ln in diag[:12]:
            print("   " + ln)
        # MSVC localises its message text (and this console codepage is GBK), so the
        # diagnostics above may render as '?' -- the codes and identifiers are ASCII.
        if "C2374" in out:
            print("   [gloss] C2374 = \"redefinition; multiple initialization\"")
        if "C2086" in out:
            print("   [gloss] C2086 = \"redefinition; previous definition\"")
        if rc != 0 and re.search(r"C2374|C2371|C2086|C2011|redefinition|redeclared", out, re.I):
            reproduced.append("MSVC rejects the emitted C: "
                              + " | ".join(d.strip() for d in diag if "error" in d.lower()))
        elif rc != 0:
            notes.append("cl failed but not with a redefinition diagnostic")

    # ---------------- case B: nested try blocks ----------------
    cB = emit(NESTED_SRC, "d01_nested")
    pathB = os.path.join(SCRATCH, "d01_nested.c")
    open(pathB, "w", encoding="utf-8", newline="\n").write(cB)
    bodyB = func_body(cB, "nested_try")
    print()
    print("=" * 72)
    print("CASE B - nested try inside an except handler (emitted C, %s)" % pathB)
    print("=" * 72)
    inner = bodyB.splitlines()
    shown = 0
    for i, ln in enumerate(inner, 1):
        if any(re.match(r"\s*(int|PyObject\*)\s+%s\s*=" % re.escape(n), ln) for n in FIXED_NAMES):
            print("   body-line %2d | %s" % (i, ln.strip()))
            shown += 1
    print("   -> %d declarations of the same 3 fixed names; inner block SHADOWS the "
          "outer one (legal C, so no diagnostic) and" % shown)
    print("      current_try_result_var is the constant \"_try_result\" at :1661 for "
          "every nesting level, so outer state is clobbered.")
    src = open(os.path.join(REPO, "cypy_bridge", "compiler.py"), encoding="utf-8").read()
    if re.search(r'self\.current_try_result_var\s*=\s*"_try_result"', src):
        reproduced.append("nested try: current_try_result_var hardwired to \"_try_result\" "
                          "for every level (compiler.py:1661)")

    print()
    print("=" * 72)
    if reproduced:
        print("RESULT: REPRODUCED (%d independent confirmations)" % len(reproduced))
        for r in reproduced:
            print("  * " + r)
        for n in notes:
            print("  (note) " + n)
        return 1
    print("RESULT: NOT REPRODUCED")
    for n in notes:
        print("  (note) " + n)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        traceback_print = __import__("traceback").format_exc()
        sys.stderr.write("HARNESS ERROR\n" + traceback_print)
        sys.exit(3)
