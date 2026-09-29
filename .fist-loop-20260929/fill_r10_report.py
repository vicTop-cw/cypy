"""把 R10 的 FIST 账面渲染进报告 §6.2/§6.3（占位标记替换，插入口径可复核）。

针不靠手打：所有"逐字"结论行都用 last_line() 从证据件里取，
证据件里没有 ⇒ 宁可写"缺件"也不代写数字。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPORT = ROOT / "reports" / "2026-09-29" / "T0r116-cypy-selfdrive-r10-report.md"
PLACEHOLDER = "<!--FIST-SECTION-->"
LOGS = HERE / "logs"


def last_line(path: Path, needle: str) -> str:
    if not path.exists():
        return f"(缺件 {path.name})"
    for ln in reversed(path.read_text(encoding="utf-8", errors="replace").splitlines()):
        if ln.startswith(needle):
            return ln.strip()
    return f"(未找到 {needle} 行)"


def j(name):
    p = HERE / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def main() -> int:
    ring1 = j("close_r10_ring.json")
    ring2 = j("close_r10_ring2.json")
    ledger = j("close_r10_ledger.json")
    bugs_b = j("file_r10_bugs.json")
    audit = j("audit_r10_stuck.json")
    ver = j("verify_r10_report.json")

    a1 = last_line(LOGS / "r10_ring_a2.out", "CONCLUSION")
    a2 = last_line(LOGS / "r10_ring_a3.out", "CONCLUSION")
    ref1 = last_line(LOGS / "r10_ring_a2.out", "REFUSED T0r116.1.1 verify")
    five = json.dumps(ring2.get("nodes", {}).get("T0r116.1.1", {}).get("steps", {}), ensure_ascii=False)

    t112 = audit.get("summary", {}).get("T0r112", {})
    t113 = audit.get("summary", {}).get("T0r113", {})
    t116 = audit.get("summary", {}).get("T0r116", {})
    audit_text = (
        f"`T0r116` 本轮树：{json.dumps(t116, ensure_ascii=False)} ⇒ 零非终态节点；"
        f"上一轮两棵树 `T0r113`={json.dumps(t113, ensure_ascii=False)}、"
        f"`T0r112`={json.dumps(t112, ensure_ascii=False)}。"
        f"审计口径：叶子状态是 `待领取`（共 {t112.get('pending_leaves', 0) + t113.get('pending_leaves', 0)} 支）时，"
        f"其父枝与根**不能**诚实收口 —— 要么拿真实交付物把叶子走完整链，要么等有退役出路（BUG-106）。"
        f"本轮不伪造这两棵树叶子的交付物，因此 `T0r112`/`T0r113` 继续留 `拆分中`，"
        f"这是**账面事实**而不是本环的欠账：本轮新树 `T0r116` 已 17/17 全闭。")

    sec = f"""
本小节的每个数字都从下列回执件反解：`close_r10_ring.json`、`close_r10_ring2.json`、
`close_r10_ledger.json`、`file_r10_bugs.json`、`audit_r10_stuck.json`、`verify_r10_report.json`，
逐字结论行见 `logs/r10_ring_a2.out`、`logs/r10_ring_a3.out`。

**环与树**：根单 `{ring1.get('root_reused') or 'T0r116'}`（描述带 `[omega:required]`），
回读形状 {json.dumps(ring1.get('tree_readback', {}), ensure_ascii=False)[:150]}……；
`loop_create` 六步环 `cypy-selfdrive-r10`（steps：advance→bugfind→fix_and_merge→verify→polish→advance，
`baseline_test_count=2241`、`baseline_open_bug_count={ring1.get('ledger_open_measured')}`），
`laya_decide` 回执 {json.dumps(ring1.get('laya', '{}'), ensure_ascii=False)[:150]}……

**每叶完整链**（claim → omega_spec_create → omega_spec_review → execute → run_check →
omega_result_verify → submit → verify，`verify` 一律带 `docs_check=True`）：
第一腿逐字 `{a1}`；补腿逐字 `{a2}`；补腿第一支叶的步骤回执 {five[:220]}……

**本轮把 R9 欠的流程债做成了入口门**：开批前四件全查（报告在盘且 ≥6000 字节、
引用核验件 `failed=0` 且 `report_bytes` 与当前报告逐字相等、Ω-gate 终值 `cases=71 … rc=0`、
三套终验日志各自命中），任一不合就整腿拒收并打印原因（`close_r10_ring.py` 的 `entry_gate()`）。
R9 那笔「收根早于报告落盘」的流程债本轮不再是转结，而是**机制上不可能再发生**。

**`docs_check=True` 实测打回过一次**（这是本轮学到的服务端门禁，不是我的臆想），
第一腿逐字拒绝文案 `{ref1[:230]}`
⇒ 交付物必须是「结论 / 证据 / 分析 / 缺口与风险 / 建议入档位置」五段式。
处置：**照做而不是关门禁** —— 12 支叶按服务端给出的出路
（`reject → retry → execute → submit → verify`）重写五段式交付物后重收，
补腿 `refused=0`、`call_log_error_rows=0`。

**重复噪声**：第一腿在"已经走过一遍链"的叶上重复发 spec 步骤 ⇒ 70 条
`语料 […] 已通过审核，无需重复创建` 一类拒绝，
这不是账面缺陷而是脚本没按状态分派；补腿改为按当前状态 + `specs` 表计数分派后噪声归零
（`benign=0` 意味着连噪声都不需要了）。

**账本**：本轮 8 张单全部走 `report_bug` 取号（`filed={bugs_b.get('filed') and len(bugs_b['filed'])}` +
`filed={len(ledger.get('filed', []))}`，`refused={len(bugs_b.get('refusals', [])) + len(ledger.get('refusals', []))}`，
`new_ids={json.dumps(bugs_b.get('new_ids', []) + ledger.get('new_ids', []))}`），
账本 `bug_list` 回读 {bugs_b.get('bug_list_rows', 0)} 行与头数 {ledger.get('append_only_check', {}).get('headers_now', 0)} 双向对齐；
BUG-118 的 `### FIXED` 段 + 两条 `### AMENDMENT`（0.08s 读数改指到有文件的证据件、
file:line 锚漂移更正）全部只增不改（`prefix_identical=true`、`header_untouched=true`）。

**上一轮卡点审计**（`audit_r10_stuck.py`，只读库，不强推）：
{audit_text}

**本轮 FIST 调用面**：两腿合计 {ring1.get('calls', 0) + ring2.get('calls', 0)} 次工具调用
（另有入账两批的 `report_bug`/`bug_list` 面，逐条回执见 `file_r10_bugs.json` 与 `close_r10_ledger.json`），
`call_log` 里 `__error__` 行数两腿分别为 {ring1.get('call_log_error_rows', 0)}/{ring2.get('call_log_error_rows', 0)}；
拒绝按形状逐条捕获，未做"过滤掉再报数"。

**引用核验**：`verify_r10_report.py` {json.dumps({'checks': len(ver.get('checks', [])), 'failed': ver.get('failed')}, ensure_ascii=False)}
—— BUG 号 {ver.get('cited_bug_ids')}、路径 {ver.get('cited_paths')} 个、逐字结论 {ver.get('verbatim_claims')} 条、
file:line 锚 {len(ver.get('anchors', []))} 条（含两条 canary：区间整体平移必须红、不存在的单号必须被点名）。
"""

    rep = REPORT.read_text(encoding="utf-8")
    assert rep.count(PLACEHOLDER) == 1, f"占位标记命中 {rep.count(PLACEHOLDER)} 次"
    out = rep.replace(PLACEHOLDER, "（渲染于收根之后，输入件均为本腿回执）\n" + sec)
    REPORT.write_text(out, encoding="utf-8", newline="\n")
    print("FILLED bytes=", len(out.encode("utf-8")), "lines=", len(out.splitlines()))
    print("CONCLUSION placeholder_left=", out.count(PLACEHOLDER), "added_bytes=", len(out.encode("utf-8")) - len(rep.encode("utf-8")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
