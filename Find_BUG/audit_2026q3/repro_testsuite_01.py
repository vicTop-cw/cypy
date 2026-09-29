"""OMEGA repro T0r61.5.1 / defect 1 -- test_suite DEMO metadata mis-attribution.

Claim
-----
Nine sites in the four suite modules attach DEMO metadata with the idiom

    test = <suite>.tests[-1]          # "the current test", per the comment
    test.with_demo(category, name, source)

but every `@<suite>.test(...)` decorator runs at *import* time
(test_suite/core/suite.py:20-25 -> `self.tests.append(Test(name, fn))`), while the
attach line runs later, inside the test body, during `Suite.run()`
(test_suite/core/suite.py:59-61).  The `tests` list is never mutated during the run,
so at every one of those nine lines `<suite>.tests[-1]` is the *last-registered* Test
of the whole suite -- not the Test whose body is executing.

Consequences (all shown by this script):
  * the metadata is written onto a Test object that is not `self`;
  * `Test.run()` snapshots `self.demo_*` into the TestResult (test.py:51-58), so the
    executing test reports "passed with no demo" and never gets synced;
  * every earlier site for the same suite is overwritten by the last one, so per suite
    only ONE demo survives -- the one whose demo test happens to be registered last,
    which is correct purely by coincidence;
  * `scripts/sync_demo.py` / `scripts/run_tests.py --sync-demo` therefore write 4
    `.cypy` files where 9 are intended.

Sections
  A  mechanism proof, real Suite/Test classes, scratch harness, zero compiler calls
  B  the nine real sites: AST-extracted, resolved against the real imported suites
  C  replay the run in registration order with the real TestResult/DemoWriter, and
     compare what sync writes vs what is on disk in examples/demos/legacy

Exit code: 1 = bug reproduced, 0 = not reproduced, 2 = harness problem.
Reads the repo, writes only under Find_BUG/audit_2026q3/scratch/tsuite/.
"""

import ast
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

SCRATCH = os.path.join(HERE, "scratch", "tsuite")
OUT_DIR = os.path.join(SCRATCH, "demos_replay")

if sys.platform == "win32":  # match scripts/run_tests.py:17-22 so CJK demo sources print
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from test_suite.core.runner import RunResult, SuiteResult  # noqa: E402
from test_suite.core.suite import Suite  # noqa: E402
from test_suite.core.test import Test, TestResult  # noqa: E402
from test_suite.utils.demo_writer import DemoWriter  # noqa: E402

SUITES = ["parser_suite", "analyzer_suite", "codegen_suite", "integration_suite"]
# order used by scripts/run_tests.py:87 and scripts/sync_demo.py:101
RUN_ORDER = ["parser_suite", "analyzer_suite", "codegen_suite", "integration_suite"]


def hr(title):
    print("")
    print("=" * 78)
    print(title)
    print("=" * 78)


# ---------------------------------------------------------------- Section A
def section_a():
    hr("A. mechanism proof -- real Suite/Test classes, scratch harness")
    scratch = Suite("ScratchDemoSuite")
    trace = []

    # Exactly the shape used by the nine real sites.
    @scratch.test("demo_first")
    def _demo_first():
        source_first = "FIRST-DEMO-SOURCE"
        seen = scratch.tests[-1]                      # <- the "current test" idiom
        trace.append(("demo_first body ran", "tests[-1] is", seen.name, id(seen)))
        seen.with_demo("scratch", "first", source_first)

    @scratch.test("demo_second")
    def _demo_second():
        source_second = "SECOND-DEMO-SOURCE"
        seen = scratch.tests[-1]
        trace.append(("demo_second body ran", "tests[-1] is", seen.name, id(seen)))
        seen.with_demo("scratch", "second", source_second)

    print("")
    print("live Test objects at the moment Suite.run() starts:")
    for i, t in enumerate(scratch.tests):
        print(f"      tests[{i}]  {t.name!r:<14} id=0x{id(t):x}")

    result = scratch.run()

    print("")
    print("trace captured *inside* the test bodies (i.e. during Suite.run):")
    for row in trace:
        print(f"  during {row[0]:<20} tests[-1] -> Test(name={row[2]!r}) id=0x{row[3]:x}")

    print("")
    print("after Suite.run() -- what Test.run() snapshotted into each TestResult:")
    for tr in result.results:
        print(f"  {tr.test_name:<14} demo_name={tr.demo_name!r:<10} demo_source={tr.demo_source!r}")
    print("live Test objects after the run (metadata mutated onto the last registered one):")
    for t in scratch.tests:
        print(f"  {t.name:<14} demo_name={t.demo_name!r:<10} demo_source={t.demo_source!r}")

    # the first demo's metadata never reached its own result -> lost
    misattributed = []
    first = next(t for t in scratch.tests if t.name == "demo_first")
    first_result = next(t for t in result.results if t.test_name == "demo_first")
    second = next(t for t in scratch.tests if t.name == "demo_second")
    if (
        trace[0][2] != "demo_first"                 # tests[-1] was NOT the running test
        and first_result.demo_name is None          # its own result kept nothing
        and second.demo_name == "second"            # and the earlier payload was clobbered
    ):
        misattributed.append(
            f"inside demo_first's body tests[-1] resolved to {trace[0][2]!r} "
            f"(id=0x{trace[0][3]:x}), so with_demo('scratch','first',...) was written onto "
            "the wrong Test and then overwritten; demo_first's own TestResult has demo=None"
        )
    print("")
    for m in misattributed:
        print("  REPRODUCED:", m)
    return bool(misattributed)


# ---------------------------------------------------------------- Section B
def extract_sites(path, suite_var):
    """Pull (lineno, decorator_test_name, with_demo args, resolved source text) for each
    `<suite>.tests[-1]` attach site in a suite module."""
    with open(path, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)

    sites = []
    decorators_found = 0
    mutation_calls = []

    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        dec_name = None
        for dec in fn.decorator_list:
            if (
                isinstance(dec, ast.Call)
                and isinstance(dec.func, ast.Attribute)
                and dec.func.attr == "test"
                and isinstance(dec.func.value, ast.Name)
                and dec.func.value.id == suite_var
                and dec.args
                and isinstance(dec.args[0], ast.Constant)
            ):
                dec_name = dec.args[0].value
                decorators_found += 1
        if dec_name is None:
            continue

        # string constants assigned inside the body, so we can resolve `demo_source`
        str_consts = {}
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        str_consts[tgt.id] = node.value.value

        body = fn.body
        for i, stmt in enumerate(body):
            if not (isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Subscript)):
                continue
            sub = stmt.value
            tgt = sub.value
            if not (
                isinstance(tgt, ast.Attribute)
                and tgt.attr == "tests"
                and isinstance(tgt.value, ast.Name)
                and tgt.value.id == suite_var
            ):
                continue
            idx = sub.slice
            if not (isinstance(idx, ast.UnaryOp) and isinstance(idx.op, ast.USub)
                    and isinstance(idx.operand, ast.Constant) and idx.operand.value == 1):
                continue
            var_name = stmt.targets[0].id if stmt.targets and isinstance(stmt.targets[0], ast.Name) else None
            # the with_demo(...) call that must follow
            cat = name = src = None
            for follow in body[i + 1:]:
                expr = follow.value if isinstance(follow, ast.Expr) else None
                if (
                    isinstance(expr, ast.Call)
                    and isinstance(expr.func, ast.Attribute)
                    and expr.func.attr == "with_demo"
                ):
                    args = []
                    for a in expr.args:
                        if isinstance(a, ast.Constant):
                            args.append(a.value)
                        elif isinstance(a, ast.Name):
                            args.append(str_consts.get(a.id, f"<unresolved:{a.id}>"))
                        else:
                            args.append("<unresolved>")
                    cat, name, src = args[0], args[1], args[2]
                    break
            sites.append(
                {
                    "file": os.path.relpath(path, REPO).replace("\\", "/"),
                    "lineno": stmt.lineno,
                    "attach_lineno_end": getattr(follow, "lineno", stmt.lineno) if cat else stmt.lineno,
                    "enclosing_test": dec_name,
                    "var": var_name,
                    "category": cat,
                    "demo_name": name,
                    "demo_source": src,
                }
            )

    # sanity: nothing inside a test *body* mutates suite.tests (decorators live outside bodies)
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        for stmt in fn.body:
            for node in ast.walk(stmt):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                if node.func.attr == "add_test" or (
                    node.func.attr == "test"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == suite_var
                ):
                    mutation_calls.append((fn.name, node.func.attr, node.lineno))
    return sites, decorators_found, mutation_calls


def section_b():
    hr("B. the nine real sites, resolved against the real imported suite objects")
    mods = {}
    for name in SUITES:
        mod = __import__(f"test_suite.suites.{name}", fromlist=[name])
        mods[name] = mod
        suite = getattr(mod, name.replace("_suite", "_suite"))
        print(f"\n  {name}: suite {suite!r}, registration order:")
        for i, t in enumerate(suite.tests):
            print(f"      tests[{i}]  {t.name!r:<36} id=0x{id(t):x}")

    all_sites = []
    total_decorators = 0
    for name in SUITES:
        suite_var = name.replace("_suite", "_suite")
        suite = getattr(mods[name], suite_var)
        path = os.path.join(REPO, "test_suite", "suites", f"{name}.py")
        sites, ndec, mutations = extract_sites(path, suite_var)
        total_decorators += ndec
        print(f"  {name}: {ndec} @test decorators executed at import time; "
              f"mutations of suite.tests found inside test bodies: {mutations or 'none'}")
        for s in sites:
            target = suite.tests[-1]
            expected = next(t for t in suite.tests if t.name == s["enclosing_test"])
            s["suite"] = suite_var
            s["suite_obj"] = suite
            s["expected_id"] = id(expected)
            s["actual_name"] = target.name
            s["actual_id"] = id(target)
            s["actual_index"] = len(suite.tests) - 1
            s["expected_index"] = suite.tests.index(expected)
            s["correct"] = target is expected
            all_sites.append(s)

    print("")
    print(f"  total attach sites found: {len(all_sites)} (expected 9)")
    print("")
    print("  SITE                          | SHOULD LAND ON (body)          | ACTUALLY LANDS ON tests[-1]      | idx exp->act | verdict")
    print("  " + "-" * 116)
    bad = 0
    for s in all_sites:
        verdict = "accidentally ok" if s["correct"] else "MIS-ATTRIBUTED"
        if not s["correct"]:
            bad += 1
        print(f"  {s['file']}:{s['lineno']:<3}          | {s['enclosing_test']:<31}| "
              f"{s['actual_name']:<29}| {s['expected_index']:>2} -> {s['actual_index']:<4}| {verdict}")
    print("")
    print("  with_demo() payload each site *intends* vs where it lands:")
    for s in all_sites:
        print(f"    {s['file']}:{s['lineno']:<3} with_demo({s['category']!r}, {s['demo_name']!r}, <{len(s['demo_source'])} chars>)"
              f"  -> Test(id=0x{s['actual_id']:x}) {s['actual_name']!r}"
              f"  [expected Test(id=0x{s['expected_id']:x}) {s['enclosing_test']!r}]")
    return all_sites, bad


# ---------------------------------------------------------------- Section C
def section_c(all_sites):
    hr("C. replay the run in registration order with real TestResult + real DemoWriter")
    by_suite = {}
    for s in all_sites:
        by_suite.setdefault(s["suite_obj"], []).append(s)

    suite_results = []
    passed = failed = 0
    for name in RUN_ORDER:
        mod = __import__(f"test_suite.suites.{name}", fromlist=[name])
        suite = getattr(mod, name)
        sites = {s["enclosing_test"]: s for s in by_suite.get(suite, [])}
        results = []
        for t in suite.tests:
            # the compiler assertion of the real body passes (baseline: 47 passed / 0 failed),
            # so what remains observable here is exactly the metadata half of the body.
            site = sites.get(t.name)
            if site:
                tgt = suite.tests[-1]          # verbatim replay of the buggy line
                tgt.with_demo(site["category"], site["demo_name"], site["demo_source"])
            results.append(
                TestResult(
                    suite_name=suite.name,
                    test_name=t.name,
                    status="passed",
                    demo_category=t.demo_category,
                    demo_name=t.demo_name,
                    demo_source=t.demo_source,
                )
            )
            passed += 1
        suite_results.append(SuiteResult(suite.name, results, passed=len(results), failed=0, skipped=0))

    run = RunResult(results=suite_results, passed=passed, failed=failed, skipped=0, elapsed=0.0)
    demo_results = run.get_demo_results()        # runner.py:172-179, what sync_demo.py:112 uses

    print(f"  replayed {passed} tests; get_demo_results() returned {len(demo_results)} (intended: 9)")
    print("")
    print("  RESULT (test_name)              | demo_category | demo_name        | file sync_demo.py writes")
    print("  " + "-" * 92)
    for tr in demo_results:
        safe = tr.demo_name.replace("/", "_").replace(" ", "_")
        print(f"  {tr.test_name:<30}| {tr.demo_category:<13}| {tr.demo_name:<16}| "
              f"{'examples/demos/legacy'}/{tr.demo_category}/{safe}.cypy")

    # which intended demos vanished
    landed = {tr.demo_name for tr in demo_results}
    intended = {s["demo_name"] for s in all_sites}
    print("")
    print("  intended demo_name set (9):", sorted(intended))
    print("  actually synced set        (%d):" % len(landed), sorted(landed))
    print("  LOST demos (%d):" % len(intended - landed), sorted(intended - landed))

    # the tests whose own bodies attached metadata but whose results carry none
    result_by_name = {tr.test_name: tr for sr in suite_results for tr in sr.results}
    lost_tests = sorted(
        {s["enclosing_test"] for s in all_sites if not result_by_name[s["enclosing_test"]].has_demo}
    )
    print("  tests that pass with demo=None despite containing a with_demo() line (%d): %s"
          % (len(lost_tests), lost_tests))

    if os.path.isdir(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    os.makedirs(OUT_DIR, exist_ok=True)
    writer = DemoWriter(OUT_DIR)
    synced = writer.sync_from_tests(demo_results)
    produced = sorted(os.path.relpath(p, OUT_DIR).replace("\\", "/") for p in
                      [f for files in synced.values() for f in files])
    print("")
    print("  DemoWriter.sync_from_tests() wrote %d files into scratch:" % len(produced))
    for p in produced:
        print("     ", p)

    # compare with what is checked in under examples/demos/legacy
    repo_dir = os.path.join(REPO, "examples", "demos", "legacy")
    existing = []
    for cat in ("parser", "analyzer", "codegen", "integration", "builtins"):
        d = os.path.join(repo_dir, cat)
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                if f.endswith(".cypy"):
                    existing.append(f"{cat}/{f}")
    print("")
    print("  files currently committed under examples/demos/legacy (%d):" % len(existing))
    for p in existing:
        print("     ", p)
    want = {f"{s['category']}/{s['demo_name']}.cypy" for s in all_sites}
    print("")
    print("  intended-by-source but ABSENT from the repo (%d):" % len(want - set(existing)),
          sorted(want - set(existing)))
    print("  produced by replay but NEVER WRITTEN by any real sync since (stale/orphan) (%d):"
          % len(set(existing) - want), sorted(set(existing) - want))

    # byte-identity check for the four "accidentally correct" files
    print("")
    print("  byte-identity of the surviving files vs the suite's own demo_source string:")
    import difflib

    for s in all_sites:
        p = os.path.join(repo_dir, s["category"], f"{s['demo_name']}.cypy")
        if not os.path.exists(p):
            continue
        with open(p, "r", encoding="utf-8") as fh:
            disk = fh.read()
        same = disk == s["demo_source"]
        print(f"    {s['category']}/{s['demo_name']}.cypy  matches {s['file']}:{s['lineno']}: {same}")
        if not same:
            for line in difflib.unified_diff(
                s["demo_source"].splitlines(), disk.splitlines(),
                fromfile=f"{s['file']}:{s['lineno']} (harness source of truth)",
                tofile=f"examples/demos/legacy/{s['category']}/{s['demo_name']}.cypy",
                lineterm="", n=0,
            ):
                print("        " + line)

    # and the real replay dir must equal the four surviving files
    print("")
    print("  replay produced exactly the surviving set:",
          sorted(produced) == sorted(f"{s['category']}/{s['demo_name']}.cypy"
                                     for s in all_sites if os.path.exists(os.path.join(repo_dir, s['category'], s['demo_name'] + '.cypy'))))

    # cross-check against the ONE real end-to-end run:
    #   python scripts/run_tests.py --sync-demo --demo-dir <scratch>/demos_real
    real_dir = os.path.join(HERE, "scratch", "demos_real")
    print("")
    if os.path.isdir(real_dir):
        real = sorted(
            f"{cat}/{f}"
            for cat in ("parser", "analyzer", "codegen", "integration", "builtins")
            for f in (os.listdir(os.path.join(real_dir, cat))
                      if os.path.isdir(os.path.join(real_dir, cat)) else [])
            if f.endswith(".cypy")
        )
        print("  ground truth from the real run (`run_tests.py --sync-demo` into scratch/demos_real):")
        for p in real:
            print("     ", p)
        print("  replay set == real sync set:", real == sorted(produced))
        print("  freshly-synced content vs the committed copy:")
        for p in real:
            cat, fn = p.split("/")
            fresh_p = os.path.join(real_dir, cat, fn)
            repo_p = os.path.join(repo_dir, cat, fn)
            if not os.path.exists(repo_p):
                print(f"     {p}: committed copy MISSING")
                continue
            with open(fresh_p, "r", encoding="utf-8") as fh:
                fresh = fh.read()
            with open(repo_p, "r", encoding="utf-8") as fh:
                committed = fh.read()
            print(f"     {p}: identical={fresh == committed}"
                  + ("" if fresh == committed else "  <-- committed copy is STALE"))
        for s in all_sites:
            expected_file = os.path.join(real_dir, s["category"], f"{s['demo_name']}.cypy")
            if not os.path.exists(expected_file):
                print(f"    LOST in the real run: {s['category']}/{s['demo_name']}.cypy "
                      f"(attached at {s['file']}:{s['lineno']} by test {s['enclosing_test']!r})")
    else:
        print("  (scratch/demos_real absent -- run scripts/run_tests.py --sync-demo to populate it)")
    return len(demo_results), produced


def section_d():
    hr("D. counterfactual on the same idiom -- the pairing goes actively WRONG")
    # Same shape as the four suites, but the last-registered test is NOT the last demo.
    # (Adding any test below the demo block, or reordering, moves the target -- which is
    # exactly why the current 4-of-9 result is luck, not correctness.)
    suite = Suite("ReorderedSuite")
    order = []

    @suite.test("demo_alpha")
    def _alpha():
        order.append("demo_alpha body")
        suite.tests[-1].with_demo("cat", "alpha", "ALPHA-SOURCE")

    @suite.test("demo_beta")          # this one now FAILS, like a broken demo would
    def _beta():
        order.append("demo_beta body")
        assert False, "beta's compiler check failed"
        suite.tests[-1].with_demo("cat", "beta", "BETA-SOURCE")

    @suite.test("plain_zulu")         # registered last -> becomes the metadata magnet
    def _zulu():
        order.append("plain_zulu body (attaches nothing)")

    sr = suite.run()
    print("  execution order:", " | ".join(order))
    for tr in sr.results:
        print(f"  result {tr.test_name:<12} status={tr.status:<7} demo_name={tr.demo_name!r} "
              f"has_demo={tr.has_demo} demo_source={tr.demo_source!r}")
    demos = RunResult([sr], 2, 1, 0, 0.0).get_demo_results()
    out2 = os.path.join(SCRATCH, "demos_reordered")
    if os.path.isdir(out2):
        shutil.rmtree(out2)
    os.makedirs(out2, exist_ok=True)
    written = DemoWriter(out2).sync_from_tests(demos)
    files = sorted(
        f"{cat}/{os.path.basename(p)}" for cat, ps in written.items() for p in ps
    )
    wrong = any("alpha" in f for f in files)
    print(f"  files synced: {files}")
    print("  -> plain_zulu never ran any demo source, yet it is the result carrying the "
          "metadata; and demo_alpha's source was published on the strength of plain_zulu "
          f"passing. mis-pairing present: {wrong}")
    print("  -> note demo_beta is 'failed' and its with_demo() line never executed, so the "
          "only surviving payload is the one written by demo_alpha onto the last Test.")
    return wrong


def main():
    try:
        a_bad = section_a()
        sites, b_bad = section_b()
        n_synced, produced = section_c(sites)
        d_bad = section_d()
    except Exception as exc:  # pragma: no cover
        import traceback

        traceback.print_exc()
        print("HARNESS PROBLEM:", exc)
        return 2

    hr("VERDICT")
    print(f"  scratch harness mis-attribution observed ......... {a_bad}")
    print(f"  real sites landing on the wrong Test ............. {b_bad} of {len(sites)}")
    print(f"  demos actually synced by the real writer ......... {n_synced} (intended {len(sites)})")
    print(f"  reordered-idiom mis-pairing (counterfactual) ..... {d_bad}")
    reproduced = a_bad and b_bad > 0 and n_synced < len(sites)
    print(f"  DEFECT 1 REPRODUCED: {reproduced}")
    return 1 if reproduced else 0


if __name__ == "__main__":
    sys.exit(main())
