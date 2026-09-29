#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R2 unit-1 probe  T0r258.3.1 / dispatch 02 -- runtime arm selection by argument type.

Clause: P-2 (dispatch key = runtime type of the arguments) and the acceptance shape the
task pack asks for ("运行时按哪些参数类型选择").  **DEFERRED cluster** -- this probe is a
red line for the next round, not a claim that anything works.

The corpus below is written so that unit 2 can lift it into the golden set unchanged:
the expected stdout is 'Circle/Square/Circle' (most specific arm per runtime type).

Exit: 1 = not implemented, 0 = implemented, 2 = the judge itself broke.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _feat_typesys_lib as F                                   # noqa: E402

PROGRAM = (
    "class Shape:\n    pass\n\n"
    "class Circle(Shape):\n    r: float\n\n"
    "class Square(Shape):\n    a: float\n\n"
    "dispatch describe(s: Shape) -> str:\n"
    "    arm Circle:\n        return 'Circle'\n"
    "    arm Square:\n        return 'Square'\n"
    "    arm Shape:\n        return 'Shape'\n"
    "\n"
    "print(describe(Circle()))\n"
    "print(describe(Square()))\n"
    "print(describe(Shape()))\n"
)
report = F.Report("PROBE feat_dispatch_02", "SYNTAX/33 P-2 (DEFERRED cluster)")


def body(rep):
    rep.banner("dispatch 02: the runtime type of the argument picks the arm")

    res = F.transpile("dispatch_sel", PROGRAM)
    rep.raw("python -m cypyc transpile <dispatch selection program>",
            F.error_summary(res))
    out, err, rc, artifact = F.cli("dispatch_sel_run", PROGRAM, command="run")
    rep.raw("python -m cypyc run <same program> (tail)",
            "\n".join((out + "\n" + err).strip().splitlines()[-5:]))
    rep.note("CLI returncode=%s (always 0: cypyc/__main__.py:4) -- so the verdict must be "
             "read from stdout text, never from the exit code" % rc)

    rep.expect("P-2 the dispatch program transpiles without diagnostics",
               res["success"], F.error_summary(res))
    rep.expect("P-2 codegen emits a dispatch table/helper",
               "_cypy_dispatch" in res["code"], "artifact bytes=%d" % len(res["code"]))
    rep.expect("P-2 running it prints exactly Circle/Square/Shape",
               [ln for ln in out.splitlines() if ln.strip() in
                ("Circle", "Square", "Shape")] == ["Circle", "Square", "Shape"],
               "stdout tail=%r" % out.strip().splitlines()[-4:])

    # multi-key selection: the second argument must not be able to steer the arm
    multi = (
        "class A:\n    pass\n\nclass B(A):\n    pass\n\n"
        "dispatch f(x: A, y: A) -> str:\n"
        "    arm B, B:\n        return 'BB'\n"
        "    arm A, A:\n        return 'AA'\n"
        "\n"
        "print(f(B(), B()))\nprint(f(B(), A()))\n"
    )
    mres = F.transpile("dispatch_multi", multi)
    rep.raw("two-key dispatch (arm B, B / arm A, A)", F.error_summary(mres))
    rep.expect("P-2 multi-key dispatch either works ('BB'/'AA') or is refused by name "
               "(D-8 pending -- today it cannot even parse)",
               mres["success"] or any("multi" in e.lower() or "not supported" in e.lower()
                                      for e in mres["errors"]),
               F.error_summary(mres))


if __name__ == "__main__":
    sys.exit(F.run_probe(report, body))
