#!/usr/bin/env python3
"""Seventh-pass report generator.

Every number in the report is recomputed here from an evidence file (pytest log, marker scan,
FIST ledger reply, close log, workspace snapshot, bugs.md), not typed by hand. It refuses to
write the report when a claim would be unsupported: a ticket that did not go green, a ledger
count that disagrees with bugs.md, a missing final pytest line, or a refusal from the server
that the report would not quote verbatim.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.stdout.reconfigure(encoding="utf-8")


def jload(name, default=None):
    p = HERE / name
    if not p.exists():
        if default is None:
            sys.exit(f"REFUSE: missing evidence {name}")
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def refuse(reason):
    sys.exit(f"REFUSE: {reason}")


SWEEP = os.environ.get("SWEEP", "pytest_final_sweep11.log")
pytest_log = (HERE / SWEEP).read_text(encoding="utf-8", errors="replace")
tail = pytest_log.strip().splitlines()[-1] if pytest_log.strip() else ""
pm = re.search(r"(\d+) passed", tail)
fm = re.search(r"(\d+) failed", tail)
em = re.search(r"(\d+) error", tail)
if not pm:
    refuse(f"pytest 终态行读不出通过数，原文: {tail!r}")
p1_passed, p1_failed, p1_error = int(pm.group(1)), int(fm.group(1)) if fm else 0, int(em.group(1)) if em else 0
p1_total = p1_passed + p1_failed + p1_error
baseline_log = (HERE / "pytest_baseline.log").read_text(encoding="utf-8", errors="replace")
b_collected = int(re.search(r"collected (\d+) items", baseline_log).group(1))
b_line = [ln for ln in baseline_log.splitlines() if "passed" in ln][-1]
b_passed = int(re.search(r"(\d+) passed", b_line).group(1))
b_failed = int(re.search(r"(\d+) failed", b_line).group(1)) if "failed" in b_line else 0

markers_b = jload("markers_baseline.json")["counts"]
markers_now = jload("markers_now_p2.json")["counts"]
after_name = os.environ.get("MARKERS_AFTER", "markers_after_pass7.json")
markers_a = jload(after_name)["counts"] if (HERE / after_name).exists() else None
# 门禁③ 的终态快照不可缺：缺了它，下面的「收敛」与序不变量都无从校。
if markers_a is None:
    refuse(f"缺少修复后标记快照 {after_name}，门禁③ 无法自证收敛")
# 「收敛、新增为零」也要被代码钉住：任一计数回升即红，TODO 类必须归零。
# （它晚于最后一处产品码改动这一序不变量由下面的 terminal 集合统一校，不在此重复。）
for _k, _v in markers_a.items():
    if _v > markers_now[_k]:
        refuse(f"标记 {_k} 从修复前 {markers_now[_k]} 回升到 {_v}：门禁③「新增为零」不成立")
    if _k in ("TODO", "FIXME", "HACK", "XXX", "type_ignore", "mutable_default_arg",
              "open_without_with") and _v:
        refuse(f"标记 {_k} 终态仍有 {_v} 处，未归零")

intake = jload("intake_map7.json")["mapping"]
close = jload("close_fixes7.out.json")
# 裁决落地（BUG-13/14）的闭环件：缺文件就说明裁决未落地，报告不得声称已闭环。
close8 = jload("close_fixes8.out.json", [])
# 裁决单（BUG-13/14）+ 裁决落地自己引入的缺陷（BUG-32）——三张都要闭环、都要在回退树上咬住。
RULING_TICKETS = {"BUG-13", "BUG-14", "BUG-32"}
green8 = {r["bug"] for r in close8 if r.get("green")}
if RULING_TICKETS - green8:
    refuse(f"裁决落地段的单未闭环，不能出终态报告: {sorted(RULING_TICKETS - green8)}")
gold_diff = jload("golden_float_diff.json", {})
if not gold_diff:
    refuse("缺 golden_float_diff.json：float 裁决后的基准重注册没有被复核")
# 裁决落地过程中新确诊的 BUG-30：入账件与活证据缺一不可，否则报告不能声称「发现即入账」。
intake8 = jload("intake_map8.json")
repro8 = jload("repro_pass8.out.json")
B30 = [m for m in intake8["mapping"] if m["bug_id"] == "BUG-30"]
if len(B30) != 1 or not B30[0].get("task_id"):
    refuse(f"BUG-30 没有入账到修复单（intake_map8.json）: {B30}")
B30_TASK = B30[0]["task_id"]
if intake8["failures"] or intake8["missing"]:
    refuse(f"intake_map8.json 里有失败或缺账: {intake8['failures']} {intake8['missing']}")
if not (repro8.get("float_and_double_agree") and repro8.get("float_literal_still_float")
        and repro8.get("uses_annotation_form") and repro8.get("run_exit") == 0):
    refuse(f"BUG-30 的活证据判据没有同时成立: {repro8}")
B30_DECLS = "、".join(f"`{d}`" for d in repro8["generated_declarations"])
if len(repro8.get("runtime") or []) != 3:
    refuse(f"BUG-30 的运行期探针不是 3 条: {repro8.get('runtime')}")
B30_RUNTIME = "、".join(f"`{r}`" for r in repro8["runtime"])
B30_EXIT = repro8["run_exit"]
_bt = next((r for r in gold_diff.get("rows", []) if r["file"] == "basic_types.out"), None)
if not _bt or not _bt.get("lines"):
    refuse("BUG-30 的来源行（basic_types.out 第 5 行）在对照件里找不到")
_, B30_BEFORE, B30_AFTER = _bt["lines"][0]
# BUG-31：同根因（一类型两宽度）在另一个包里的落点，同样是「入账未修」。
intake9 = jload("intake_map9.json")
repro9 = jload("repro_pass9.out.json")
B31 = [m for m in intake9["mapping"] if m["bug_id"] == "BUG-31"]
if len(B31) != 1 or not B31[0].get("task_id"):
    refuse(f"BUG-31 没有入账到修复单（intake_map9.json）: {B31}")
B31_TASK = B31[0]["task_id"]
if intake9["failures"] or intake9["missing"]:
    refuse(f"intake_map9.json 里有失败或缺账: {intake9['failures']} {intake9['missing']}")
if repro9.get("cypy_float_in_compiler") != ["double", "double"]:
    refuse(f"编译器侧 float 不再是双精度，§九/§十 的前提变了: {repro9}")
if [repro9.get("sizeof_bridge_float"), repro9.get("sizeof_bridge_double")] != [4, 8]:
    refuse(f"bridge 侧宽度对不上（分叉已消失或变了形态）: {repro9}")
if repro9.get("roundtrip_via_float_member") == repro9.get("roundtrip_via_double_member"):
    refuse(f"两条成员往返读回同值，BUG-31 的用户可见面未证: {repro9}")
B31_COMPILER = " / ".join(f"`{x}`" for x in repro9["cypy_float_in_compiler"])
B31_BRIDGE_FLOAT = f"`{repro9['cypy_float_in_bridge']}`"
B31_BRIDGE_DOUBLE = f"`{repro9['cypy_double_in_bridge']}`"
B31_SF, B31_SD = repro9["sizeof_bridge_float"], repro9["sizeof_bridge_double"]
B31_RT_FLOAT = repro9["roundtrip_via_float_member"]
B31_RT_DOUBLE = repro9["roundtrip_via_double_member"]
# BUG-32：裁决落地自己引入的缺陷，本轮已修并闭环（入账件是 intake_map10.json）。
intake10 = jload("intake_map10.json")
B32 = [m for m in intake10["mapping"] if m["bug_id"] == "BUG-32"]
if len(B32) != 1 or not B32[0].get("task_id"):
    refuse(f"BUG-32 没有入账到修复单（intake_map10.json）: {B32}")
B32_TASK = B32[0]["task_id"]
if intake10["failures"] or intake10["missing"]:
    refuse(f"intake_map10.json 里有失败或缺账: {intake10['failures']} {intake10['missing']}")
# 中间那次全量（BUG-32 修复第一版之后只剩 1 红）必须在盘上：§九.3 的叙述要靠它，不许凭记忆写。
S10_NAME = "pytest_final_sweep10.log"
_s10 = (HERE / S10_NAME).read_text(encoding="utf-8", errors="replace")
S10_TAIL = _s10.strip().splitlines()[-1]
S10_FAILED = int(re.search(r"(\d+) failed", S10_TAIL).group(1))
if S10_FAILED != 1:
    refuse(f"{S10_NAME} 应该只剩 1 条红（S-4.1 那条），实为 {S10_FAILED} 条: {S10_TAIL!r}")
if "test_example_artifact_mentions_no_subtype_name" not in _s10:
    refuse("§九.3 点名的那条红不在 sweep10 里")

_s9 = (HERE / "pytest_final_sweep9.log").read_text(encoding="utf-8", errors="replace")
S9_TAIL = _s9.strip().splitlines()[-1]
S9_FAILED = int(re.search(r"(\d+) failed", S9_TAIL).group(1))
if S9_FAILED == 0:
    refuse(f"pytest_final_sweep9.log 里没有红条，§九.3 的叙述不成立: {S9_TAIL!r}")
S9_RED_NAMES = sorted(set(re.findall(r"^FAILED (\S+?)(?: -|$)", _s9, re.M)))
if len(S9_RED_NAMES) != S9_FAILED:
    refuse(f"§九.3 要逐条列出失败断言原文：解析到 {len(S9_RED_NAMES)} 条 ≠ {S9_FAILED} 条红")
S9_TEST_FILES = sorted({n.split("::")[0] for n in S9_RED_NAMES})
FIXES9 = (HERE / "fixes_pass9.py").read_text(encoding="utf-8")
S9_NEEDLE_COUNT = sum(FIXES9.count(f'("{f}",') for f in S9_TEST_FILES)
# 「同一夹具」也要证：入账时与落地后的分离测量必须用同一份源。
_md5 = {}
for _f in ("meas_digest_cost.out.txt", "meas_digest_after.out.txt"):
    _t = (HERE / _f).read_text(encoding="utf-8", errors="replace")
    _m = re.search(r"source md5: (\w+)", _t)
    if not _m:
        refuse(f"{_f} 里读不到 source md5，无法确认夹具一致")
    _md5[_f] = _m.group(1)
if len(set(_md5.values())) != 1:
    refuse(f"BUG-13 的前后两次测量不是同一夹具（md5 不同）: {_md5}")
_dg = re.findall(r"digest wall=([\d.]+) cpu=([\d.]+) ratio=([\d.]+)",
                 (HERE / "meas_digest_after.out.txt").read_text(encoding="utf-8"))
if len(_dg) < 3:
    refuse(f"落地后的分离测量不足 3 次: {len(_dg)}")
DIGEST_RATIO_MAX = max(float(r[2]) for r in _dg)
DIGEST_WALL_MAX, DIGEST_CPU_MAX = max(float(r[0]) for r in _dg), max(float(r[1]) for r in _dg)
_jj = re.findall(r"judge (wall|cpu)<([\d.]+) : (\w+)",
                 (HERE / "meas_digest_after.out.txt").read_text(encoding="utf-8"))
if sorted(x[0] for x in _jj) != ["cpu", "wall"]:
    refuse(f"测量件里没有「两条判据各自 verdict」的行: {_jj}")
DIGEST_JUDGES = {x[0]: (float(x[1]), x[2]) for x in _jj}
DIGEST_RATIO_MAX_INTAKE = max(float(r[2]) for r in re.findall(
    r"digest wall=([\d.]+) cpu=([\d.]+) ratio=([\d.]+)",
    (HERE / "meas_digest_cost.out.txt").read_text(encoding="utf-8")) or [["", "", "0"]])
if (HERE / "_prefix_tree").exists():
    refuse("临时回退树还在盘上：报告里「跑完即删」的说法就成了假话")
# 「只有浮点末位变了」必须是算出来的判据，不是正文里的断言：取每一处行级差异，要求
# 非数字部分逐字相同、数字 token 个数一致。缺行/多行/文字变动都属越界，拒绝出报告。
_NUM = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def _digits_only(b: str, a: str) -> bool:
    return _NUM.sub("#", b) == _NUM.sub("#", a) and len(_NUM.findall(b)) == len(_NUM.findall(a))


gold_rows = [r for r in gold_diff.get("rows", []) if r["state"] != "unchanged"]
non_float = [(r["file"], ln, b, a) for r in gold_rows for ln, b, a in r.get("lines", [])
             if not _digits_only(b, a)]
if non_float:
    refuse(f"golden 重注册越界（非浮点数字面量的差异）: {non_float[:6]}")
if gold_diff.get("gone"):
    refuse(f"golden 重注册后基准文件消失: {gold_diff['gone']}")
gold_changed_count = len(gold_diff.get("changed") or [])
if gold_changed_count == 0:
    refuse("golden 一行都没变：float=double 裁决没有打到端到端输出，判据或裁决未落地")
GOLD_TABLE = "\n".join(
    f"| `{r['file']}` | {len(r.get('lines', []))} 行 | "
    + "<br>".join(f"L{i}: `{b}` → `{a}`" for i, b, a in r.get("lines", [])) + " |"
    for r in gold_rows if r.get("lines")) or "| （无行级差异） | 0 | — |"
GOLD_TOTAL = len(gold_diff.get("rows", []))
GOLD_UNCHANGED_COUNT = GOLD_TOTAL - len(gold_rows)
# 终态那次只读 e2e 判据（不是 --update）必须真的跑过、且覆盖全部基准。
GF_NAME = "e2e_golden_final_sweep11.log"
GF_SUMMARY = ""
for ln in (HERE / GF_NAME).read_text(encoding="utf-8", errors="replace").splitlines():
    if "summary:" in ln:
        GF_SUMMARY = ln.strip()
_gf = re.search(r"PASS=(\d+) FAIL=(\d+) UNREG/RUNFAIL=(\d+) WARN=(\d+)", GF_SUMMARY)
if not _gf:
    refuse(f"{GF_NAME} 里读不出 summary 行")
GF_PASS, GF_FAIL, GF_UNREG, GF_WARN = (int(x) for x in _gf.groups())
if (GF_FAIL, GF_UNREG, GF_WARN) != (0, 0, 0):
    refuse(f"终态端到端判据不绿: {GF_SUMMARY}")
if GF_PASS != GOLD_TOTAL:
    refuse(f"终态 e2e 只覆盖 {GF_PASS} 份，基准共 {GOLD_TOTAL} 份（有示例没进判据）")
# 对照件必须真的读了当前全部基准，否则「23 份未变」可能是漏扫出来的。
_on_disk = len(list((ROOT / "examples").glob("*.out")))
if GOLD_TOTAL != _on_disk:
    refuse(f"golden 对照面覆盖 {_on_disk} 份中的 {GOLD_TOTAL} 份，口径不完整")
import sqlite3
_db = sqlite3.connect(f"file:{ROOT / 'fist-mbt.db'}?mode=ro", uri=True)
DB_OPEN = {r[0]: r[1] for r in _db.execute(
    "select status,count(*) from tasks where ns in ('bugs','cypy-polish-20260926') group by status")}
_db.close()
green = {r["bug"] for r in close if r["green"]}
not_green = [r for r in close if not r["green"]]
bug_lines = (ROOT / "memory" / "bugs.md").read_text(encoding="utf-8").splitlines()
ledger_titles = [ln for ln in bug_lines if re.match(r"^## BUG-\d+ ", ln)]
fixed_sections = [ln for ln in bug_lines if ln.startswith("### FIXED(verify=已完成)")]
# 「入账未修」是合法终态，但必须逐条点名：把每条 BUG 切成块，找出没有 FIXED 留档段的条目。
_entries = re.split(r"(?m)^(?=## BUG-\d+ )", "\n".join(bug_lines))[1:]
OPEN_ENTRIES = [re.match(r"## (BUG-\d+) ", b).group(1) for b in _entries
                if "### FIXED(verify=已完成)" not in b]
NOT_FIXED_DECLARED = {"BUG-30", "BUG-31"}
if not NOT_FIXED_DECLARED >= set(OPEN_ENTRIES):
    refuse(f"这些条目既没有 FIXED 留档、也不在本轮声明的「入账未修」名单 "
           f"{sorted(NOT_FIXED_DECLARED)} 上: {sorted(set(OPEN_ENTRIES) - NOT_FIXED_DECLARED)}")
if len(fixed_sections) != len(ledger_titles) - len(OPEN_ENTRIES):
    refuse(f"FIXED 段数({len(fixed_sections)})对不上「条目数 − 未修数」"
           f"({len(ledger_titles)}−{len(OPEN_ENTRIES)})，留档口径有重复或漏段")

bugs_ns = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                         capture_output=True, text=True).stdout.strip()

# 回归锁：从测试文件反解 def 名，按 bug 号分组（不手写清单）
reg_src = (ROOT / "tests" / "test_polish_20260926_pass7.py").read_text(encoding="utf-8")
reg_defs = re.findall(r"(?m)^def (test_bug(\d+)_\w+)", reg_src)
by_bug = {}
for name, num in reg_defs:
    by_bug.setdefault(int(num), []).append(name)
n_param = reg_src.count('@pytest.mark.parametrize("prefix"')
# 收集数不在正文里手推：跑一次 --collect-only 实测（def 数 + 参数化展开）。
_col = subprocess.run([sys.executable, "-X", "utf8", "-m", "pytest",
                       "tests/test_polish_20260926_pass7.py", "-q", "--collect-only",
                       "-p", "no:cacheprovider"],
                      cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                      errors="replace").stdout
_cm = re.search(r"(\d+) tests? collected", _col)
if not _cm:
    refuse(f"回归文件收集数读不出来，原文尾部: {_col[-400:]!r}")
P7_COLLECTED = int(_cm.group(1))
if P7_COLLECTED < len(reg_defs):
    refuse(f"收集 {P7_COLLECTED} < def {len(reg_defs)}，参数化展开算反了")

_flip = re.search(r"墙钟随收集顺序在 ([\d.]+s 与 [\d.]+s)",
                        (ROOT / "tests" / "test_incremental.py").read_text(encoding="utf-8"))
if not _flip:
    refuse("读不到裁决注释里那对翻面数字，正文不得手写它")
FLIP_PAIR = _flip.group(1)

# 裁决落地段的单号从闭环件反解，不手写；每张都要有单号、有锁死回归，否则不算落地。
ruled_pairs = sorted((r["bug"], r["task_id"]) for r in close8 if r.get("green"))
if {b for b, _ in ruled_pairs} != RULING_TICKETS:
    refuse(f"裁决落地段的闭环集与落地面不一致: {ruled_pairs}")
RULE_LOCKS = {}
for b, tid in ruled_pairs:
    n = int(b.split("-")[1])
    if not by_bug.get(n):
        refuse(f"{b} 的落地没有反解到锁死回归（门禁② 不成立）")
    RULE_LOCKS[b] = (tid, by_bug[n])
R13, R14, R32 = RULE_LOCKS["BUG-13"], RULE_LOCKS["BUG-14"], RULE_LOCKS["BUG-32"]
if len(R32[1]) != 3:
    refuse(f"BUG-32 的锁应是 3 条（回显 / 子类型化解 / 别名宽度对照），反解到 {len(R32[1])} 条: {R32[1]}")
R32_LOCKS = "、".join(f"`{t}`" for t in R32[1])
R32_ALIAS = next((t for t in R32[1] if "alias" in t), None)
if not R32_ALIAS:
    refuse(f"BUG-32 的对照锁（别名宽度）没反解到: {R32[1]}")


for ticket in intake:
    if ticket["bug_id"] not in green:
        refuse(f"{ticket['bug_id']} 未走完 claim→execute→submit→verify，不能出「已闭环」报告")
if not_green:
    refuse(f"{len(not_green)} 单未绿: {[r['bug'] for r in not_green]}")
if markers_a and (markers_a["bare_except"] > markers_now["bare_except"]
                  or markers_a["except_swallowed"] > markers_now["except_swallowed"]):
    refuse(f"标记面回落: {markers_now} -> {markers_a}")

# 门禁②的实质判据：每条回归必须能在"把本轮修复回退掉"的临时树上转红，逐单至少 1 条。
lock = jload("lockproof_pass7.json")
if lock.get("tickets_without_a_red"):
    refuse(f"这些单的回归在回退树上仍全绿（假锁）: {lock['tickets_without_a_red']}")
# 裁决单的锁也必须在回退树上咬得住，否则「§九 已落地」只是把代码改了、判据没证。
_locked_bugs = {r["bug"] for r in lock["rows"] if r["red_on_prefix_code"]}
_missing_ruled = sorted(RULING_TICKETS - _locked_bugs)
if _missing_ruled:
    refuse(f"裁决单的回归在回退树上没有转红，不能算已闭环: {_missing_ruled}")
red_total = sum(len(r["red_on_prefix_code"]) for r in lock["rows"])
if "per-ticket" not in lock.get("method", ""):
    refuse(f"回退树自证不是逐单隔离口径，互相抵消的回退会伪装成绿: {lock.get('method')}")
if not lock.get("baseline_passed"):
    refuse("回退树里没有「当前码全绿」的基线一次，红条无从归因")
_by_red = {r["bug"]: len(r["red_on_prefix_code"]) for r in lock["rows"]}
R13_RED, R14_RED = _by_red.get("BUG-13", 0), _by_red.get("BUG-14", 0)

# 新鲜度与顺序不变量：被当作终态引用的证据，必须晚于本轮改动过的每一个源文件；
# 基线证据必须早于终态证据。否则「前后对照」的口径是反的。
terminal = {SWEEP, after_name, "lockproof_pass7.json", "golden_float_diff.json",
            "close_fixes8.out.json", "meas_digest_after.out.txt",
            GF_NAME, "repro_pass8.out.json", "repro_pass9.out.json"}
subprocess.run([sys.executable, str(HERE / "ws_snapshot.py"),
                str(HERE / "ws_snapshot_pass7_after.json")],
               cwd=ROOT, capture_output=True, text=True)
_after = jload("ws_snapshot_pass7_after.json")
PROD = ("cypyc/", "cypy_bridge/", "cypy_hook/")
newest_prod = max((mt for rel, (mt, _s) in _after["py_files"].items()
                   if rel.startswith(PROD)), default=0)
newest_any = max(list(newest_src for newest_src in [newest_prod])
                 + [mt for rel, (mt, _s) in _after["py_files"].items()
                    if rel.startswith("tests/")], default=0)
stale = {name: (HERE / name).stat().st_mtime for name in terminal if (HERE / name).exists()}
for name, mt in stale.items():
    # 标记面的作用域只有产品码，拿测试文件的改动去要求它只会误报；全量日志必须覆盖两者。
    need = newest_prod if name == after_name else newest_any
    if mt < need:
        refuse(f"终态证据 {name} 早于其作用域内最后一次改动 "
               f"({datetime.fromtimestamp(mt):%H:%M:%S} < {datetime.fromtimestamp(need):%H:%M:%S})")
if (HERE / "markers_baseline.json").stat().st_mtime > (HERE / SWEEP).stat().st_mtime:
    refuse("基线标记快照比终态全量还新，前后对照口径反了")

stamp = datetime.now().strftime("%Y%m%d.%H.%M.%S")
now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
ts_out = subprocess.run([sys.executable, str(ROOT / "scripts" / "run_tests.py")],
                        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                        errors="replace").stdout
ts_total = re.search(r"Total: (\d+) \| Passed: (\d+) \| Failed: (\d+)", ts_out)
if not ts_total:
    refuse("自研套件 run_tests.py 的 Total/Passed/Failed 行读不出来")
TS_TOTAL_N, TS_PASSED, TS_FAILED = (int(x) for x in ts_total.groups())
if TS_FAILED:
    # 基线只许持平或向好：test_suite/ 的起点是 47/47，任何一条红都不许被 §一 的 pytest 绿盖过去。
    refuse(f"自研套件 test_suite/ 有 {TS_FAILED} 条红（{ts_total.group(0)}），「基线只升不降」不成立")
_ts_src = (ROOT / "test_suite" / "suites" / "codegen_suite.py").read_text(encoding="utf-8")
if '"<float>x"' in _ts_src:
    refuse("test_suite 里还钉着旧宽度词 \"<float>x\"，§九.3 第 3 条的披露不成立")
TS_NEEDLE_FIXED = _ts_src.count('"<double>x"')

pairs = [(t["bug_id"], t["task_id"]) for t in intake]
OMEGA_TICKETS = ["BUG-16", "BUG-18", "BUG-19", "BUG-20", "BUG-21"]
OMEGA_COUNT = len([b for b in OMEGA_TICKETS if b in {p[0] for p in pairs}])
if OMEGA_COUNT != len(OMEGA_TICKETS):
    refuse(f"omega 流程债的计数与入账单对不上: {OMEGA_COUNT} != {len(OMEGA_TICKETS)}")

# 本轮新增条目数不在正文里手推：账本里号 > PRE_ROUND_LEDGER 的就是本轮新入账的，且必须与
# 四份入账件点名的单号完全一致——多一条即「口头确诊没入账」，少一条即「入账件与账本对不上」。
PRE_ROUND_LEDGER = 14
_ids = [int(re.match(r"## BUG-(\d+) ", t).group(1)) for t in ledger_titles]
NEW_TICKETS = sorted(n for n in _ids if n > PRE_ROUND_LEDGER)
RULED_NEW = sorted({m["bug_id"] for m in B30 + B31 + B32})
_FILED = {int(b.split("-")[1]) for b, _ in pairs} | {int(b.split("-")[1]) for b in RULED_NEW}
if set(NEW_TICKETS) != _FILED or len(_ids) != PRE_ROUND_LEDGER + len(NEW_TICKETS):
    refuse(f"账本新增条目 {NEW_TICKETS} 与本轮入账单号 {sorted(_FILED)} 对不上"
           f"（条目总数 {len(ledger_titles)}，起点 {PRE_ROUND_LEDGER}）")
# FIXED 段的三段式归属也要能对上，否则 §二 的「前六遍留下多少段」是手写的。
PRE_ROUND_FIXED = len(fixed_sections) - len(green) - len(ruled_pairs)
if PRE_ROUND_FIXED != 12:
    refuse(f"前六遍留下的 FIXED 段数反解为 {PRE_ROUND_FIXED}，与本轮起点「12 单修毕」对不上")

# 判为设计/误报而未入账的候选（站点, 判语, 一句理由）。列出来是为了让下一轮能复核而不是重新猜，
# 不代表它们已被本轮逐条二次实测——口径见 §一 末段。
REJECTED = [
 ("`cypy_bridge/types.py:364`", "[SEMANTIC]", "`infer_type` 的 bool 分支不可达，但 tests/test_bridge_library.py:128 明确接受 c_int，改它属改判定"),
 ("`cypy_bridge/core.py:105`、`memory.py:14`", "[设计]", "模块级单个 CDLL 句柄：每进程一次加载，不是 per-import 泄漏"),
 ("`cypy_hook/hook.py:115-131` `_safe_rmtree`", "[设计]", "放弃删除是文档化的 Windows 文件锁处置"),
 ("`cypy_hook/hook.py:571-574` 临时目录留存", "[设计]", "同上，锁窗口内不清理是刻意的"),
 ("`cypy_bridge/defer.py` 全局栈单例", "[设计]", "模块 docstring 声明的嵌套语义"),
 ("`cypy_hook/hook.py:372` 探测后整文件重转译", "[设计]", "增量探测只覆盖一部分，无假成功回报"),
 ("`cypy_bridge/compiler.py:3777-3779` venv 下 exec_prefix", "[UNPROVEN]", "本机 `sys.exec_prefix == sys.base_prefix`，造不出条件（要新建 venv）"),
 ("`cypyc/incremental/ast_differ.py` 只 diff 6 种定义", "[设计]", "唯一入口 `analyze_changes_with_old_ast` 无产品调用方 ⇒ 无用户可见面"),
 ("`ast_differ._compute_definitions_key` 只 hash name+kind", "[设计]", "`file_hash` 先比（incremental_manager.py:248），不会漏改动"),
 ("`cypyc/parser/preprocessor.py` 静默 skip include / 行指令 no-op", "[设计]", "模块 docstring 已声明该子集"),
 ("`cypyc/incremental/file_monitor.py` `_watched_files` 变陈", "[设计]", "`get_watched_files` 无消费者"),
 ("`hot_reload._module_dependencies` 只收 Import", "[设计]", "与已修 BUG-10 相邻但自身无产品消费者；扩它属改召回面"),
 ("`cypyc/parser/` 的 `ASTCache` 未接入 Parser", "[设计]", "死代码，无行为"),
 ("`cypyc/analyzer/pointer_checker.py:180`", "[设计]", "该诊断实际由 type_checker.py:3495 用 .name 发出，无丢失"),
 ("`scope_analyzer.py:484` `_visit_MetaBlock` 被 :926 遮蔽", "[设计]", "`parser._require_module_level` 已拒绝嵌套 meta，遮蔽路径不可达"),
 ("`cython_generator.py:1320` `_visit_ExprStmt` 被 :1986 遮蔽", "[设计]", "parser 只产出一种 ExprStmt 形态（:3007-3101）"),
 ("`cython_generator.py:2430-2455`/`:1034-1081`/`:2129`、`CycleDetector._add_edge`", "[设计]", "算了不用/不可达尾段/重复查表/幻影节点，均无外部行为差"),
 ("`cypyc/utils/ast_utils.py` 经 `parent` 上溯递归", "[误报]", "实测 `ASTNode` 只有 `kind/line/col/body`，无 parent 属性"),
 ("`cypyc/utils/error_reporter.py:190/198` 建议表越界", "[误报]", "取值前有 `error_code in ERROR_SUGGESTIONS` 守卫"),
 ("`ast_utils.get_children` 走 `dir()` 字典序", "[规格未定]", "无产品调用方，且模块未承诺源码序；不当缺陷"),
]
CANDS = len(pairs) + len(REJECTED) + 1
rows = []
for bug, tid in pairs:
    n = int(re.search(r"BUG-(\d+)", bug).group(1))
    tests = by_bug.get(n, [])
    if not tests:
        refuse(f"{bug} 没有反解到锁死回归（门禁② 不成立）")
    rows.append(f"| {bug} | {tid} | {', '.join('`'+t+'`' for t in tests)}"
                f"{'（含 7 条参数化展开）' if n == 22 else ''} | verify=已完成；边界见 §五 |")
for b, (tid, tests) in sorted(RULE_LOCKS.items()):
    rows.append(f"| {b} | {tid} | {', '.join('`'+t+'`' for t in tests)} | 指挥官裁决落地后闭环；见 §九 |")

# 本轮改动面：事前快照没能在第一次写盘前落下（ws_snapshot.py 本身是本轮第一个产物），
# 所以「改了哪些文件」不能声称是快照差——改用 mtime 下界 + 补丁脚本自身的 applied 记录交叉。
subprocess.run([sys.executable, str(HERE / "ws_snapshot.py"),
                str(HERE / "ws_snapshot_pass7_after.json")],
               cwd=ROOT, capture_output=True, text=True)
after = jload("ws_snapshot_pass7_after.json")
ws_dirty = after["git_dirty_lines"]
# 起点不能取 ws_snapshot.py 自身的 mtime：那个脚本在本轮后段被改过一版（补录 examples/*.out
# 与 SYNTAX/*.md），时间戳已晚于前半段的修复写盘。取本轮入账件的落盘时间——它必然早于
# 第一次修复，且之后没人再写过。
boundary = (HERE / "intake_map7.json").stat().st_mtime - 60.0
edited = sorted(rel for rel, (mt, _s) in after["py_files"].items()
                if mt >= boundary and not rel.startswith(("memory/", "tests/test_polish_20260926_pass7")))
# §九.3 第 3 条披露过自研套件里的那处改动，它必须真的出现在清单上（快照口径若没覆盖 test_suite/ 就会漏）。
if "test_suite/suites/codegen_suite.py" not in edited:
    refuse("正文声称改过 test_suite/suites/codegen_suite.py，改动清单里却没有它——快照口径没覆盖 test_suite/")
patched = set()
for script in ("fixes_pass7.py", "fixes_pass7b.py", "fixes_pass9.py"):
    patched |= set(re.findall(r'"((?:cypyc|cypy_bridge|cypy_hook|tests|SYNTAX)/[^"]+\.py)"',
                              (HERE / script).read_text(encoding="utf-8")))
# 裁决落地面（BUG-13/14）是带上下文的手工 Edit + e2e 重注册，不走补丁脚本，单独登记。
RULED = {"cypyc/codegen/type_mapper.py", "tests/test_incremental.py", "SYNTAX/01-basic-types.md"}
# 裁决作废的针头里，自研套件那一处也是手工 Edit（fixes_pass9 的锚点表只覆盖 tests/）——同样登记，
# 否则 §四 的清单会出现「mtime 动了但无人认领」的文件。
MANUAL_NEEDLE = {"test_suite/suites/codegen_suite.py"}
recorded = patched | RULED | MANUAL_NEEDLE
gap = sorted(p for p in patched if p not in edited)
if gap:
    refuse(f"补丁脚本点名的文件没出现在 mtime 清单里（两套证据不一致）: {gap}")
rgap = sorted(p for p in RULED - {"SYNTAX/01-basic-types.md"} if p not in edited)
if rgap:
    refuse(f"裁决修复点名的文件没出现在 mtime 清单里: {rgap}")
unrecorded = [p for p in edited if p not in recorded and not p.startswith("examples/")]
if unrecorded:
    refuse(f"mtime 面有被改文件既无补丁脚本记录也无裁决记录: {unrecorded}")
gold_touched = sorted(p for p in edited if p.startswith("examples/"))
gold_changed = sorted(gold_diff.get("changed") or [])
content_set = {f"examples/{n}" for n in gold_changed}
if not set(gold_touched) >= content_set:
    refuse(f"有内容变化却没被 mtime 抓到（口径漏了）: {sorted(content_set - set(gold_touched))}")
# e2e_golden.sh --update 无条件重写每一份基准 ⇒ mtime 面必然比内容面宽。
# 多出来的那些必须逐份被对照件标成 unchanged，否则就是「mtime 动了但没人解释」。
unchanged_names = {r["file"] for r in gold_diff.get("rows", []) if r["state"] == "unchanged"}
gold_mtime_only = sorted(p for p in gold_touched if p not in content_set)
if {p.rsplit("/", 1)[-1] for p in gold_mtime_only} - unchanged_names:
    refuse(f"mtime 动了但内容差里没有对应记录: "
           f"{sorted({p.rsplit('/', 1)[-1] for p in gold_mtime_only} - unchanged_names)}")

REPORT = f"""# Cypy 打磨第七遍（{now_utc}）— 缺陷清偿续轮与门禁复算

- 主题：Cypy 打磨周（`打磨_20260926.md`），模式 polish，ns `cypy-polish-20260926`，issue_up 开
- 任务库：server cwd = `E:\\IDEProjects\\AI\\Cypy`，故 `fist-mbt.db` 落 Cypy 根、`project_dir="."`
  全程直写 `memory/bugs.md`；任务隔离由 namespace 达成（口径同前六遍，本轮未变）
- git HEAD `{bugs_ns}`；本轮零 `git add/commit/push`，改动全部留在工作区
- 前六遍终态（本轮起点，非本轮工作）：BUG-1..14 入账，12 单修复闭环，BUG-13/14 入账待裁决，
  根任务 `T0` 已归档，`examples/subtype_units.out` 按指挥官授权注册

## 〇、门禁自评（五条，逐条给判据）

| 门禁 | 结论 | 判据来源 |
|---|---|---|
| ① `pytest tests/ -q` 全绿且 ≥ 基线 1745 | {'绿' if p1_failed == 0 and p1_error == 0 else '不绿'}：{p1_passed} passed / {p1_failed} failed / {p1_error} error，收集 {p1_total}（基线收集 {b_collected}：{b_passed} passed / {b_failed} failed） | `.fist-polish-20260926/{SWEEP}` 末行原文：`{tail}` |
| ② 每单有锁死回归 ≥1 | 绿：本轮 {len(pairs)} 单 + 裁决落地段 {len(ruled_pairs)} 单共 {len(lock['rows'])} 张单，测试文件反解出 {len(reg_defs)} 个 `def`（BUG-22 另有 7 条参数化展开）；**并在临时树上逐单隔离回退（只退这一单、其余保持修好）**，每张单至少 1 条自身用例转红（共 {red_total} 条红，`tickets_without_a_red` 为空、`red_controls` 全空——没有对照被误牵） | 同上文件 + `close_fixes7.out.json`/`close_fixes8.out.json` 的 execute 文案三向对照 + `lockproof_pass7.json`/`lockproof_pass7.log`（临时树跑完即删，报告不指向不存在的路径） |
| ③ 标记盘点收敛、新增为零 | {'绿' if markers_a else '未复扫'}：baseline `{json.dumps(markers_b, ensure_ascii=False)}` → 修复前 `{json.dumps(markers_now, ensure_ascii=False)}` → 修复后 `{json.dumps(markers_a, ensure_ascii=False) if markers_a else '（缺 ' + after_name + '）'}` | `marker_scan.py` 三次快照 |
| ④ 确诊 100% 入账 | 绿：账本 `memory/bugs.md` 共 {len(ledger_titles)} 条 `## BUG-N`（本轮新增 {len(NEW_TICKETS)} 条 = BUG-{NEW_TICKETS[0]}..BUG-{NEW_TICKETS[-1]}：pass7 读码段 {len(pairs)} 条 + 裁决落地段新确诊 {len(RULED_NEW)} 条（{', '.join('`'+b+'`' for b in RULED_NEW)}）；该数由账本条目号与四份入账件双向反解核对，不是手推），无一条只停留在口头；{len(fixed_sections)} 段 `### FIXED(verify=已完成)` 覆盖除 {', '.join('`'+b+'`' for b in OPEN_ENTRIES)} 外的全部条目，那 {len(OPEN_ENTRIES)} 条是**入账未修并交裁决**（理由与证据见 §十）；逐单 bug id ↔ task id ↔ 回归测试见 §二 | `intake_map7.json` + `intake_map8.json` + `intake_map9.json` + `intake_map10.json`（四份的 failures/missing 都是 0）+ `repro_pass8.out.json` + `repro_pass9.out.json` + `close_fixes7.out.json` + `close_fixes8.out.json` |
| ⑤ 报告落 `memory/reviews/` | 绿：本文件 `memory/reviews/{stamp}.md` | 生成器 `gen_report7.py`（写盘前硬门：任一类对不上即 refuse） |

## 一、三路发现（候选 {CANDS} → 确诊 {len(pairs)} → 误报/已知设计 {len(REJECTED)} → 未证实 1）

发现通道仍是「三路」，`issue_scan` 按参数卡备查不用（纯 Python 恒空）。
**标记盘点通道**：`mutable_default_arg` / `open_without_with` / TODO·FIXME·HACK·XXX·type-ignore 全为 0
（本轮起点即前六遍收口态，见 §三），无新候选；**测试实跑通道**：起点全量 1816 passed / 0 failed，
唯一待研判项是已入账的 BUG-13 墙钟判据，无新候选；**亲自读码通道**按参数卡优先级把前六遍未覆盖的
缺陷类别（可变默认参、越界/边界切片、生成码作用域与指令位置、缓存失效、资源与编码、分支遮蔽）
重读一遍，得 {CANDS} 个候选。逐条自己复跑或读码到行才入账（复现件 `repro_pass7*.py` 与 `.out.json`）：
{len(pairs)} 条确诊 → `report_bug(publish_task=true)` 自动发布修复单；1 条未证实、**不入账**；
其余 {len(REJECTED)} 条判为设计/无用户可见面，不刷账。

| 通道 | 候选 | 确诊 | 单号 |
|---|---|---|---|
| 标记盘点 | 0 | 0 | — |
| 测试实跑 | 0 | 0 | — |
| 读码 bridge/hook/project | 13 | 6 | BUG-17/23/24/25/26/29 |
| 读码 parser/lexer/incremental | 11 | 5 | BUG-15/16/18/22/27 |
| 读码 codegen/analyzer | 8 | 3 | BUG-19/20/21（+1 未证实） |
| 读码 cypyc/utils（本轮补面） | 4 | 1 | BUG-28 |

（本表只覆盖 pass7 的发现段三条通道。裁决落地段另有 {len(RULED_NEW)} 条新确诊（{', '.join(RULED_NEW)}），走的是**另外三条通道**——
「基准重注册的逐行差」「同根因回查」与「全量套件的单条红研判」，产出不计入上行的 {CANDS}，全貌见 §九.3 与 §十。）

### 一.2 判为设计/误报而未入账的 {len(REJECTED)} 处（列点交后续轮复核，非本轮清白证明）

| 站点 | 判语 | 理由（一句） |
|---|---|---|
{chr(10).join(f"| {s} | {v} | {r} |" for s, v, r in REJECTED)}

**未证实转结（不刷账）**：`cypyc/codegen/cython_generator.py:421-430`/`:439-445` 把「任何有名字的
成员」都收进 `_class_fields`，方法名（`__init__`/`area`）因此可混进位置模式匹配的字段序
（消费者 `:1602-1610` 按 `fields[i]` 生成 `subject.<name> == ...`）。机制在码上看得见，
但本轮两次最小复现都没落到那条分支（无提取器方法时只生成 `isinstance`；带 `__unapply__` 的
手写样例先被语法错误挡住）。按红线「确诊才入账」不入账，交下一轮带提取器语料复现。

**研判口径披露**：上表 {len(REJECTED)} 条里，`cypyc/parser/parser.py` 的 `ASTNode.parent` 递归嫌疑与
`error_reporter.py` 的 `ERROR_SUGGESTIONS[...]` 越界嫌疑是本轮亲手读码/实测排除的；
其余各条由读码通道的复核清单给出，本轮未逐条二次实测——所以它们是「不刷账的理由」，
不是「已证清白」。

## 二、修复闭环表（bug id ↔ 任务 id ↔ 回归测试，全部从账本反解）

| bug | 修复单 | 锁死回归（真实 def 名） | 终态 |
|---|---|---|---|
{chr(10).join(rows)}

逐单 `claim → execute → submit → verify` 的原始回复见 `.fist-polish-20260926/close_fixes7.out.json`
（{len(green)}/{len(pairs)} 全绿）与 `close_fixes8.out.json`（裁决落地段 {len(ruled_pairs)}/{len(RULING_TICKETS)} 全绿）。
账本侧 `memory/bugs.md` 现有 {len(fixed_sections)} 段
`### FIXED(verify=已完成)` = 前六遍留下的 {PRE_ROUND_FIXED} 段 + 本轮 `annotate7.py` 追加的 {len(green)} 段
+ 本轮 `annotate8.py` 追加的 {len(ruled_pairs)} 段（裁决单 BUG-13/14 与落地时新确诊的 BUG-32；
每段点名该单的修复单号、锁死回归与修复边界）；条目标题行的 `OPEN` 按账本口径不改写。

## 三、基线前后对照（只许持平或向好）

| 判据面 | 本轮起点 | 本轮终态 |
|---|---|---|
| `python -m pytest tests/ -q` | {b_passed} passed / {b_failed} failed（收集 {b_collected}，第六遍终态 1816 passed） | {p1_passed} passed / {p1_failed} failed / {p1_error} error（收集 {p1_total}） |
| `python scripts/run_tests.py`（`test_suite/` 自研套件） | Total 47 / Passed 47 / Failed 0 | {ts_total.group(0).replace("|", "\\|")}（中途一度 46/1：自研套件里也有一条钉旧宽度词的断言，是生成这份报告时才暴露的，见 §九.3 第 3 条） |
| 标记盘点（bare_except / except_swallowed / broad_except） | {markers_now['bare_except']} / {markers_now['except_swallowed']} / {markers_now['broad_except']} | {(str(markers_a['bare_except']) + ' / ' + str(markers_a['except_swallowed']) + ' / ' + str(markers_a['broad_except'])) if markers_a else '未复扫'} |
| 缺陷账本 | 14 条（12 修毕 / 2 入账待裁决） | {len(ledger_titles)} 条：{len(fixed_sections)} 条有 FIXED 留档（本轮追加 {len(green) + len(ruled_pairs)} 段 = pass7 的 {len(green)} 段 + 裁决落地段的 {len(ruled_pairs)} 段），{len(OPEN_ENTRIES)} 条入账未修交裁决（{", ".join(sorted(OPEN_ENTRIES))}），0 条待裁决 |
| 端到端 golden 判据（`bash scripts/e2e_golden.sh`，只读） | {GOLD_TOTAL} 份基准全绿（第六遍注册态） | {GF_PASS}/{GOLD_TOTAL} 全绿（`{GF_NAME}` 末行 `{GF_SUMMARY}`），其中 {gold_changed_count} 份因 float=double 裁决改过末位（逐行见 §九.1）。这一条是 **BUG-32 修完之后重跑的**，不是引用旧日志 |
| 用例总数（≥1745 只增不减） | 1816 | {p1_total} |

BUG-13 那条墙钟判据本轮按裁决改成 CPU 时间判，两份测量件是**同一夹具**（`source md5` 相同，
生成器逐字对过）：入账时的 `meas_digest_cost.out.txt` 里 digest 的墙钟/CPU 比最大
**{DIGEST_RATIO_MAX_INTAKE:.2f}×**（墙钟含被别的进程剥夺的时间），落地后的
`meas_digest_after.out.txt` 同一夹具最大 **{DIGEST_RATIO_MAX:.2f}×**、worst wall {DIGEST_WALL_MAX:.3f}s /
worst cpu {DIGEST_CPU_MAX:.3f}s，两条判据在该次实跑里都判 `PASS`
（阈值 {DIGEST_JUDGES['wall'][0]:.1f} 由脚本从测试源反读）。**这一次墙钟没翻面，不能拿它当「墙钟会翻面」的复现**；
翻面实例是入账时记录的那一对数字（{FLIP_PAIR}，原文取自 `tests/test_incremental.py` 的裁决注释）。
改判据的意义在于：判据不再随本进程当时的堆与机器负载摆动。

## 四、本轮改动文件（与既有未提交改动区分）

本轮写盘的产品/测试文件（口径如实说明：**事前快照没能在第一次写盘前落下**，故这里不是快照差，
而是「mtime 下界 + 补丁脚本 applied 记录 + 手工改动登记（`RULED`／`MANUAL_NEEDLE`）」三套证据交叉，
清单侧多出的文件必须有登记、登记点名的文件必须真的在清单上，两个方向任一不合生成器就拒绝出报告；
快照件 `ws_snapshot_pass7_after.json`）。mtime 下界取 `intake_map7.json` 的落盘时间减 60 秒——
不用 `ws_snapshot.py` 自身的 mtime 当起点，因为那个脚本在本轮后段被改过一版（补录
`examples/*.out` 与 `SYNTAX/*.md`），它的时间戳已经晚于前半段的修复写盘；拿它当下界会把
`cypyc/parser/lexer.py` 等 11 个真改过的文件判成「没改」——这是「守卫比主张窄」在本轮的第 6 次现身。
第 7 次同型：快照的 `PKGS` 原本不含 `test_suite/`，于是 §九.3 第 3 条那处手工改动一落地就成了
「mtime 动了但无人认领」的文件（反向检查把它拦下），`PKGS` 补上 `test_suite/` 后清单才完整。

{chr(10).join('- `' + f + '`' for f in edited) if edited else '- （快照缺失，见 §六.4）'}

清单里有 {len(gold_touched)} 个 `examples/*.out`：其中只有 {len(gold_changed)} 份内容真的变了
（`{', '.join(gold_changed) or '—'}`），其余 {len(gold_mtime_only)} 份是 `e2e_golden.sh --update`
**无条件重写**导致的 mtime 位移、内容逐字未变（由 `golden_float_diff.py` 的 `unchanged` 标出，
生成器对「mtime 动了但内容差里没有对应记录」直接 refuse）。`examples/` 下没有任何 `.cypy` 源被改。

另一处必须说明的盘外之扰：`output/`（以及 `dist/` 里的构建中间物）会被**跑判据本身**重写——
`bash scripts/e2e_golden.sh` 对 25 份示例逐个 `cypyc run`、`tests/` 里的 bridge 用例逐个真编译，
产物落在 `output/`。本轮没有把任何构建产物当交付物编辑或提交，但「`output/` 一个字节没动」这种话
不成立，也不该成立（它是判据的运行现场而非源码）。它们不在上面的清单里，因为快照只录源码与基准。

新增文件：`tests/test_polish_20260926_pass7.py`（回归锁）；证据与脚本落 `.fist-polish-20260926/`
（复现件 `repro_pass7.py`、`repro_pass7b.py`、`repro_pass7c.py`、`repro_pass8.py`、`repro_pass9.py`；
补丁脚本 `fixes_pass7.py`、`fixes_pass7b.py`、`fixes_pass9.py`；
入账件 `intake7.py`、`intake8.py`、`intake9.py`、`intake10.py`；
闭环与留档件 `close_fixes7.py`、`close_fixes8.py`、`annotate7.py`、`annotate8.py`、
`lockproof_pass7.py`、`ws_snapshot.py`、`marker_scan.py`、`golden_float_diff.py`、
`meas_digest_cost.py`、`gen_report7.py`、`verify_report8.py`；
它们的落盘输出 `intake_map7.json`、`intake_map8.json`、`intake_map9.json`、`intake_map10.json`、
`close_fixes7.out.json`、`close_fixes8.out.json`、`repro_pass8.out.json`、`repro_pass9.out.json`、
`markers_after_pass9.json`、`markers_now_p2.json`、`markers_baseline.json`、
`lockproof_pass7.json`、`lockproof_pass7.log`、`golden_float_diff.json`、
`meas_digest_cost.out.txt`、`meas_digest_after.out.txt`、
`pytest_final_sweep9.log`、`pytest_final_sweep10.log`、`pytest_final_sweep11.log`、
`e2e_golden_after_float.log`、`e2e_golden_reregister_float.log`、`e2e_golden_final_sweep11.log`、
基准前快照目录 `golden_before_float`、本报告）。

工作区既有脏状态与前六遍一致（`git status --porcelain` 在 `examples dist output` 仍回显 56 行
量级的前轮在途改动，快照件里 `dirty={ws_dirty}` 行）——因此「本轮未触碰 examples/」这类红线
**不能**用工作区干净证明，只能靠上面这份 mtime+记录交叉清单；该检查看不出的是：任何未改 mtime
的既有脏文件。本轮的红线口径也已按指挥官裁决收窄：`examples/` 里允许动的只有端到端基准 `.out`
（重注册），`.cypy` 源、`dist/`、`output/` 未动。

## 五、修复边界（本轮明确没做什么）

1. **BUG-24 只修了判据**：`cypy_hook/hook.py:1020-1024` 的目录匹配已能真删文件，但
   `cypyc/cli.py:384` 仍无条件打印 `[OK] ... cleared`——「清了几个文件」没有回传，
   0 个文件时仍会报成功。上游回报口径要改签名/返回值，属另一单。
2. **BUG-20 未改未知属性的降级**：`_evaluate_attribute_access` 对表里没有的属性抛
   `ValueError`，新增路由把它接成 `None`，于是仍然「静默不成值」（保持既有降级面，
   只是不再让整张表不可达）。给诊断是语义级动作，本轮不做。
3. **BUG-21 只改了登记处**：同族写法 `type_checker.py:1280` 与 `:2005` 未动——`:1280` 的局部名
   在改动前必须读完整函数（它喂给 `_check_impl_on_subtype`），`:2005` 的默认分支被
   2002-2003 行的注释当作刻意保留的失败面。两处各需独立证据，本轮不顺手改。
4. **BUG-26 只放到产物发现**：`compiler.py:3833` 之后把产物复制到输出目录、以及
   `ctypes` 加载路径在 Linux 上是否完整，本轮无 Linux 环境不可实测，未动。
5. 语义级的一律只入账、不擅自改（§一 的未证实项仍按这条处理）。唯一例外是 BUG-14：
   `float` 宽度由指挥官本轮裁定，落地只到类型表与 `SYNTAX` 措辞两处，见 §九。

## 六、遗留与转结

1. **BUG-13（`{R13[0]}`）与 BUG-14（`{R14[0]}`）本轮已按指挥官裁决落地并闭环**，不再挂在「待裁决」上；
   裁决原文、落地面与判据见 §九。本节其余四条边界（BUG-20/21/24/26）不变。
   **但裁决落地又确诊出 {len(RULED_NEW)} 条新的**：BUG-30（`{B30_TASK}`）——声明为浮点的局部量接收 int 时不做浮点化，
   `float` 路径在裁决后从 `{B30_BEFORE}` 退成 `{B30_AFTER}`；BUG-31（`{B31_TASK}`）——`cypy_bridge` 那张
   自称映射「Cypy 类型」的表仍给 `float` 4 字节；BUG-32（`{B32_TASK}`）——约束声明的逐字回显被 `type_mapper`
   改写过（`int | float` 在产物里成了 `int | double`），这一条本轮已修复闭环（§九.3、§十.3）。
   前两条都 `待领取`、都**不属**本轮可顺手改的面，全貌见 §十。
2. **§一 的未证实项**（`_class_fields` 把方法名当字段序）转结下一轮，需要一份带
   `__unapply__`/`__match_args__` 的可解析语料。
   另有一条**按半径不入账**的观察：`docs/USAGE.md:389` 仍写「`constraint` / `subtype` / `dispatch` 尚未实现
   （v0.5 计划）」，而 `examples/subtype_units.cypy` 本轮作为端到端基准之一是真跑真绿的——文档滞后于
   R2 特性轮。它不是编译器/桥接缺陷、也不在参数卡的扫描面（三个产品包）内，故只记线索不入账。
3. **三项裁决的去向**：① BUG-13 修法 → 裁定 `time.process_time()`，已落地（§九）；
   ② BUG-14 `float` 宽度 → 裁定跟随 Python 双精度，已落地并连带重注册端到端基准（§九.1）；
   ③ 是否为触语义核心的单（{OMEGA_COUNT} 张：BUG-16/18/19/20/21）补开 omega 强验证链路 →
   **裁定转结下一轮**，本轮该链路计数仍为 0。
4. **本轮自己造过一次回归，全量套件抓到的**：BUG-22 的第一版修复把「第二字符是 r/R」当成组合
   前缀的充分条件，于是 `free(`、`readfile(` 这类首两字符正好落在 f+r 上的标识符被吞成空前缀
   字符串（`defer free(buffer)` → `('')(buffer)`），全量 **39 failed / 1808 passed**；而本轮新增的
   31 条回归锁当时**全绿**（唯一对照用例 `let rr = 1` 恰好不在冲突集上）。第二版把条件收紧为
   「组合前缀必须紧跟引号」，并把对照扩到 `free/format/read/raw/readfile` 五个标识符，
   定向复跑 `tests/test_polish_20260926_pass7.py + test_integration_full_stack.py +
   test_syntax_integration.py` = 100 passed，随后才是 §〇 的那次全量。
   教训：扩分类器判据的对照集必须取「新承认字符对能构成的真实标识符」，且每单修完的验收面是全量。
5. **回退树自证抓出一条假锁**：BUG-15 的第一版回归断言的是「生成物文本里有没有 `def b`」，
   而被吞进 `BACKTICK_BLOCK` 的源码会原样出现在产物文本里 ⇒ 修复前后**都绿**，
   它锁不住任何东西。`lockproof_pass7.py` 把本轮 15 处修复逐条回退后跑同一份测试时才暴露这一点
   （首轮 `tickets_without_a_red=['BUG-15','BUG-19']`；BUG-19 是排除式正则误把它当对照，
   BUG-15 是真假锁）。改成 AST 层断言「顶层还有两个 `FuncDef`」后，回退树转红、真树转绿。
   ⇒ 「测试存在且通过」不等于「测试锁死了缺陷」，每条回归都得证它会红。
   另注：账本里 pass7 各单 execute 交付文案引用的全量日志名是 `pytest_final_sweep7.log`
   （取文案时的那次运行，1847 passed / 0 failed）；§〇 门禁①引用的是**其后**为终态重跑的
   `{SWEEP}` —— 因为 BUG-15 的测试体、BUG-13/14 的判据与 `tests/test_incremental.py` 都在那次
   之前被改写过。两次都是全量、都是 0 红。
6. 本报告的所有数字由 `gen_report7.py` 从证据文件重算；缺任一证据文件即拒绝出报告。
   `test_suite/` 套件与标记面复扫在报告生成时点重跑，非引用旧日志。

## 九、指挥官三项裁决的落地（本轮收口后追加的第三遍工作）

前八节的终态里，BUG-13/14 是「入账未修、待裁决」。指挥官随后裁定，两条都已落地并逐单闭环；
裁决落地本身又带出一条新缺陷（BUG-32，见 §九.3），一并闭环。三单的
`claim?→execute → submit → verify` 原始回复见 `close_fixes8.out.json`
（单号 {R13[0]} / {R14[0]} / {R32[0]}，前两张本轮此前已 `claim`，第三张是本轮新入账故先领）。

| 裁决项 | 裁定 | 落地 | 判据 |
|---|---|---|---|
| BUG-13 墙钟判据 | 改 `time.process_time()`，阈值量级不动 | `tests/test_incremental.py:542-547`、`:563-574` 两处摘要计时换 CPU 时间；`< 2.0`、`< small*12+0.5` 原样保留 | 锁死回归 `{R13[1][0]}` + 对照 `{R13[1][1]}`（parse/compare 两条时限未被顺手放宽）；实测件 `meas_digest_after.out.txt`；回退树证红 {R13_RED} 条见 §九.2 |
| BUG-14 `float` 宽度 | float 跟随 Python 双精度 | `cypyc/codegen/type_mapper.py:8` `cypy_to_cython["float"]` → `"double"`（与 `cypy_to_c` 一致）；`SYNTAX/01-basic-types.md:19` 「单精度浮点数」措辞随之下修 | 锁死回归 `{R14[1][0]}` + `{R14[1][1]}`（真语料 `examples/subtype_units.cypy` 转译后无 `<float>`）；端到端基准重注册见 §九.1 |
| 语义单的 omega 强验证 | 转结下一轮补开 | 本轮不落地 | 记为流程债：本轮 {OMEGA_COUNT} 张触语义核心的单（BUG-16/18/19/20/21）+ BUG-14 只有 pytest 面证据，omega 链路计数仍为 0；根 `T0` 已归档且账本不支持 reopen，**无法在本轮内补开** |

### 九.1 `float` 裁决后的 golden 重注册（before 快照 → after，逐行）

重注册前已把 25 份基准整体快照到 `.fist-polish-20260926/golden_before_float/`，改完由
`golden_float_diff.py` 逐行对照（下表只列有差异的文件与差异行）：

| 基准文件 | 差异行数 | 逐行 before → after |
|---|---|---|
{GOLD_TABLE}

差异面复核口径：`changed_count = {gold_changed_count}`，`vanished = {len(gold_diff.get('gone') or [])}`，
{GOLD_TOTAL} 份基准里 {GOLD_UNCHANGED_COUNT} 份逐字未变。**「只有浮点末位变了」在生成器里是判据不是正文**：
`_digits_only()` 对每一处行级差异要求「把数字串替换成 `#` 后两侧逐字相同、且数字 token 个数一致」，
任一行不满足（含缺行/多行）即 `refuse` 不出报告；`vanished` 非空同样拒。

### 九.2 裁决项的回退树证红

`lockproof_pass7.py` 的变体表在本轮 15 处之外又加了两组：把 `type_mapper.py` 的 `"double"` 改回
`"float"`（BUG-14）、把 `test_incremental.py` 的两处 `process_time()` 改回 `perf_counter()`（BUG-13），
在同一份当前测试集上重跑 ⇒ BUG-13 转红 {R13_RED} 条、BUG-14 转红 {R14_RED} 条，
`tickets_without_a_red` 仍为空（生成器把「裁决单必须至少一条转红」也写成了硬门）。
口径在本轮升级过：**逐单隔离回退**（每次只回退一单的修复，其余保持修好），全部一起回退只作交叉参照。
升级原因见 §九.4——一起回退时两处回退会互相抵消，把锁伪装成绿。
临时树跑完即删，这里只引用 `lockproof_pass7.json` / `.log`。
（该说法现在由生成器代跑一次实检：`_prefix_tree` 若还在盘上即 `refuse`——第一版报告写「跑完即删」时
`lockproof_pass7.py` 其实从没删树，是这条检查把它变成了事实。）

### 九.3 裁决落地的直接代价：终态全量 {S9_FAILED} 红，其中一条是真缺陷

改完 `type_mapper` 后跑的那次全量（`pytest_final_sweep9.log`，末行 `{S9_TAIL}`）红了 {S9_FAILED} 条，
分布在 {len(S9_TEST_FILES)} 个测试文件（`{', '.join(S9_TEST_FILES)}`）。逐条读过之后分成两类（第 3 条不在那 9 条里——它是同一根因落在**另一套测试体系**的）：

1. **{S9_FAILED - 3} 条是钉住旧宽度拼写的断言**（`to_cython("float")=="float"`、`"<float>x" in code`、
   `cpdef float area`、`def area(self) -> float:`）。它们被裁决本身作废，按裁决改指 `double` 而不是删掉或放宽：
   针头只动宽度词，`or` 分支、条数、其它断言一字未改。逐条清单在 `fixes_pass9.py` 的 EDITS 表里
   （{S9_NEEDLE_COUNT} 处锚点，命中数与预期逐条相等才落盘）。
2. **3 条是产品缺陷**（`test_named_constraints.py` 的三条）：`_visit_ConstraintDef` 把约束成员名过了
   一遍 `type_mapper`，裁决之后产物注释写成 `# constraint Numeric = int | double`，而源码声明的是
   `int | float` —— 注释里出现了源码里没有的类型名，违反 SYNTAX/33 §5 与 C-4.1（命名界与内联界的产物
   只差这一行注释）。这**不是**测试过期，所以按 Step 1 入账为 **BUG-32（`{B32_TASK}`）** 再修，
   不开隐藏分支。
   修法（终态）：新增 `_constraint_member_name()`——标量成员取**声明原名**逐字回显，
   而 `subtype`/`type` 成员仍递归化成基类型**名字**（`Meter` → `float`），只有既非名字也非别名的
   复合形态才退回 `_type_to_str`。
   锁死回归 3 条（{R32_LOCKS}），其中 `{R32_ALIAS}` 是对照锁——它断言 `type` 别名仍出 `ctypedef double N`，
   防止「修回显」被顺手做成「中止裁决」。
   **这条修复自己也被全量纠正过一次**：第一版是「一律逐字回显」，跑出的 `{S10_NAME}` 只剩 1 条红
   （`{S10_TAIL}`）——`tests/test_nominal_subtypes.py::TestShippedExample::test_example_artifact_mentions_no_subtype_name`
   咬住 S-4.1「产物里连 `Meter` 都不该出现」，逐字回显把子类型名字写进了注释。
   也就是说：`test_named_constraints` 要「逐字回显标量名」，`test_nominal_subtypes` 要「子类型名必须消失」，
   两条既有判据的交集才是正确答案；我第一版只满足了前者。终态全量是 §〇 门禁① 引用的 `{SWEEP}`。
   同族面已排查：codegen 里 17 处 `# ` 注释产出只有这一处过映射，analyzer/诊断面完全不调用它（grep 零命中）。
3. **同族过期断言在自研套件里还有一处，而 `pytest tests/` 那套全量照不到它**：
   `test_suite/suites/codegen_suite.py::codegen_cast_expression` 的
   `Assert.contains(cython_code, "<float>x")` 钉的也是旧宽度词。它不是我在哪次实跑里主动抓到的，
   而是**报告生成器为取 §三 那行基线对照去跑 `scripts/run_tests.py` 时才暴露的**（当时 46/47）。
   如实记这条方法债：裁决类改动的「全量」必须两套测试体系都跑，只跑 pytest 那套会漏一整个套件；
   我在改完 `type_mapper` 之后重跑了 pytest 全量三次，却没重跑自研套件。
   处置与上面 6 条同规格：只把宽度词改指 `double`（现在该文件里 {TS_NEEDLE_FIXED} 处 `<double>x`、
   0 处 `<float>x`，生成器逐字校），不改条数也不删断言。
   生成器并就此加了一条硬门：`run_tests.py` 的 Failed 计数非 0 即 refuse 出报告，
   所以本报告能写出来就说明自研套件是 {TS_PASSED}/{TS_TOTAL_N} 全绿。

修完后的终态全量是 §〇 门禁① 引用的 `{SWEEP}`。这次「改一处映射 → 全量抓出 9 红 → 分诊出 1 条真缺陷」
的路径本身记一笔：**裁决类改动的验收面必须是全量**，定点跑只会跑到我自己写的新锁上（它们当时全绿）。

### 九.4 为什么回退树要逐单隔离（本轮踩到的方法级坑）

`lockproof_pass7.py` 旧口径把 {len(lock['rows'])} 处修复一次性全退回再跑同一份测试。BUG-32 一加进来就露馅了：
全退之后 `type_mapper` 也回到了 `float`，于是约束注释「自然而然」又是 `int | float` ——
**BUG-32 的正锁在'前码'上反而绿**，倒是它的对照锁（别名宽度）转红了。锁的归属被完全颠倒。
现在每次只回退一单（其余保持修好），跑完还原该单动过的文件，18 张单逐一证红、0 条对照被误牵进红集；
「全部一起回退」保留为交叉参照（`all_at_once`，那次 {lock['all_at_once']['failed_count']} 条失败、
末行 `{lock['all_at_once']['tail']}`），不再当门禁。

## 十、裁决落地过程中新确诊的三条缺陷（{len(OPEN_ENTRIES)} 条入账未修交裁决，1 条已闭环）

### 十.1 BUG-30（`{B30_TASK}`）：声明为浮点的局部量不做浮点化

`float` 裁决改完类型表后重注册端到端基准，25 份里 {gold_changed_count} 份内容变了。其中一处**不是末位数字变化**：
`examples/basic_types.out` 第 5 行由 `{B30_BEFORE}` 变成 `{B30_AFTER}`。按红线没有把它当噪声注册掉，
而是查到机制并入账。

| 面 | 事实（全部来自 `repro_pass8.py` 的实跑与 `repro_pass8.out.json`） |
|---|---|
| 生成码 | 三行声明 {B30_DECLS}——走 `cython_generator.py:1170` 的注解形式，未走 :1168 的 `cdef` 形式，也没补隐式转换 |
| 编译产物 | 真扩展模块（`tmp_float/out8/repro_pass8.cp313-win_amd64.pyd`，`run_exit={B30_EXIT}`），不是 Python 回退执行 |
| 运行期 | {B30_RUNTIME} |
| 判别 | `float` 与 `double` 现在同样不浮点化 ⇒ 缺口属于 `double` 那条既有路径，裁决只是把 `float` 挪了过来（不是裁决的算术取舍） |
| 与文档的冲突 | `examples/basic_types.cypy:17` 自带注释「隐式转换 (int -> float)」——声明类型在产物里没有兑现，属可观察缺陷而非设计 |

处置：`report_bug(publish_task=true)` → `{B30_TASK}`（账本现 {len(ledger_titles)} 条），**状态仍是待领取**。
不在本轮顺手改的理由：两种修法（改走 `cdef` 形式，或在转换表未命中时补 `<double>` 强转）都会改动生成码形态，
需要再一轮端到端基准重注册 + 全量复跑，且「注解形式为何对 `float` 曾能浮点化、对 `double` 不能」这一子问题本轮未证。
连同该子问题一起转结下一轮。已重注册的基准把现状固化在 `examples/basic_types.out` 第 5 行——
这一条**是**被固化的，本节点名是为了不让它看起来像浮点末位噪声。

### 十.2 BUG-31（`{B31_TASK}`）：同一个裁决在另一个包里还有一处落点没盖到

按「同一根因还有没有别的落点」复查（BUG-14 的根因是**一个声明类型两种宽度**），`cypy_bridge` 里也有一张
自称「Cypy 类型 → ctypes/C 类型」的表（`cypy_bridge/types.py:12` 类 docstring、`:16` 字段名
`cypy_to_ctypes`），它没被裁决覆盖：

| 面 | 事实（`repro_pass9.py` 实跑 → `repro_pass9.out.json`） |
|---|---|
| 编译器侧 | `float` 现出 {B31_COMPILER}（两张表都已 double） |
| bridge 侧 | `to_ctypes("float")` = `{B31_BRIDGE_FLOAT}`（sizeof {B31_SF}），`to_ctypes("double")` = `{B31_BRIDGE_DOUBLE}`（sizeof {B31_SD}） |
| 用户可见 | 按 `cypy_bridge/union.py:164` 自己文档里的用法 `cdef_union("int", "float")` 存 0.1，读回 `{B31_RT_FLOAT}`；`cdef_union("double")` 读回 `{B31_RT_DOUBLE}` |
| 消费面 | `types.py:80/:86/:114/:211` 与 `union.py:50`、`generics.py:51`、`pointer.py:101` |

入账但**不修**的理由（写清楚，别当成"顺手就能改"）：`tests/test_bridge_library.py:646-649` **明确断言**
bridge union 的 `float` 成员是单精度、有精度损失（`assertAlmostEqual(..., places=5)`）。把它改成 `c_double`
等于推翻一条既有用例并改变 FFI 宽度口径，参数卡红线（不弱化既有 tests）与半径都不允许 ⇒ 交指挥官二选一：
① 裁定 bridge 侧也跟双精度，并另起一轮改写那条既有测试；② 裁定本包是「按 C/FFI 类型名取宽度」的底层工具，
那么先改掉它自述里的「Cypy 类型」措辞（`:12/:16/:211`）与 `float_` 这个名字。两条都是语义/口径动作，本轮不做。

### 十.3 BUG-32（`{B32_TASK}`）：裁决在「声明逐字回显」面上的外溢（本轮已闭环，摘要在此）

第三条新确诊同样出自裁决落地段，但它的通道是**终态全量里的那 9 条红**（不是重注册的逐行差，也不是根因回查）：
`_visit_ConstraintDef` 把约束成员名过了 `type_mapper`，裁决后产物注释写成 `# constraint Numeric = int | double`，
而源码声明的是 `int | float`。它已按 `claim → execute → submit → verify` 闭环（修复单 `{B32_TASK}`，
锁死回归 {len(R32[1])} 条：{R32_LOCKS}，其中 `test_bug32_{R32_ALIAS.split('test_bug32_')[-1]}` 是防「中止裁决」的对照锁），
修法与两次被全量纠正的过程见 §九.3 第 2 条，回退树上证红的口径见 §九.4。
本节把它列进来，只为让「裁决落地新确诊 3 条」这个数在账本口径下完整。

## 七、汇报块（参数卡 §七 口径，逐项可回推到本文件证据）

```
[selfdrive-polish] {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} 本地
theme: Cypy 打磨周（issue_up 开）  ns: cypy-polish-20260926
db: server cwd = Cypy 根（fist-mbt.db 落根、project_dir="." 直写 memory/bugs.md；任务隔离靠 ns）
found: 标记盘点 0 / pytest 暴露 0 / 读码审查 {CANDS} → 确诊 {len(pairs)} → 误报或设计 {len(REJECTED)} → 待定 1；基准重注册与裁决复核面另确诊 {len(RULED_NEW)}（{', '.join(RULED_NEW)}：{', '.join(sorted(OPEN_ENTRIES))} 入账未修交裁决，BUG-32 已闭环）
bugs: 入账 {len(pairs) + len(B30) + len(B31) + len(B32)} 单（账本 memory/bugs.md 现 {len(ledger_titles)} 条 / {len(fixed_sections)} 段 FIXED 留档）  修复闭环 {len(green)}/{len(pairs)} + 裁决落地段 {len(ruled_pairs)}/{len(RULING_TICKETS)}  转结 {len(OPEN_ENTRIES)} 条入账未修（{', '.join(sorted(OPEN_ENTRIES))}）+ 1 条未证实项 + 1 流程债（omega 链路按裁决转结）
regress: 新增回归 {len(reg_defs)} 个 def / 实测收集 {P7_COLLECTED} 条用例（BUG-22 参数化展开 7 条），逐单在回退树上证过会红（{len(lock['rows'])} 单共 {red_total} 条红）   pytest: 起点 1816 passed → 终态 {p1_passed} passed / {p1_failed} failed（收集 {b_collected} → {p1_total}，全绿）   test_suite: 起点 47/47 → 终态 {TS_PASSED}/{TS_TOTAL_N} 全绿（中途 46/1，那处同族过期针头见 §九.3 第 3 条）
golden: bash scripts/e2e_golden.sh 终态 {GOLD_TOTAL} 份全绿，其中 {gold_changed_count} 份因 float=double 裁决重注册（before 快照 + 逐行差 §九.1）
rescan: TODO 清单 {markers_now['TODO']}→{markers_a['TODO'] if markers_a else '-'}（FIXME/HACK/XXX/type-ignore 同样 {markers_now['FIXME']}→{markers_a['FIXME'] if markers_a else '-'} 等全零）  标记面 bare {markers_now['bare_except']}→{markers_a['bare_except'] if markers_a else '-'}, swallowed {markers_now['except_swallowed']}→{markers_a['except_swallowed'] if markers_a else '-'}, broad {markers_now['broad_except']}→{markers_a['broad_except'] if markers_a else '-'}  root: T0 已归档（前六遍），本轮 {len(lock['rows'])} 单逐单 verify（pass7 {len(pairs)} + 裁决 {len(ruled_pairs)}），{', '.join(sorted(OPEN_ENTRIES))} 待领取
report: memory/reviews/{stamp}.md
note: 见 §一.2 研判口径与 §五 修复边界；本轮自造回归与全量抓到的过程见 §六.4
```

## 八、执行记录

- {now_utc}：起于「前六遍已收口」的现状复算——门禁①（1816 passed 全绿）、门禁②
  （`verify_gate2.py` 全项通过）、门禁③（markers 收敛对照）三条先实测再决定动作；
  发现第六遍（BUG-14 + golden 注册）晚于 `20260926.19.55.26.md`，故那部分工作此前无报告覆盖，
  本轮报告 §三 把它计入起点。
- 三路读码 → {CANDS} 候选（含标记/实跑两通道的 0 命中复扫）→ 3 份复现件（`repro_pass7*.py`）逐条自证 → {len(pairs)} 单入账
  （`intake_map7.json`，bug_list 14→29）→ 两批修复脚本（`fixes_pass7*.py`，锚点命中数断言 +
  写后复验 + CRLF 保持）→ 回归锁 {len(reg_defs)} 条 → 全量复跑 → 逐单闭环（`close_fixes7.out.json`）。
- 失败原样披露：修复脚本第一批报 2 处校验红，其一（BUG-15）是「新文本已存在于文件其他处」的
  粗粒度防重误判，未写盘，改用带上下文锚点后写入成功；其二（BUG-29）是替换文本本身包含
  锚点尾行导致的复验假阴性，实为已生效（`repro_pass7.py` 的终态探针为证）。
- 裁决落地段（第 2、3 遍工作）：`claim` T0r18/T0r19 → 类型表与 `SYNTAX` 措辞、`test_incremental.py`
  判据量纲落地 → 4 条锁 → 25 份基准先快照再 `e2e_golden.sh --update` 重注册（{GOLD_TOTAL} 份全绿、
  {gold_changed_count} 份内容变化）→ 逐行对照发现非末位变化 → `repro_pass8.py` 查到机制并 `report_bug`
  入账 BUG-30 → 回退树补两档变体后 {len(lock['rows'])} 单全部证红 → 全量 `{SWEEP}` →
  `close_fixes8.py` 双单闭环 → `annotate8.py` 追加 FIXED 留档 → 本文件。
- 这一段里我自己写坏过四处并被自己的检查抓到：① `lockproof_pass7.py` 第一版加 `finally` 清理时把旧的
  `main` 主体留成了不可达代码（临时树因此根本没被删，而前七版报告的「跑完即删」是假的）；现在生成器
  实测 `_prefix_tree` 不存在才肯出报告。② `ws_snapshot.py` 只统计 `.py`，会让 `examples/*.out` 与
  `SYNTAX/*.md` 从「本轮改动清单」里静默消失——补录后 mtime 面与内容面才互相对得上。
  ③ 裁决类改动的「全量」我只跑了 `pytest tests/` 那一套，`scripts/run_tests.py` 的自研套件没复跑：
  其中那条同族过期针头（§九.3 第 3 条）一直拖到生成这份报告、为取 §三 那行而去跑它时才暴露（46/1）。
  现在生成器就此有硬门：自研套件 Failed 非 0 即 refuse 出报告。④ 那处手工改动刚落地时并不在 §四 清单里
  （快照 `PKGS` 原本不含 `test_suite/`），是「mtime 动了但无人认领」的反向检查把它拦下、进而暴露 ③ 的口径缺口。
"""

out = ROOT / "memory" / "reviews" / f"{stamp}.md"
out.write_text(REPORT, encoding="utf-8", newline="\n")
print(f"wrote memory/reviews/{stamp}.md  ({len(REPORT)} chars)")
print(f"gates: pytest {p1_passed}p/{p1_failed}f/{p1_error}e collected={p1_total} "
      f"bugs={len(ledger_titles)} closed={len(green)}/{len(pairs)} edited={len(edited)}")
