#!/usr/bin/env python3
"""Repro-gate runner for the 2026-Q3 audit round.

    python Find_BUG/audit_2026q3/repro_gate.py repro_frontend_ reproduce
    python Find_BUG/audit_2026q3/repro_gate.py repro_frontend_ fixed
    python Find_BUG/audit_2026q3/repro_gate.py repro_frontend_ scripts

mode=reproduce: every matching script must exit 1 (the defect still reproduces).
mode=fixed:     every matching script must exit 0 (the defect is gone).
mode=scripts:   no expectation on the direction — every matching script must run to a
                decisive verdict (exit 0 = defect fixed, exit 1 = defect reproduces);
                a crash or any other exit code means the evidence is not usable.
                This is the acceptance criterion of the reproduction units themselves,
                valid at any point in the timeline.
Exit code 0 means the gate agrees with the requested mode, so FIST's `run_check`
records it as `passed`. Anything else (crash, wrong exit code) is reported.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TIMEOUT = 600
MODES = ("reproduce", "fixed", "scripts")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    args = [a for a in sys.argv[1:]]
    mode = next((m for m in MODES if m in args), None)
    prefixes = [a for a in args if a not in MODES]
    if mode is None or not prefixes:
        print(f"[gate] usage: repro_gate.py <prefix>... [{'|'.join(MODES)}]")
        return 2
    expected = 1 if mode == "reproduce" else 0

    # The runner matches its own `repro_` prefix: without this exclusion
    # `repro_gate.py repro_ scripts` feeds itself, gets exit 2 (usage) and reports
    # a bogus "NO VERDICT" mismatch. Measured 2026-09-26: 32 matched / 1 failing.
    me = Path(__file__).resolve()
    scripts = sorted({p for pre in prefixes for p in HERE.glob(f"{pre}*.py")
                      if p.resolve() != me})
    if not scripts:
        print(f"[gate] no scripts matched {prefixes}")
        return 1

    bad = []
    for script in scripts:
        try:
            code = subprocess.run([sys.executable, str(script)], capture_output=True,
                                  text=True, encoding="utf-8", errors="replace",
                                  timeout=TIMEOUT).returncode
        except subprocess.TimeoutExpired:
            code = -99
        if mode == "scripts":
            ok = code in (0, 1)
            state = {0: "fixed", 1: "reproduces"}.get(code, "NO VERDICT")
            print(f"[gate] {script.name}: exit={code} -> {state}")
        else:
            ok = code == expected
            print(f"[gate] {script.name}: exit={code} want={expected} "
                  f"{'OK' if ok else 'MISMATCH'}")
        if not ok:
            bad.append(script.name)

    print(f"[gate] mode={mode} scripts={len(scripts)} mismatches={len(bad)}")
    if bad:
        print("[gate] FAILING: " + ", ".join(bad))
    return 1 if bad else 0




if __name__ == "__main__":
    sys.exit(main())
