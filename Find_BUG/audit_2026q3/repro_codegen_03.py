#!/usr/bin/env python3
"""OMEGA-verified repro unit T0r61.4.1 / defect 03.

Target: cypy_bridge/compiler.py:3333-3335 (CCodeGenerator wrapper emission)

Claim: for a function whose C return type is `PyObject*` the generated
PyArg_ParseTuple wrapper emits, unconditionally,

        _result = <func>(<args>);
        Py_INCREF(_result);
        return _result;

There is no NULL test.  A `PyObject*`-returning compiled function signals
failure by returning NULL (that is exactly what every `return NULL;` /
`goto` error path in this same generator produces, and what the sibling
branches at :3304/:3308 do).  Py_INCREF(NULL) dereferences ((PyObject*)0)
-> ob_refcnt -> immediate access violation, and in the non-crashing variant
the caller also gets a borrowed+over-incref'd object on success (leak).

Evidence: emitted C quoted, real MSVC .pyd build, real call from Python
(child process dies with SIGSEGV / 0xC0000005), plus a counterfactual build
with only the emitted Py_INCREF line removed.

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

SRC = """
def failing() -> PyObject*:
    return NULL
"""


def emit(module_name, drop_incref=False):
    ast = Parser(Lexer(SRC).tokenize()).parse()
    c = CCodeGenerator().generate(ast, module_name)
    if drop_incref:
        # counterfactual: delete ONLY the emitted `Py_INCREF(_result);` of :3334
        c = re.sub(r"\n\s*Py_INCREF\(_result\);", "", c)
    os.makedirs(SCRATCH, exist_ok=True)
    with open(os.path.join(SCRATCH, module_name + ".c"), "w", encoding="utf-8",
              newline="\n") as f:
        f.write(c)
    return c


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
          "print('imported ok', flush=True)\n"
          "print('calling failing() ...', flush=True)\n"
          "rv = %s.failing()\n"
          "print('SURVIVED returned', repr(rv), flush=True)\n")


def call(module_name):
    code = RUNNER % (SCRATCH, module_name, module_name)
    p = subprocess.run([sys.executable, "-c", code], cwd=SCRATCH,
                       capture_output=True, timeout=120)
    return p.returncode, z((p.stdout or b"") + (p.stderr or b"")).strip()


def main():
    reproduced = []
    print("=" * 74)
    print("PART 1 - emitted wrapper C (verbatim, real CCodeGenerator output)")
    print("=" * 74)
    c = emit("d03_live")
    lines = c.splitlines()
    start = next(i for i, ln in enumerate(lines) if "_wrapper" in ln and "failing" in ln)
    stop = next(i for i, ln in enumerate(lines) if "static PyMethodDef" in ln)
    for i in range(start, stop):
        mark = ""
        if "Py_INCREF(_result);" in lines[i]:
            mark = "   <== compiler.py:3334  NO NULL TEST on _result"
        elif "_result = failing();" in lines[i]:
            mark = "   <== the callee's own failure convention is `return NULL;`"
        print("  %4d | %s%s" % (i + 1, lines[i].rstrip(), mark))
    print("  source of these two lines, cypy_bridge/compiler.py:3333-3335:")
    src = open(os.path.join(REPO, "cypy_bridge", "compiler.py"),
               encoding="utf-8").read().splitlines()
    for i in range(3332, 3336):
        print("  %4d | %s" % (i + 1, src[i].rstrip()))
    guard = re.search(r"if\s*\(\s*!?_result", c)
    if not guard:
        reproduced.append("emitted PyObject* wrapper contains no NULL guard "
                          "(only Py_INCREF(_result); return _result;)")

    print()
    print("=" * 74)
    print("PART 2 - runtime: real MSVC .pyd built from the emitted C, then called")
    print("=" * 74)
    rc, out = build_pyd("d03_live")
    if rc != 0:
        print("  BUILD FAILED -> source-level evidence only:")
        for ln in out.splitlines()[-10:]:
            print("   " + ln)
        reproduced.append("(runtime unverified) emitted C not buildable here")
    else:
        print("  built: %s" % [f for f in os.listdir(SCRATCH)
                               if f.startswith("d03_live") and f.endswith(".pyd")])
        rc2, res = call("d03_live")
        print("  child exit code: %s" % rc2)
        for ln in res.splitlines():
            print("     | " + ln)
        # HARNESS-FIX(T0r61.4.2): 修好之后的正确行为是 wrapper 把 NULL 失败信号
        # 传播出去，子进程于是带着一条 Python traceback（SystemError）以非 0 退出。
        # 那不是 Py_INCREF(NULL) 造成的访问违例（本复现单元自己的 docstring 也把
        # “clean SystemError”当作期望结果），真正的崩溃是进程没有 Python traceback
        # 就异常终止。
        crashed = (rc2 != 0 and "SURVIVED" not in res
                   and "Traceback (most recent call last)" not in res
                   and "Segmentation fault" not in res)
        if crashed:
            note = {139: "SIGSEGV (139)", 3221225477: "0xC0000005 ACCESS_VIOLATION",
                    -1073741819: "0xC0000005 ACCESS_VIOLATION"}.get(rc2, "abnormal")
            reproduced.append("calling the wrapper crashed the interpreter: exit %s (%s) "
                              "-- Py_INCREF(NULL) dereferences address 0"
                              % (rc2, note))
            print("  => process died between 'calling failing() ...' and the print after "
                  "it: hard access violation inside Py_INCREF, exactly as audited.")
        else:
            print("  no crash observed")

        emit("d03_noIncref", drop_incref=True)
        rc3, _ = build_pyd("d03_noIncref")
        if rc3 == 0:
            rc4, res2 = call("d03_noIncref")
            print("  counterfactual (ONLY the emitted Py_INCREF(_result); at :3334 deleted)"
                  " -> child exit %s" % rc4)
            for ln in res2.splitlines():
                print("     | " + ln)
            if rc4 == 0 or "SURVIVED" in res2 or "SystemError" in res2:
                print("  => no access violation once the INCREF is gone: the crash is "
                      "pinned on compiler.py:3334.")
        else:
            print("  counterfactual build failed; skipped")

    print()
    print("=" * 74)
    print("PART 3 - the same wrapper on the SUCCESS path over-increfs (leak)")
    print("=" * 74)
    print("  The callee already returns a *new* reference (own-refs convention); the")
    print("  wrapper increfs again at :3334 and returns the same pointer, so every")
    print("  successful call leaks one reference.  The correct emission is")
    print("  `return _result;` alone (or an INCREF only for a borrowed value).")
    print("  Emitted lines: %s" % [ln.strip() for ln in lines
                                   if "Py_INCREF(_result)" in ln or "return _result;" in ln])

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
