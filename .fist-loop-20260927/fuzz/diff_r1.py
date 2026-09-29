"""Round 1 invariant / differential checks for the Cypy compiler.

B1  idempotence      : source -> generated Cython, run twice, byte-compare
                       (a) tight repeat        (same second)
                       (b) wall-clock repeat   (sleep > 1s between the runs)
B1b generator reuse  : gen.generate(A); gen.generate(B)  vs  fresh gen per source
B1c self-reparse     : feed the generated .pyx text back through the front-end
                       (NOT a documented path - used only as a robustness probe)
B2  cross-consistency: direct pipeline  vs  CypyHook.transpile  vs
                       ProjectCompiler (project mode) for the same source
"""
from __future__ import annotations

import importlib.util
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)

spec = importlib.util.spec_from_file_location("fz", os.path.join(HERE, "fuzz_r1.py"))
fz = importlib.util.module_from_spec(spec)
_fz_log_open = None
spec.loader.exec_module(fz)

from cypyc.parser.preprocessor import Preprocessor
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.codegen.cython_generator import CythonGenerator

OUT = os.path.join(HERE, "diff_r1.out.txt")
_f = open(OUT, "w", encoding="utf-8")


def say(msg: str = "") -> None:
    _f.write(msg + "\n")
    _f.flush()
    print(msg)


def parse_only(source: str):
    src = Preprocessor().process(source)
    return Parser(list(Lexer(src).tokenize())).parse()


def gen_once(source: str) -> str:
    return CythonGenerator().generate(parse_only(source))


def gen_project_style(source: str) -> str:
    """exactly what ProjectCompiler.compile_module does (steps before the C compiler)"""
    src = source  # NOTE: project mode never runs the Preprocessor
    ast = Parser(list(Lexer(src).tokenize())).parse()
    g = CythonGenerator()
    g.generate(ast)
    return "\n".join(g.output)


def first_diff(a: str, b: str) -> str:
    la, lb = a.splitlines(), b.splitlines()
    for i in range(max(len(la), len(lb))):
        x = la[i] if i < len(la) else "<eof>"
        y = lb[i] if i < len(lb) else "<eof>"
        if x != y:
            return f"line {i+1}: {x!r} != {y!r}"
    return "<no line diff (bytes differ)"


def main() -> int:
    seeds = fz.seed_files()
    say(f"=== B1 idempotence: {len(seeds)} examples/*.cypy ===")
    tight_bad, clock_bad = [], []
    for name, text in seeds:
        try:
            a = gen_once(text)
            b = gen_once(text)
        except BaseException as e:
            say(f"ERR  {name}: {type(e).__name__}: {e}")
            continue
        if a != b:
            tight_bad.append((name, first_diff(a, b)))
        time.sleep(1.05)
        c = gen_once(text)
        if a != c:
            clock_bad.append((name, first_diff(a, c)))
    say(f"tight repeat byte-identical failures: {len(tight_bad)}")
    for n, d in tight_bad:
        say(f"  DIFF(tight) {n} :: {d}")
    say(f"wall-clock (>1s apart) byte-identical failures: {len(clock_bad)}")
    for n, d in clock_bad[:30]:
        say(f"  DIFF(clock) {n} :: {d}")

    say("")
    say("=== B1b generator reuse (one CythonGenerator for two sources) ===")
    for i in range(len(seeds) - 1):
        n1, t1 = seeds[i]
        n2, t2 = seeds[i + 1]
        try:
            g = CythonGenerator()
            g.generate(parse_only(t1))
            reused = g.generate(parse_only(t2))
        except BaseException as e:
            say(f"  reuse-run raised on {n1}->{n2}: {type(e).__name__}: {e}")
            continue
        try:
            fresh = gen_once(t2)
        except BaseException as e:
            say(f"  fresh-run raised {n2}: {type(e).__name__}: {e}")
            continue
        if reused != fresh:
            say(f"  DIFF reuse {n1}->{n2} :: {first_diff(reused, fresh)[:200]}")
    say("")

    say("=== B2 cross-consistency: direct vs CypyHook.transpile vs project-mode ===")
    from cypy_hook.hook import CypyHook
    hook = CypyHook()
    hook.set_output_dir(HERE)
    mism = 0
    for name, text in seeds:
        direct = None
        try:
            direct = gen_once(text)
        except BaseException as e:
            direct = "RAISED " + type(e).__name__ + ": " + str(e)[:120]
        hr = hook.transpile(text)
        via_hook = hr.cython_code if hr.success else "ERRORS " + " | ".join(hr.errors)[:200]
        try:
            proj = gen_project_style(text)
        except BaseException as e:
            proj = "RAISED " + type(e).__name__ + ": " + str(e)[:120]
        if not (direct == via_hook == proj):
            mism += 1
            say(f"  MISMATCH {name}")
            if direct != via_hook:
                say(f"    direct vs hook.transpile: {first_diff(direct, via_hook)[:200]}")
            if direct != proj:
                say(f"    direct vs project-mode : {first_diff(direct, proj)[:200]}")
    say(f"  mismatches: {mism}/{len(seeds)}")

    say("")
    say("=== B1c reparse generated .pyx through the same front-end (robustness probe) ===")
    cls_count = {}
    for name, text in seeds:
        try:
            out = gen_once(text)
        except BaseException:
            continue
        try:
            Parser(list(Lexer(Preprocessor().process(out)).tokenize())).parse()
            k = "parsed"
        except BaseException as e:
            k = type(e).__name__
            if k in ("ValueError",):
                k = "ValueError(lex/parse diagnostic)"
            elif k not in ("ValueError",):
                say(f"  CRASH-CLASS {name}: {k}: {str(e)[:140]}")
                say("     " + ("".join(traceback.format_tb(e.__traceback__)).strip().splitlines()[-3:] or [""])[-1][:160])
        cls_count[k] = cls_count.get(k, 0) + 1
    say(f"  outcomes: {cls_count}")

    say("")
    say("=== B2b real ProjectCompiler check vs single-file diagnostics ===")
    import shutil
    import tempfile
    from cypyc.project.project_compiler import ProjectCompiler
    tmp = tempfile.mkdtemp(prefix="cypy_proj_", dir=HERE)
    proj_mismatch = 0
    for name, text in seeds:
        d = os.path.join(tmp, name[:-5])
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "main.cypy"), "w", encoding="utf-8") as f:
            f.write(text)
        pc = ProjectCompiler(project_root=d, output_dir=os.path.join(d, "out"), verbose=False)
        pc.discover_modules()
        pc.parse_all_modules()
        pc.build_dependency_graph()
        pc.collect_type_exports()
        perr = []
        try:
            ok, errs = pc.type_check_module("main")
            perr = [f"{'ok' if ok else 'fail'}: " + str(x) for x in (errs or [])[:4]]
        except BaseException as e:
            perr = ["RAISED " + type(e).__name__ + ": " + str(e)[:100]]
        serr = []
        try:
            fz.run_pipeline(text)
        except BaseException as e:
            serr = [f"{type(e).__name__}: {str(e)[:100]}"]
        pe = [x for x in perr if "ok: " not in x]
        if bool(pe) != bool(serr):
            proj_mismatch += 1
            say(f"  DIAG-MISMATCH {name}: project={perr[:2]} single={serr[:2]}")
    say(f"  diagnostic-set mismatches: {proj_mismatch}/{len(seeds)}  (temp projects kept in {os.path.relpath(tmp, HERE)})")

    say("")
    say("=== B-extra: preprocessor directives honoured by single-file mode only ===")
    for label, fn in (("single-file", gen_once), ("project-mode", gen_project_style)):
        for tag, probe in (("#define", "#define LIMIT 10\nlet x: int = LIMIT\nprint(x)\n"),
                           ("#line", "#line 100\ndef g() -> int:\n    return 1\n")):
            try:
                r = fn(probe)
                keep = [ln for ln in r.splitlines() if "LIMIT" in ln or " x" in ln or ln.startswith("let") or "x =" in ln]
                say(f"  {tag:<8} {label:<13} OK   generated lines mentioning x: {keep[:3]}")
            except BaseException as e:
                say(f"  {tag:<8} {label:<13} FAIL {type(e).__name__}: {str(e)[:120]}")
    try:
        a = gen_once("#define LIMIT 10\nlet x: int = LIMIT\nprint(x)\n")
        b = gen_project_style("#define LIMIT 10\nlet x: int = LIMIT\nprint(x)\n")
        say(f"  both succeeded, texts equal: {a == b}  diff: {first_diff(a, b)[:220]}")
    except BaseException as e:
        say(f"  comparison aborted: {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
