"""OMEGA repro T0r61.5.1 / gap analysis for defects 1+2 -- what a fix must not break.

Runs three candidate repairs against *scratch copies* of test_suite/ (the repo copy is
never touched; only Find_BUG/audit_2026q3/scratch/fixed_*/ is written), then reports the
observable deltas a permanent guard test would have to absorb:

  A  index-pinned sites:  `t = <suite>.tests[-1]` -> `t = <suite>.tests[K]`
     (K = registration index of the test the block actually describes)
  B  core-side binding:   Suite.run() publishes the running Test as <suite>.current_test
                          (test_suite/core/suite.py:59) and the nine sites use it
  C  B + defect-2 repair: the bool flag is renamed to `skipped`, freeing `skip()` as a
                          callable method, and the three vacuous parser_suite bodies
                          (parser_suite.py:91/98/105) are declared skipped at import time

Integration suite is deliberately excluded from these three runs: it spends 178 s of the
real 178 s total on Cython builds (scripts/run_tests.py measured 47/0/0 in 178.38 s).
The mechanism is suite-agnostic and is already proven end-to-end in
repro_testsuite_01.py sections B/C against the real integration_suite objects.

Exit code: 0 = all variants behaved as predicted, 1 = a prediction failed, 2 = harness problem.
"""

import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SCRATCH = os.path.join(HERE, "scratch")
SUITE_FILES = ["parser_suite.py", "analyzer_suite.py", "codegen_suite.py", "integration_suite.py"]
FAST_SUITES = ["parser", "analyzer", "codegen"]
FAST_SUITE_MODULES = [s + "_suite" for s in FAST_SUITES]
SUITES_IN_RUN_ORDER = ["parser_suite", "analyzer_suite", "codegen_suite", "integration_suite"]

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

RUNNER = '''"""written by repro_testsuite_04.py -- scratch copy driver, not part of the repo."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)                      # test_suite/ here is the scratch copy
sys.path.insert(1, {repo!r})                  # cypyc / cypy_hook come from the real repo

from test_suite.core.runner import TestRunner
from test_suite.utils.demo_writer import DemoWriter
import test_suite
assert os.path.normcase(test_suite.__file__).startswith(os.path.normcase(ROOT)), (
    "runner imported the repo copy instead of the scratch copy: " + test_suite.__file__)
print("SUITE_PACKAGE " + test_suite.__file__)

suites = []
for name in {suites!r}:
    mod = __import__("test_suite.suites." + name, fromlist=[name])
    suites.append(getattr(mod, name))

runner = TestRunner()
runner.add_suites(suites)
res = runner.run_all()

out = os.path.join(ROOT, "demos")
synced = DemoWriter(out).sync_from_tests(res.get_demo_results())
files = sorted(
    cat + "/" + os.path.basename(p) for cat, ps in synced.items() for p in ps
)
per_test = []
for sr in res.results:
    for tr in sr.results:
        per_test.append([sr.suite_name, tr.test_name, tr.status, tr.demo_name])
print("RESULT " + json.dumps({{
    "passed": res.passed, "failed": res.failed, "skipped": res.skipped,
    "demos": files, "per_test": per_test,
}}, ensure_ascii=False))
'''

VACUOUS = ["parse_build_assign", "parse_build_call", "parse_build_gen"]


def hr(title):
    print("")
    print("=" * 78)
    print(title)
    print("=" * 78)


def copy_test_suite(dst):
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    src = os.path.join(REPO, "test_suite")
    shutil.copytree(src, os.path.join(dst, "test_suite"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return os.path.join(dst, "test_suite")


def read(p):
    with open(p, "r", encoding="utf-8") as fh:
        return fh.read()


def write(p, text):
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)


def registration_index(suite_copy_path, suite_var, enclosing):
    """K such that suite.tests[K].name == enclosing (import-time registration order)."""
    with open(suite_copy_path, "r", encoding="utf-8") as fh:
        tree_order = re.findall(r"@%s\.test\(\"([^\"]+)\"\)" % suite_var, fh.read())
    return tree_order.index(enclosing), tree_order


SITE_RE = re.compile(r"^(\s+)(\w+) = (\w+_suite)\.tests\[-1\]$", re.M)


def patch_sites_index(tree):
    """Variant A: pin each site to the index of the test whose body it sits in."""
    changed = []
    for fn in SUITE_FILES:
        p = os.path.join(tree, "suites", fn)
        text = read(p)
        suite_var = fn[:-3]
        lines = text.splitlines(keepends=True)
        out = []
        for i, line in enumerate(lines):
            m = SITE_RE.match(line.rstrip("\n"))
            if not m:
                out.append(line)
                continue
            indent, var, sname = m.groups()
            # the enclosing decorated test = nearest preceding @<suite>.test("...")
            enc = None
            for back in range(i, -1, -1):
                d = re.search(r"@%s\.test\(\"([^\"]+)\"\)" % sname, lines[back] or "")
                if d:
                    enc = d.group(1)
                    break
            k, _ = registration_index(p, sname, enc)
            out.append(f"{indent}{var} = {sname}.tests[{k}]  # {enc} (fixed by repro_testsuite_04)\n")
            changed.append((f"suites/{fn}:{i + 1}", enc, k))
        write(p, "".join(out))
    return changed


def patch_core_current_binding(tree):
    """Variant B: publish the running Test on the suite, then use it at every site."""
    p = os.path.join(tree, "core", "suite.py")
    text = read(p)
    text = text.replace(
        "        # 执行所有测试\n        for test in self.tests:",
        "        # 执行所有测试\n"
        "        for test in self.tests:\n"
        "            self.current_test = test  # FIX B: the body can now name itself\n",
    )
    text = text.replace(
        "        self.teardown_fn: Optional[Callable] = None",
        "        self.teardown_fn: Optional[Callable] = None\n"
        "        self.current_test: Optional[Test] = None\n",
    )
    write(p, text)
    changed = []
    for fn in SUITE_FILES:
        sp = os.path.join(tree, "suites", fn)
        text = read(sp)
        lines = text.splitlines(keepends=True)
        out = []
        for i, line in enumerate(lines):
            m = SITE_RE.match(line.rstrip("\n"))
            if m:
                indent, var, sname = m.groups()
                out.append(f"{indent}{var} = {sname}.current_test  # FIX B\n")
                changed.append(f"suites/{fn}:{i + 1}")
            else:
                out.append(line)
        write(sp, "".join(out))
    return changed


def patch_skip_rename(tree):
    """Variant C, part 1: rename the shadowing bool flag so skip() is callable again."""
    p = os.path.join(tree, "core", "test.py")
    text = read(p)
    text = text.replace("        self.skip = False\n", "        self.skipped_flag = False\n")
    text = text.replace("            self.skip = True\n", "            self.skipped_flag = True\n")
    text = text.replace("        self.skip = True\n", "        self.skipped_flag = True\n")
    text = text.replace("        if self.skip:\n", "        if self.skipped_flag:\n")
    text = text.replace("return f\"Test(name='{self.name}', skip={self.skip})\"",
                        "return f\"Test(name='{self.name}', skip={self.skipped_flag})\"")
    write(p, text)
    assert "self.skip = False" not in text, "rename incomplete"
    return ["core/test.py:13,22,28,41,77 (self.skip -> self.skipped_flag)"]


def patch_declared_skips(tree):
    """Variant C, part 2: the three vacuous parser tests become real skips, at import time.

    Note that `tests[-1]` IS the right handle at module/import level -- the idiom only
    breaks inside a test body. We look up by name anyway so the patch reads clearly.
    """
    p = os.path.join(tree, "suites", "parser_suite.py")
    text = read(p)
    tail = "\n\n# FIX C: declarative skip via the now-callable Test.skip() (import time)\n"
    for name in VACUOUS:
        tail += (
            f"parser_suite.tests[[t.name for t in parser_suite.tests].index(\"{name}\")]"
            f".skip(\"build-block syntax not supported yet\")\n"
        )
    write(p, text + tail)
    return [f"suites/parser_suite.py (import-time skip of {VACUOUS})"]


def run_variant(tree, label):
    # the runner must live OUTSIDE the copied package so that ROOT == fixed_<label>/
    runner_path = os.path.normpath(os.path.join(tree, "..", "_runner.py"))
    write(runner_path, RUNNER.format(repo=REPO, suites=FAST_SUITE_MODULES))
    proc = subprocess.run(
        [sys.executable, runner_path], cwd=REPO, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=600,
    )
    payload = None
    for line in (proc.stdout or "").splitlines():
        if line.startswith("RESULT "):
            payload = json.loads(line[len("RESULT "):])
        if line.startswith("SUITE_PACKAGE "):
            print("  (imported " + line[len("SUITE_PACKAGE "):].strip() + ")")
    if payload is None:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise RuntimeError(f"variant {label} produced no RESULT line (rc={proc.returncode})")
    os.remove(runner_path)
    return payload


def main():
    predictions = []

    hr("0. control: unmodified scratch copy of the three fast suites")
    tree = copy_test_suite(os.path.join(SCRATCH, "fixed_0_control"))
    res0 = run_variant(tree, "0")
    print(f"  suites {FAST_SUITES}: passed={res0['passed']} failed={res0['failed']} "
          f"skipped={res0['skipped']}")
    print(f"  demos synced ({len(res0['demos'])}): {res0['demos']}")
    # FIX T0r61.5.2: pre-fix the unpatched control copy exhibited the 1-demo-per-suite
    # mis-attribution signature (only the last-registered demo survived). Post-fix the
    # repo's own test_suite publishes current_test, so the control now syncs BOTH demos
    # of every fast suite with correct 1:1 test<->demo pairing. The control expectation
    # flipped accordingly -- this is the counter-proof that the defect is gone.
    predictions.append(("the scratch copy carries the T0r61.5.2 fix "
                        "(2 demos per fast suite, correct pairing)",
                        res0["demos"] == ["analyzer/scope_usage.cypy",
                                          "analyzer/type_safety.cypy",
                                          "codegen/codegen_basic.cypy",
                                          "codegen/codegen_struct.cypy",
                                          "parser/basic_syntax.cypy",
                                          "parser/type_conversion.cypy"]
                        and res0["passed"] == 37 and res0["failed"] == 0
                        and sorted(t[1] for t in res0["per_test"] if t[3])
                        == ["demo_basic_syntax", "demo_codegen_basic",
                            "demo_codegen_struct", "demo_scope_usage",
                            "demo_type_conversion", "demo_type_safety"]))

    hr("A. index-pinned sites")
    tree = copy_test_suite(os.path.join(SCRATCH, "fixed_A"))
    changed = patch_sites_index(tree)
    for site, enc, k in changed:
        print(f"  {site} -> tests[{k}]   (describes {enc})")
    resA = run_variant(tree, "A")
    print(f"  suites {FAST_SUITES}: passed={resA['passed']} failed={resA['failed']} "
          f"skipped={resA['skipped']}")
    print(f"  demos synced ({len(resA['demos'])}): {resA['demos']}")
    predictions.append(("A yields 2 demos per fast suite (6 total, up from 3)",
                        len(resA["demos"]) == 6 and resA["failed"] == 0))
    creditedA = {(t[1], t[3]) for t in resA["per_test"] if t[3]}
    print(f"  (test_name, demo_name) pairs: {sorted(creditedA)}")
    expected_pairs = {
        ("demo_basic_syntax", "basic_syntax"),
        ("demo_type_conversion", "type_conversion"),
        ("demo_type_safety", "type_safety"),
        ("demo_scope_usage", "scope_usage"),
        ("demo_codegen_basic", "codegen_basic"),
        ("demo_codegen_struct", "codegen_struct"),
    }
    predictions.append(("A credits each demo to the test whose body attached it",
                        creditedA == expected_pairs))

    hr("A2. are the 5 currently-unsynced demo sources valid .cypy at all?")
    print("     (they have never been published, so nobody ever checked; a fix would")
    print("      publish them into examples/demos/legacy, which tests/test_demos.py rglobs)")
    from cypyc.analyzer.type_checker import TypeChecker
    from cypyc.codegen.cython_generator import CythonGenerator
    from cypyc.parser.lexer import Lexer
    from cypyc.parser.parser import Parser

    demo_out = os.path.normpath(os.path.join(SCRATCH, "fixed_A", "demos"))
    bad = []
    for cat in sorted(os.listdir(demo_out)):
        cdir = os.path.join(demo_out, cat)
        if not os.path.isdir(cdir):
            continue
        for f in sorted(os.listdir(cdir)):
            if not f.endswith(".cypy"):
                continue
            p = os.path.join(cdir, f)
            code = read(p)
            stage = "parse"
            try:
                mod = Parser(Lexer(code).tokenize()).parse()
                stage = "typecheck"
                tc = TypeChecker()
                tc.check(mod)
                errs = list(getattr(tc, "errors", []) or [])
                stage = "codegen"
                gen = CythonGenerator()
                out = gen.generate(mod)
                ok = (not errs) and bool(out)
                print(f"  {cat}/{f}: parse+typecheck+codegen ok={ok} "
                      + (f"errors={errs[:2]}" if errs else ""))
                if not ok:
                    bad.append(f"{cat}/{f}")
            except Exception as exc:
                print(f"  {cat}/{f}: EXCEPTION at {stage}: {type(exc).__name__}: {exc}")
                bad.append(f"{cat}/{f}@{stage}")
    predictions.append(("every demo the fix would publish still compiles", not bad))
    if bad:
        print("  would-be-broken additions:", bad)

    hr("B. core-side current_test binding (preferred fix)")
    tree = copy_test_suite(os.path.join(SCRATCH, "fixed_B"))
    for c in patch_core_current_binding(tree):
        print("  patched", c)
    resB = run_variant(tree, "B")
    print(f"  suites {FAST_SUITES}: passed={resB['passed']} failed={resB['failed']} "
          f"skipped={resB['skipped']}")
    print(f"  demos synced ({len(resB['demos'])}): {resB['demos']}")
    predictions.append(("B yields the same 6 demos as A", sorted(resB["demos"]) == sorted(resA["demos"])))

    hr("C. B + skip() unshadowed + the three vacuous parser tests declared skipped")
    tree = copy_test_suite(os.path.join(SCRATCH, "fixed_C"))
    patch_core_current_binding(tree)
    for c in patch_skip_rename(tree):
        print("  patched", c)
    for c in patch_declared_skips(tree):
        print("  patched", c)
    resC = run_variant(tree, "C")
    print(f"  suites {FAST_SUITES}: passed={resC['passed']} failed={resC['failed']} "
          f"skipped={resC['skipped']}")
    print(f"  demos synced ({len(resC['demos'])}): {resC['demos']}")
    skipped = sorted(t[1] for t in resC["per_test"] if t[2] == "skipped")
    print(f"  skipped tests: {skipped}")
    predictions.append(("C skips exactly the 3 vacuous parser tests", skipped == sorted(VACUOUS)))
    predictions.append(("C keeps every other test passing", resC["failed"] == 0))
    predictions.append(("C's green count drops 37 -> 34 for the fast suites (47 -> 44 overall)",
                        resC["passed"] == resB["passed"] - 3))

    hr("PREDICTIONS")
    ok = True
    for label, verdict in predictions:
        print(f"  [{'OK ' if verdict else 'FAIL'}] {label}")
        ok = ok and verdict
    print("")
    print("  Baseline for comparison (real repo, real scripts/run_tests.py --sync-demo):")
    print("    47 passed / 0 failed / 0 skipped in 178.38 s -> only 4 DEMO files synced of 9 sites")
    print("    scratch/demos_real = ['analyzer/scope_usage.cypy', 'codegen/codegen_struct.cypy',")
    print("                          'integration/array_operations.cypy', 'parser/type_conversion.cypy']")
    print("")
    print("  Things a fix must not break, evidenced by the above:")
    print("    1. any assertion pinning the number 47 (variant C makes it 44 + 3 skipped)")
    print("    2. any assertion pinning '0 skipped' -- the 3 vacuous bodies are the honest skips")
    print("    3. the four accidentally-correct demos (they are the only committed ones that")
    print("       sync today; parser/type_conversion.cypy etc. must survive unchanged)")
    print("    4. `self.skip` is READ by test.py:41 and by __repr__ at test.py:77, so renaming")
    print("       the flag touches 4 lines, not 1; TestResult/RunResult counts stay compatible")
    print("    5. scripts/sync_demo.py never deletes: adding the 5 missing demos is additive, but")
    print("       examples/demos/legacy keeps 9 stale files no site generates any more")
    print("       (see repro_testsuite_01.py section C 'stale/orphan')")
    print("    6. tests/test_demos.py (pytest root) rglobs examples/demos/**/*.cypy, so the 5 newly")
    print("       synced files enter the pytest surface and must themselves compile")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback

        traceback.print_exc()
        sys.exit(2)
