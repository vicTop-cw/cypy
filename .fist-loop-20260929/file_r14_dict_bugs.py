"""R14 的两张新单：字典字面量不推断类型（正身）+ R13 手册里一条悬空的用例路径（账面完整性）。

纪律沿用既往轮：先取号再写正文（编号由服务端定）、按 `reported_key` 幂等、
拒绝按形状识别且逐字不截断、三向对照（md 条目 ↔ `bug_list` 回读 ↔ `call_log` 的 report_bug 行）、
正文里的数一律从证据件反解（缺件即拒跑，不许凭记忆写数）。
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
OUT_TMPL = "file_r14_dict_bugs_{tag}.json"
NS = "cypy-loop-20260929"
AGENT = "cypy-selfdrive-agent"
PROBE_BEFORE = HERE / "logs" / "r14_dict_probe_a2.json"
PROBE_AFTER = HERE / "logs" / "r14_dict_probe_b1.json"
sys.path.insert(0, str(HERE))
import probe_r14_dict as pr  # noqa: E402

LOCK_FILE = "tests/test_dict_elements_r14.py"
SPEC_FILE = "corpus/cypy.dict.elements.json"


def utc_z() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def counts(text: str) -> dict:
    return {
        "headers": len(re.findall(r"(?m)^## BUG-\d+", text)),
        "open": len(re.findall(r"(?m)^## BUG-\d+ \[[^\]]+\] \[[^\]]+\] OPEN", text)),
        "fixed": len(re.findall(r"(?m)^### FIXED", text)),
    }


def readings() -> dict:
    for p in (PROBE_BEFORE, PROBE_AFTER, ROOT / SPEC_FILE):
        if not p.exists():
            raise SystemExit(f"证据件缺失：{p.name} ⇒ 不起跑")
    before = json.loads(PROBE_BEFORE.read_text(encoding="utf-8"))
    after = json.loads(PROBE_AFTER.read_text(encoding="utf-8"))
    spec = json.loads((ROOT / SPEC_FILE).read_text(encoding="utf-8"))
    n_locks = len(re.findall(r"(?m)^def test_", (ROOT / LOCK_FILE).read_text(encoding="utf-8")))
    must_red, must_green = list(pr.MUST_RED), list(pr.MUST_GREEN)
    # 「该红却静默」只能在**探针声明的 MUST_RED** 里数：把 G 栏（设计上该绿）也算进静默清单，
    # 就等于宣称"这些也是缺陷"—— R13 的账本段落正为同类混栏返过工。
    silent_before = sorted(
        k for k in must_red if before[k]["stage"] == "ok" and before[k]["n"] == 0
    )
    now_red = sorted(k for k in silent_before if after[k]["stage"] == "ok" and after[k]["n"] > 0)
    still_silent = sorted(k for k in silent_before if k not in now_red)
    kept_green = sorted(k for k in must_green if after[k]["stage"] == "ok" and after[k]["n"] == 0)
    broke_green = sorted(set(must_green) - set(kept_green))
    if still_silent or broke_green:
        raise SystemExit(f"栏位与实得不一致 ⇒ 不取数：仍静默={still_silent} 该绿却红={broke_green}")
    return {
        "before_cases": len(before),
        "after_cases": len(after),
        "silent_before": silent_before,
        "now_red": now_red,
        "still_silent": still_silent,
        "green_now": kept_green,
        "must_green": len(must_green),
        "must_red": len(must_red),
        "spec_cases": len(spec["tests"]),
        "spec_fp": spec["fingerprint"],
        "locks": n_locks,
        "first_diag": next(
            (
                v["errs"][0]
                for k, v in after.items()
                if k == "D01_value_wrong" and v["n"] and v["errs"]
            ),
            "",
        ),
    }


R = readings()

CARDS = [
    {
        "key": "R14-DICT-LITERAL-NO-INFER",
        "severity": "high",
        "summary": (
            "[typing:container] 字典字面量不推断类型 ⇒ `dict<K, V>` 的键位与值位永远无从判定："
            '`let x: dict<str, int> = {"a": "b"}` 等 7 形 0 诊断（含返回位、嵌套位、别名位、dict 套 dict）'
        ),
        "detail": (
            "\n".join(
                [
                    f"实测口径：`.fist-loop-20260929/probe_r14_dict.py` 走 `scripts/omega_gate.py` 同一份"
                    f" `execute()`；改动前基线 `.fist-loop-20260929/logs/{PROBE_BEFORE.name}`"
                    f"（{R['before_cases']} 形，读取通道对照 `CTRL_scalar_mismatch`/`CTRL_list_elem_wrong`"
                    " 两条都先红 ⇒ 下面的 0 不是观测口径坏），"
                    f"改动后 `.fist-loop-20260929/logs/{PROBE_AFTER.name}`（{R['after_cases']} 形）。",
                    "改动前**该红却静默**的形（逐条）："
                    + ", ".join(R["silent_before"])
                    + " —— 覆盖值位、键位、返回位、嵌套 `dict<str, list<int>>`、"
                    "`type Count = dict<str, int>` 别名、`dict<str, dict<str,int>>` 套娃、"
                    "以及 `{True: 1}` 这种键位标量错配。",
                    "机制（实测定位，不是猜测）：`cypyc/analyzer/type_checker.py` 的 `_visit` 按 "
                    "`_visit_<kind>` 派发，而 **没有** `_visit_DictLiteral` ⇒ 落到 `_visit_children` "
                    "返回 `None` ⇒ `_visit_LetStmt`/`_visit_ReturnStmt` 的 "
                    "`if declared_type and value_type` 整条不成立 ⇒ 声明侧的键值位连「实得类型」都没有。"
                    "上一轮（R13）把 `dict` 排除在 `_ELEMENT_CHECKED_CONTAINERS` 之外，正是为了让这条"
                    "不判的边界有文字依据 —— 排除是对的，但排除的理由（字面量不推断）本身就是缺陷。",
                    "修法：新增 `_visit_DictLiteral` + `_slot_lub`（键位/值位各自求「最宽可表类型」："
                    "同形取该类型并保留参数、数值串取 `bool→int→float→double` 最宽、其余塌 `object`），"
                    "`dict` 进入 `_ELEMENT_CHECKED_CONTAINERS`，"
                    "诊断文案对 dict 点名 `Dict key`/`Dict value` 而不是 `element 1/2`。",
                    f"本单验证：改动后同一探针 {len(R['now_red'])} 形全部转红，首条文案（逐字）："
                    + R["first_diag"]
                    + f"；仍绿 {len(R['green_now'])} 形（占位、混形塌位、单向加宽、用户类保守集、"
                    "无声明的 let、参数注解位）⇒ 收紧没有把该放行的扫进红堆。",
                    f"判据与锁：Ω-spec `{SPEC_FILE}`（{R['spec_cases']} 对，指纹 {R['spec_fp']}）"
                    f"+ 回归锁 `{LOCK_FILE}`（{R['locks']} 支）；规范依据 "
                    "`SYNTAX/02-type-annotations.md`「字典字面量的键值位判定（R14 补）」规则 1-6。",
                    "同轮收紧的两条 R13 豁免锁（断言反向，不是删除）："
                    "`tests/test_container_elements_r13.py::test_dict_value_slot_is_required_since_r14` 与 "
                    "`::test_dict_is_now_in_the_checked_container_list`；"
                    "R13 语料 `cypy.container.elements` 里那条 dict 豁免案例一并由 `errors=0` 改为 "
                    "`errors=1`，该份 spec 因此重封指纹。",
                    "未覆盖（本单不粉饰）：混形塌位仍静默 —— `dict<str, int>` 收 "
                    '`{"a": 1, "b": "c"}` 值位塌成 object 后放行（手册规则 6 钉成正向对照）；'
                    "字典推导式、`for k, v in d` 解包位、`d[k] = v` 写入位都不走字面量推断这条路，"
                    "本单不判；联合形态别名的成员元素位仍不判（`_type_in_union` 只比成员名，另计入开项）。",
                ]
            )
        ),
    },
    {
        "key": "R14-MANUAL-DANGLING-TEST-PATH",
        "severity": "low",
        "summary": (
            "[docs] `SYNTAX/02-type-annotations.md` R13 节把「锁死用例」写成 "
            "`tests/regression/test_container_elements_r13.py`，该路径不存在（实际在 `tests/` 下）"
            "⇒ 手册指路失败，且当时没有任何判据覆盖文档里的路径引用"
        ),
        "detail": "\n".join(
            [
                "活证据（file:line）：该手册 R13 节末句原写 "
                "那句「锁死用例见 tests/regression/test_container_elements_r13.py」，"
                "而 `tests/regression/` 目录里只有 `test_corpus_pairs.py`"
                "（`ls tests/regression/` 可读回）⇒ 按手册去找会一无所获。",
                "为什么当时没被抓出来：R13 的引用核验件（`verify_r13_report.py`）只校"
                "「报告点名的文件是否存在」，手册本身不在它的检查面里；"
                "也没有一条锁把「手册引用的仓内路径都存在」当判据 ⇒ 文档引用是无人认领的一类主张。",
                "修法：手册该行改为实际路径并同句点名 R14 的锁文件；"
                "新增会红的锁 `tests/test_dict_elements_r14.py::test_manual_revokes_the_r13_dict_exemption`"
                "断言手册引用的就是这份文件本身（`Path(__file__).name` 对表，不是抄字符串）。",
                "范围声明：本轮只把「手册引用的这份具体路径」钉进判据；"
                "全量文档路径存在性扫描（SYNTAX/ 全部 + CHANGELOG + STATUS）仍是一件没做的事，"
                "记在这里而不是假装已闭合。",
            ]
        ),
    },
]


def refused(res) -> bool:
    txt = json.dumps(res, ensure_ascii=False)
    return "__error__" in txt or txt.startswith("RPC-ERROR") or "RPC-ERROR" in txt


def main() -> int:
    tag = sys.argv[1] if len(sys.argv) > 1 else "a1"
    OUT = HERE / OUT_TMPL.format(tag=tag)
    started = utc_z()
    before_text = LEDGER.read_text(encoding="utf-8")
    rep = {
        "started_z": started,
        "ns": NS,
        "readings": {k: v for k, v in R.items() if k != "first_diag"},
        "first_diag": R["first_diag"],
        "before": counts(before_text),
        "filed": [],
        "skipped_existing": [],
        "refusals": [],
    }
    keys = [c["key"] for c in CARDS]
    present = [k for k in keys if k in before_text]
    if present:
        print(f"幂等守卫：{present} 已在账上 ⇒ 本脚本不重发这些条")

    sys.path.insert(0, str(ROOT / "scripts"))
    os.environ["FIST_NAMESPACE"] = NS
    os.environ["FIST_SERVER_CWD"] = str(ROOT).replace("\\", "/")
    import fist

    c = fist.FistClient(timeout=240)
    for card in CARDS:
        if card["key"] in before_text:
            rep["skipped_existing"].append(card["key"])
            continue
        detail = card["detail"] + f"\n- reported_key: {card['key']}"
        residue = re.findall(r"\{[A-Za-z_][A-Za-z0-9_]*\}", detail)
        if residue:
            raise SystemExit(f"正文残留未插值占位 {residue}（{card['key']}）⇒ 不落盘不提交")
        res = c.call(
            "report_bug",
            {
                "project_dir": ".",
                "summary": card["summary"],
                "severity": card["severity"],
                "detail": detail,
                "reported_by": AGENT,
                "publish_task": False,
            },
        )
        rec = {"key": card["key"], "reply_verbatim": json.dumps(res, ensure_ascii=False)}
        (rep["refusals"] if refused(res) else rep["filed"]).append(rec)
        print(f"{card['key']} -> {rec['reply_verbatim'][:220]}")

    lst = c.call("bug_list", {"project_dir": ".", "limit": 400})
    bugs = lst.get("bugs") if isinstance(lst, dict) else lst
    rep["bug_list_shape"] = type(lst).__name__
    rep["bug_list_count"] = lst.get("count") if isinstance(lst, dict) else len(bugs or [])
    after_text = LEDGER.read_text(encoding="utf-8")
    rep["after"] = counts(after_text)
    new_ids = sorted(
        set(re.findall(r"(?m)^## (BUG-\d+)", after_text))
        - set(re.findall(r"(?m)^## (BUG-\d+)", before_text))
    )
    rep["new_ids"] = new_ids
    rep["key_to_id"] = {
        card["key"]: bid
        for card in CARDS
        for bid, body in re.split(r"(?m)^## (BUG-\d+)", after_text) and []
    }
    # 编号↔键的对照从台账反解（正文里写"BUG-141"之前必须先知道服务端给的是几号）
    parts = re.split(r"(?m)^(?=## BUG-\d+)", after_text)
    id_of = {}
    for b in parts:
        m = re.match(r"## (BUG-\d+)", b)
        if m:
            for card in CARDS:
                if f"reported_key: {card['key']}" in b:
                    id_of[card["key"]] = m.group(1)
    rep["id_of_key"] = id_of
    rep["summaries_in_bug_list"] = {
        card["key"]: any(
            card["summary"][:36] in json.dumps(b, ensure_ascii=False) for b in (bugs or [])
        )
        for card in CARDS
        if card["key"] not in present
    }
    db = ROOT / "fist-mbt.db"
    rep["db_path"] = str(db.relative_to(ROOT)) + ("(exists)" if db.exists() else "(MISSING)")
    if db.exists():
        con = sqlite3.connect(str(db))
        rep["call_log_report_bug_rows"] = con.execute(
            "select count(*) from call_log where tool='report_bug' and ns=?", (NS,)
        ).fetchone()[0]
        rep["call_log_error_rows"] = con.execute(
            "select count(*) from call_log where ok=0 and ns=?", (NS,)
        ).fetchone()[0]
        con.close()
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    need = "call_log_report_bug_rows" in rep and "bug_list_count" in rep
    ok = (
        need
        and not rep["refusals"]
        and len(new_ids) == len(rep["filed"])
        and all(rep["summaries_in_bug_list"].values())
        and len(id_of) == len(rep["filed"]) + len(rep["skipped_existing"])
        and rep["after"]["headers"] == rep["before"]["headers"] + len(rep["filed"])
        and rep["bug_list_count"] == rep["after"]["headers"]
        and rep["call_log_report_bug_rows"] >= len(rep["filed"])
    )
    print(
        f"CONCLUSION r14_filed tag={tag} filed={len(rep['filed'])} "
        f"skipped={len(rep['skipped_existing'])} refused={len(rep['refusals'])} "
        f"new_ids={new_ids} id_of_key={id_of} bug_list_count={rep['bug_list_count']} "
        f"headers={rep['before']['headers']}->{rep['after']['headers']} "
        f"report_bug_rows={rep.get('call_log_report_bug_rows')} db={rep.get('db_path')} "
        f"three_way_ok={ok} out={OUT.name}"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
