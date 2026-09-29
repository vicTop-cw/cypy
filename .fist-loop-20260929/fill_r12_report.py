"""把 R12 收口腿的逐字回执追加进报告的 §6.3（顺序只能是"报告 → 引用核验 → 收口 → 补记 → 再核验"）。

纪律：
 · 数字全部从 `ring_r12_close_*.json` 反解，正文不手加一个数；rollup 用 `json.dumps` 原样印；
 · 幂等：本件那段已在账上就 SKIP，要覆盖用 `--refresh`（只回收自己写的那一段，别的一律不碰）；
 · 有拒绝就**逐字全量**印出（不截断 —— 上一轮的 `[:260]` 让"逐字引用"在打印环节失守）；
 · 追加后自证：段内每个反引号串都能在回执 JSON 里找到原文，且报告里没有未插值占位。
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPORT = ROOT / "reports" / "2026-09-29" / "T0r118-cypy-selfdrive-r12-report.md"
MARK = "R12 收口腿逐字回执"
# 插入锚用"下一节标题"而不是那段待补记的话：话术会随报告改写而断（第一版就是被一个换行折断的），
# 而 `### 6.4` 是报告骨架级的结构锚，它对不上就该停手，不该猜位置。
INSERT_ANCHOR = "\n### 6.4 "


def utc_z():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def section(rep_json: dict, tag: str) -> str:
    g = (rep_json.get("loop_drive") or {}).get("gates") or {}
    obs = (rep_json.get("entry_gate") or {}).get("observed") or {}
    refusal_lines = [
        f"  - `{r['node']}` / `{r['tool']}` ⇒ {r['reply_verbatim']}"
        for r in rep_json.get("refusals", [])
    ]
    idem_lines = [
        f"  - `{r['node']}` / `{r['tool']}` ⇒ {r['reply_verbatim']}"
        for r in rep_json.get("idempotent", [])
    ][:6]
    per_leaf = "\n".join(
        f"  - `{n}`：{v.get('status_before')} → {v.get('status_after')}（步序 "
        f"`{json.dumps(v.get('steps', {}), ensure_ascii=False)}`）"
        for n, v in sorted(rep_json["nodes"].items())
    )
    return (
        f"（收口腿已在盘，补记于 {utc_z()}，回执 `.fist-loop-20260929/ring_r12_close_{tag}.json`。）\n\n"
        f"**{MARK}（`--tag {tag}`）**\n\n"
        f"- 开批门四道读数（每条各自取自对应日志，不合并成一个「再序列化后的引用」）：\n"
        f"  - 终版 pytest：`{obs.get('pytest')}`\n"
        f"  - 自研套件：`{json.dumps(obs.get('suite'), ensure_ascii=False)}`\n"
        f"  - e2e golden：`{obs.get('e2e')}`\n"
        f"  - Ω-gate：`{obs.get('gate')}`（期望对数从 corpus 目录反解 = "
        f"`{obs.get('corpus_case_total_derived_from_corpus_dir')}`）\n"
        f"  - 台账脏检：`{json.dumps(obs.get('ledger_sweep'), ensure_ascii=False)}`；"
        f"承重矩阵：`{json.dumps(obs.get('matrix'), ensure_ascii=False)}`\n"
        f"- 根与树：根 `{rep_json.get('nodes') and sorted(rep_json['nodes'])[0].rsplit('.', 1)[0]}`，"
        f"逐叶终态 rollup `{json.dumps(rep_json.get('rollup'), ensure_ascii=False)}`，"
        f"枝干 `{json.dumps(rep_json.get('branch_final'), ensure_ascii=False)}`，"
        f"待领取叶 `{rep_json.get('pending_leaves')}`，根终态 `{rep_json.get('root_final')}`。\n"
        f"- 调用账：calls={rep_json.get('calls')} refused={len(rep_json.get('refusals', []))} "
        f"idempotent={len(rep_json.get('idempotent', []))} benign={len(rep_json.get('benign', []))}；"
        f"本窗口 `call_log` 红行（ok=0 口径）{rep_json.get('call_log_error_rows')} 行，"
        f"旧口径 `%__error__%` 同窗 `{rep_json.get('call_log_error_rows_old_needle')}` 行"
        "（两口径并印：恒 0 那把尺不再单独承重，见 R11 报告 §6.4 与 BUG-131）。\n"
        f"- 组合环推进腿（服务端、同一会话内走完）：ticks_ok={rep_json.get('loop_drive', {}).get('ticks_ok')}"
        f"/{rep_json.get('loop_drive', {}).get('steps')}，"
        f"门表 `{json.dumps(g, ensure_ascii=False)}`，"
        f"round `{rep_json.get('loop_drive', {}).get('pre', {}).get('round')}→"
        f"{rep_json.get('loop_drive', {}).get('post', {}).get('round')}`，"
        f"mode 序列 `{json.dumps(rep_json.get('loop_drive', {}).get('seq'), ensure_ascii=False)}`。\n"
        + (f"- 逐叶步序：\n{per_leaf}\n" if per_leaf else "")
        + (
            f"- 拒绝（逐字全量，不截断）：\n" + "\n".join(refusal_lines) + "\n"
            if refusal_lines
            else "- 拒绝：无（`refusals` 为空数组）。\n"
        )
        + (
            f"- 幂等回执（状态本就达成，单独计不并入门）：\n" + "\n".join(idem_lines) + "\n"
            if idem_lines
            else ""
        )
        + f"- 收口腿结论行（逐字取自 `.fist-loop-20260929/logs/r12_ring_close_{tag}.out`）：\n"
        + f"  {close_conclusion(tag)}\n"
    )


def close_conclusion(tag: str) -> str:
    """收口腿的 CONCLUSION 行整行取用（不截断、不重排）—— 缺行就不该有这一段。"""
    log = HERE / "logs" / f"r12_ring_close_{tag}.out"
    if not log.exists():
        raise SystemExit(f"收口日志缺失：{log.name} ⇒ 拒绝补记")
    lines = [
        l.strip()
        for l in log.read_text(encoding="utf-8", errors="replace").splitlines()
        if l.startswith("CONCLUSION stage=close")
    ]
    if len(lines) != 1:
        raise SystemExit(f"收口日志里 CONCLUSION stage=close 行数={len(lines)}（必须 1）⇒ 拒绝补记")
    return "`" + lines[0] + "`"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["post"], default="post")
    ap.add_argument("--tag", default="a1")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    src = HERE / f"ring_r12_close_{args.tag}.json"
    if not src.exists():
        raise SystemExit(f"收口回执不在盘：{src.name} ⇒ 不补记（没有回执就没有这一段）")
    rep_json = json.loads(src.read_text(encoding="utf-8"))
    if rep_json.get("stage") != "close":
        raise SystemExit(f"{src.name} 的 stage={rep_json.get('stage')} 不是 close ⇒ 拿错件")
    doc = REPORT.read_text(encoding="utf-8")
    # 标题里 `--tag` 两侧有反引号，针要按实际字节写（第一版把 `（--tag ` 当字面量 ⇒ 永远匹配不上，
    # --refresh 退化成"再插一份"，报告里同时躺着两份回执）。
    pat = re.compile(r"(?ms)\*\*" + re.escape(MARK) + r"（[^*]*?）\*\*.*?(?=\n#+ |\Z)")
    already = pat.search(doc)
    if already and not args.refresh:
        print("CONCLUSION filled=0（本件那段已在报告里，覆盖用 --refresh）")
        return 0
    seg = section(rep_json, args.tag)
    residue = re.findall(r"\{[A-Za-z_][A-Za-z_]*\}", re.sub(r"`[^`]*`", "", seg))
    if residue:
        raise SystemExit(f"补记段含未插值占位 ⇒ 不落盘：{residue[:6]}")
    if already:
        new_doc = doc[: already.start()] + seg + doc[already.end() :]
    else:
        if doc.count(INSERT_ANCHOR) != 1:
            raise SystemExit(
                f"插入锚计数={doc.count(INSERT_ANCHOR.strip())}（必须 1）⇒ 停手不猜位置"
            )
        new_doc = doc.replace(INSERT_ANCHOR, "\n" + seg + INSERT_ANCHOR, 1)
    # 自证：补记段里每个反引号代码串都得能在回执里找到原文。
    # 取"奇数段"而不是正则跨行匹配 —— 一行里有两个代码串时，正则会从第一个的**收尾**反引号
    # 匹到第二个的**起头**反引号，把中间那句散文当成引用打回（第一版就是这么红的）。
    ticks = seg.count("`")
    if ticks % 2:
        raise SystemExit(f"补记段反引号不成对（{ticks}）⇒ 布局坏了，不落盘")
    log_txt = (HERE / "logs" / f"r12_ring_close_{args.tag}.out").read_text(
        encoding="utf-8", errors="replace"
    )
    blob = json.dumps(rep_json, ensure_ascii=False) + "\n" + log_txt
    quoted = [
        q for q in seg.split("`")[1::2] if len(q) >= 12 and not q.startswith(("--tag", "ok=0"))
    ]

    def resolvable(q):
        return (ROOT / q.removeprefix("./")).exists()

    orphan = [
        q for q in quoted if q not in blob and q.strip("[]{}\"'") not in blob and not resolvable(q)
    ]
    grew = len(new_doc.encode("utf-8")) > len(doc.encode("utf-8"))
    # 双写门：补记段全文里那份标记只能出现一次（`already` 分支是替换、否则是首次插入）。
    want_marks = doc.count("**" + MARK) if already else 1
    if new_doc.count("**" + MARK) != want_marks:
        raise SystemExit(
            f"回执段标记数={new_doc.count('**' + MARK)} 应为 {want_marks}（already={bool(already)}）⇒ 不落盘"
        )
    if orphan or not grew:
        (HERE / "logs" / "r12_fill_post_refused.json").write_text(
            json.dumps({"orphan": orphan[:8], "grew": grew}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        for q in orphan[:12]:
            print("ORPHAN_QUOTE |", q)  # 不截断：逐字印
        raise SystemExit(f"补记自证不符（orphan={len(orphan)} grew={grew}）⇒ 不落盘")
    REPORT.with_name("T0r118-cypy-selfdrive-r12-report.md.pre_fill").write_text(
        doc, encoding="utf-8", newline="\n"
    )
    tmp = REPORT.with_name("report.tmp")
    tmp.write_text(new_doc, encoding="utf-8", newline="\n")
    assert tmp.read_text(encoding="utf-8") == new_doc, "回读不一致 ⇒ 停手"
    tmp.replace(REPORT)
    print(
        f"CONCLUSION filled=1 bytes={len(doc.encode('utf-8'))}->{len(new_doc.encode('utf-8'))} "
        f"quoted_ok={len(quoted)} refresh={args.refresh}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
