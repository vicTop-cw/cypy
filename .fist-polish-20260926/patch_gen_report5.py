#!/usr/bin/env python3
"""Retarget the report generator + closer for the fifth pass (BUG-13: a brittle wall-clock gate).

Every edit must match exactly once or the script dies without writing.  Multi-line anchors are
re-joined with the target file's own newline (driver .py files are CRLF here).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.stdout.reconfigure(encoding="utf-8")

GEN = os.path.join(HERE, "gen_report.py")
CLOSE = os.path.join(HERE, "close_fixes4.py")

EDITS = [
    # ---------------- gen_report.py: terminal log becomes sweep6 ----------------
    (GEN, 'final = suite("pytest_final_sweep5.log")',
         'final = suite("pytest_final_sweep6.log")'),

    # ---------------- intake5 wiring + arithmetic ----------------
    (GEN, '''intake4 = load("intake_map4.json")
MAPPING = (intake["mapping"] + intake2["mapping"] + intake3["mapping"]
           + intake4["mapping"])
BUG_TOTAL = len(MAPPING)''',
         '''intake4 = load("intake_map4.json")
intake5 = load("intake_map5.json")
MAPPING = (intake["mapping"] + intake2["mapping"] + intake3["mapping"]
           + intake4["mapping"] + intake5["mapping"])
BUG_TOTAL = len(MAPPING)
FIXED_TOTAL = BUG_TOTAL - len(intake5["mapping"])
if intake5["ledger_after"] != BUG_TOTAL or intake5["ledger_before"] != intake4["ledger_after"]:
    sys.exit(f"[gen_report] 第五遍入账对账不上：ledger={intake5['ledger_before']}→"
             f"{intake5['ledger_after']} / mapping 累计={BUG_TOTAL}")
if not any(m["bug_id"] == "BUG-13" for m in intake5["mapping"]):
    sys.exit(f"[gen_report] intake_map5 里没有 BUG-13：{[m['bug_id'] for m in intake5['mapping']]}")'''),

    (GEN, 'if intake2["ledger_after"] != BUG_TOTAL - len(intake3["mapping"]) \\',
         'if intake2["ledger_after"] != (BUG_TOTAL - len(intake3["mapping"]) - len(intake4["mapping"])\n        - len(intake5["mapping"])) \\'),

    (GEN, 'if intake3["ledger_after"] != BUG_TOTAL - len(intake4["mapping"]) \\',
         'if intake3["ledger_after"] != BUG_TOTAL - len(intake4["mapping"]) - len(intake5["mapping"]) \\'),

    (GEN, 'if intake4["ledger_after"] != BUG_TOTAL or intake4["ledger_before"] != intake3["ledger_after"]:',
         'if intake4["ledger_after"] != FIXED_TOTAL or intake4["ledger_before"] != intake3["ledger_after"]:'),

    # ---------------- read-only DB audit: one ticket is deliberately still open ----------------
    (GEN, '''selfdb = load("probe_ledger_final.json")
if selfdb["tickets_done"] != selfdb["tickets_total"] or selfdb["tickets_total"] != BUG_TOTAL:
    sys.exit(f"[gen_report] 只读查库与账本对不上：{selfdb['tickets_done']}/{selfdb['tickets_total']}"
             f"，确诊条目数 {BUG_TOTAL} —— §五.9 不能写「11/11 已完成」")''',
         '''selfdb = load("probe_ledger_final.json")
_open_tickets = [t for t in selfdb["tickets"] if t["status"] != "已完成"]
if selfdb["tickets_total"] != BUG_TOTAL:
    sys.exit(f"[gen_report] 只读查库的修复单数 {selfdb['tickets_total']} != 确诊条目数 {BUG_TOTAL}")
if len(_open_tickets) != 1 or _open_tickets[0].get("bug") != "BUG-13" \\
        or selfdb["tickets_done"] != FIXED_TOTAL:
    sys.exit(f"[gen_report] 终态应当是 {FIXED_TOTAL} 单已完成 + 唯一在途 BUG-13，"
             f"实测 done={selfdb['tickets_done']} 在途={_open_tickets}")'''),

    (GEN, '''_left = {k: v for k, v in selfdb["status_counts"].items()
         if k in ("待领取", "执行中", "待验收", "已打回")}
if _left:
    sys.exit(f"[gen_report] 库里还有可行动行 {selfdb['status_counts']}，§五.9 的「无挂账」不成立")''',
         '''_left = {k: v for k, v in selfdb["status_counts"].items()
         if k in ("执行中", "待验收", "已打回")}
if _left or selfdb["status_counts"].get("待领取") != 1:
    sys.exit(f"[gen_report] 库里状态分布 {selfdb['status_counts']} 与「12 已完成 + 1 待领取"
             f"(BUG-13)」不符，§五.9 不能出报告")'''),

    (GEN, '''if any(t["status"] != "已完成" for t in selfdb["tickets"]):
    sys.exit(f"[gen_report] 修复单终态里有非 已完成 的行：{selfdb['tickets']}")''',
         '''if len(_open_tickets) != 1:
    sys.exit(f"[gen_report] 修复单里非 已完成 的行不止 BUG-13 一条：{selfdb['tickets']}")'''),

    # ---------------- BUG-13 rows for the closure table ----------------
    (GEN, '''    "BUG-12": "GilState.__exit__ 无条件 acquire，把用户异常顶成 NoGilError",
}''',
         '''    "BUG-12": "GilState.__exit__ 无条件 acquire，把用户异常顶成 NoGilError",
    "BUG-13": "TestDigestCost 的墙钟阈值随同进程既有堆涨落，判据跨收集顺序不可复现",
}'''),
    (GEN, '''    "BUG-12": "cypy_bridge/nogil.py",
}''',
         '''    "BUG-12": "cypy_bridge/nogil.py",
    "BUG-13": "tests/test_incremental.py:547（判据本体；未改）",
}'''),
    (GEN, '''    "BUG-12": "test_bug12_gilstate_exit_does_not_replace_user_exception / "
              "test_bug12_gilstate_exit_still_restores_state",
}''',
         '''    "BUG-12": "test_bug12_gilstate_exit_does_not_replace_user_exception / "
              "test_bug12_gilstate_exit_still_restores_state",
    "BUG-13": "无（入账未修：任何修法都要改既有判据口径，见 §六.8）",
}'''),
    (GEN, '''else "未闭环（账本不可用，见 §六）"''',
         '''else ("入账未修（§六.8 转结）" if bid == "BUG-13" else "未闭环（账本不可用，见 §六）")'''),

    # ---------------- gates table ----------------
    (GEN, '''| ① `pytest tests/ -q` 全绿且用例数 ≥ 基线 1745 | {g1}；用例 {base['collected']} → {final['collected']} | `.fist-polish-20260926/pytest_final_sweep5.log` 末行原文：`{final['line']}` |''',
         '''| ① `pytest tests/ -q` 全绿且用例数 ≥ 基线 1745 | {g1}；用例 {base['collected']} → {final['collected']} | `.fist-polish-20260926/pytest_final_sweep6.log` 末行原文：`{final['line']}`。{red_face_line} |'''),

    (GEN, '''| ② 每单修复 ≥1 条锁死回归 | 绿（{closed_ok}/{BUG_TOTAL} 单已 verify，每单各配 1..2 条，共 {regress_cases} 条）''',
         '''| ② 每单修复 ≥1 条锁死回归 | 绿（已修的 {closed_ok}/{FIXED_TOTAL} 单各配 1..2 条、共 {regress_cases} 条回归并 verify 到 已完成；第 13 单 BUG-13 是判据缺陷、入账未修，不占用本门禁）'''),

    (GEN, '''库里 {selfdb['tickets_done']}/{selfdb['tickets_total']} 张修复单逐行 `已完成`（只读直查，见 §五.9） |''',
         '''库里 {selfdb['tickets_done']}/{selfdb['tickets_total']} 张修复单逐行 `已完成`（唯一非已完成行就是 BUG-13，只读直查见 §五.9） |'''),

    (GEN, '''| ④ 确诊缺陷 100% 入账 | 绿（{BUG_TOTAL}/{BUG_TOTAL}，无口头发现未入账；误报 4 条按红线不刷账） | `memory/bugs.md`（`## BUG-1..BUG-{BUG_TOTAL}`）+ `bug_list` count={intake4['ledger_after']} + `intake_map.json`/`intake_map2.json`/`intake_map3.json`/`intake_map4.json`''',
         '''| ④ 确诊缺陷 100% 入账 | 绿（{BUG_TOTAL}/{BUG_TOTAL} 入账，其中 {FIXED_TOTAL} 单修完 verify、BUG-13 入账未修转结；无口头发现未入账；误报 4 条按红线不刷账） | `memory/bugs.md`（`## BUG-1..BUG-{BUG_TOTAL}`）+ `bug_list` count={intake5['ledger_after']} + `intake_map.json`/`intake_map2.json`/`intake_map3.json`/`intake_map4.json`/`intake_map5.json`'''),

    # ---------------- §一 lanes ----------------
    (GEN, '''| ③ 亲自读码审查 | 按 codegen→analyzer''',
         '''| ②b 终态全量的红条复测 | sweep6 里若 `TestDigestCost` 再红：单跑该用例 / 整文件跑 / 灌 1.5M 循环对象 + `gc.freeze()` 三种堆下各测一次（`pytest_digestcost_ordering.log`、`meas_digest_cost.out.txt`、`meas_digest_gc.out.txt`） | 判据缺陷确诊 → BUG-13（CPU 时间恒 0.39–0.47s，墙钟 0.54→3.385s 随收集顺序翻面），产品侧判 [误报]：`ast_differ.py` 自 09-25 16:39 未改 |\n| ③ 亲自读码审查 | 按 codegen→analyzer'''),

    (GEN, '''确诊 {BUG_TOTAL} 条 → 全部 `report_bug(publish_task=true)` 入账；''',
         '''确诊 {BUG_TOTAL} 条（其中 {FIXED_TOTAL} 条已修复并 verify，BUG-13 是判据缺陷、入账后转结待裁决）→ 全部 `report_bug(publish_task=true)` 入账；'''),

    # ---------------- §三 sweep chain ----------------
    (GEN, '''`pytest_final_sweep4.log` → `{mid4['line']}`；第四遍（BUG-12）落地后终态
`pytest_final_sweep5.log` → `{final['line']}`，
「唯一红 = subtype golden」这一不变量保持，且六次收集数与通过数只增不减
（{mid1['collected']}、{mid2['collected']} → {prev['collected']} → {mid3['collected']} →
{mid4['collected']} → {final['collected']}）。''',
         '''`pytest_final_sweep4.log` → `{mid4['line']}`；第四遍（BUG-12）落地后
`pytest_final_sweep5.log` → `{mid5['line']}`（多出的那条红就是 BUG-13 的墙钟判据，机制见 §六.8）；
第五遍复测后终态 `pytest_final_sweep6.log` → `{final['line']}`。
「与产品/基准有关的红只有 subtype golden 一条」这一不变量保持，且七次收集数与通过数只增不减
（{mid1['collected']}、{mid2['collected']} → {prev['collected']} → {mid3['collected']} →
{mid4['collected']} → {mid5['collected']} → {final['collected']}）。'''),

    (GEN, '''mid4 = suite("pytest_final_sweep4.log")''',
         '''mid4 = suite("pytest_final_sweep4.log")
mid5 = suite("pytest_final_sweep5.log")'''),
    (GEN, '''                   ("pytest_final_sweep4.log", mid4)):''',
         '''                   ("pytest_final_sweep4.log", mid4), ("pytest_final_sweep5.log", mid5)):'''),

    # ---------------- red-line inventory of the terminal log ----------------
    (GEN, '''_failed = [l.strip() for l in read("pytest_final_sweep5.log").splitlines()
           if l.startswith("FAILED")]
failed_line = _failed[0] if _failed else "（末态日志无 FAILED 行）"''',
         '''_failed = [l.strip() for l in read("pytest_final_sweep6.log").splitlines()
           if l.startswith("FAILED")]
_golden = [l for l in _failed if "test_every_example_has_golden" in l]
_other_reds = [l for l in _failed if l not in _golden]
if len(_golden) != 1:
    sys.exit(f"[gen_report] 终态日志里 subtype golden 红条应有且只有一条，实测 {_golden}")
if len(_other_reds) > 1:
    sys.exit(f"[gen_report] 终态出现第 3 类红条，文案未覆盖，不能出报告：{_other_reds}")
failed_line = _golden[0]
red_face_line = ("另一条红是 " + "；".join(_other_reds) + " —— 判据自身缺陷（BUG-13），"
                 "同一条用例单跑为绿、整文件跑为红，机制与三条可复跑证据见 §六.8"
                 ) if _other_reds else "终态红条只有 golden 那一条，BUG-13 的墙钟判据本轮没再翻面"'''),

    # ---------------- §六.2 wording: "唯一的红" ----------------
    (GEN, '''2. **subtype 的 golden 缺失＝门禁 ① 唯一的红，而它的三条出路全部要越红线，交你裁决**''',
         '''2. **subtype 的 golden 缺失＝门禁 ① 里与产品/基准有关的红（另有 §六.8 的判据红），而它的三条出路全部要越红线，交你裁决**'''),
    (GEN, '''   终态唯一红条即 `{failed_line}`。判据机制本轮重测过（不复用旧登记）：要求写在''',
         '''   终态该红条为 `{failed_line}`。判据机制本轮重测过（不复用旧登记）：要求写在'''),
    (GEN, '''      f"三条出路都要动 `examples/` 或放宽判据，详见 §六.2，交指挥官裁决")''',
         '''      f"三条出路都要动 `examples/` 或放宽判据，详见 §六.2，交指挥官裁决"
      + ("" if not _other_reds else
         "；另有 " + "；".join(_other_reds) + " —— 判据自身缺陷（BUG-13，见 §六.8），"
         "本轮不降阈值、不拿它冒充产品回退"))'''),

    # ---------------- §六.8: the fifth pass, filed and left open ----------------
    (GEN, '''
## 七、执行记录''',
         '''
8. **第五遍（BUG-13）：门禁 ① 的红条里有一条是判据自己坏了，已入账、刻意不修**
   （`tests/test_incremental.py:547`，修复单 `{tid_by_bug.get('BUG-13')}` 留在 待领取）。
   终态全量 sweep5 里 `TestDigestCost::test_digest_cost_on_ten_thousand_line_module` 报
   `digest cost too high: 3.223s`（阈值 `wall < 2.0`），只跑该文件也是同一形状
   （`pytest_isolated_incremental_sweep5.log` → `1 failed, 37 passed`、3.385s），
   但**同一条用例单独跑是绿的**（`pytest_digestcost_ordering.log`：单条 1 passed / 该 class 2
   passed / 前置 20 条后再跑 21 passed）。产品侧被排除：`meas_digest_cost.out.txt` 用同一份
   `_large_module`+`parse_source`+`ASTDiffer` 复测，摘要 CPU 时间 0.391/0.406/0.422s、
   墙钟 0.510–0.708s；`meas_digest_gc.out.txt` 再灌 1.5M 个循环对象（alloc_blocks
   135568→3135582）后 CPU 仍 0.42→0.47s，墙钟 0.793→0.945s，对这些对象 `gc.freeze()`
   （活对象数不变）墙钟回落到 0.544s。⇒ 多出来的秒数花在「GC 扫描本进程既有堆 + 被抢占」
   （纯 CPU 校准循环 wall/cpu 比 1.28–1.40），不花在 cypyc 的摘要计算上；
   `cypyc/incremental/ast_differ.py` 自 2026-09-25 16:39 未改，sweep4→sweep5 之间唯一产品
   改动是 `cypy_bridge/nogil.py` 的异常守卫。为什么现在才翻面：本轮用例数从 1745 涨到
   {final['collected']}，同一进程里先跑的越多、判据越贵——**这条判据的结论依赖与它无关的堆**。
   不修的口径：四种改法（`process_time`、计时前 `gc.collect()`+`freeze()`、拆 `-m perf`
   单进程跑、阈值改成同进程内相对比值）都要动一条既有测试的判定，超出本轮
   「`tests/` 只补回归不改语义」的授权，按门禁纪律交回指挥官；本报告也不因此把阈值调绿。

## 七、执行记录'''),

    (GEN, '''- 驱动脚本：`.fist-polish-20260926/{{pfist,intake,intake2,intake3,intake4,sweep4_classes,''',
         '''- 驱动脚本：`.fist-polish-20260926/{{pfist,intake,intake2,intake3,intake4,intake5,meas_digest_cost,meas_digest_gc,sweep4_classes,'''),
    (GEN, ''',probe_ledger_final,switchoff_bug11,gen_report}}.py`''',
         ''',probe_ledger_final,switchoff_bug11,patch_gen_report4,patch_gen_report5,verify_report4,verify_report5,gen_report}}.py`'''),
    (GEN, '''- 终态证据：`.fist-polish-20260926/{{markers_after_sweep4,markers_after_sweep4b,intake_map,intake_map2,intake_map3,intake_map4,sweep4_classes,''',
         '''- 终态证据：`.fist-polish-20260926/{{markers_after_sweep4,markers_after_sweep4b,intake_map,intake_map2,intake_map3,intake_map4,intake_map5,meas_digest_cost.out,meas_digest_gc.out,sweep4_classes,'''),
    (GEN, '''  `.fist-polish-20260926/{{pytest_baseline,pytest_final_sweep5,test_suite_after_sweep4,pytest_testsuite_final}}.log`、''',
         '''  `.fist-polish-20260926/{{pytest_baseline,pytest_final_sweep6,test_suite_after_sweep4,pytest_testsuite_final,pytest_isolated_incremental_sweep5,pytest_digestcost_ordering}}.log`、'''),
    (GEN, '''  `pytest_final_sweep3.log`、`pytest_final_sweep4.log`（终态为 `pytest_final_sweep5.log`）——''',
         '''  `pytest_final_sweep3.log`、`pytest_final_sweep4.log`、`pytest_final_sweep5.log`（终态为 `pytest_final_sweep6.log`）——'''),

    # ---------------- close_fixes4.py: cite the real terminal log face ----------------
    (CLOSE, '''FINAL = tally("pytest_final_sweep5.log")''',
         '''FINAL_LOG = sys.argv[1] if len(sys.argv) > 1 else "pytest_final_sweep6.log"
FINAL = tally(FINAL_LOG)
_REDS = [ln.strip() for ln in text(FINAL_LOG).splitlines() if ln.startswith("FAILED")]
if not any("test_every_example_has_golden" in r for r in _REDS):
    raise SystemExit("[close4] 终态日志里没有 subtype golden 红条，交付物文案要重写")
if len(_REDS) > 2:
    raise SystemExit(f"[close4] 终态红条多于两条，本轮文案不覆盖：{_REDS}")
DIGEST_RED = [r for r in _REDS if "TestDigestCost" in r]'''),
    (CLOSE, '''    f"基线不回落（本单收尾时的终态实测）：`pytest tests/ -q` → {FINAL}"
    "（`.fist-polish-20260926/pytest_final_sweep5.log`）——唯一红条仍是 "
    "tests/test_golden_anchor_probes.py::TestGoldenPairing::test_every_example_has_golden，"
    "缺 `examples/subtype_units.out`，属上一轮在途产物与「examples/ 不动」红线的冲突，"
    f"本单不顺手注册基准。自研体系 `python scripts/run_tests.py` → Total {TS_TOT} / "''',
         '''    f"基线不回落（本单收尾时的终态实测）：`pytest tests/ -q` → {FINAL}"
    f"（`.fist-polish-20260926/{FINAL_LOG}`）——红条逐条点名：{'；'.join(_REDS)}。"
    "其中 subtype golden（缺 `examples/subtype_units.out`）属上一轮在途产物与「examples/ 不动」"
    f"红线的冲突，本单不顺手注册基准{'；另 ' + DIGEST_RED[0] + ' 已按判据缺陷单独入账为 BUG-13'
     '（单跑该用例为绿、整文件跑为红，产品代码不在被测路径上），不是本单修复带来的回退'
     if DIGEST_RED else '，本轮再无其它红条'}。自研体系 `python scripts/run_tests.py` → Total {TS_TOT} / "'''),
]


def main() -> int:
    cache = {}
    for path, old, new in EDITS:
        if path not in cache:
            with open(path, "rb") as fh:
                raw = fh.read()
            nl = "\r\n" if b"\r\n" in raw else "\n"
            cache[path] = [raw, nl, 0]
        raw, nl, _ = cache[path]
        o = old.replace("\n", nl)
        n = new.replace("\n", nl)
        text = raw.decode("utf-8")
        hits = text.count(o)
        if hits != 1:
            raise SystemExit(f"[patch5] 锚点命中 {hits} 次（要求 1）：{os.path.basename(path)} :: "
                             f"{old[:70]}...")
        cache[path][0] = text.replace(o, n, 1).encode("utf-8")
        cache[path][2] += 1

    stale = []
    gr = cache[GEN][0].decode("utf-8")
    for needle, why in (("pytest_final_sweep5.log`）——唯一红条", "收尾文案还留着旧的红条口径"),
                        ("「唯一红 = subtype golden」", "§三 仍宣称唯一红"),
                        ("终态证据：`.fist-polish-20260926/{{markers_after_sweep4,markers_after_sweep4b,intake_map,intake_map2,intake_map3,intake_map4,sweep4_classes",
                         "§七 终态证据没列 intake5/meas_*"),
                        ("tickets_done']}/{selfdb['tickets_total']} 张修复单逐行 `已完成`（只读直查，见 §五.9）",
                         "门禁② 仍说全部修复单已完成")):
        if needle in gr:
            stale.append(why)
    if stale:
        raise SystemExit("[patch5] 改完仍有旧口径：" + "；".join(stale))

    for path, (data, _nl, cnt) in cache.items():
        if cnt == 0:
            raise SystemExit(f"[patch5] {path} 一处都没改到，说明锚点写错了")
        with open(path, "wb") as fh:
            fh.write(data)
        comp = compile(data.decode("utf-8"), path, "exec")
        assert comp is not None
        print(f"{os.path.basename(path)}: {cnt} 处已改，CRLF={data.count(b'\\r\\n')} "
              f"裸LF={data.count(b'\\n') - data.count(b'\\r\\n')} md5={__import__('hashlib').md5(data).hexdigest()}"
              f" ast.parse OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
