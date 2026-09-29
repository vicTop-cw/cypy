#!/usr/bin/env python3
"""OMEGA-verified repro unit T0r61.4.1 / defect 05.

Target: cypyc/project/project_compiler.py:210
        base_parts = current_parts[:len(current_parts) - dot_count + 1]

Claim: the resolution base for a relative import is off by one level.  CPython
semantics for `from .x import y` in module `a.b.c` (a leaf module, not a
package) take the base to be the containing package `a.b`; the formula keeps
`a.b.c` itself, so `from .sib import f` becomes `a.b.c.sib` and resolves to
nothing.  Every relative import from a non-package module is therefore silently
dropped from the dependency graph (and from TypeRegistry.add_import at :162),
which means no cross-module type information and no ordering constraint.
The `+1` is only correct when current_module names a *package* - and
_path_to_module_name (:100-101) has already erased that distinction.

Exit codes: 1 = defect REPRODUCED, 0 = not reproduced, 3 = harness error.
Creates throwaway projects only under Find_BUG/audit_2026q3/scratch/.
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir))
sys.path.insert(0, REPO)
SCRATCH = os.path.join(HERE, "scratch", "proj05")

from cypyc.project.project_compiler import ProjectCompiler  # noqa: E402

FILES = {
    # a leaf module inside a package that uses a level-1 relative import
    "pkg/sub/leaf.cypy": "from .sib import leaf_fn\n\ndef caller() -> int:\n    return leaf_fn()\n",
    "pkg/sub/sib.cypy": "def leaf_fn() -> int:\n    return 1\n",
    # control: the *same* level-1 import written in a package __init__
    "pk2/__init__.cypy": "from .sib2 import leaf2\n\ndef caller2() -> int:\n    return leaf2()\n",
    "pk2/sib2.cypy": "def leaf2() -> int:\n    return 2\n",
    # control: a level-2 relative import from a leaf module
    "pk3/a/b/deep.cypy": "from ..top import top_fn\n\ndef use() -> int:\n    return top_fn()\n",
    "pk3/a/top.cypy": "def top_fn() -> int:\n    return 3\n",
    "pk3/__init__.cypy": "def z() -> int:\n    return 0\n",
}


def cpython_base(current_module, dot_count):
    """What CPython's import machinery uses as the level-`dot_count` base."""
    parts = current_module.split(".")
    # for a LEAF module the level-1 base is its parent package
    keep = len(parts) - dot_count
    return ".".join(parts[:keep]) if keep > 0 else ""


def main():
    if os.path.isdir(SCRATCH):
        shutil.rmtree(SCRATCH, ignore_errors=True)
    for rel, body in FILES.items():
        p = os.path.join(SCRATCH, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(body)

    pc = ProjectCompiler(project_root=SCRATCH, output_dir=os.path.join(SCRATCH, "_out"))
    disc = pc.discover_modules()
    pc.parse_all_modules()

    print("=" * 74)
    print("discovered modules (project %s)" % SCRATCH)
    for k in sorted(disc):
        print("   %-16s <- %s" % (k, os.path.relpath(disc[k], SCRATCH).replace(os.sep, "/")))

    cases = [
        ("pkg.sub.leaf", ".sib", 1, "pkg.sub.sib"),      # leaf module, level 1
        ("pk2", ".sib2", 1, "pk2.sib2"),                 # package __init__, level 1
        ("pk3.a.b.deep", "..top", 2, "pk3.a.top"),       # leaf module, level 2
        ("pkg.sub.leaf", "..sib", 2, "pkg.sib"),         # leaf module, level 2 (absent)
    ]
    reproduced = []
    print()
    print("=" * 74)
    print("relative-import resolution (project_compiler._resolve_import_target)")
    print("=" * 74)
    print("  %-15s %-7s | %-22s | %-22s | %s"
          % ("current module", "import", "code :210 base -> result", "CPython expects", "verdict"))
    for cur, imp, dots, expected in cases:
        parts = cur.split(".")
        buggy_base_parts = parts[:len(parts) - dots + 1]
        buggy_target = ".".join(buggy_base_parts + imp.lstrip(".").split(".")[:-1]
                                + [imp.lstrip(".").split(".")[-1]])
        got = pc._resolve_import_target(imp, cur)
        want_here = "resolves" if got == expected else ("None (dropped)" if got is None
                                                        else "WRONG module %s" % got)
        verdict = "ok" if got == expected else "*** MISMATCH ***"
        print("  %-15s %-7s | %-22s | %-22s | %s %s"
              % (cur, imp, ".".join(buggy_base_parts), expected, want_here, verdict))
        if got != expected:
            reproduced.append("%s: %r resolved to %r, expected %r (formula base %r is "
                              "one level too deep -- :210 uses len-dot+1)"
                              % (cur, imp, got, expected, ".".join(buggy_base_parts)))

    print()
    print("=" * 74)
    print("consequence for the dependency graph / type registry")
    print("=" * 74)
    g = pc.build_dependency_graph()
    for cur in ("pkg.sub.leaf", "pk2", "pk3.a.b.deep"):
        deps = sorted(g.get_dependencies(cur))
        print("   %-15s -> dependencies %s" % (cur, deps))
    if "pkg.sub.leaf" in g._nodes and not g.get_dependencies("pkg.sub.leaf"):
        reproduced.append("build_dependency_graph() records NO edge for "
                          "pkg.sub.leaf -> pkg.sub.sib although leaf.cypy imports sib.cypy;"
                          " so no ordering constraint and no cross-module types")

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
