#!/usr/bin/env python3
"""Add the `output_validate` (L4) retrospective audit + skip/xfail evidence to gen_report.py.

Three edits, each required to match exactly once, nothing written until all three are located
(a match-once patcher that fails early leaves no half-patched generator behind).
"""
import os
import py_compile
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "gen_report.py")

OLD_LOAD = 'annot = load("annotate_bugs_fixed.out.json")'
NEW_LOAD = OLD_LOAD + """
l4 = load("ov_audit_and_fist_report.json")
L4_AUDITED = l4["part1_audit"]["audited"]
L4_PASS = l4["part1_audit"]["pass"]
L4_NOTPASS = l4["part1_audit"]["not_pass"]
L4_CTRL = l4["part1_audit"]["control_negative"]
L4_TICKETS = l4["part1_audit"]["tickets_total"]
L4_ARTIFACTS = sum(r["n_artifacts"] for r in l4["part1_audit"]["rows"])
L4_ROWS = "、".join("{}={}".format(r["bug"], r["verdict"]) for r in l4["part1_audit"]["rows"])
FIST_L4_BUG = l4["part2_fist_report"]["reply"]["bug_id"]
FIST_L4_BEFORE = l4["part2_fist_report"]["ledger_before"]
FIST_L4_AFTER = l4["part2_fist_report"]["ledger_after"]
FIST_L4_PUBLISH = l4["part2_fist_report"]["publish_task"]
SKIP_BASE = read("pytest_baseline.log").count("skipped") + read("pytest_baseline.log").count("xfail")
SKIP_FINAL = (read("pytest_final_sweep6.log").count("skipped")
              + read("pytest_final_sweep6.log").count("xfail"))
if L4_CTRL["agree"] is not True:
    sys.exit(f"[gen_report] L4 负向对照没有 fail（got={L4_CTRL['got']}）——硬门形同虚设，不生成报告")
if L4_NOTPASS or L4_PASS != L4_AUDITED:
    sys.exit(f"[gen_report] L4 审计存在非 pass 单：{L4_NOTPASS}")"""

OLD_S1 = "\n## 二、修复闭环表（bug id ↔ 任务 id ↔ 回归测试）\n"
NEW_S1 = """跳过/预期失败逐条研判：基线日志与终态日志里 `skipped`、`xfail` 两个needle 的命中数为
{SKIP_BASE} → {SKIP_FINAL}（`pytest_baseline.log`、`pytest_final_sweep6.log` 全文计数），
即两遍全量都没有任何被跳过或被标记预期失败的用例，该通道**无待研判对象**——这是实测出来的 0，
不是「没去看」。真正需要逐条研判的是那 1 条 `TestDigestCost` 红条（②b）。

""" + OLD_S1

OLD_S6 = "\n## 六、遗留与转结\n"
NEW_S6 = """10. **§四 的 `output_validate` 此前只是表格里的一行，本轮真用了它一次**：把 {L4_TICKETS} 张修复单里
   已 verify 的 {L4_AUDITED} 张（BUG-13 未 verify，不纳入）拿去做**交付物硬门复算**——artifact 清单不写死，
   由 `ov_audit_and_fist_report.py` 从 `memory/bugs.md` 本轮追加的 `### FIXED` 段落里解析出「改动文件」与
   「锁死回归」两行，展开成 {L4_ARTIFACTS} 条 `path` + `contains`/`min_chars` 检查交给 server 读真实文件：
   结果 {L4_PASS}/{L4_AUDITED} 全部 `verdict=pass`、证据层 `l4-pass`（逐单：{L4_ROWS}）。
   同一次运行还带一条**负向对照**：给 BUG-1 的清单再塞一个仓库里不存在的 `def test_zzz...` 路标，
   server 立刻判 `l4-hard-failed`——说明上面那批 pass 不是空转出来的。脚本与逐单回显见
   `.fist-polish-20260926/ov_audit_and_fist_report.json`。
   复算过程中顺带把 `output_validate` 的**真实契约**量清楚了（第 41 条工具事实，供下一轮少走弯路）：
   文件型 artifact 只认 `contains` / `not_contains` / `min_chars`，`check_key` 只能引用
   `external_results`；我最初按 §四 表格那句「`path`/`check_key` + invariant」写的探针参数名是错的，
   因此**先前两条「缺陷」候选都是我的探针坏了而不是工具坏了**——「`check_key` 被忽略」由改用正确字段后
   推翻；「`not_contains` 被静默忽略」由一次假对照推翻（我给的禁止串在源码里被拆成两行，`count` 实测为 0，
   于是 `pass` 本来就是正确答案）。判据见 `probe_output_validate3.py` 与其 json。
   真正**活下来的一条**已入账：`parse_artifact` 只 `m.get` 那五个已知键、从不检查剩余键，
   所以拼错或臆造的字段（`contans`、`invariant`）会把硬门静默降级成「文件存在+非空」，
   而 pass 文案仍断言「invariant 全部通过」——上报为其账本 {FIST_L4_BUG}（`severity=medium`，
   账本 {FIST_L4_BEFORE} → {FIST_L4_AFTER} 条，落 `E:\\\\IDEProjects\\\\AI\\\\FIST-Mbt\\\\memory\\\\bugs.md`）。
   **本轮对它账本累计 {len(fist_filed) + len(fist2_filed) + 1} 条。** 该条 `publish_task={FIST_L4_PUBLISH}`：
   修 FIST-Mbt 不在本轮范围内、也不该往它现网看板播种任务，这是与 §三「publish_task=true」的一处**有意偏离**，
   与前两遍上报同口径。
""" + OLD_S6

EDITS = [(OLD_LOAD, NEW_LOAD), (OLD_S1, NEW_S1), (OLD_S6, NEW_S6)]


def main() -> int:
    src = open(TARGET, encoding="utf-8").read()
    hits = [(src.count(old), old[:48]) for old, _ in EDITS]
    bad = [h for h in hits if h[0] != 1]
    for n, tag in hits:
        print(f"count={n} :: {tag}")
    if bad:
        sys.exit(f"[patch7] 锚点匹配异常 {bad} —— 未写文件")
    if "L4 负向对照" in src:
        print("[patch7] 已打过，no-op")
        return 0
    for old, new in EDITS:
        src = src.replace(old, new, 1)
    for frag in ("echo ", "TODO ", "FIXME "):
        if frag in NEW_LOAD + NEW_S1 + NEW_S6:
            sys.exit(f"[patch7] 插入文本里出现 {frag!r}，会污染 §六 标记盘点口径")
    before = len(src.encode("utf-8"))
    open(TARGET, "w", encoding="utf-8", newline="").write(src)
    compile(src, TARGET, "exec")
    py_compile.compile(TARGET, doraise=True)
    after = len(open(TARGET, "rb").read())
    print(f"[patch7] applied=3 bytes {before} -> {after}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
