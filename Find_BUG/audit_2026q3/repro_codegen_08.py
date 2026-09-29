#!/usr/bin/env python3
"""OMEGA-verified repro unit T0r61.4.1 / defect 08.

Target: cypyc/project/project_compiler.py:85  (discovered[module_name] = file_path)
        with :100-103 (_path_to_module_name erases the __init__ distinction)

Claim: `foo.cypy` and `foo/__init__.cypy` both map to the dotted module name
`foo`.  :85 writes into a plain dict with no existence check, so the module
discovered LAST by os.walk silently REPLACES the earlier one: one of the two
source files disappears from the project without a warning, an error, or a
failed build - and `build()` reports success having "compiled" a single module
whose identity depends on directory traversal order.  The same collision also
swallows `foo.cypy` vs `foo/bar.cypy` siblings when :102-103 rewrites a bare
`__init__` to the directory's basename.

Exit codes: 1 = defect REPRODUCED, 0 = not reproduced, 3 = harness error.
Creates throwaway projects only under Find_BUG/audit_2026q3/scratch/.
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir))
sys.path.insert(0, REPO)
SCRATCH = os.path.join(HERE, "scratch", "proj08")

FILES = {
    "foo.cypy": "def only_in_module_file() -> int:\n    return 1\n",
    "foo/__init__.cypy": "def only_in_package_init() -> int:\n    return 2\n",
    "foo/bar.cypy": "def bar_fn() -> int:\n    return 3\n",
}


def main():
    from cypyc.project.project_compiler import ProjectCompiler

    if os.path.isdir(SCRATCH):
        shutil.rmtree(SCRATCH, ignore_errors=True)
    for rel, body in FILES.items():
        p = os.path.join(SCRATCH, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(body)

    reproduced = []
    print("=" * 74)
    print("project on disk (%s)" % SCRATCH)
    print("=" * 74)
    for rel in sorted(FILES):
        print("   %s" % rel)

    pc = ProjectCompiler(project_root=SCRATCH, output_dir=os.path.join(SCRATCH, "_out"))

    print()
    print("=" * 74)
    print("PART 1 - _path_to_module_name maps two different files onto one name")
    print("=" * 74)
    base = os.path.abspath(SCRATCH)
    for rel in sorted(FILES):
        fp = os.path.join(base, rel.replace("/", os.sep))
        name = pc._path_to_module_name(fp, base)
        print("   %-20s -> %r" % (rel, name))
    n1 = pc._path_to_module_name(os.path.join(base, "foo.cypy"), base)
    n2 = pc._path_to_module_name(os.path.join(base, "foo", "__init__.cypy"), base)
    print("   collision: %r == %r -> %s" % (n1, n2, n1 == n2))

    print()
    print("=" * 74)
    print("PART 2 - discover_modules(): 3 files in, silent last-write-wins at :85")
    print("=" * 74)
    disc = pc.discover_modules()
    print("   .cypy files on disk ........ %d" % len(FILES))
    print("   entries in `discovered` .... %d" % len(disc))
    for k in sorted(disc):
        print("      %-10s -> %s" % (k, os.path.relpath(disc[k], SCRATCH).replace(os.sep, "/")))
    present = {os.path.relpath(v, SCRATCH).replace(os.sep, "/") for v in disc.values()}
    dropped = sorted(set(FILES) - present)
    print("   files silently dropped ..... %s" % dropped)
    print("   warnings / errors raised ... none (the API has no channel for it;"
          " the dict assignment at :85 just overwrites)")
    if len(disc) < len(FILES) and dropped:
        reproduced.append("%s dropped from module discovery: %r and %r both map to %r, "
                          "the later os.walk hit overwrote the earlier one"
                          % (dropped, "foo.cypy", "foo/__init__.cypy", n1))

    print()
    print("=" * 74)
    print("PART 3 - the whole build silently reports success on the collided name")
    print("=" * 74)
    pc2 = ProjectCompiler(project_root=SCRATCH, output_dir=os.path.join(SCRATCH, "_out3"))
    called = []

    def stub_compile(module_name):
        # stubbed only to keep the run fast: the audited behaviour here is WHICH
        # modules reach the backend, not the C/Cython toolchain itself.
        called.append(module_name)
        return True, os.path.join(SCRATCH, "_out3", module_name + ".pyd"), []

    pc2.compile_module = stub_compile
    res = pc2.build()
    print("   modules compiled ........... %s" % res.compiled_modules)
    print("   compile_module() calls ..... %d %s" % (len(called), called))
    print("   success .................... %s" % res.success)
    print("   warnings ................... %s" % res.warnings)
    print("   errors ..................... %s" % dict(res.errors))
    print("   -> `only_in_module_file` from foo.cypy is now invisible to the whole")
    print("      project: no type exports, no dependency edge, no diagnostic")
    if res.success and len(res.compiled_modules) < len(FILES):
        reproduced.append("build() returns success=%s after compiling %d of %d .cypy files"
                          % (res.success, len(res.compiled_modules), len(FILES)))

    print()
    print("=" * 74)
    print("PART 4 - order dependence of the winner (same generator, reversed walk)")
    print("=" * 74)
    alt = os.path.join(SCRATCH + "_alt")
    if os.path.isdir(alt):
        shutil.rmtree(alt, ignore_errors=True)
    # only the colliding pair, with the package dir listed BEFORE the module file
    os.makedirs(os.path.join(alt, "zzz_pkg"), exist_ok=True)
    with open(os.path.join(alt, "zzz_pkg", "__init__.cypy"), "w", encoding="utf-8") as f:
        f.write("def pkg_only() -> int:\n    return 9\n")
    with open(os.path.join(alt, "zzz_pkg.cypy"), "w", encoding="utf-8") as f:
        f.write("def module_only() -> int:\n    return 8\n")
    pc3 = ProjectCompiler(project_root=alt, output_dir=os.path.join(alt, "_out"))
    d3 = pc3.discover_modules()
    print("   files: zzz_pkg.cypy + zzz_pkg/__init__.cypy")
    print("   discovered -> %s" % {k: os.path.relpath(v, alt).replace(os.sep, "/")
                                   for k, v in d3.items()})
    print("   the surviving entry is whichever os.walk yielded last; nothing in")
    print("   project_compiler.py makes the choice deterministic or visible")

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
