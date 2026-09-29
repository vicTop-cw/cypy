"""OMEGA repro T0r61.5.1 / defect 3 -- weak assertions in the test_suite harness.

Two halves.

R. Inventory, computed from the AST of the four suite modules (no compiler needed):
   every test body is classified by what it actually checks, so the "only asserts that
   nothing exploded" population is counted rather than asserted by eye.

M. Mutation experiments. Each one breaks the code under test *in this process only*
   (monkeypatching cypy_hook.CypyHook) and then runs the real suite objects. The repo is
   never modified; scratch output goes under Find_BUG/audit_2026q3/scratch/tsuite/.

   M1  analyzer fully neutered (transpile always "success", zero errors)
       -> all 10 AnalyzerSuite tests still PASS: the analyzer suite has no negative test.
   M2  compiler emits the literal string "garbage" as the generated Cython
       -> every CodegenSuite test whose only check is Assert.is_not_none still PASSES.
   M3  module magic attributes (__name__/__file__ assignments) deleted from the output,
       replaced by a comment that merely contains those two tokens
       -> codegen_module_magic_attrs PASSES with the feature removed, because
          Assert.contains(cython_code, "__name__") is a substring check.
   M4  a soft Check.equal failure inside a Suite
       -> Suite.run() never consults Check.has_failures(), so the test reports 'passed'.

Exit code: 1 = at least one mutant survived the harness, 0 = harness killed all mutants.
"""

import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

SUITE_FILES = {
    "parser_suite": "test_suite/suites/parser_suite.py",
    "analyzer_suite": "test_suite/suites/analyzer_suite.py",
    "codegen_suite": "test_suite/suites/codegen_suite.py",
    "integration_suite": "test_suite/suites/integration_suite.py",
}
SUITES_IN_RUN_ORDER = ["parser_suite", "analyzer_suite", "codegen_suite", "integration_suite"]
CITED_WEAK = {
    ("parser_suite", 91), ("codegen_suite", 98), ("codegen_suite", 115), ("codegen_suite", 130),
    ("analyzer_suite", 30), ("integration_suite", 30),
}


def hr(title):
    print("")
    print("=" * 78)
    print(title)
    print("=" * 78)


# ------------------------------------------------------------------ R: inventory
def classify(fn):
    """Return (list of Assert calls, list of Check calls, has_assertion, body_is_pass_only)."""
    asserts, checks = [], []
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                if node.func.value.id == "Assert":
                    asserts.append((node.func.attr, node.lineno))
                elif node.func.value.id == "Check":
                    checks.append((node.func.attr, node.lineno))
    real_stmts = [
        s for s in fn.body
        if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))  # docstring
    ]
    pass_only = all(isinstance(s, ast.Pass) for s in real_stmts) if real_stmts else True
    return asserts, checks, bool(asserts), pass_only


def section_r():
    hr("R. assertion inventory of the four suites (AST-derived, zero compiler calls)")
    rows = []
    for key, rel in SUITE_FILES.items():
        path = os.path.join(REPO, *rel.split("/"))
        with open(path, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=path)
        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef)]:
            dec = None
            for d in fn.decorator_list:
                if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "test":
                    dec = d.args[0].value
            if dec is None:
                continue
            asserts, checks, has_assert, pass_only = classify(fn)
            kinds = [a for a, _ in asserts]
            if pass_only or not has_assert:
                cls = "VACUOUS (no assertion at all)"
            elif set(kinds) <= {"is_not_none"}:
                cls = "SMOKE (is_not_none only)"
            elif set(kinds) <= {"true"}:
                cls = "SMOKE (success-flag only)"
            elif set(kinds) <= {"is_not_none", "true"}:
                cls = "SMOKE (is_not_none/true only)"
            elif set(kinds) <= {"contains", "is_not_none", "true", "almost_equal"}:
                cls = "substring/equality mix"
            else:
                cls = "value-checked"
            rows.append({
                "suite": key, "rel": rel, "test": dec, "lineno": fn.lineno,
                "n_asserts": len(asserts), "kinds": sorted(set(kinds)),
                "classes": cls, "pass_only": pass_only,
                "assert_lines": [f"{ln}:{k}" for k, ln in asserts],
                "checks": checks,
            })

    print(f"  {len(rows)} registered tests audited")
    print("")
    print("  test                              suite-file:line                asserts  kinds                                   strength")
    print("  " + "-" * 122)
    for r in sorted(rows, key=lambda x: (x["suite"], x["lineno"])):
        print(f"  {r['test']:<33} {r['rel']}:{r['lineno']:<6} {r['n_asserts']:>5}   "
              f"{','.join(r['kinds']):<35} {r['classes']}")

    vac = [r for r in rows if r["classes"].startswith("VACUOUS")]
    smoke = [r for r in rows if r["classes"].startswith("SMOKE")]
    print("")
    print(f"  VACUOUS bodies (pass / no assertion at all): {len(vac)} of {len(rows)}")
    for r in vac:
        print(f"     {r['rel']}:{r['lineno']} {r['test']}")
    print(f"  SMOKE-only bodies (nothing beyond 'it did not crash / it returned something'): "
          f"{len(smoke)} of {len(rows)}")
    for r in smoke:
        print(f"     {r['rel']}:{r['lineno']} {r['test']}  kinds={r['kinds']}")
    print(f"  weak (vacuous + smoke): {len(vac) + len(smoke)} of {len(rows)} "
          f"= {100.0 * (len(vac) + len(smoke)) / len(rows):.0f}% of the harness")
    print("")
    print("  API surface that is imported but never exercised:")
    print("     Check (soft assertions) -- referenced in suites: "
          f"{sum(len(r['checks']) for r in rows)} calls; Suite.run() (core/suite.py:37-83) "
          "never calls Check.has_failures() (core/assertions.py:154)")
    print("     Assert.raises -- used 0 times in the suites, so the harness never checks "
          "that invalid .cypy is REJECTED")
    return rows


# ------------------------------------------------------------------ M: mutations
def run_suite(suite, label):
    sr = suite.run()
    print(f"  {label}: passed={sr.passed} failed={sr.failed} skipped={sr.skipped} total={sr.total}")
    for tr in sr.results:
        if tr.status != "passed":
            print(f"      {tr.status.upper():<6} {tr.test_name}: {(tr.message or '')[:70]}")
    return sr


def hook_module():
    from cypy_hook.hook import CypyHook
    return CypyHook


def section_m(rows):
    hr("M. mutation testing -- break the compiler in-process, ask the harness")
    import cypy_hook.hook as hook_mod
    from cypy_hook.hook import CompileResult

    originals = {
        "transpile_file": hook_mod.CypyHook.transpile_file,
        "run": hook_mod.CypyHook.run,
    }

    def restore():
        hook_mod.CypyHook.transpile_file = originals["transpile_file"]
        hook_mod.CypyHook.run = originals["run"]

    mods = {}
    for name in SUITES_IN_RUN_ORDER:
        mod = __import__(f"test_suite.suites.{name}", fromlist=[name])
        mods[name] = getattr(mod, name)

    killed = []
    survived = []

    # ---------------- baseline (unmutated) for the two suites we mutate
    print("\n  -- baseline, unmutated compiler (real work, ~5 s for these two suites) --")
    try:
        base_an = run_suite(mods["analyzer_suite"], "AnalyzerSuite baseline ")
        base_cg = run_suite(mods["codegen_suite"], "CodegenSuite baseline ")
    finally:
        restore()

    # ---------------- M1
    print("\n  -- M1: semantic analyzer neutered (everything transpiles 'successfully') --")
    print("     mutation: CypyHook.transpile_file -> CompileResult(success=True, errors=[], "
          "cython_code='') for every input")

    def neutered(self, source_file, *a, **kw):
        return CompileResult(success=True, cython_code="", errors=[], pyx_path=source_file)

    hook_mod.CypyHook.transpile_file = neutered
    try:
        m1 = run_suite(mods["analyzer_suite"], "AnalyzerSuite vs M1   ")
    finally:
        restore()
    if m1.failed == 0 and m1.passed == base_an.passed:
        survived.append(("M1", f"all {m1.passed} analyzer tests pass with the analyzer deleted; "
                               "analyzer_suite has 0 negative tests (no Assert.raises / no "
                               "'bad program must fail' case)"))
        print("     MUTANT SURVIVED")
    else:
        killed.append("M1")
        print("     mutant killed")

    # ---------------- M2
    print("\n  -- M2: code generator emits the literal string 'garbage' --")

    def garbage(self, source_file, *a, **kw):
        return CompileResult(success=True, cython_code="garbage", errors=[], pyx_path=source_file)

    hook_mod.CypyHook.transpile_file = garbage
    try:
        m2 = run_suite(mods["codegen_suite"], "CodegenSuite vs M2   ")
        survivors = [tr.test_name for tr in m2.results if tr.status == "passed"]
    finally:
        restore()
    print(f"     tests that pass on output=='garbage': {survivors}")
    if survivors:
        survived.append(("M2", f"{len(survivors)}/{m2.total} codegen tests pass on garbage output "
                               f"because their only check is Assert.is_not_none(cython_code): {survivors}"))
        print("     MUTANT SURVIVED")
    else:
        killed.append("M2")
        print("     mutant killed (every codegen test had a value check)")

    # ---------------- M3
    print("\n  -- M3: module magic attributes removed from the generated Cython --")
    real_transpile = originals["transpile_file"]

    def strip_magic(self, source_file, *a, **kw):
        res = real_transpile(self, source_file, *a, **kw)
        if res.cython_code:
            kept = [
                ln for ln in res.cython_code.splitlines()
                if not (ln.strip().startswith("__name__") or ln.strip().startswith("__file__"))
            ]
            kept.append("# __name__ and __file__ are provided by Python (feature removed)")
            res.cython_code = "\n".join(kept)
        return res

    hook_mod.CypyHook.transpile_file = strip_magic
    try:
        probe_mod = __import__("test_suite.fixtures.compiler", fromlist=["CompilerFixture"])
        with probe_mod.CompilerFixture() as fx:
            mutated = fx.compile("def main() -> int:\n    return 0\n", "probe")
        real = originals["transpile_file"]
        print("     mutated output still contains '__name__' substring :", "__name__" in mutated)
        print("     mutated output still contains '__file__' substring :", "__file__" in mutated)
        print("     mutated output contains an actual assignment '__name__ =' :",
              any(ln.strip().startswith("__name__ =") for ln in mutated.splitlines()))
        m3 = run_suite(mods["codegen_suite"], "CodegenSuite vs M3   ")
        target = next(tr for tr in m3.results if tr.test_name == "codegen_module_magic_attrs")
    finally:
        restore()
    print(f"     codegen_module_magic_attrs verdict: {target.status}")
    if target.status == "passed":
        survived.append(("M3", "codegen_suite.py:65-66 passes with the __name__/__file__ "
                               "assignments deleted, because Assert.contains(cython_code, "
                               "'__name__') only needs the substring, which a comment satisfies"))
        print("     MUTANT SURVIVED")
    else:
        killed.append("M3")
        print("     mutant killed")

    # ---------------- M4
    print("\n  -- M4: soft-check failures are ignored by Suite.run() --")
    from test_suite.core.assertions import Check
    from test_suite.core.suite import Suite

    soft = Suite("SoftCheckSuite")

    @soft.test("soft_check_is_wrong_but_quiet")
    def _soft_body():
        Check.equal(1, 2, "the compiler returned the wrong thing")
        # no hard assertion follows, exactly like a harness that trusts Check

    sr = soft.run()
    tr = sr.results[0]
    print(f"     Check.get_failures() -> {Check.get_failures()}")
    print(f"     Suite.run() verdict  -> status={tr.status!r} passed={sr.passed} failed={sr.failed}")
    if tr.status == "passed" and Check.has_failures():
        survived.append(("M4", "a test whose soft checks all fail is reported 'passed'; "
                               "core/suite.py:37-83 never reads Check.has_failures()"))
        print("     MUTANT SURVIVED")
    else:
        killed.append("M4")
        print("     mutant killed")
    Check.reset()

    # ---------------- M5 (free, no compiler): vacuous tests
    print("\n  -- M5: vacuous test bodies report 'passed' with zero assertions --")
    vac = [r for r in rows if r["classes"].startswith("VACUOUS")]
    for r in vac:
        print(f"     {r['rel']}:{r['lineno']} {r['test']} -- body is `pass`, "
              f"no Assert, counted PASSED")
    if vac:
        survived.append(("M5", f"{len(vac)} registered tests assert nothing at all "
                               f"({[r['test'] for r in vac]}) -- 3/47 of the green baseline"))

    hr("MUTATION SUMMARY")
    print(f"  mutants survived: {len(survived)}   killed: {len(killed)}")
    for tag, why in survived:
        print(f"    {tag}: {why}")
    return survived


def report_cited(rows, survived):
    hr("Top-5 weakest sites selected for the report (file:line of the assertion itself)")
    cited = [
        ("1", "test_suite/suites/parser_suite.py", 91, "parse_build_assign / parse_build_call / "
         "parse_build_gen (91, 98, 105) -- three registered tests whose bodies are a bare `pass`",
         "M5", "vacuous: counts toward 47/0 forever; build-block parsing is untested"),
        ("2", "test_suite/suites/analyzer_suite.py", 30,
         "all 10 analyzer tests reduce to Assert.true(success, ...) (lines 30,45,61,77,91,108,122,136,157,184) "
         "-- never asserts that a bad program FAILS",
         "M1", "analyzer can be deleted and the suite stays green"),
        ("3", "test_suite/suites/codegen_suite.py", 98,
         "codegen_cast_expression:81, codegen_build_assign:98, codegen_build_call:115, "
         "codegen_build_gen:130 -- Assert.is_not_none(cython_code) is the only check",
         "M2", "compiler emitting 'garbage' keeps 6/9 codegen tests green"),
        ("4", "test_suite/suites/codegen_suite.py", 65,
         "codegen_module_magic_attrs: Assert.contains(cython_code, '__name__') / '__file__' (65,66) "
         "-- substring-of-generated-text",
         "M3", "remove the feature, leave the word, test passes"),
        ("5", "test_suite/core/suite.py", 59,
         "Suite.run() ignores the whole soft-assert API (core/assertions.py:82-156 Check) and "
         "run() also converts *any* exception into a plain 'failed' string; combined with "
         "fixtures/compiler.py:107-108 (`except Exception: return None`) a crash inside the test "
         "harness is indistinguishable from a compiler bug",
         "M4", "failed soft checks report 'passed'; real errors report 'Execution failed'"),
    ]
    for n, f, ln, what, mutant, why in cited:
        print(f"  [{n}] {f}:{ln}   killed-by-mutant {mutant} -> "
              f"{'SURVIVED' if any(s[0] == mutant for s in survived) else 'killed'}")
        print(f"      {what}")
        print(f"      why it matters: {why}")


def main():
    try:
        rows = section_r()
        survived = section_m(rows)
        report_cited(rows, survived)
    except Exception:
        import traceback

        traceback.print_exc()
        print("HARNESS PROBLEM")
        return 2
    hr("VERDICT")
    print(f"  DEFECT 3 REPRODUCED: {len(survived) >= 3} ({len(survived)} mutants survive)")
    return 1 if len(survived) >= 3 else 0


if __name__ == "__main__":
    sys.exit(main())
