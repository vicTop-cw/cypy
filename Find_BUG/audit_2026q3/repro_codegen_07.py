#!/usr/bin/env python3
"""OMEGA-verified repro unit T0r61.4.1 / defect 07.

Target: cypyc/project/project_compiler.py:509-512

Claim: `result.success = True` is assigned unconditionally *before* the compile
loop at :512, so a build whose module list is EMPTY reports success.  Two
ordinary ways to reach it:
  (a) `build(entry_point=X)` where X is not a discovered module (typo, moved
      file, renamed package): :502-506 filters compilation_order down to []
      and the loop body never runs;
  (b) a project whose modules are all members of a dependency cycle:
      ModuleDependencyGraph.topological_sort() (:147-160, Kahn) silently DROPS
      every node still holding in-degree, so compilation_order == [] and the
      cycle is only reported as a *warning*.
In both cases the caller gets success=True, compiled_modules=[], and no error -
the CLI therefore prints "[OK] Build succeeded" having compiled nothing.

Exit codes: 1 = defect REPRODUCED, 0 = not reproduced, 3 = harness error.
Creates throwaway projects only under Find_BUG/audit_2026q3/scratch/.
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir))
sys.path.insert(0, REPO)
SCRATCH_A = os.path.join(HERE, "scratch", "proj07a")
SCRATCH_B = os.path.join(HERE, "scratch", "proj07b")

CASE_A = {  # real modules present; bogus entry point empties the list
    "lib.cypy": "def helper() -> int:\n    return 1\n",
    "main.cypy": "from lib import helper\n\ndef start() -> int:\n    return helper()\n",
}

CASE_B = {  # every module is inside a cycle -> topological_sort drops them all
    "aa.cypy": "from bb import b_fn\n\ndef a_fn() -> int:\n    return b_fn()\n",
    "bb.cypy": "from aa import a_fn\n\ndef b_fn() -> int:\n    return a_fn()\n",
}


def make_project(root, files):
    if os.path.isdir(root):
        shutil.rmtree(root, ignore_errors=True)
    for rel, body in files.items():
        p = os.path.join(root, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(body)


def instrumented(root, **kw):
    """Run the REAL build() but count compile_module() calls, without paying for
    a toolchain invocation (the audited line is the success flag, not the C/C
    backend)."""
    from cypyc.project.project_compiler import ProjectCompiler
    pc = ProjectCompiler(project_root=root, output_dir=os.path.join(root, "_out"))
    calls = []
    orig = pc.compile_module

    def spy(module_name):
        calls.append(module_name)
        return orig(module_name)

    pc.compile_module = spy
    return pc, calls, pc.build(**kw)


def main():
    reproduced = []

    src = open(os.path.join(REPO, "cypyc", "project", "project_compiler.py"),
               encoding="utf-8").read().splitlines()
    print("=" * 74)
    print("source under test (project_compiler.py:498-512)")
    print("=" * 74)
    for i in range(497, 513):
        print("  %4d | %s" % (i + 1, src[i].rstrip()))

    print()
    print("=" * 74)
    print("CASE A - bogus entry_point on a project that DOES contain modules")
    print("=" * 74)
    make_project(SCRATCH_A, CASE_A)
    pc, calls, r = instrumented(SCRATCH_A, entry_point="does.not.exist")
    print("  files: %s" % sorted(CASE_A))
    print("  discovered modules ......... %s" % sorted(pc._source_files))
    print("  compilation_order .......... %s" % r.compilation_order)
    print("  modules_to_compile (derived) -> 0 entries (entry not in graph deps)")
    print("  compile_module() calls ..... %d  %s" % (len(calls), calls))
    print("  result.success ............. %s" % r.success)
    print("  result.compiled_modules .... %s" % r.compiled_modules)
    print("  result.failed_modules ...... %s" % r.failed_modules)
    print("  result.errors .............. %s" % dict(r.errors))
    if r.success and not calls:
        reproduced.append("build(entry_point='does.not.exist') -> success=True with zero "
                          "modules compiled and an empty errors dict (:510)")

    # uninstrumented control: same result without any monkeypatching
    from cypyc.project.project_compiler import ProjectCompiler
    pc2 = ProjectCompiler(project_root=SCRATCH_A, output_dir=os.path.join(SCRATCH_A, "_out2"))
    r2 = pc2.build(entry_point="typo.main")
    print("  control, no instrumentation : success=%s compiled=%s errors=%s"
          % (r2.success, r2.compiled_modules, dict(r2.errors)))

    print()
    print("=" * 74)
    print("CASE B - fully cyclic project (topological_sort drops every module)")
    print("=" * 74)
    make_project(SCRATCH_B, CASE_B)
    pc3, calls3, r3 = instrumented(SCRATCH_B)
    print("  files ..................... %s" % sorted(CASE_B))
    print("  discovered modules ......... %s" % sorted(pc3._source_files))
    print("  compilation_order .......... %s   <-- empty, cyclic nodes dropped"
          % r3.compilation_order)
    print("  cycles_detected ............ %s" % r3.cycles_detected)
    print("  warnings ................... %s" % r3.warnings)
    print("  compile_module() calls ..... %d" % len(calls3))
    print("  result.success ............. %s" % r3.success)
    print("  result.errors .............. %s" % dict(r3.errors))
    if r3.success and not r3.compiled_modules and len(pc3._source_files) > 1:
        reproduced.append("cyclic project: %d modules discovered, 0 compiled, "
                          "success=True, errors empty -- the cycle is only a warning"
                          % len(pc3._source_files))

    print()
    print("=" * 74)
    print("CASE C - sanity control: a normal entry_point DOES compile")
    print("=" * 74)
    pcC = ProjectCompiler(project_root=SCRATCH_A, output_dir=os.path.join(SCRATCH_A, "_outC"))
    pcC.discover_modules()
    pcC.parse_all_modules()
    pcC.build_dependency_graph()
    order = pcC._dependency_graph.topological_sort()[0]
    sel = [m for m in order if m == "main" or m in
           pcC._dependency_graph.get_transitive_dependencies("main")]
    print("  entry_point='main' -> modules_to_compile would be %s (non-empty)" % sel)
    print("  => the emptiness in CASE A/B is the entry_point/cycle, not the harness")

    print()
    print("=" * 74)
    if reproduced:
        print("RESULT: REPRODUCED (%d confirmations)" % len(reproduced))
        for r_ in reproduced:
            print("  * " + r_)
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
