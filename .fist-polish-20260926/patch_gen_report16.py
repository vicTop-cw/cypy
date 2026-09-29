#!/usr/bin/env python3
"""gen_report.py 补丁 16：加 §五.13「门禁③④ 现场复扫」，数字全部从 markers_* 三份 JSON 现算，
并把现场复扫产物挂进终态证据表。四处替换各自要求唯一命中，写前 compile()。"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.stdout.reconfigure(encoding="utf-8")
GR = os.path.join(HERE, "gen_report.py")
src = open(GR, encoding="utf-8", newline="").read()
nl = "\r\n" if "\r\n" in src else "\n"
if "markers_rescan_live.json" in src:
    print("[patch16] 已应用过，跳过")
    sys.exit(0)

DATA = '''mb = load("markers_baseline.json")
ml = load("markers_rescan_live.json")
ms = load("markers_after_sweep4.json")
if ml["git_head"] != mb["git_head"] != ms["git_head"] or ml["git_head"] != lp["head"]:
    sys.exit(f"[gen_report] 现场复扫与基线/锁死对照不是同一 commit："
             f"{ml['git_head']} / {mb['git_head']} / {ms['git_head']} / {lp['head']}")
if ml["counts"] != ms["counts"]:
    sys.exit(f"[gen_report] 现场复扫与报告登记的终态不一致（门禁③口径已漂移）："
             f"{ {k: (ms['counts'][k], ml['counts'][k]) for k in ml['counts'] if ms['counts'][k] != ml['counts'][k]} }")
ML_GREW = sorted(k for k in ml["counts"] if ml["counts"][k] > mb["counts"][k])
if ML_GREW:
    sys.exit(f"[gen_report] 门禁③ 不过：现扫有 {ML_GREW} 类计数超过基线（新增不为零）")
ML_ZERO = [k for k in ("TODO", "FIXME", "HACK", "XXX", "type_ignore") if ml["counts"][k] != 0]
if ML_ZERO:
    sys.exit(f"[gen_report] 门禁③ 不过：标记类现扫不为 0：{ML_ZERO}")
if ml["files_scanned"] != 56 or ml["taken_at_utc"] <= ms["taken_at_utc"]:
    sys.exit(f"[gen_report] 现场复扫覆盖面/时间戳异常：{ml['files_scanned']} 文件，"
             f"{ml['taken_at_utc']} vs 快照 {ms['taken_at_utc']}")
ML_CATS = len(ml["counts"])
ML_HEAD = ml["git_head"]
ML_AT = ml["taken_at_utc"]
ML_LINES = ml["lines_scanned"]
ML_SW = f'{mb["counts"]["except_swallowed"]}→{ml["counts"]["except_swallowed"]}'
ML_BARE = f'{mb["counts"]["bare_except"]}→{ml["counts"]["bare_except"]}'
ML_BROAD = f'{mb["counts"]["broad_except"]}→{ml["counts"]["broad_except"]}'
'''
OLD_DATA = 'LP_S_WT = LP_SUB["worktree"]["cypyc/analyzer/scope_analyzer.py"]'
NEW_DATA = OLD_DATA + nl + DATA.rstrip("\n")

OLD_EV = '                     ("门禁② 审计器违例对照", "control_gate2.json")]'
NEW_EV = '                     ("门禁② 审计器违例对照", "control_gate2.json"),' + nl + \
         '                     ("门禁③④ 收口后现场复扫", "markers_rescan_live.json")]'

HEAD = "## 六、遗留与转结"
ITEM = "13. **门禁③④ 在收口之后又被现场重算了一遍**（`verify_gates_live.py` → " + nl + \
    "   `markers_rescan_live.json`）：不复用任何历史快照，重新跑同一份 `marker_scan.py`" + nl + \
    "   （{ML_AT}，同一 commit `{ML_HEAD}`，仍 {ML_CATS} 类 / 56 文件 / {ML_LINES} 行），与基线" + nl + \
    "   `markers_baseline.json` 逐类比：{ML_CATS} 类计数**无一超过基线**（新增为零），" + nl + \
    "   TODO/FIXME/HACK/XXX/type:ignore 现扫仍全 0，吞异常 {ML_SW}、裸 except {ML_BARE}、" + nl + \
    "   宽 except {ML_BROAD}，且与报告登记的终态快照 `markers_after_sweep4.json` 逐类别相等。" + nl + \
    "   三向对照同时现场重算：`memory/bugs.md` 的 13 条 `## BUG-n` ↔ §二 闭环表 13 行（T0r6..T0r18）" + nl + \
    "   ↔ `pytest --collect-only` 实收的 {LP_CASES} 条 `test_bugN_`，逐单用例数与门禁② 锁死对照" + nl + \
    "   登记的完全一致；12 条已闭环条目各带一段 `### FIXED(verify=已完成)`，BUG-13 没有（入账未修）。" + nl + \
    "   这一项**先红后绿**：审计器初版把 `test_bug\\d_` 少写一个 `+`（BUG-10..12 全被判无回归），" + nl + \
    "   又按 node-id 形状解析 collect-only 输出（本仓 addopts 强制树形，只给 `<Function …>`），" + nl + \
    "   首跑 47 项 RED 全部来自判据自身；修完解析才有资格说「全项通过」。" + nl + nl + HEAD

EDITS = [(OLD_DATA, NEW_DATA, "数据块"), (OLD_EV, NEW_EV, "终态证据"), (HEAD, ITEM, "§五.13 正文")]
for old, new, tag in EDITS:
    n = src.count(old)
    if n != 1:
        sys.exit(f"[patch16] {tag} 锚点命中 {n} 次（要求恰好 1 次）：{old[:60]!r}")
    src = src.replace(old, new)

compile(src, GR, "exec")
open(GR, "w", encoding="utf-8", newline=nl).write(src)
print("[patch16] 三处替换完成，compile() 通过；现场数字：",
      {k: json.load(open(os.path.join(HERE, "markers_rescan_live.json"), encoding="utf-8"))[k]
       for k in ("git_head", "taken_at_utc", "files_scanned", "lines_scanned")})
