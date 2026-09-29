#!/usr/bin/env python3
"""OMEGA-verified repro unit T0r61.4.1 / defect 06.

Target: cypyc/project/project_compiler.py:217
        if mod_name == import_path or mod_name.endswith('.' + import_path):

Claim: for an absolute import the resolver accepts ANY discovered module whose
dotted name merely ENDS WITH the requested name, and it returns the first such
hit in `self._source_files` iteration order (i.e. os.walk order).  A request
for `pkg.mod` therefore binds to `vendor.pkg.mod` (deeper `other/pkg/mod`), and
a request for an ambiguous `mod` silently resolves to whichever candidate the
filesystem walk happened to yield first.  The wrong module's types are then
pulled into the dependency graph (edge + TypeRegistry.add_import at :161-162)
and the intended import error is never reported.

Exit codes: 1 = defect REPRODUCED, 0 = not reproduced, 3 = harness error.
Creates throwaway projects only under Find_BUG/audit_2026q3/scratch/.
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir))
sys.path.insert(0, REPO)
SCRATCH_A = os.path.join(HERE, "scratch", "proj06a")
SCRATCH_B = os.path.join(HERE, "scratch", "proj06b")

CASE_A = {  # `pkg.mod` does NOT exist; only a vendored copy one level deeper
    "vendor/pkg/mod.cypy": "def vendored() -> int:\n    return 42\n",
    "app/consumer.cypy": "from pkg.mod import vendored\n\ndef use() -> int:\n    return vendored()\n",
}

CASE_B = {  # `mod` is ambiguous: two sibling packages both provide it
    "left/mod.cypy": "def only_in_left() -> int:\n    return 1\n",
    "right/mod.cypy": "def only_in_right() -> int:\n    return 2\n",
    "consumer.cypy": "from mod import only_in_left\n\ndef use() -> int:\n    return only_in_left()\n",
}


def build_project(root, files):
    if os.path.isdir(root):
        shutil.rmtree(root, ignore_errors=True)
    for rel, body in files.items():
        p = os.path.join(root, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(body)
    from cypyc.project.project_compiler import ProjectCompiler
    pc = ProjectCompiler(project_root=root, output_dir=os.path.join(root, "_out"))
    disc = pc.discover_modules()
    pc.parse_all_modules()
    return pc, disc


def main():
    reproduced = []

    print("=" * 74)
    print("CASE A - request for `pkg.mod` binds to the deeper `vendor.pkg.mod`")
    print("=" * 74)
    pc, disc = build_project(SCRATCH_A, CASE_A)
    print("  files on disk:")
    for rel in sorted(CASE_A):
        print("     %s" % rel)
    print("  discovered module names: %s" % sorted(disc))
    print("  'pkg.mod' present as a real module? %s" % ("pkg.mod" in disc))
    got = pc._resolve_import_target("pkg.mod", "app.consumer")
    print("  _resolve_import_target('pkg.mod', 'app.consumer') -> %r" % got)
    print("  why: 'vendor.pkg.mod'.endswith('.pkg.mod') == %s"
          % "vendor.pkg.mod".endswith(".pkg.mod"))
    g = pc.build_dependency_graph()
    print("  dependency edge recorded for app.consumer -> %s" % sorted(g.get_dependencies("app.consumer")))
    reg = pc._type_registry
    try:
        mod_info = getattr(reg, "_modules", {}).get("app.consumer")
        reg_dump = getattr(mod_info, "imports", mod_info)
    except Exception as exc:                                   # noqa: BLE001
        reg_dump = "<unavailable: %s>" % exc
    print("  TypeRegistry entry for app.consumer: %s" % (reg_dump,))
    if got == "vendor.pkg.mod":
        reproduced.append("absolute import 'pkg.mod' silently resolved to "
                          "'vendor.pkg.mod' (a deeper unrelated package) and a dependency "
                          "edge was created to it")

    print()
    print("=" * 74)
    print("CASE B - ambiguous `mod`: resolution depends on os.walk order")
    print("=" * 74)
    pc2, disc2 = build_project(SCRATCH_B, CASE_B)
    print("  discovered module names (walk order): %s" % list(disc2))
    cands = [m for m in disc2 if m == "mod" or m.endswith(".mod")]
    print("  candidates matching endswith('.mod'): %s" % cands)
    got2 = pc2._resolve_import_target("mod", "consumer")
    print("  _resolve_import_target('mod', 'consumer') -> %r   (returns the FIRST match,"
          " no ambiguity error)" % got2)
    got2b = pc2._resolve_import_target("right.mod", "consumer")
    print("  a request for the *sibling* 'right.mod' -> %r" % got2b)
    if got2 and got2 != "mod" and len(cands) > 1:
        reproduced.append("ambiguous import 'mod' resolved to %r purely by dict/walk "
                          "order; both left.mod and right.mod satisfy endswith('.mod')"
                          % got2)

    print()
    print("=" * 74)
    print("source under test (cypyc/project/project_compiler.py:214-218)")
    print("=" * 74)
    src = open(os.path.join(REPO, "cypyc", "project", "project_compiler.py"),
               encoding="utf-8").read().splitlines()
    for i in range(213, 218):
        print("  %4d | %s" % (i + 1, src[i].rstrip()))
    print("  (the `for mod_name in self._source_files` loop has no depth limit,")
    print("   no longest/shortest-match preference, and no ambiguity diagnostic)")

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
