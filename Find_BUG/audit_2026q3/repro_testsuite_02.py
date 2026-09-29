"""OMEGA repro T0r61.5.1 / defect 2 -- Test.skip() is shadowed by an instance attribute.

Claim
-----
test_suite/core/test.py:13 executes `self.skip = False` inside `Test.__init__`, while
test.py:26 defines `def skip(self, reason="")` on the class.  The instance attribute
shadows the method for every constructed Test, so the documented "unconditional skip"
API (`test.py:26-30`, docstring 无条件跳过) is uncallable:

    Test("name", fn).skip("reason")   ->   TypeError: 'bool' object is not callable

Knock-on effect inside this harness: the only usable skip is `skip_if(True, ...)`
(test.py:19), so no suite author can mark a test skipped declaratively -- and indeed
test_suite/suites/parser_suite.py:91-109 stubs three "not yet supported" tests with a
bare `pass` instead of skipping them, which is why the real run reports 47 passed /
0 skipped (see repro_testsuite_03.py section R for the inventory).

Nothing in the repo ever calls `.skip(` -- consistent with it raising.

Exit code: 1 = bug reproduced, 0 = not reproduced, 2 = harness problem.
Reads the repo, writes nothing.
"""

import inspect
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

if sys.platform == "win32":  # match scripts/run_tests.py:17-22 so CJK docstrings print
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from test_suite.core.suite import Suite  # noqa: E402
from test_suite.core.test import Test  # noqa: E402


def hr(title):
    print("")
    print("=" * 78)
    print(title)
    print("=" * 78)


def noop():
    return None


def main():
    findings = 0

    hr("1. what the class defines vs what an instance carries")
    print("  test.py:13  -> `self.skip = False`  (instance attribute)")
    print("  test.py:26  -> `def skip(self, reason='')`  (class method)")
    cls_skip = inspect.getattr_static(Test, "skip")
    print(f"  Test.skip (class slot, static)      : {type(cls_skip).__name__} "
          f"{getattr(cls_skip, '__name__', '')} -> {getattr(cls_skip, '__doc__', None)!r}")
    t = Test("demo_skip_api", noop)
    print(f"  Test('demo_skip_api', noop) built   : {t!r}")
    print(f"  instance.__dict__                   : { {k: v for k, v in t.__dict__.items() if k in ('name', 'skip', 'skip_reason')} }")
    print(f"  'skip' in instance __dict__         : {'skip' in t.__dict__}")
    print(f"  t.skip resolved at runtime          : {type(t.skip).__name__} = {t.skip!r}")
    if "skip" in t.__dict__ and not callable(t.skip):
        findings += 1
        print("  FINDING: the instance attribute shadows the method -- the method is "
              "unreachable through normal attribute lookup.")

    hr("2. the documented API raises")
    try:
        Test("demo_skip_api", noop).skip("not supported yet")
        print("  NO ERROR -- defect not reproduced")
    except TypeError as exc:
        print(f"  TypeError: {exc}")
        last = traceback.extract_tb(sys.exc_info()[2])[-1]
        print(f"  raised at  : {os.path.relpath(last.filename, REPO).replace(chr(92), '/')}:{last.lineno}  "
              f"`{last.line}`")
        print("  FINDING: Test(...).skip(reason) cannot be called on any constructed Test.")
        findings += 1

    hr("3. the method body is dead code; only skip_if() works")
    bypass = Test("descriptor_only", noop)
    unbound = inspect.getattr_static(Test, "skip")
    returned = unbound.__get__(bypass)("reached only via the descriptor protocol")
    print(f"  Test.skip.__get__(t)('...') returns the same Test (fluent API preserved): {returned is bypass}")
    print(f"  after that call: t.skip={bypass.skip!r} t.skip_reason={bypass.skip_reason!r}")
    print("  NOTE the fluent contract is itself broken: the method returns Test, but every")
    print("  real call site would get a bool attribute, so `Test(...).skip(x).with_demo(...)`")
    print("  can never chain.")

    t2 = Test("via_skip_if", noop)
    t2.skip_if(True, "unsupported syntax")
    r2 = t2.run()
    print(f"  skip_if(True, reason).run() -> status={r2.status!r} message={r2.message!r}  (works)")
    t3 = Test("never_skipped", noop)
    r3 = t3.run()
    print(f"  plain test.run()            -> status={r3.status!r}  (counts as PASSED)")

    hr("4. proof that the shadowing survives a whole suite run")
    suite = Suite("SkipShadowSuite")

    @suite.test("wanted_to_skip_this")
    def _body():
        pass

    reg = suite.tests[-1]
    print(f"  registered test object: {reg.name!r} id=0x{id(reg):x}")
    try:
        reg.skip("build-block syntax not supported")
        print("  reg.skip(...) succeeded -- unexpected")
    except TypeError as exc:
        print(f"  reg.skip(...) -> TypeError: {exc}")
        findings += 1
    sr = suite.run()
    print(f"  Suite.run(): passed={sr.passed} failed={sr.failed} skipped={sr.skipped}")
    print("  FINDING: a test that cannot be skipped is reported as passed, inflating the")
    print("  green count -- exactly the situation of parser_suite.py:91/98/105.")

    hr("5. repo-wide call-site census")
    hits = []
    skipped_noise = []
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", "build", "dist", ".pytest_cache", "Find_BUG"}]
        for fn in files:
            if not fn.endswith(".py"):
                continue
            p = os.path.join(root, fn)
            try:
                with open(p, "r", encoding="utf-8") as fh:
                    for i, line in enumerate(fh, 1):
                        if ".skip(" not in line:
                            continue
                        rel = os.path.relpath(p, REPO).replace("\\", "/")
                        if "pytest.skip" in line:
                            skipped_noise.append((rel, i, line.strip()))
                            continue
                        hits.append((rel, i, line.strip()))
            except (UnicodeDecodeError, OSError):
                pass
    for rel, i, line in hits:
        print(f"  harness `.skip(` call site -> {rel}:{i}: {line}")
    print(f"  Test.skip() call sites in the harness: {len(hits)}")
    print(f"  (other `.skip(` text found, all pytest's own API: {len(skipped_noise)} -> "
          f"{[f'{r}:{i}' for r, i, _ in skipped_noise]})")

    hr("VERDICT")
    print(f"  findings recorded: {findings}")
    reproduced = findings >= 2
    print(f"  DEFECT 2 REPRODUCED: {reproduced}")
    return 1 if reproduced else 0


if __name__ == "__main__":
    sys.exit(main())
