#!/usr/bin/env python3
"""Decide whether tests/test_incremental.py::TestDigestCost is a product regression or an
environment artifact.

Same face as the real judge: the module under test is loaded from tests/test_incremental.py by
path, so _large_module / parse_source / ASTDiffer are the very objects the pytest case uses.

Discriminator:
  * time.process_time() counts only on-CPU time.  wall >> cpu  =>  the process was descheduled
    (other processes stealing CPU).  wall ~= cpu but cpu inflated =>  machine throttled/busy.
  * A pure-python calibration loop (no cypyc code) is measured the same way, so "the machine is
    slower right now" can be separated from "our digest got slower".
"""
import gc
import importlib.util
import os
import sys
import time

REPO = r"E:\IDEProjects\AI\Cypy"
DRIVER = os.path.dirname(os.path.abspath(__file__))
# 默认写 after 件：meas_digest_cost.out.txt 是 BUG-13 入账时的原始证据，误跑不得覆盖它。
OUT = os.path.join(DRIVER, os.environ.get("MEAS_OUT", "meas_digest_after.out.txt"))
sys.stdout = open(OUT, "w", encoding="utf-8", newline="\n")

spec = importlib.util.spec_from_file_location(
    "ti_under_meas", os.path.join(REPO, "tests", "test_incremental.py"))
ti = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ti)

print("python:", sys.version.replace("\n", " "))
print("executable:", sys.executable)
print("cpu_count:", os.cpu_count())
print("PYTHONHASHSEED:", os.environ.get("PYTHONHASHSEED"))
print("cwd:", os.getcwd())

CAL_LOOPS = 6_000_000


def calibration():
    """Fixed pure-CPU work: integer adds + a few dict ops. Independent of cypyc."""
    c0 = time.process_time()
    w0 = time.perf_counter()
    acc = 0
    d = {}
    for i in range(CAL_LOOPS):
        acc += i * 7 % 1000
        if i % 100000 == 0:
            d[i] = acc
    ttl = sum(d.values())
    return (time.perf_counter() - w0, time.process_time() - c0, acc + ttl)


def digest_once(source):
    tree = ti.parse_source(source)
    differ = ti.ASTDiffer()
    c0 = time.process_time()
    w0 = time.perf_counter()
    for stmt in tree.body:
        differ._compute_definition_hash(stmt)
    return time.perf_counter() - w0, time.process_time() - c0, len(tree.body)


src = ti._large_module()
print("source lines:", len(src.splitlines()))
print("source md5:", __import__("hashlib").md5(src.encode("utf-8")).hexdigest())

gc.disable()
reps = []
for rep in range(3):
    cw, cc, _ = calibration()
    dw, dc, nstmt = digest_once(src)
    reps.append((dw, dc))
    print("rep%d calib wall=%.3f cpu=%.3f ratio=%.2f | digest wall=%.3f cpu=%.3f ratio=%.2f "
          "stmts=%d" % (rep, cw, cc, cw / cc, dw, dc, dw / dc, nstmt))
gc.enable()

# 裁决后的对照：同一批测量值分别套「墙钟判据」（BUG-13 的原判据）与「CPU 判据」（现判据）。
# 阈值不在这里手写，直接从 tests/test_incremental.py 的断言里反读。
import re as _re

_test_txt = open(os.path.join(REPO, "tests", "test_incremental.py"), encoding="utf-8").read()
_m = _re.search(r"assert digest_elapsed < (\d+\.\d+)", _test_txt)
if not _m:
    raise SystemExit("REFUSE: 读不到 digest 阈值断言，判据面已变")
THRESH = float(_m.group(1))
print("threshold read from test: %.1f" % THRESH)
print("judge wall<%.1f : %s (worst wall=%.3f)" % (
    THRESH, "PASS" if max(w for w, _c in reps) < THRESH else "FLIP-RED", max(w for w, _c in reps)))
print("judge cpu<%.1f : %s (worst cpu =%.3f)" % (
    THRESH, "PASS" if max(c for _w, c in reps) < THRESH else "FLIP-RED", max(c for _w, c in reps)))
print("gc counts:", gc.get_count())
sys.stdout.flush()
sys.stdout.close()
print("written", OUT, file=sys.stderr)
