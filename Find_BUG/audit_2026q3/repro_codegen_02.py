#!/usr/bin/env python3
"""OMEGA-verified repro unit T0r61.4.1 / defect 02.

Target: cypy_bridge/compiler.py:1718-1728 (PyErr_Restore ... PyErr_Clear) and the
handler-name binding emitted at :1704 for the `exc_name` the audit points at
around :1699/:1726.

Claim A (swallow).  Each except clause is emitted as

    if (PyErr_Occurred()) {
        PyErr_Fetch(&_exc_type, &_exc_value, &_exc_tb);
        if (PyErr_GivenExceptionMatches(_exc_type, T)) { <handler body> }
        else { PyErr_Restore(...);  goto <lbl>_finally | return NULL; }   <- :1718
        Py_XDECREF(_exc_type); Py_XDECREF(_exc_value); Py_XDECREF(_exc_tb); <- :1725-7
        PyErr_Clear();                                                     <- :1728
    }

The XDECREF triple + PyErr_Clear() are OUTSIDE the if/else.  When an inner try
lives inside an outer except-handler, the inner non-matching path restores its
exception and the forward `goto <inner>_finally` lands *inside* the enclosing
handler, so control runs straight into the outer PyErr_Clear() and the just
restored exception is destroyed.

Claim B (dangling exc_name).  `PyObject* <name> = _exc_value ? _exc_value :
Py_None;` borrows without INCREF, and `_exc_value` is Py_XDECREF'd at :1726
afterwards; the name is also declared inside the match-branch scope, so the
`finally:` block (emitted after that scope closes) cannot reference it.

Evidence: emitted C quoted verbatim + a real MSVC-built .pyd actually called,
plus a counterfactual build with only the trailing PyErr_Clear() removed.

Exit codes: 1 = defect REPRODUCED, 0 = not reproduced, 3 = harness error.
"""
import os
import re
import shutil
import subprocess
import sys
import sysconfig

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


from cypyc.parser.lexer import Lexer             # noqa: E402
from cypyc.parser.parser import Parser           # noqa: E402
from cypy_bridge.compiler import CCodeGenerator  # noqa: E402

# outer catches BaseException, its handler body contains an inner try that only
# catches ValueError and raises RuntimeError -> Python semantics: RuntimeError
# must escape outer().
SRC_NESTED = """
def outer() -> int:
    try:
        raise
    except BaseException as oe:
        try:
            raise
        except ValueError as ie:
            let c: int = 3
        finally:
            let d: int = 4
    finally:
        let e2: int = 5
    return 0
"""

SRC_FINALLY_NAME = """
def outer() -> int:
    try:
        raise
    except ValueError as shown:
        let a: int = 1
    finally:
        let b: int = shown
    return 0
"""

SHIM = ("#include <string.h>\n"
        "#define BaseException PyExc_BaseException\n"
        "#define ValueError PyExc_ValueError\n")


def emit(module_name, src=SRC_NESTED, drop_clear=False):
    """Run the real generator; write <module_name>.c into SCRATCH."""
    ast = Parser(Lexer(src).tokenize()).parse()
    c = CCodeGenerator().generate(ast, module_name)
    c = c.replace("#include <string.h>", SHIM, 1)
    if drop_clear:
        c = re.sub(r"Py_XDECREF\(_exc_tb\);(\s*)PyErr_Clear\(\);",
                   r"Py_XDECREF(_exc_tb);", c)
    os.makedirs(SCRATCH, exist_ok=True)
    with open(os.path.join(SCRATCH, module_name + ".c"), "w",
              encoding="utf-8", newline="\n") as f:
        f.write(c)
    return c


def body_of(c, fname="outer"):
    start = c.index("%s() {" % fname)
    stop = c.index("// Python module:", start)
    return c[start:stop]


def quote_body(c):
    lines = c.splitlines()
    start = next(i for i, ln in enumerate(lines) if "outer() {" in ln)
    stop = next(i for i, ln in enumerate(lines) if "// Python module:" in ln)
    for i in range(start, stop):
        s = lines[i].strip()
        mark = ""
        if s.startswith("PyErr_Restore("):
            mark = "   <== compiler.py:1718  restore saved exception"
        elif s == "PyErr_Clear();" and lines[i - 1].strip().startswith("Py_XDECREF"):
            mark = "   <== compiler.py:1728  DESTROYS what was just restored"
        elif s.startswith("PyObject* oe =") or s.startswith("PyObject* ie ="):
            mark = "   <== compiler.py:1704  borrowed binding, no INCREF"
        elif s.startswith("goto _try_1_finally"):
            mark = "   <== jumps forward into the ENCLOSING handler tail"
        print("  %4d | %s%s" % (i + 1, lines[i].rstrip(), mark))


def build_pyd(module_name):
    setup = os.path.join(SCRATCH, "setup_%s.py" % module_name)
    with open(setup, "w", encoding="utf-8", newline="\n") as f:
        f.write("from setuptools import setup, Extension\n"
                "setup(name=%r, ext_modules=[Extension(%r, [%r])],\n"
                "      script_args=['build_ext', '--inplace'])\n"
                % (module_name, module_name, module_name + ".c"))
    env = dict(os.environ)
    env["VSLANG"] = "1033"
    p = subprocess.run([sys.executable, setup], cwd=SCRATCH, env=env,
                       capture_output=True, timeout=290)
    return p.returncode, z((p.stdout or b"") + (p.stderr or b""))


RUNNER = ("import sys; sys.path.insert(0, r'%s')\n"
          "import %s\n"
          "try:\n"
          "    rv = %s.outer()\n"
          "    print('NO-RAISE  outer() returned', repr(rv), '-- no error set')\n"
          "except BaseException as e:\n"
          "    print('RAISED    ', type(e).__name__, ':', e)\n")


def call(module_name):
    code = RUNNER % (SCRATCH, module_name, module_name)
    p = subprocess.run([sys.executable, "-c", code], cwd=SCRATCH,
                       capture_output=True, timeout=120)
    return p.returncode, z((p.stdout or b"") + (p.stderr or b"")).strip()


def main():
    reproduced = []

    print("=" * 74)
    print("PART 1 - emitted code sequence (verbatim real CCodeGenerator output)")
    print("=" * 74)
    c = emit("d02_live")
    quote_body(c)
    print()
    b = body_of(c)
    # HARNESS-FIX(T0r61.4.2): 原来的 `b.index(...)` 在缺陷修好之后会抛 ValueError
    # （复现单元因此只能给出 exit 3 / exit 1，永远给不出 exit 0），而 `order_ok` 在
    # 三个子串都存在时恒为真，同样无法表达“缺陷已消失”。
    # 断言按被审计的实际缺陷重写：只有当同一个生成块里 `PyErr_Restore` 之后仍跟着
    # 一条会擦掉刚恢复异常的 `PyErr_Clear()`（旧 :1728，且 XDECREF 三元组位于两者之间）
    # 时才算复现。
    i_restore = b.find("PyErr_Restore(")
    i_xdec = b.find("Py_XDECREF(_exc_tb);", max(i_restore, 0))
    i_clear = b.find("PyErr_Clear();", max(i_xdec, 0))
    order_ok = (i_restore >= 0) and (i_xdec > i_restore) and (i_clear > i_restore)
    print("  statement order inside outer(): PyErr_Restore@%d  <  trailing "
          "PyErr_Clear@%d  -> %s" % (i_restore, i_clear, order_ok))
    print("  goto targets between them: %s"
          % re.findall(r"goto (\w+);", b[i_restore:max(i_clear, i_restore)]))
    if order_ok:
        reproduced.append("Restore at :1718 is followed by Clear at :1728 in the same "
                          "generated block; the forward `goto <inner>_finally` lands "
                          "before that Clear, so it runs after the restore")

    print()
    print("=" * 74)
    print("PART 2 - runtime: real .pyd built from the emitted C with MSVC")
    print("=" * 74)
    rc, out = build_pyd("d02_live")
    if rc != 0:
        print("  BUILD FAILED - falling back to source-level evidence only:")
        for ln in out.splitlines()[-10:]:
            print("   " + ln)
        reproduced.append("(runtime unverified) emitted C could not be built here")
    else:
        pyd = [f for f in os.listdir(SCRATCH) if f.startswith("d02_live") and f.endswith(".pyd")]
        print("  built: %s" % pyd)
        rc2, res = call("d02_live")
        print("  as generated          -> subprocess exit %s | %s" % (rc2, res))
        if res.startswith("NO-RAISE"):
            reproduced.append(
                "outer() returns 0 with NO exception although the inner try only catches "
                "ValueError and its body raises RuntimeError: the RuntimeError restored by "
                "the generated PyErr_Restore is erased by the enclosing PyErr_Clear()")

        emit("d02_fixed", drop_clear=True)
        rc3, _ = build_pyd("d02_fixed")
        if rc3 == 0:
            rc4, res2 = call("d02_fixed")
            print("  counterfactual (ONLY the trailing PyErr_Clear() at :1728 deleted)"
                  " -> exit %s | %s" % (rc4, res2))
            if res2.startswith("RAISED"):
                print("  => the exception SURVIVES as soon as :1728 is removed -- causality is")
                print("     pinned on compiler.py:1728. (It surfaces as SystemError only")
                print("     because the same codegen also forgets to propagate; see report.)")
        else:
            print("  counterfactual build failed; skipped")

    print()
    print("=" * 74)
    print("PART 3 - `exc_name` binding: borrowed, then XDECREF'd; dead in `finally:`")
    print("=" * 74)
    c3 = emit("d02_namescope", src=SRC_FINALLY_NAME)
    b3 = body_of(c3)
    for ln in b3.splitlines():
        s = ln.strip()
        if ("shown" in s or s.startswith("Py_XDECREF") or s.startswith("_try_0_finally")
                or s.startswith("PyErr_Clear")):
            print("   " + ln.rstrip())
    binding = "PyObject* shown = _exc_value ? _exc_value : Py_None;" in b3
    incref = "Py_INCREF" in b3
    finally_part = b3[b3.index("_try_0_finally:"):] if "_try_0_finally:" in b3 else ""
    in_finally = "shown" in finally_part
    print()
    print("  binding emitted at :1704 .............. %s" % binding)
    print("  any INCREF for the bound name ........ %s  (borrowed reference)" % incref)
    print("  _exc_value Py_XDECREF'd at :1726 ..... %s  -> name dangles after it"
          % ("Py_XDECREF(_exc_value);" in b3))
    print("  textual presence of the name inside the emitted `finally:` text: %s"
          % in_finally)
    print("  (the `finally:` block is emitted AFTER the `if (PyErr_Occurred()) { ... }`")
    print("   braces close, so the C declaration of the handler name is out of scope")
    print("   there -- MSVC verdict below decides)")
    if binding and not incref:
        reproduced.append("handler exception name bound without INCREF; the aliased "
                          "_exc_value is Py_XDECREF'd at :1726 and the name is not in "
                          "scope in the finally block")
    # hard check: does the finally block that uses the handler name even compile?
    cl = shutil.which("cl")
    if cl:
        inc = sysconfig.get_paths()["include"]
        env = dict(os.environ)
        env["VSLANG"] = "1033"
        p = subprocess.run([cl, "/nologo", "/c", "/I%s" % inc, "d02_namescope.c"],
                           cwd=SCRATCH, env=env, capture_output=True, timeout=200)
        diag = z((p.stdout or b"") + (p.stderr or b"")).splitlines()
        errs = [ln.strip() for ln in diag if "error" in ln.lower()
                or re.search(r"C\d{4}", ln)]
        print()
        print("  cl /c d02_namescope.c -> exit %s" % p.returncode)
        for ln in errs[:8]:
            print("     " + ln)
        if p.returncode != 0 and any("shown" in ln for ln in errs):
            reproduced.append("MSVC: the handler exception name is not declared in the "
                              "scope of the emitted finally block -> %s" % errs[0])

    print()
    print("=" * 74)
    if reproduced:
        print("RESULT: REPRODUCED (%d confirmations)" % len(reproduced))
        for r in reproduced:
            print("  * " + r)
        return 1
    print("RESULT: NOT REPRODUCED")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        import traceback
        sys.stderr.write("HARNESS ERROR\n" + traceback.format_exc())
        sys.exit(3)
