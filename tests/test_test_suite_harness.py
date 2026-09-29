"""OMEGA 永久守卫测试 -- test_suite/ 自验证 harness (fix unit T0r61.5.2)。

覆盖四个缺陷的"不可回归"不变量。本文件必须秒级完成：只使用 harness 自身的
核心类 (Suite/Test/TestResult/RunResult/DemoWriter) + AST 静态扫描，
绝不调用 Cypy 编译器、绝不运行 scripts/run_tests.py。

缺陷 -> 守卫映射
  D1  demo 元数据挂错 Test（`<suite>.tests[-1]` 在 run() 期恒为最后注册项）
      -> 禁止体内 tests[-1] 挂载点；Suite.current_test 绑定运行中的 Test；
         9 个 with_demo 站点与所在测试 1:1 配对；examples/demos/legacy 与
         站点字节级一致且无孤儿文件。
  D2  实例属性 self.skip 遮蔽方法 skip() -> 方法必须可调用、标志位为 skipped、
      skip_if 保持可用。
  D3  空体/冒烟断言 + Suite.run() 不咨询 Check.has_failures()
      -> AST 检查无 vacuous/smoke-only 测试体、注册总数恒为 47、
         软断言失败必须把测试判 failed。
  D4  demo 流水线数据腐蚀（漏同步/漂移/孤儿）
      -> 与 D1 的字节级守卫合并（漂移文件任何改动都会在这里失败）。
"""
import ast
import os
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from test_suite.core.runner import RunResult  # noqa: E402
from test_suite.core.suite import Suite  # noqa: E402
# `Test`/`TestResult` 取别名，避免 pytest 把它们当作测试类收集
from test_suite.core.test import Test as _HarnessTest  # noqa: E402
from test_suite.core.test import TestResult as _HarnessResult  # noqa: E402,F401
from test_suite.utils.demo_writer import DemoWriter  # noqa: E402

SUITES_DIR = os.path.join(REPO_ROOT, "test_suite", "suites")
LEGACY_DIR = os.path.join(REPO_ROOT, "examples", "demos", "legacy")

# 与 scripts/run_tests.py / scripts/sync_demo.py 相同的套件清单
SUITE_MODULES = ["parser_suite", "analyzer_suite", "codegen_suite", "integration_suite"]

EXPECTED_TOTAL_TESTS = 47          # 47 = 18 parser + 10 analyzer + 9 codegen + 10 integration
EXPECTED_PER_SUITE = {"parser_suite": 18, "analyzer_suite": 10,
                      "codegen_suite": 9, "integration_suite": 10}
EXPECTED_DEMO_SITES = 9            # 9 个 with_demo 挂载点，全部必须 1:1 配对并同步


# ------------------------------------------------------------------ AST helpers
def _resolve_str_arg(node, str_consts):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return str_consts.get(node.id)
    return None


def _string_consts(fn):
    consts = {}
    for node in ast.walk(fn):
        if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    consts[tgt.id] = node.value.value
    return consts


def scan_suite_file(module_name):
    """AST-scan one suite module.

    Returns a list of dicts per registered test:
      name, lineno, assert_kinds, body_is_pass_only, demo (None or
      (category, demo_name, demo_source)), runaway_sites (line numbers where a
      test body resolves `<suite>.tests[-1]`).
    """
    path = os.path.join(SUITES_DIR, f"{module_name}.py")
    with open(path, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)

    rows = []
    for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef)]:
        dec_name = None
        for dec in fn.decorator_list:
            if (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                    and dec.func.attr == "test" and dec.args
                    and isinstance(dec.args[0], ast.Constant)):
                dec_name = dec.args[0].value
        if dec_name is None:
            continue

        assert_kinds = []
        demo = None
        runaway = []
        consts = _string_consts(fn)
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "Assert":
                    assert_kinds.append(node.func.attr)
                if (node.func.attr == "with_demo" and len(node.args) == 3):
                    args = [_resolve_str_arg(a, consts) for a in node.args]
                    if all(a is not None for a in args):
                        demo = tuple(args)
            if isinstance(node, ast.Subscript):
                v = node.value
                idx = node.slice
                if (isinstance(v, ast.Attribute) and v.attr == "tests"
                        and isinstance(v.value, ast.Name)
                        and isinstance(idx, ast.UnaryOp) and isinstance(idx.op, ast.USub)
                        and isinstance(idx.operand, ast.Constant) and idx.operand.value == 1):
                    runaway.append(node.lineno)

        real_stmts = [s for s in fn.body
                      if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
        pass_only = all(isinstance(s, ast.Pass) for s in real_stmts) if real_stmts else True

        rows.append({
            "name": dec_name, "lineno": fn.lineno, "assert_kinds": assert_kinds,
            "pass_only": pass_only, "demo": demo, "runaway_sites": runaway,
        })
    return rows


ALL_ROWS = {m: scan_suite_file(m) for m in SUITE_MODULES}
ALL_DEMO_SITES = [(m, r) for m in SUITE_MODULES for r in ALL_ROWS[m] if r["demo"]]


# ------------------------------------------------------------------ D1 guards
def test_no_tests_minus_one_sites_inside_test_bodies():
    """D1: 测试体内禁止 `<suite>.tests[-1]` —— run() 期它恒为最后注册的 Test。"""
    offenders = []
    for module, rows in ALL_ROWS.items():
        for r in rows:
            for line in r["runaway_sites"]:
                offenders.append(f"{module}.py:{line} ({r['name']})")
    assert offenders == [], f"runaway tests[-1] metadata sites back in: {offenders}"


def test_suite_run_publishes_current_test():
    """D1: Suite.run() 必须在 test.run() 之前把 Suite.current_test 绑定到正在执行的 Test。"""
    suite = Suite("CurrentTestGuard")
    seen = {}

    def body_a():
        seen["a"] = suite.current_test

    def body_b():
        seen["b"] = suite.current_test
        # 元数据必须能挂到"正在运行的自己"身上
        suite.current_test.with_demo("guard", "beta", "BETA-SOURCE")

    suite.add_test(_HarnessTest("t_a", body_a))
    suite.add_test(_HarnessTest("t_b", body_b))
    assert suite.current_test is None
    sr = suite.run()
    assert seen["a"] is suite.tests[0]
    assert seen["b"] is suite.tests[1]
    assert suite.current_test is None  # run 结束后复位
    results = {tr.test_name: tr for tr in sr.results}
    assert results["t_b"].demo_name == "beta"
    assert results["t_a"].demo_name is None  # 不再被别的测试污染


def test_demo_sites_pair_one_to_one_with_their_tests(tmp_path):
    """D1: 9 个 with_demo 站点，每个的 TestResult.test_name 与其 demo_name 1:1 配对，
    且 DemoWriter 恰好同步出 9 个 .cypy 文件（真实 Suite/Test/TestResult/RunResult/
    DemoWriter 按注册顺序回放，零编译器调用）。
    """
    assert len(ALL_DEMO_SITES) == EXPECTED_DEMO_SITES, (
        f"expected {EXPECTED_DEMO_SITES} demo sites, found {len(ALL_DEMO_SITES)}")

    demo_names = [r["demo"][1] for _, r in ALL_DEMO_SITES]
    assert len(set(demo_names)) == EXPECTED_DEMO_SITES, f"demo_name collision: {demo_names}"

    all_pairs = []
    all_results = []
    for module in SUITE_MODULES:
        rows = ALL_ROWS[module]
        suite = Suite(module)
        for r in rows:
            if r["demo"] is None:
                suite.add_test(_HarnessTest(r["name"], lambda: None))
            else:
                site = r["demo"]

                def body(s=site):
                    # 复刻修复后的挂载惯用法：只允许挂到 current_test 上
                    suite.current_test.with_demo(*s)

                suite.add_test(_HarnessTest(r["name"], body))
        sr = suite.run()
        all_results.append(sr)
        by_name = {tr.test_name: tr for tr in sr.results}
        for r in rows:
            tr = by_name[r["name"]]
            if r["demo"] is None:
                assert not tr.has_demo, f"{r['name']} must not carry a demo"
            else:
                # 关键不变量：元数据落在"运行它的那个 Test"的 TestResult 上
                assert tr.demo_name == r["demo"][1], (
                    f"{r['name']} expected demo {r['demo'][1]!r}, got {tr.demo_name!r}")
                assert tr.demo_source == r["demo"][2]
                all_pairs.append((tr.test_name, tr.demo_name))

    assert len(set(all_pairs)) == EXPECTED_DEMO_SITES
    assert all(t.startswith("demo_") for t, _ in all_pairs), all_pairs

    run = RunResult(results=all_results, passed=sum(len(r.results) for r in all_results),
                    failed=0, skipped=0, elapsed=0.0)
    demo_results = run.get_demo_results()
    assert len(demo_results) == EXPECTED_DEMO_SITES, (
        f"get_demo_results() returned {len(demo_results)}, want {EXPECTED_DEMO_SITES}")

    written = DemoWriter(str(tmp_path)).sync_from_tests(demo_results)
    files = sorted(f"{cat}/{os.path.basename(p)}" for cat, ps in written.items() for p in ps)
    expected_files = sorted(f"{r['demo'][0]}/{r['demo'][1]}.cypy" for _, r in ALL_DEMO_SITES)
    assert files == expected_files, f"synced {len(files)} demos, want 9: {expected_files}"
    for rel in expected_files:
        src = next(r["demo"][2] for _, r in ALL_DEMO_SITES
                   if f"{r['demo'][0]}/{r['demo'][1]}.cypy" == rel)
        with open(os.path.join(str(tmp_path), *rel.split("/")), "r", encoding="utf-8") as fh:
            assert fh.read() == src, f"content mismatch for {rel}"


def test_legacy_demos_match_generating_sites_and_have_no_orphans():
    """D4: examples/demos/legacy 必须与 9 个生成点字节级一致，且没有任何孤儿文件。

    （任何 suite 源码字面量与已同步 demo 之间的漂移——例如历史上的
    integration/array_operations.cypy `list[int]` vs `list<int>`——都会在这里失败。）
    """
    expected = {}
    for _, r in ALL_DEMO_SITES:
        cat, name, src = r["demo"]
        expected[f"{cat}/{name}.cypy"] = src

    on_disk = {}
    for root, _dirs, files in os.walk(LEGACY_DIR):
        for f in files:
            if f.endswith(".cypy"):
                p = os.path.join(root, f)
                rel = os.path.relpath(p, LEGACY_DIR).replace("\\", "/")
                with open(p, "r", encoding="utf-8") as fh:
                    on_disk[rel] = fh.read()

    missing = sorted(set(expected) - set(on_disk))
    orphans = sorted(set(on_disk) - set(expected))
    assert not missing, f"legacy demos never synced (missing generating output): {missing}"
    assert not orphans, f"legacy demos with no generating site (orphans): {orphans}"
    for rel, src in expected.items():
        assert on_disk[rel] == src, (
            f"DRIFT: {rel} differs from its generating suite literal (re-run "
            f"`python scripts/run_tests.py --sync-demo`)")


# ------------------------------------------------------------------ D2 guards
def _noop():
    return None


def test_skip_method_is_callable_not_shadowed():
    """D2: Test(name, fn).skip(reason) 必须可调用（不再被 self.skip 布尔属性遮蔽）。"""
    t = _HarnessTest("guard_skip", _noop)
    assert callable(t.skip), f"Test.skip resolved to {type(t.skip).__name__} — shadowed again"
    returned = t.skip("not supported yet")
    assert returned is t                      # fluent API
    assert t.skipped is True                  # 标志位现在叫 skipped
    assert t.skip_reason == "not supported yet"
    assert "skip" not in t.__dict__, "instance dict must not shadow the skip() method"
    result = t.run()
    assert result.status == "skipped"
    assert result.message == "not supported yet"


def test_skip_if_still_works_and_repr_intact():
    t2 = _HarnessTest("guard_skip_if", _noop)
    assert t2.skip_if(True, "conditional") is t2
    assert t2.skipped is True
    assert t2.run().status == "skipped"
    t3 = _HarnessTest("guard_plain", _noop)
    t3.skip_if(False, "no-op")
    assert t3.skipped is False
    assert t3.run().status == "passed"
    assert "skip" in repr(t3)  # __repr__ 仍暴露跳过状态（现在用 skipped=）


def test_skipped_test_does_not_count_as_passed():
    suite = Suite("SkipGuard")

    @suite.test("skipped_one")
    def _s():
        raise AssertionError("body must not run")

    suite.tests[-1].skip("guard")
    sr = suite.run()
    assert sr.skipped == 1 and sr.passed == 0 and sr.failed == 0


# ------------------------------------------------------------------ D3 guards
def test_registered_test_count_is_pinned():
    """D3 约束: 三 vacuous parser 测试改真断言而非 skip —— 总数必须仍是 47。"""
    from test_suite.suites.analyzer_suite import analyzer_suite
    from test_suite.suites.codegen_suite import codegen_suite
    from test_suite.suites.integration_suite import integration_suite
    from test_suite.suites.parser_suite import parser_suite
    counts = {
        "parser_suite": len(parser_suite.tests),
        "analyzer_suite": len(analyzer_suite.tests),
        "codegen_suite": len(codegen_suite.tests),
        "integration_suite": len(integration_suite.tests),
    }
    assert counts == EXPECTED_PER_SUITE, counts
    assert sum(counts.values()) == EXPECTED_TOTAL_TESTS


def test_no_vacuous_or_smoke_only_test_bodies():
    """D3 (AST): 任何注册测试体不得为空 pass / 无 Assert / 只有 is_not_none 或只有 true。"""
    offenders = []
    for module, rows in ALL_ROWS.items():
        for r in rows:
            kinds = set(r["assert_kinds"])
            if r["pass_only"] or not kinds:
                offenders.append(f"{module}.py:{r['lineno']} {r['name']}: VACUOUS")
            elif kinds <= {"is_not_none"}:
                offenders.append(f"{module}.py:{r['lineno']} {r['name']}: is_not_none-only")
            elif kinds <= {"true"}:
                offenders.append(f"{module}.py:{r['lineno']} {r['name']}: Assert.true-only")
    assert offenders == [], "weak assertions back in:\n" + "\n".join(offenders)


def test_analyzer_suite_has_negative_tests():
    """D3/M1: analyzer 套件必须包含"坏程序必须被拒绝"的负例（Assert.false 等）。"""
    negatives = [r["name"] for r in ALL_ROWS["analyzer_suite"] if "false" in r["assert_kinds"]]
    assert len(negatives) >= 3, (
        "analyzer suite regressed to positive-only smoke: a neutered analyzer "
        f"(always success) would pass; negatives found: {negatives}")


def test_suite_run_fails_on_soft_check_failures():
    """D3/M4: Suite.run() 必须咨询 Check.has_failures()，软断言失败 -> failed。"""
    from test_suite.core.assertions import Check

    suite = Suite("SoftCheckGuard")

    @suite.test("quietly_wrong")
    def _body():
        Check.equal(1, 2, "guard: soft failure must be fatal")

    Check.reset()
    sr = suite.run()
    try:
        tr = sr.results[0]
        assert tr.status == "failed", (
            f"soft-check failure reported {tr.status!r} — Suite.run() stopped consulting "
            f"Check.has_failures()")
        assert "guard: soft failure must be fatal" in (tr.message or "")
        assert sr.failed == 1 and sr.passed == 0
    finally:
        Check.reset()


def test_fixture_compile_and_run_does_not_swallow_exceptions():
    """D3: fixtures/compiler.py 的 compile_and_run 不得再用 except Exception 折叠真异常。"""
    path = os.path.join(REPO_ROOT, "test_suite", "fixtures", "compiler.py")
    with open(path, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "compile_and_run"), None)
    assert fn is not None, "CompilerFixture.compile_and_run not found"
    for h in [n for n in ast.walk(fn) if isinstance(n, ast.ExceptHandler)]:
        name = getattr(h.type, "id", None) if h.type is not None else "bare-except"
        assert name not in ("Exception", "BaseException", None), (
            f"compile_and_run() swallows {name!r} into None again")
