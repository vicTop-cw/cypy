#!/usr/bin/env python3
"""gen_report.py 补丁 15：把 control_gate2.py 的违例对照结论写进 §五.12，并让 §五.12 的
traceback 条数改由 LP_RED 派生（不再硬写 23）。三处替换各自要求唯一命中，写前先 compile()。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.stdout.reconfigure(encoding="utf-8")
GR = os.path.join(HERE, "gen_report.py")
src = open(GR, encoding="utf-8", newline="").read()
nl = "\r\n" if "\r\n" in src else "\n"
if src.count("CTL_ROWS") or src.count("control_gate2.json"):
    print("[patch15] 已应用过（CTL_ROWS 已在文件中），跳过")
    sys.exit(0)

DATA = '''ctl = load("control_gate2.json")
if ctl["baseline_rc"] != 0:
    sys.exit("[gen_report] 违例对照的基准（未改动的 JSON）没让 verify_gate2 判绿 —— 对照本身坏了")
CTL_ROWS = ctl["rows"][1:]
CTL_N = ctl["variants"]
if len(CTL_ROWS) != CTL_N or ctl["missed"]:
    sys.exit(f"[gen_report] 违例对照未全覆盖：漏 {ctl['missed']}；行数 {len(CTL_ROWS)} != {CTL_N}")
if ctl["caught"] != CTL_N or not all(r["caught"] and r["rc"] != 0 and r["matched"]
                                    for r in CTL_ROWS):
    sys.exit("[gen_report] 有违例变体没被指名的那条判据抓住，不生成报告")
if not any(r["variant"] == "forge_unlocked" for r in CTL_ROWS):
    sys.exit("[gen_report] 违例对照缺 forge_unlocked（把 JSON 改到自洽的那种伪造）")
CTL_C = ctl["caught"]
'''

OLD_DATA = 'LP_S_WT = LP_SUB["worktree"]["cypyc/analyzer/scope_analyzer.py"]'
NEW_DATA = OLD_DATA + nl + DATA.rstrip("\n")

OLD_EV = '                     ("门禁② 锁死对照原始输出", "lockproof_head.log")]'
NEW_EV = '                     ("门禁② 锁死对照原始输出", "lockproof_head.log"),' + nl + \
         '                     ("门禁② 审计器违例对照", "control_gate2.json")]'

OLD_PROSE = "无一条是 import 失败类的连带噪声）。"
NEW_PROSE = (
    "无一条是 import 失败类的连带噪声）。" + nl +
    "   **这一节的结论本身过了违例对照**（`control_gate2.py` → `control_gate2.json`）：审计器" + nl +
    "   `verify_gate2.py` 先对未改动的 JSON 判绿（rc=0，否则后面所有「抓到了」都不成立），再喂" + nl +
    "   {CTL_N} 份逐条改坏的副本——少报收集数、汇总行谎称全绿、删掉对照声明、把点名的锁死用例换成" + nl +
    "   日志里为 PASSED 的那条、身份探针指回工作区真身、换掉基准 commit、把不同 `.py` 数写成 0、" + nl +
    "   谎称 HEAD 已含特性码——每份都要求「退出码非 0 **且** RED 明细命中该变体预先指名的那一条判据」，" + nl +
    "   {CTL_C}/{CTL_N} 全部命中。最硬的是 `forge_unlocked`：把 BUG-3 唯一的红用例整体改口成「对照」并" + nl +
    "   把 JSON 改到与日志自洽，此时「JSON 与重算一致」那道检查已经失效，只有门禁②自身的判据" + nl +
    "   （每单 ≥1 条非对照非混因红）会响。对照顺带翻出审计器自己的一处缺陷并已修掉：原先两条" + nl +
    "   「正文里有这个数字」式检查会被别处 incidental 的数字蒙混（把 56 改成 0 照样判绿），现已改成" + nl +
    "   从正文锚定句抠数，并与 `git show {LP_HEAD}` + 工作区实读的重算值做等值比较。")

for old, new, tag in ((OLD_DATA, NEW_DATA, "数据块"), (OLD_EV, NEW_EV, "终态证据"),
                      ("（23 条一行式 traceback", "（{LP_RED} 条一行式 traceback", "traceback 条数"),
                      (OLD_PROSE, NEW_PROSE, "§五.12 正文")):
    n = src.count(old)
    if n != 1:
        sys.exit(f"[patch15] {tag} 锚点命中 {n} 次（要求恰好 1 次）：{old[:60]!r}")
    src = src.replace(old, new)

compile(src, GR, "exec")
open(GR, "w", encoding="utf-8", newline=nl).write(src)
print("[patch15] 三处替换完成，compile() 通过")
