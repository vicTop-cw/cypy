#!/usr/bin/env python3
"""Mechanism proof for the tests/test_incremental.py::TestDigestCost terminal red.

Question: is digest cost a property of cypyc's code, or of the heap the *process* happens to
have accumulated (unrelated earlier tests -> CPython cyclic-GC gen-2 scans inside the timed
loop)?

Same measurement face as the pytest case (module loaded by path from tests/test_incremental.py),
only the surrounding heap is manipulated:
  step A  clean process          -> reference cost
  step B  + 1.5M cyclic objects  -> cost is expected to inflate like the pytest failure
  step C  gc.freeze() those same objects (live set unchanged, allocation count unchanged)
          -> if the cost falls back, the inflation was GC scanning, not extra work in cypyc
"""
import gc
import importlib.util
import os
import sys
import time

REPO = r"E:\IDEProjects\AI\Cypy"
DRIVER = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(DRIVER, "meas_digest_gc.out.txt")
sys.stdout = open(OUT, "w", encoding="utf-8", newline="\n")

spec = importlib.util.spec_from_file_location(
    "ti_under_gc", os.path.join(REPO, "tests", "test_incremental.py"))
ti = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ti)

SOURCE = ti._large_module()
NOISE = 1_500_000
keeper = []


def digest_wall():
    tree = ti.parse_source(SOURCE)
    differ = ti.ASTDiffer()
    gc.collect()
    gc.collect()
    w0 = time.perf_counter()
    c0 = time.process_time()
    for stmt in tree.body:
        differ._compute_definition_hash(stmt)
    return time.perf_counter() - w0, time.process_time() - c0


def report(label):
    w, c = digest_wall()
    st = gc.get_stats()
    gen2 = st[2]["collections"] if len(st) > 2 else -1
    print("%-28s wall=%.3f cpu=%.3f ratio=%.2f alloc_blocks=%d gen2_collections=%d"
          % (label, w, c, w / c, __import__("sys").getallocatedblocks(), gen2))
    sys.stdout.flush()


report("A clean process")


class Node:
    __slots__ = ("nxt", "tag")

    def __init__(self, nxt):
        self.nxt = nxt
        self.tag = "x"


for i in range(NOISE):
    a = Node(None)
    b = Node(a)
    a.nxt = b
    keeper.append(a)

report("B +%d cyclic objects" % NOISE)
gc.freeze()
report("C same objects, gc.freeze")
del keeper[:]
gc.unfreeze()
gc.collect()
report("D noise released")

print("threshold in the pytest case: wall < 2.0")
print("observed under pytest, whole file (38 tests): wall=3.385 -> FAILED")
print("observed under pytest, this case alone: wall<2.0 -> PASSED")
sys.stdout.flush()
sys.stdout.close()
