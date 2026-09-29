"""R13 入口的第一张单：泛型类型别名（`SYNTAX/02-type-annotations.md:92` 承诺）不代入、不判，且状态表标着"✅ 完整"。

沿用既往轮的入账纪律：
 · 先取号再写台账（编号由服务端定，脚本不手写 `## BUG-NN`）；
 · 幂等守卫：起跑先按 reported_key 查账本，已存在 ⇒ 只指认不重发；
 · 拒绝按形状识别（`__error__` / RPC-ERROR），不看 `ok` 字面；
 · 三向对照：md 条目 ↔ `bug_list` 回读 ↔ `call_log` 的 report_bug 行；
 · 答复只印元信息，不读 .env、不探测任何凭据。
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LEDGER = ROOT / "memory" / "bugs.md"
OUT = HERE / "file_r13_alias_bug.json"
NS = "cypy-loop-20260929"
AGENT = "cypy-selfdrive-agent"

CARD = {
    "key": "R13-GENERIC-TYPE-ALIAS-NO-SUBST",
    "severity": "medium",
    "summary": (
        "[generics:alias] 泛型类型别名 `type Result<T> = tuple<bool, T>` 收下但不代入不判："
        "四组成对反例（内层类型错/标志位错/两位错/未知类型名）全 0 诊断，"
        "而 `SYNTAX_IMPLEMENTATION_STATUS.md:330` 把 `02-type-annotations.md` 标成「✅ 完整/无」"
    ),
    "detail": (
        "实测（`.fist-loop-20260929/probe_r13_type_alias.py` 走 `scripts/omega_gate.py` 同一份 `execute()`，"
        "日志 `.fist-loop-20260929/logs/r13_probe_alias_a2.out`，12 形）：\n"
        ' (a) `G_wrong_inner`：`type Result<T> = tuple<bool, T>` + `bad: Result<int> = (True, "x")` ⇒ errors=0；\n'
        " (b) `H_wrong_flag`：同别名 + `bad: Result<int> = (1, 2)`（首项该是 bool）⇒ errors=0；\n"
        ' (c) `J_alias_wrong_kind`：`type Pair<T> = tuple<T, T>` + `bad: Pair<int> = (1, "s")` ⇒ errors=0；\n'
        " (d) `I_unknown_in_alias`：`bad: Result<NotAType> = (True, 1)`（类型实参不存在）⇒ errors=0；\n"
        " (e) `K_alias_arity_use`：`bad: Pair = (1, 2)`（用了别名却不给类型实参）⇒ errors=0；\n"
        " (f) `C_alias_bound_use`：定义侧写约束界 `type Num<T: int | float> = tuple<bool, T>` 直接解析失败"
        "（`Expected IDENTIFIER, got COLON at 1:11`）⇒ 手册「类型别名」一节只给了不带界的形态，带界形态既不接受也不给"
        "「不支持」的硬拒文案，与 BUG-120 是同一族定义侧冒号形态、不同使用点。\n"
        "正向对照：`A_basic_alias`（非泛型别名）与 `B/D/E/F`（泛型别名 + 正确实参 + codegen 出 31 行产物）都 0 诊断 "
        "⇒ 不是「整条语法没实现」而是「收下但参数从不代入」，所以错误程序与正确程序得到同一个读数。\n"
        "机制：`type X<...> = ...` 走 `TypeAlias` 一类的登记路径，展开时不建 `GenericType` 绑定 ⇒ "
        "注解位看到的仍是别名右端的**未参数化**形状，`tuple<bool, T>` 里的 `T` 没有替换点，"
        "后续 tuple 元素检查拿到的是裸 `T`（或 object）⇒ 判不出来也不报。\n"
        "账面一致性：`SYNTAX_IMPLEMENTATION_STATUS.md:330` 那行写「✅ 完整 | 无」——本单入账后同时改这行，"
        "不改就会重复 R11 的「文档面·主张宽于判据」形状。\n"
        "同族已开口、修法需同批的：BUG-135（构造位不写类型实参 ⇒ 不推断）、BUG-128（struct 方法不代入）、"
        "BUG-122（类型实参不判存在性，(d) 正是它在别名路径上的同形）。"
    ),
}


def utc_z() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def refused(res) -> bool:
    if isinstance(res, dict):
        if "__error__" in res or "error" in res or res.get("ok") is False:
            return True
        if str(res.get("code", "")).startswith("-32"):
            return True
    return False


def headers():
    text = LEDGER.read_text(encoding="utf-8")
    return text, re.findall(r"(?m)^## (BUG-\d+)", text)


def counts(text: str) -> dict:
    blocks = [b for b in re.split(r"(?m)^(?=## BUG-)", text) if b.startswith("## BUG-")]
    open_blocks = [b for b in blocks if not re.search(r"(?m)^### (FIXED|DUPLICATE|OUT|WONT)", b)]
    narrow = [b for b in blocks if not re.search(r"(?m)^### (FIXED|DUPLICATE)", b)]
    return {
        "headers": len(blocks),
        "open_ring": len(open_blocks),
        "open_narrow": len(narrow),
        "fixed": len(re.findall(r"(?m)^### FIXED", text)),
    }


def main() -> int:
    started = utc_z()
    before_text, before_ids = headers()
    rep = {
        "started_z": started,
        "ns": NS,
        "before": counts(before_text),
        "ledger_last_id": before_ids[-1] if before_ids else None,
        "filed": [],
        "skipped_existing": [],
        "refusals": [],
    }
    if CARD["key"] in before_text:
        rep["skipped_existing"].append(
            {"key": CARD["key"], "why": "账本已含该 reported_key ⇒ 不重发"}
        )
        skip_only = True
    else:
        skip_only = False

    sys.path.insert(0, str(ROOT / "scripts"))
    os.environ["FIST_NAMESPACE"] = NS
    os.environ["FIST_SERVER_CWD"] = str(ROOT).replace("\\", "/")
    import fist

    c = fist.FistClient(timeout=240)
    if not skip_only:
        res = c.call(
            "report_bug",
            {
                "project_dir": ".",
                "summary": CARD["summary"],
                "severity": CARD["severity"],
                "detail": CARD["detail"] + f"\n- reported_key: {CARD['key']}",
                "reported_by": AGENT,
                "publish_task": False,
            },
        )
        rec = {"key": CARD["key"], "reply_verbatim": json.dumps(res, ensure_ascii=False)[:400]}
        (rep["refusals"] if refused(res) else rep["filed"]).append(rec)
    lst = c.call("bug_list", {"project_dir": ".", "limit": 400})
    # `bug_list` 回读的是 **dict**（`{count, bugs: [...]}`）不是裸 list —— 上一版按 list 假设，
    # 把"三向对照"的第三条腿读成了恒 False（形状假设错了先判自己的尺）。
    rows = (
        lst.get("bugs") or [] if isinstance(lst, dict) else (lst if isinstance(lst, list) else [])
    )
    rep["bug_list_shape"] = type(lst).__name__
    rep["bug_list_count_field"] = lst.get("count") if isinstance(lst, dict) else len(rows)
    rep["bug_list_rows"] = len(rows)
    hit = [r for r in rows if CARD["summary"][:24] in json.dumps(r, ensure_ascii=False)]
    rep["bug_list_has_new_summary"] = bool(hit)
    rep["bug_list_row_for_card"] = json.dumps(hit[:1], ensure_ascii=False)[:300]
    c.close()

    after_text, after_ids = headers()
    rep["after"] = counts(after_text)
    rep["new_ids"] = [i for i in after_ids if i not in before_ids]
    rep["key_present_after"] = CARD["key"] in after_text
    con = sqlite3.connect(f"file:{ROOT / 'fist-mbt.db'}?mode=ro", uri=True)
    rep["call_log"] = {
        "rows": con.execute("select count(*) from call_log where ts>=?", (started,)).fetchone()[0],
        "error_rows_ok_needle": con.execute(
            "select count(*) from call_log where ts>=? and ok=0", (started,)
        ).fetchone()[0],
        "error_rows_old_needle": con.execute(
            "select count(*) from call_log where ts>=? and result_json like '%__error__%'",
            (started,),
        ).fetchone()[0],
        "report_bug_rows": con.execute(
            "select count(*) from call_log where ts>=? and tool='report_bug'", (started,)
        ).fetchone()[0],
    }
    con.close()
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in rep["filed"] + rep["refusals"]:
        print(
            ("FILED " if r in rep["filed"] else "REFUSED "),
            r["key"],
            "|",
            r["reply_verbatim"][:220],
        )
    print(
        f"CONCLUSION filed={len(rep['filed'])} skipped={len(rep['skipped_existing'])} "
        f"refused={len(rep['refusals'])} new_ids={rep['new_ids']} "
        f"before={json.dumps(rep['before'], ensure_ascii=False)} after={json.dumps(rep['after'], ensure_ascii=False)} "
        f"bug_list_shape={rep['bug_list_shape']} count={rep['bug_list_count_field']} "
        f"has_new_summary={rep['bug_list_has_new_summary']} call_log={json.dumps(rep['call_log'], ensure_ascii=False)}"
    )
    three_way = (
        rep["bug_list_has_new_summary"]
        and rep["key_present_after"]
        and rep["call_log"]["report_bug_rows"] >= 1
    )
    if skip_only:
        three_way = rep["bug_list_has_new_summary"] and rep["key_present_after"]
    return (
        0
        if not rep["refusals"]
        and three_way
        and (len(rep["filed"]) == len(rep["new_ids"]) or skip_only)
        else 1
    )


if __name__ == "__main__":
    sys.exit(main())
