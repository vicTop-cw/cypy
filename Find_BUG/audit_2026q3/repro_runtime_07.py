"""OMEGA repro T0r61.3.1 / defect 7
cypy_bridge/memory.py:70-93 -- aligned_alloc(alignment, size)

Claims under test:
  A. :84  the power-of-two test `(alignment & (alignment - 1)) != 0` accepts alignment == 0
      (0 & -1 == 0), so the documented contract "alignment must be a power of 2" is violated
      and :88 then allocates `size + 0 - 1` == size - 1 bytes (one byte SHORT of the request)
      with no slack to align into.
  B. :92-93 the function returns the raw malloc() result ("简化实现，实际应该计算对齐地址"),
      so the pointer is not aligned to anything larger than malloc's own guarantee.
  C. the audit also claimed negative alignments pass. Measured in section 3: they do NOT
     (a negative power of two always has `a & (a-1) != 0`), so that half of the wording is
     wrong and is reported as NOT-REPRODUCED.

Exit: 1 = A and/or B reproduced, 0 = fixed, 2 = harness problem.
"""

import ctypes
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from cypy_bridge.core import MemoryError as BridgeMemoryError  # noqa: E402
from cypy_bridge.memory import aligned_alloc, free, malloc  # noqa: E402

failures = []
notes = []


def check(cond, label, detail):
    print("  %s %s" % ("PASS" if cond else "FAIL", label))
    if not cond:
        print("       %s" % detail)
        failures.append(label)


def addr(p):
    """malloc()/aligned_alloc() return a plain int (restype c_void_p), not a c_void_p."""
    return p if isinstance(p, int) else (p.value or 0)


print("=== 0. what malloc() actually returns ===")
m = malloc(16)
print("  malloc(16) -> %r (type %s)   annotation says -> ctypes.c_void_p" % (m, type(m).__name__))
free(m)

print("=== 1. alignment == 0 must be rejected (memory.py:84) ===")
accepted = None
try:
    p = aligned_alloc(0, 64)
    accepted = p
    print("  aligned_alloc(0, 64) -> 0x%x  NO error raised" % addr(p))
    print("     underlying call was malloc(64 + 0 - 1) = malloc(63): %d bytes for a 64-byte request"
          % 63)
except BridgeMemoryError as e:
    print("  aligned_alloc(0, 64) -> raises MemoryError: %s" % e)
except Exception as e:  # noqa: BLE001
    print("  aligned_alloc(0, 64) -> %s: %s" % (type(e).__name__, e))
check(accepted is None, "alignment=0 rejected",
      "0 passes the `(a & (a-1)) != 0` test, so a 64-byte request is served by malloc(63) "
      "and the caller can overflow the block by one byte")
if accepted is not None:
    free(accepted)

try:
    p1 = aligned_alloc(0, 1)
    print("  aligned_alloc(0, 1) -> 0x%x" % addr(p1))
    free(p1)
except Exception as e:  # noqa: BLE001
    print("  aligned_alloc(0, 1) -> %s: %s   (size + 0 - 1 == 0)" % (type(e).__name__, e))

print("=== 2. is the returned pointer actually aligned? (memory.py:92-93) ===")
worst = 0
for want in (16, 32, 64, 128, 256, 1024):
    residues = set()
    for _ in range(64):
        p = aligned_alloc(want, want * 2)
        residues.add(addr(p) % want)
        free(p)
    ok = residues == {0}
    worst = max(worst, max(residues))
    print("  alignment=%4d -> addr%%%d in %-14s %s"
          % (want, want, sorted(residues), "ALIGNED" if ok else "*** NOT ALIGNED ***"))
    check(ok, "alignment=%d honoured" % want,
          "returned addresses are consistently off by %s byte(s) -- :93 returns the raw "
          "malloc() pointer without rounding up" % (sorted(residues)[0] if residues else "?",))
print("  worst observed misalignment: %d bytes (malloc's own guarantee is 16 on this platform)"
      % worst)

print("=== 3. audit wording check: negative alignments ===")
for bad in (-16, -1, -4096):
    try:
        p = aligned_alloc(bad, 64)
        print("  aligned_alloc(%5d, 64) -> ACCEPTED 0x%x" % (bad, addr(p)))
        check(False, "negative alignment %d rejected" % bad, "accepted")
        free(p)
    except BridgeMemoryError as e:
        print("  aligned_alloc(%5d, 64) -> MemoryError: %s" % (bad, e))
notes.append("audit claim 'alignment=0 (and negative) passes validation' is only half true: "
             "negative values are rejected by :84; only 0 slips through.")

print("=== 4. non power-of-two control (must be rejected) ===")
for bad in (3, 12, 100):
    try:
        p = aligned_alloc(bad, 64)
        print("  aligned_alloc(%3d, 64) -> ACCEPTED" % bad)
        check(False, "alignment=%d rejected" % bad, "accepted")
        free(p)
    except BridgeMemoryError as e:
        print("  aligned_alloc(%3d, 64) -> MemoryError (correct)" % bad)

print("=== 5. guard: whatever the fix does, the returned pointer must stay free()able ===")
try:
    p = aligned_alloc(64, 128)
    free(p)          # single free only -- a double free would abort the process
    print("  free(aligned_alloc(64,128)) accepted by the CRT wrapper")
except Exception as e:  # noqa: BLE001
    print("  free() on the aligned pointer raised %s: %s" % (type(e).__name__, e))

print()
if notes:
    for n in notes:
        print("NOTE: %s" % n)
if failures:
    print("RESULT: REPRODUCED (%d checks failed): %s" % (len(failures), "; ".join(failures)))
    sys.exit(1)
print("RESULT: NOT-REPRODUCED (alignment validated and honoured)")
sys.exit(0)
