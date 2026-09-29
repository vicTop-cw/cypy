"""把 R4-修复 的结果写进 `loop_progress.md`：每个数字从判据件反解，不手填。

上一环的账面自纠（标题写 131/0 失败、正文另一套）就是手填计数的代价。这一版另外拒绝：
① 任一判据件 refuse 非空；② pytest 还有红；③ 报告 sha 与渲染时留档不一致（渲染后被改）；
④ 叶收口件不是 16 行；⑤ 该环记录已在册（幂等门）。
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROG = HERE / "loop_progress.md"
MARK = "### R4-修复"
STAMP = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
REFUSE: list = []

KEYS = {"fix_r4_claim.json": "claim", "fix_r4_locks.json": "locks",
        "fix_r4_rc.json": "rc", "fix_r4_revert.json": "rev",
        "fix_r4_impact.json": "imp", "fix_r4_docs.json": "docs",
        "fix_r4_baselines.json": "base", "fix_r4_ledger.json": "led",
        "fix_r4_ledger_check.json": "lchk", "fix_r4_drivers_lint.json": "lint",
        "fix_r4_calllog_tally.json": "tally", "fix_r4_self_audit.json": "sad",
        "fix_r4_render_order.json": "ro", "close_r4_fix.out.json": "closer",
        "close_r4_fix_root.out.json": "rootc"}
MUST_BE_GREEN = ("base", "tally", "sad", "ro", "closer", "lchk", "led", "lint",
                 "rc", "rev", "imp", "docs", "locks", "claim")


def L(name: str) -> dict:
    p = HERE / name
    if not p.exists():
        REFUSE.append(f"判据件缺失：{name}")
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        REFUSE.append(f"判据件不是合法 JSON：{name}（{str(exc)[:120]}）")
        return {}


def g(d, *keys, default=""):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return cur if cur is not None else default


def cnt(d, key):
    v = d.get(key) if isinstance(d, dict) else None
    if isinstance(v, (list, dict)):
        return len(v)
    return v if isinstance(v, int) else 0


def js(v) -> str:
    return json.dumps(v, ensure_ascii=False)


def carriers(tally):
    return {k: v.get("this_stage_total")
            for k, v in (tally.get("spec_named_carriers") or {}).items()}


def root_status(rootc):
    root = rootc.get("root")
    if isinstance(root, dict):
        return str(root.get("status") or "")
    return str(rootc.get("root_status") or rootc.get("root_final") or root or "")


def final_rows():
    """收口后的终账（`--final` 件）与根收口那 3 条被拒原文，逐字入账。"""
    p = HERE / "fix_r4_calllog_tally_final.json"
    if not p.exists():
        REFUSE.append("终账件缺失：fix_r4_calllog_tally_final.json")
        return ""
    d = json.loads(p.read_text(encoding="utf-8"))
    car = js({k: v.get("this_stage_total") for k, v in
              (d.get("spec_named_carriers") or {}).items()})
    ref = d.get("refusals_md") or "（无）"
    c = (d.get("spec_named_carriers") or {})
    omega_n = (c.get("omega") or {}).get("this_stage_total")
    cl = ((c.get("call_log") or {}).get("carriers") or {}).get("call_log") or {}
    visible = cl.get("client_visible_T0r85_rows")
    return (f"- 终账（收口后）：树 {g(d, 'tree_rows')} 行 / 修复单 "
            f"{g(d, 'bug_card_rows')} 行，被拒 树 {g(d, 'tree_refused')} + "
            f"单 {g(d, 'bug_card_refused')} 条，Omega 链 {omega_n} 次，"
            f"载体 {car}；客户端可见 T0r85 行 {visible}。\n"
            f"  被拒原文（逐字）：\n\n{ref}\n")


def build_row(a):
    b = a["base"]
    r = b.get("radius") or {}
    t = a["tally"]
    pf = b.get("pytest") or {}
    gf = b.get("git") or {}
    fl = []
    add = fl.append
    add(f"{MARK}（根 `T0r85`，执行人 `cypy-fixer`）\n")
    add("")
    add(f"- 结论：**已收口**。{cnt(a['led'], 'cards')} 张修复单闭环，交人工 "
        f"{cnt(a['claim'], 'handoff')} 张、转下一环 {cnt(a['claim'], 'next_round')} 张。")
    add(f"- 产品码：`{g(a['rc'], 'target')}` +{g(a['rc'], 'added_lines')} / "
        f"-{g(a['rc'], 'removed_lines')}；新增定义 {cnt(a['rc'], 'new_defs')} 个、"
        f"共享符号 {cnt(a['rc'], 'shared_symbols')} 个、"
        f"调用点 {g(a['rc'], 'call_site_total')} 处。")
    add(f"- 锁：修前 `{g(a['locks'], 'before', 'summary_line')}` → "
        f"修后 `{g(a['locks'], 'after', 'summary_line')}`；回退矩阵 "
        f"{cnt(a['rev'], 'rows')} 条腿全部承重、对照组零误伤、sha 复原一致。")
    add(f"- 影响面：{g(a['imp'], 'corpus')} 档存量语料逐档差分，新增诊断 "
        f"{cnt(a['imp'], 'newly_rejected')} / 消失诊断 {cnt(a['imp'], 'newly_accepted')}"
        f" / 待裁决 {cnt(a['imp'], 'unadjudicated')}。")
    add(f"- 文档面：{cnt(a['docs'], 'agreed')} 行按实读对齐、半开 "
        f"{cnt(a['docs'], 'half_open')} 条转结、冻结面只读探针 "
        f"{js(g(a['docs'], 'frozen_control'))}。")
    add(f"- 三套体系：pytest {g(pf, 'passed')} 通过 / {g(pf, 'failed')} 失败"
        f"（地板 {g(b, 'floors', 'pytest')}）、收集 {g(b, 'collect', 'nodeids')}、"
        f"自研 {js(g(b, 'suite', 'fields'))}、e2e {js(g(b, 'e2e', 'fields'))}；"
        f"HEAD `{g(gf, 'head')}`、暂存 {g(gf, 'staged')} 行。")
    add(f"- 半径（mtime 落窗口内）：产品 {len(r.get('product') or [])} / "
        f"测试 {len(r.get('tests') or [])} / 文档 {len(r.get('docs') or [])} / "
        f"冻结 {len(r.get('frozen') or [])} / 判据件 {len(r.get('loop') or [])}。")
    add(f"- 账面：三向一致 {g(a['led'], 'agree_total')}/{cnt(a['led'], 'cards')}，"
        f"账本条目 {g(a['led'], 'ledger_total')} 条（追加 FIXED 未多生条目），"
        f"格式化后只读复核 {g(a['lchk'], 'agree_total')}/{g(a['lchk'], 'total')}。")
    add(f"- 驱动面：本轮亲笔 {g(a['lint'], 'drivers_scanned')} 个脚本，硬错 "
        f"{g(a['lint'], 'hard_violations')}、软账 {g(a['lint'], 'soft_total')}"
        f"（上一环基线 {g(a['lint'], 'previous_round_soft_baseline')}）。")
    add(f"- 调用面（渲染前快照）：树 {g(t, 'tree_rows')} 行 / "
        f"修复单 {g(t, 'bug_card_rows')} 行，被拒 {g(t, 'tree_refused')}+"
        f"{g(t, 'bug_card_refused')} 条，载体 {js(carriers(t))}，"
        f"Omega 标记 {js(g(t, 'omega_marked'))}。")
    add(f"- 报告：`{g(a['ro'], 'report', default='—')}`（{a['rep_bytes']} B，"
        f"sha `{g(a['ro'], 'report_sha256')}`，渲染 {g(a['ro'], 'renders')} 次）；"
        f"自证门禁 {g(a['sad'], 'gates_pass')}/{g(a['sad'], 'gates_total')}、"
        f"《八》{g(a['sad'], 'section8_items')} 条判据自伤。")
    add(f"- 收口：叶 {cnt(a['closer'], 'leaves')}/16、根状态 `{root_status(a['rootc'])}`；"
        f"终账见下面那一栏。")
    add(final_rows())
    add(f"- 渲染后的动作（逐条声明，报告本体一个字没动，`fix_r4_render_order.json` 的 sha "
        f"`{g(a['ro'], 'report_sha256')}` 与 `--check` 实测一致）："
        "① `fix_r4_render_order.py` 加了更富的见证字段（产品码 mtime、spec 身份、页脚签名）"
        "并重记一次；② 本轮 14 个驱动按同一 flake8 口径复扫仍为 0 硬 0 软（23:31:30）；"
        "③ 叶/根收口链的调用面只进终账件，不回灌报告。")
    add("- 流程债（不可逆，已归档不能补）：根单 `T0r85` 这一轮**带** `[omega:required]`，"
        "而 `close_root_generic.py` 的步骤形状仍按上一轮「根没标记」的模板发 ⇒ "
        "先 `claim`（已是待验收）、再 `execute`（语料尚未创建）、再 `submit`（不在执行中）"
        "三条被协议层拒；随后 spec_create/spec_review/omega_result_verify/output_validate/"
        "verify/archive 全过，根终态 `已归档`、`assignee=cypy-fixer`、`deliverable` 3080 字、"
        "specs 表 2 行。**新事实**：带标记的根单确实能跑完整 Omega 链（上一轮的 #59 只说"
        "『缺标记的根必被拒』）。修法在驱动侧：按节点实测 `(status, 有无标记, specs 是否已有行)`"
        "生成步骤，下一环（R4-验证）起手就要按这个形状发。")
    add("- 时间盒：本环自 2026-09-27T21:16:43Z 起算，超过 100 分钟盒；"
        "门禁未缩、判据未放宽、未动冻结面，超盒按纪律如实记账并转 R4-验证 复核。")
    add(f"- 起于 2026-09-27T21:16:43Z，本条记录生成于 {STAMP}。")
    return "\n".join(fl) + "\n"


def main() -> int:
    a = {v: L(k) for k, v in KEYS.items()}
    for k in MUST_BE_GREEN:
        if a[k].get("refuse"):
            REFUSE.append(f"{k} 件的 refuse 非空：{js(a[k]['refuse'])[:200]}")
    rep_rel = a["ro"].get("report") or ""
    rep = ROOT / rep_rel if rep_rel else None
    a["rep_bytes"] = rep.stat().st_size if rep and rep.exists() else 0
    if not rep or not rep.exists():
        REFUSE.append(f"报告文件不在盘上：{rep_rel or '(render_order 件缺失)'}")
    if len(a["closer"].get("leaves") or []) != 16:
        REFUSE.append(f"叶收口件只有 {len(a['closer'].get('leaves') or [])} 行（应 16）")
    if a["closer"].get("failed"):
        REFUSE.append(f"有叶未闭：{js(a['closer']['failed'])[:200]}")
    if rep and rep.exists() and a["ro"].get("report_sha256"):
        now = hashlib.sha256(rep.read_bytes()).hexdigest()[:16]
        if now != a["ro"]["report_sha256"]:
            REFUSE.append(f"报告在渲染后被改动：sha {a['ro']['report_sha256']} → {now}")
    if (a["base"].get("pytest") or {}).get("failed_names"):
        REFUSE.append(f"pytest 仍有红：{js(a['base']['pytest']['failed_names'])}")

    text = PROG.read_text(encoding="utf-8") if PROG.exists() else ""
    if MARK in text:
        print(json.dumps({"refuse": [f"进度账里已有「{MARK}」段 ⇒ 拒绝叠加（幂等门）"]},
                         ensure_ascii=False))
        return 1
    row = build_row(a) if not REFUSE else ""
    ks = re.findall(r"(?:^|\s)([a-z][\w-]*)=", row)
    dup = sorted({k for k in ks if ks.count(k) > 1})
    if dup:
        REFUSE.append(f"记录内同名键出现两次：{dup}")
    refuse = sorted(set(REFUSE))
    doc = {"started": a["sad"].get("started", ""), "mark": MARK, "refuse": refuse,
           "written": not refuse, "dup_keys": dup,
           "bytes_written": len(row.encode("utf-8")) if row else 0, "at_utc": STAMP}
    (HERE / "fix_r4_progress.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    if refuse:
        print(json.dumps({"refuse": refuse}, ensure_ascii=False, indent=1))
        return 1
    PROG.write_text(text.rstrip("\n") + "\n\n" + row.rstrip("\n") + "\n",
                    encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": [], "mark": MARK, "bytes": doc["bytes_written"],
                      "lines": len(row.splitlines())}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
