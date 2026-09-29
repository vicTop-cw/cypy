"""R11 报告数字填充：正文里的每个计数都从终版日志/账本/环回执**反解**后代入，手加一律禁止。

两道 pass：
 · `--stage pre`  填除「close 回执」以外的全部格；close 未跑时把 `{{RING_CLOSE}}` 写成"尚未收口"，
   这样引用核验能在收口前先跑一遍（收批门要求核验件 failed=0 且 report_bytes 与盘面相等）；
 · `--stage post` 收口后把 close 回执渲染进去，随后必须重跑 `verify_r11_report.py`（字节变了核验就红）。
任何 token 残留 ⇒ refuse 并列出残留名（上一轮踩过"未插值占位一路提交"）。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPORT = ROOT / "reports" / "2026-09-29" / "T0r117-cypy-selfdrive-r11-report.md"
LOGS = HERE / "logs"
CORPUS_REL = "corpus/cypy.generic.class.json"
BASELINE_PYTEST = 2241  # R10 终版实测（a5 日志），不是本轮现算


def tail_needle(path: Path, prefix: str) -> str:
    if not path.exists():
        raise SystemExit(f"缺证据件 {path.name}")
    for ln in reversed(path.read_text(encoding="utf-8", errors="replace").splitlines()):
        if ln.startswith(prefix):
            return ln.strip()
    raise SystemExit(f"{path.name} 里没有以 {prefix!r} 开头的行")


def summary_line(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    hits = re.findall(r"=+ .*(?:\d+ passed|\d+ failed).*?=+", text)
    if not hits:
        raise SystemExit(f"{path.name} 里解析不到汇总行")
    return hits[-1].strip(" =")


def ledger_counts() -> dict:
    """账本数字：直接复用引用核验件的读取函数，避免"报告数一遍、核验数一遍"的两处读取。"""
    sys.path.insert(0, str(HERE))
    import verify_r11_report as vr

    led = vr.ledger_state()
    prev = json.loads((HERE / "verify_r10_report.json").read_text(encoding="utf-8"))["ledger"]
    return {"headers": led["headers"], "unique": len(led["ids"]), "open": led["open"],
            "fixed": led["fixed_sections"], "amend": led["amendment_sections"],
            "open_wide": led["open_wide"], "judge_ids": led["judge_face"],
            "judge": len(led["judge_face"]), "product": led["product_face"],
            "sev": led["severity"], "prev_fixed": prev["fixed_sections"],
            "prev_amend": prev["amendment_sections"]}


def ring(stage: str) -> dict:
    p = HERE / f"ring_r11_{stage}.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def ev(path_name: str, prefix: str) -> str:
    """收口腿的读数一律从证据件逐字取；缺文件或缺该行 ⇒ 直接 raise，不写"大概是这样"的句子。"""
    return "`" + tail_needle(LOGS / path_name, prefix) + "`"


def pending_from_log() -> str:
    """a4 的结论行里有 `pending_leaves=N`；回执件没这个键时只能从这里取，取不到就拒绝写这句。"""
    line = tail_needle(LOGS / "r11_ring_close_a4.out", "CONCLUSION")
    m = re.search(r"pending_leaves=(\d+)", line)
    if not m:
        raise SystemExit("a4 结论行里解析不到 pending_leaves ⇒ 待领取叶数无来源")
    return m.group(1)


def close_leg_tokens() -> dict:
    """§6.3 收口回执 + §6.4 收口腿的尺子账：全部反解自 a3/a4/驱动/自检/负控制/入账六件。"""
    a4 = ring("close")
    needles = json.loads((HERE / "r11_loop_tick_fix.json").read_text(encoding="utf-8"))["error_rows_two_needles"]
    filed = json.loads((HERE / "file_r11_ledger_bugs.json").read_text(encoding="utf-8"))
    neg = json.loads((LOGS / "r11_ring_close_refused.json").read_text(encoding="utf-8"))["entry_gate"]["reasons"]
    return {
        "{{EV_CLOSE_A3}}": ev("r11_ring_close_a3.out", "CONCLUSION"),
        "{{EV_CLOSE_A4}}": ev("r11_ring_close_a4.out", "CONCLUSION"),
        "{{EV_SHAPE}}": ev("r11_loopfix_a2.out", "SHAPE_CONTROL"),
        "{{EV_DRIVE}}": ev("r11_loopdrive_a2.out", "CONCLUSION"),
        "{{EV_SELFTEST}}": ev("r11_loopdrive_selftest_a1.out", "CONCLUSION"),
        "{{EV_NEGCTL}}": ev("r11_ring_close_negctl_a1.out", "CONCLUSION"),
        "{{EV_NEGCTL_REASON}}": "、".join(f"「{r}」" for r in neg),
        "{{EV_FILED}}": "、".join(filed["new_ids"]),
        "{{EV_FILED_LOG}}": json.dumps(filed["call_log"], ensure_ascii=False),
        "{{EV_NEEDLES}}": json.dumps({"ok_0": needles["ok_0_needle_since_0759"],
                                      "percent_error": needles["percent_error_needle_same_window"]},
                                     ensure_ascii=False),
        "{{RING_CALLS_A4}}": str(a4.get("calls", "?")),
        "{{RING_REFUSED_A4}}": str(len(a4.get("refusals", []))),
        "{{RING_IDEMPOTENT_A4}}": str(len(a4.get("idempotent", []))),
    }


def main() -> int:
    stage = "post" if "--stage" in sys.argv and "post" in sys.argv else "pre"
    text = REPORT.read_text(encoding="utf-8")
    if stage == "post" and "{{RING_CLOSE}}" not in text:
        # 上一轮实测：token 已被替换时重跑 fill 会"filled=1 tokens_left=0"却一个字没改 —— 静默 no-op 的控件
        raise SystemExit("报告里没有 {{RING_CLOSE}}（已填过？）⇒ 拒绝 no-op 式重跑；"
                         "要更新回执先把 §6.3 换回占位，或直接改本件为按段落幂等替换")

    gate = tail_needle(LOGS / "r11_gate_a3.log", "CONCLUSION")
    pytest_tail = tail_needle(LOGS / "r11_pytest_a2.log", "pytest_rc=")
    if pytest_tail != "pytest_rc=0":
        raise SystemExit(f"pytest 终版非全绿：{pytest_tail}")
    pytest_sum = summary_line(LOGS / "r11_pytest_a2.log")
    count = int(re.search(r"(\d+) passed", pytest_sum).group(1))
    delta = count - BASELINE_PYTEST
    # 增量必须逐条点名并合账：新锁 + 拆出的边界反例 + corpus 里新 op 的每对一条参数化用例
    lock_src = (ROOT / "tests" / "test_generic_class_r11.py").read_text(encoding="utf-8")
    locks = len(re.findall(r"(?m)^def test_", lock_src))
    pairs = len(json.loads((ROOT / CORPUS_REL).read_text(encoding="utf-8"))["tests"])
    boundary_extra = 1
    if locks + pairs + boundary_extra != delta:
        raise SystemExit(f"收集数增量对不齐：delta={delta} != locks {locks} + pairs {pairs} + 反例 {boundary_extra}")
    led = ledger_counts()
    close_leg = close_leg_tokens()
    st = ring("start")
    close = ring("close")
    matrix = tail_needle(LOGS / "r11_locks_a8.out", "CONCLUSION")
    mtx = json.loads((HERE / "logs" / "r11_locks_matrix_a2.json").read_text(encoding="utf-8"))
    lb = dict(mtx["load_bearing"])
    lb["L6"] = {"n_failed": mtx["cases"]["L6"]["n_failed"]}

    fills = {
        "{{CORPUS_TOTAL}}": str(sum(len(json.loads(p.read_text(encoding="utf-8"))["tests"])
                                    for p in sorted((ROOT / "corpus").glob("*.json")))),
        "{{MATRIX}}": f"`{matrix}`",
        "{{L1}}": str(lb["L1"]["n_failed"]), "{{L2}}": str(lb["L2"]["n_failed"]),
        "{{L3}}": str(lb["L3"]["n_failed"]), "{{L4}}": str(lb["L4"]["n_failed"]),
        "{{L5}}": str(lb["L5"]["n_failed"]), "{{L6}}": str(lb["L6"]["n_failed"]),
        "{{PYTEST}}": f"`{pytest_sum}`（{pytest_tail}）",
        "{{NATIVE}}": "`" + tail_needle(LOGS / "r11_native_a2.log", "Total: 47") + "`",
        "{{E2E}}": "`" + tail_needle(LOGS / "r11_e2e_a2.log", "[e2e-golden] summary:") + "`",
        "{{GATE}}": f"`{gate}`",
        "{{PYTEST_COUNT}}": str(count),
        "{{PYTEST_DELTA}}": str(delta), "{{NEW_LOCKS}}": str(locks), "{{NEW_PAIRS}}": str(pairs),
        "{{LEDGER_HEADERS}}": str(led["headers"]), "{{LEDGER_UNIQUE}}": str(led["unique"]),
        "{{LEDGER_OPEN}}": str(led["open"]), "{{LEDGER_OPEN_WIDE}}": str(led["open_wide"]),
        "{{JUDGE_FACE}}": str(led["judge"]), "{{JUDGE_IDS}}": "、".join("BUG-" + i for i in led["judge_ids"]), "{{PRODUCT_FACE}}": str(led["product"]),
        "{{SEV_HIGH}}": str(led["sev"].get("high", 0)),
        "{{SEV_MEDIUM}}": str(led["sev"].get("medium", 0)),
        "{{SEV_LOW}}": str(led["sev"].get("low", 0)),
        "{{FIXED_PREV}}": str(led["prev_fixed"]), "{{FIXED_NOW}}": str(led["fixed"]),
        "{{AMEND_PREV}}": str(led["prev_amend"]), "{{AMEND_NOW}}": str(led["amend"]),
        "{{RING_ROWS}}": str(st.get("tree_readback", {}).get("rows", "?")),
        "{{RING_BRANCHES}}": str(st.get("tree_readback", {}).get("branches", "?")),
        "{{RING_LEAVES}}": str(st.get("tree_readback", {}).get("leaves", "?")),
        "{{RING_GENERAL}}": str(len(st.get("tree_readback", {}).get("general", []))),
        "{{RING_BOUNDARY}}": str(len(st.get("tree_readback", {}).get("boundary", []))),
        "{{RING_BOUNDARY_NA}}": str(st.get("boundary_plan", {}).get("declared_na", "?")),
        "{{RING_FACES_MISSING}}": str(len(st.get("faces_missing", []))),
        "{{RING_CALLS}}": str(st.get("calls", "?") if "calls" in st else len(st.get("nodes", {}) or {})),
        "{{RING_REFUSED}}": str(len(st.get("refusals", []))),
        "{{RING_BENIGN}}": str(len(st.get("benign", []))),
    }
    if close:
        gates = (close.get("loop_drive") or {}).get("gates") or {}
        fills["{{RING_CLOSE}}"] = (
            "收口回执（逐字取自 `.fist-loop-20260929/ring_r11_close.json`，即修针后的 **a4** 复跑；a3 的读数见 §6.4）："
            f"根 `T0r117` 终态 **{close.get('root_final')}**；rollup `{json.dumps(close.get('rollup'), ensure_ascii=False)}`；"
            f"待领取叶 {close.get('pending_leaves') or pending_from_log()}；"
            f"calls={close.get('calls')} refused={len(close.get('refusals', []))} "
            f"idempotent={len(close.get('idempotent', []))} benign={len(close.get('benign', []))}；"
            f"本窗口 `call_log` 红行（`ok=0` 口径）{close.get('call_log_error_rows')} 行，"
            f"旧口径 `%__error__%` 同窗 {close.get('call_log_error_rows_old_needle')} 行"
            "（两口径并印是 §6.4 里 BUG-131 的修法，恒 0 那把尺不再单独承重）；"
            f"枝干终态 `{json.dumps(close.get('branch_final'), ensure_ascii=False)}`；"
            "入口四道门观测（四条各自逐字取自对应日志；不合并成一份再序列化后的「引用」——那串在证据里根本不存在）："
            + "、".join(f"`{v}`" for v in (close.get("entry_gate", {}).get("observed") or {}).values()
                        if isinstance(v, str)) + "。"
            + "每叶步骤按 (状态, specs 行数) 分派，交付物写成服务端要求的五段式，"
            "因此 `docs_check=True` 的 `verify` 是原样通过的（未关门禁）。"
            f"组合环的服务端推进腿在本会话内走完：九格门 `{json.dumps(gates, ensure_ascii=False)}`，"
            f"回执 `.fist-loop-20260929/r11_loop_drive.json`（`round` 0→1、`next_mode` 与登记的 steps 逐位相同）。")
    else:
        fills["{{RING_CLOSE}}"] = ("环尚未收口 —— 本行由 `fill_r11_report.py --stage post` 在收批门通过后替换，"
                                   "替换后必须重跑 `verify_r11_report.py`（核验件记 report_bytes，字节变了门就红）。")

    fills.update(close_leg)
    for k, v in fills.items():
        text = text.replace(k, v)
    left = sorted(set(re.findall(r"\{\{[A-Z_0-9]+\}\}", text)))
    if left:
        print("TOKENS_LEFT", json.dumps(left, ensure_ascii=False))
        return 1
    tmp = REPORT.with_suffix(".md.tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(REPORT)
    print(f"FILLED stage={stage} bytes={REPORT.stat().st_size} "
          f"lines={len(REPORT.read_text(encoding='utf-8').splitlines())} pytest_count={count}")
    print("CONCLUSION filled=1 tokens_left=0 close_rendered=" + str(bool(close)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
