#!/usr/bin/env python3
"""把门禁② 的「HEAD 码上跑今天测试」锁死对照接进 gen_report.py（三处补丁，match-once）。

1) 终态证据表多钉两份文件：lockproof_head.json / .log —— 否则 §三 的新鲜度守卫只覆盖老三份证据，
   新出来的门禁② 证据可以悄悄过期；
2) 数据块：读 lockproof_head.json，六条自洽守卫（单数/用例数/未锁死/绿而未释/对照变红/混因口径）
   任一不成立就不生成报告，而不是把数字抄进正文；
3) 正文 §五.12：逐单表 + 两处「不算锁」的项（反附带伤害对照、混因）及其**实测依据**。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "gen_report.py")

# ---------------------------------------------------------------- 1) 终态证据表
OLD1 = '''TERMINAL_EVIDENCE = [("pytest 全量终态", "pytest_final_sweep6.log"),
                     ("test_suite 自研套件终态", "test_suite_after_sweep4.log"),
                     ("标记盘点复扫终态", "markers_after_sweep4.json")]'''
NEW1 = '''TERMINAL_EVIDENCE = [("pytest 全量终态", "pytest_final_sweep6.log"),
                     ("test_suite 自研套件终态", "test_suite_after_sweep4.log"),
                     ("标记盘点复扫终态", "markers_after_sweep4.json"),
                     ("门禁② 锁死对照结论", "lockproof_head.json"),
                     ("门禁② 锁死对照原始输出", "lockproof_head.log")]'''

# ---------------------------------------------------------------- 2) 数据块
OLD2 = '''FRESH_ROWS = "\\n".join(_fresh_rows)
tul = load("tool_usage_ledger.json")'''
NEW2 = '''FRESH_ROWS = "\\n".join(_fresh_rows)
lp = load("lockproof_head.json")
LP_ROWS = lp["rows"]
if len(LP_ROWS) != 12:
    sys.exit(f"[gen_report] 锁死对照只覆盖 {len(LP_ROWS)} 张单，与 12 张修复单不符 —— 不生成报告")
LP_CASES = sum(r["cases"] for r in LP_ROWS)
if LP_CASES != lp["collected"]:
    sys.exit(f"[gen_report] 锁死对照逐单用例数合计 {LP_CASES}，与其收集数 {lp['collected']}"
             " 不吻合（判据自相矛盾）")
if lp["no_lock"]:
    sys.exit(f"[gen_report] 门禁② 未过：{lp['no_lock']} 的回归在 HEAD 码上锁不住")
if not all(r["locks"] and r["lock_case"] for r in LP_ROWS):
    sys.exit("[gen_report] 有单没有可引用的锁死用例")
LP_GREEN = sorted(c for r in LP_ROWS for c in r["unexplained_green"])
if LP_GREEN:
    sys.exit(f"[gen_report] 锁死用例里有 HEAD 上仍绿的项，须逐条解释后才可出报告：{LP_GREEN}")
LP_CTL_RED = sorted(c for r in LP_ROWS for c in r["controls_red"])
if LP_CTL_RED:
    sys.exit(f"[gen_report] 反附带伤害对照在 HEAD 上变红，口径已漂移：{LP_CTL_RED}")
LP_CONF_RED = sorted(c for r in LP_ROWS for c in r["confounded_red"])
if LP_CONF_RED != sorted(lp["confounds"]):
    sys.exit(f"[gen_report] 声明的混因用例 {sorted(lp['confounds'])} 与 HEAD 实际红项 "
             f"{LP_CONF_RED} 不一致 —— 重新研判")
LP_SUB = lp["subtype_confound_evidence"]
if sum(LP_SUB["head"].values()) > 0 or sum(LP_SUB["worktree"].values()) <= 0:
    sys.exit(f"[gen_report] 混因依据已失效（HEAD {LP_SUB['head']} / 工作区 {LP_SUB['worktree']}）")
LP_DIFF = lp["product_py_differing"]
if LP_DIFF <= 0:
    sys.exit("[gen_report] HEAD 与工作区产品码无差异，锁死对照不成立")
LP_TABLE = "\\n".join(
    "| {} | {} | {} | {} | `{}` |".format(r["bug"], r["cases"], r["lock_cases"],
                                          r["red_on_head"], r["lock_case"])
    for r in sorted(LP_ROWS, key=lambda x: int(x["bug"].split("-")[1])))
LP_RED = sum(r["red_on_head"] for r in LP_ROWS)
LP_SUM = lp["summary_line"] or "(无汇总行)"
LP_HEAD = lp["head"]
LP_CTL = "、".join(f"`{k}`" for k in sorted(lp["controls"]))
LP_CONF = "、".join(f"`{k}`" for k in LP_CONF_RED)
LP_P_HEAD = LP_SUB["head"]["cypyc/parser/parser.py"]
LP_S_HEAD = LP_SUB["head"]["cypyc/analyzer/scope_analyzer.py"]
LP_P_WT = LP_SUB["worktree"]["cypyc/parser/parser.py"]
LP_S_WT = LP_SUB["worktree"]["cypyc/analyzer/scope_analyzer.py"]
tul = load("tool_usage_ledger.json")'''

# ---------------------------------------------------------------- 3) 正文 §五.12
OLD3 = '''   omega，交指挥官裁。

## 六、遗留与转结'''
NEW3 = '''   omega，交指挥官裁。
12. **门禁② 的「锁死」不再靠「测试今天绿」自证**：把 HEAD（`{LP_HEAD}`）的**已跟踪产品码**用
   `git archive` 解到一次性目录，只把工作区的 `tests/` 覆盖进去，再跑
   `tests/test_polish_20260926.py`（判据 `prove_lockins.py`，汇总行「{LP_SUM}」）。
   {LP_CASES} 条用例里 {LP_RED} 条在**本轮修复缺席**的代码上直接变红，且每张单至少摊到一条，
   所以这 12/12 张单的回归是「拿掉修复就会响」的锁，不是今天恰好绿的摆设：

| 单 | 用例 | 锁死用例 | HEAD 红 | 充当锁的那条 |
|---|---|---|---|---|
{LP_TABLE}

   两项**不计入锁**并已给出实测依据：{LP_CTL} 是**反附带伤害对照**（盯的是「修 `__exit__` 别把退出时
   恢复 GIL 的本职一起削掉」，修复前后都该绿，在 HEAD 上确为绿）；{LP_CONF} 在 HEAD 上以
   `No AST for module` 变红属**混因**——HEAD 的 `cypyc/parser/parser.py` 里 `subtype` 出现
   {LP_P_HEAD} 次、`cypyc/analyzer/scope_analyzer.py` {LP_S_HEAD} 次，工作区分别是
   {LP_P_WT}/{LP_S_WT} 次，缺的是那条**未提交的 R2 特性码**而非本单修复，故 BUG-11 的锁改由
   `test_bug11_project_type_check_reports_scope_errors` 单独承担。
   三处护栏钉在判据里，防这份证据将来变成摆设：身份探针要求 `cypyc` 与 `cypy_bridge.nogil` 的
   `__file__` 落在临时树（防跑到工作区或已安装副本上，顺带暴露了 `cypy_bridge/__init__.py` 用同名
   实例遮蔽子模块这个坑——`import cypy_bridge.nogil as g` 拿到的是 `NoGilContext` 而非模块，须走
   `importlib`）；临时树与工作区产品码不同的 `.py` 必须 > 0（本轮实测 {LP_DIFF} 个）；
   解析不到任何用例状态时直接退出，而不是打印「全部锁死」。临时树跑完即删，逐条红因留档
   `.fist-polish-20260926/lockproof_head.log`（23 条一行式 traceback，全部是该单缺陷自身的签名，
   无一条是 import 失败类的连带噪声）。

## 六、遗留与转结'''

PAIRS = [("终态证据表", OLD1, NEW1), ("§五 数据块", OLD2, NEW2), ("§五.12 正文", OLD3, NEW3)]


def main() -> int:
    src = open(TARGET, encoding="utf-8", newline="").read()
    if "\r\n" in src:
        sys.exit("[patch13] gen_report.py 里出现 CRLF，先按 LF 口径处理")
    for label, old, new in PAIRS:
        if src.count(new) == 1 and src.count(old) == 0:
            print(f"[patch13] {label}: 已是补丁后形态，跳过")
            continue
        n = src.count(old)
        if n != 1:
            sys.exit(f"[patch13] {label}: 锚点命中 {n} 次（须恰好 1 次），**未写入任何东西**")
        src = src.replace(old, new, 1)
        print(f"[patch13] {label}: 命中 1 次，已替换")
    compile(src, TARGET, "exec")
    open(TARGET, "w", encoding="utf-8", newline="").write(src)
    print(f"[patch13] 写回完成，字节数 {len(src.encode('utf-8'))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
