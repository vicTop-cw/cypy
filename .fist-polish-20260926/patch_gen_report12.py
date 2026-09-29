#!/usr/bin/env python3
"""Disclose the omega / 强验证 lane as what the log shows: never opened, and now unrecoverable.

The parameter card says 强验证 defaults off but 触语义核心的单子可单点开 omega. Whether that happened is
answerable from call_log (already exported to tool_usage_ledger.json, which covers every logged row):
count tools whose name contains "omega". Zero means the four semantic-facing tickets were accepted on
regression tests + the bespoke suite only. Since every ticket is 已完成 and the root 已归档 (and archive
cannot be reopened), this cannot be paid off inside this round — so it is booked as process debt, next to
the heartbeat shortfall.
"""
import os
import py_compile
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "gen_report.py")

OLD_CODE = 'TUL_RB_REJ = "；".join(f"{k} ×{v}" for k, v in sorted(_d["report_bug_rejections"].items()))'
NEW_CODE = OLD_CODE + '''
TUL_OMEGA = sum(v["calls"] for k, v in tul["per_tool"].items() if "omega" in k.lower())
TUL_OMEGA_SEMANTIC = "BUG-3、BUG-4、BUG-8、BUG-11"'''

OLD_PROSE = """   `report_bug` 的失败原文是「{TUL_RB_REJ}」——即 §五.4 落点契约拒绝的措辞，未做任何粉饰。"""
NEW_PROSE = OLD_PROSE + """
   ④ 参数卡里的**强验证 / omega 链路本轮一次都没开**：`call_log` 中 `omega` 前缀工具计数 {TUL_OMEGA}，
   根任务描述发布时就写着 `[omega:off]`（按「默认关」定的）。后果要说清：触语义核心的
   {TUL_OMEGA_SEMANTIC} 四单，实际验收层只有「新增回归 + 全量 pytest + `test_suite/` 自研套件」，
   没有走 omega 的强验证链路；而**本轮已无法补开**——13 张修复单在库里都是 `已完成`、根 `T0` 已归档，
   归档后不可 reopen。连同 ① 的 heartbeat 欠账一起记为**本轮流程债**，是否由下一轮对语义面单子补开
   omega，交指挥官裁。"""
EDITS = [(OLD_CODE, NEW_CODE), (OLD_PROSE, NEW_PROSE)]


def main() -> int:
    src = open(TARGET, encoding="utf-8").read()
    for old, _ in EDITS:
        n = src.count(old)
        print("count={} :: {}".format(n, old[:44].replace("\n", "\\n")))
        if n != 1:
            sys.exit("[patch12] 锚点匹配异常 —— 未写文件")
    if "TUL_OMEGA" in src:
        print("[patch12] 已打过，no-op")
        return 0
    for old, new in EDITS:
        src = src.replace(old, new, 1)
    open(TARGET, "w", encoding="utf-8", newline="").write(src)
    compile(src, TARGET, "exec")
    py_compile.compile(TARGET, doraise=True)
    print("[patch12] applied={} bytes={}".format(len(EDITS), len(src.encode("utf-8"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
