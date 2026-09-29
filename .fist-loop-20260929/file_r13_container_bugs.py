"""R13 的三张新单 + BUG-136 改判：把"别名不代入"这个错机制换成实测出来的三条真根因。

纪律沿用既往轮：先取号再写正文（编号由服务端定）、按 reported_key 幂等、拒绝按形状识别且
逐字不截断、三向对照（md 条目 ↔ `bug_list` 回读 ↔ `call_log` 的 report_bug 行）、
正文里的数一律从证据件反解（不手加）。
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
# 回执按 tag 落唯一名：门与证据同名会被复跑原地覆盖（本轮 a2 就把 a1 那份盖掉了，见报告 §6.4）
OUT_TMPL = "file_r13_container_bugs_{tag}.json"
NS = "cypy-loop-20260929"
AGENT = "cypy-selfdrive-agent"
PROBE_BEFORE = HERE / "logs" / "r13_alias_paired_a1.json"
PROBE_AFTER = HERE / "logs" / "r13_container_probe_b2.json"
ISOLATION = HERE / "logs" / "r13_nested_alias_fp_a1.json"


def utc_z() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def counts(text: str) -> dict:
    return {
        "headers": len(re.findall(r"(?m)^## BUG-\d+", text)),
        "open": len(re.findall(r"(?m)^## BUG-\d+ \[[^\]]+\] \[[^\]]+\] OPEN", text)),
        "fixed": len(re.findall(r"(?m)^### FIXED", text)),
    }


def readings() -> dict:
    """从两份探针件反解出正文要用的数，缺件即拒（不许凭记忆写数）。"""
    for p in (PROBE_BEFORE, PROBE_AFTER, ISOLATION):
        if not p.exists():
            raise SystemExit(f"证据件缺失：{p.name} ⇒ 不起跑")
    before = json.loads(PROBE_BEFORE.read_text(encoding="utf-8"))
    after = json.loads(PROBE_AFTER.read_text(encoding="utf-8"))
    iso = json.loads(ISOLATION.read_text(encoding="utf-8"))
    silent_before = sorted(k for k, v in before.items() if v["stage"] == "ok" and v["n"] == 0)
    now_red = sorted(
        k for k in silent_before if k in after and after[k]["stage"] == "ok" and after[k]["n"] > 0
    )
    still_silent = sorted(
        k for k in silent_before if k in after and after[k]["stage"] == "ok" and after[k]["n"] == 0
    )
    green_now = sorted(k for k, v in after.items() if v["stage"] == "ok" and v["n"] == 0)
    return {
        "before_cases": len(before),
        "after_cases": len(after),
        "silent_before": len(silent_before),
        "now_red": now_red,
        "still_silent": still_silent,
        "green_now": green_now,
        "iso_identical": all(v["with_new_judge"] == v["with_new_judge_off"] for v in iso.values()),
        "iso_cases": len(iso),
        "fp_verbatim": iso["Triple_ok"]["with_new_judge_off"][0],
    }


R = readings()


def _detail_join(lines: list) -> str:
    return "\n".join(lines)


CARDS = [
    {
        "key": "R13-CONTAINER-ELEMENT-NO-CHECK",
        "severity": "high",
        "summary": (
            "[typing:container] 容器元素位整体不判：`cypyc/analyzer/type_checker.py` 的"
            "「容器同名即放行」分支把元素类型也一起吞了 ⇒ "
            '`let bad: tuple<bool, int> = (True, "x")` / `list<int> = ["s"]` / '
            "`tuple<int, int> = (1,)` / 返回位同形 全部 0 诊断"
        ),
        "detail": _detail_join(
            [
                f"实测口径：`.fist-loop-20260929/probe_r13_container.py` 走 `scripts/omega_gate.py` 同一份"
                f" `execute()`；改动前基线 `.fist-loop-20260929/logs/{PROBE_BEFORE.name}`"
                f"（{R['before_cases']} 形），改动后 `.fist-loop-20260929/logs/{PROBE_AFTER.name}`"
                f"（{R['after_cases']} 形，判据自带 must_be_red / must_stay_green 两组门）。",
                "改动前**该红却静默**的形（读取通道对照 `CTRL_scalar_mismatch` 已先证非静默，"
                '所以这些 0 不是观测口径坏）：标量位 `let n: int = "s"` 会红，'
                '但容器位 `tuple<bool,int> ← (True,"x")`、`tuple<bool,int> ← (1,2)`、'
                '`list<int> ← ["s"]`、`list<list<int>> ← [["s"]]`、`tuple<int,int> ← (1,)`、'
                "以及返回位两条同形，全部 errors=0。",
                "机制（实测定位，不是猜测）：`cypyc/analyzer/type_checker.py:889` 与 `:972` 两条分支"
                " 「声明与值同名容器 ⇒ 采用声明类型」直接 `return`/登记，从不比 `generic_params`；"
                "两条分支自己的注释只点名三种该放行的形态（空容器构造器、嵌套无参、含 None/object 参数），"
                "所以是实现宽于意图，不是设计如此。",
                "修法与本单验证：新增 `_slot_incompatible`/`_first_bad_element`/"
                "`_check_container_elements`（`type_checker.py:4035` 起），两条分支改为"
                "「登记声明类型 + 记一条元素位诊断」；保守集只允许两侧都是闭合标量名时报错，"
                "用户类/trait/subtype 一律放行。规范依据先落在 `SYNTAX/02-type-annotations.md`"
                "「容器元素位判定（R13 补）」规则 1-6。",
                f"改动后同探针：原本静默的 {len(R['now_red'])} 形转红（逐形点名见本脚本 stdout），"
                f"其余 {len(R['green_now'])} 形仍绿 ⇒ 占位四形态没有被打断。",
                '未覆盖（本单不粉饰）：`dict<str,int> ← {"a":"b"}` 仍静默 —— 字典字面量根本不推断类型'
                "（`_visit` 对 DictLiteral 返回 None），另立一条；`list<Dog> ← [Cat()]` 也仍静默，"
                "属规则 5 的保守集选择。",
            ]
        ),
    },
    {
        "key": "R13-NESTED-ALIAS-NOT-EXPANDED",
        "severity": "high",
        "summary": (
            "[generics:alias] 别名套别名只代入一层 ⇒ **正确程序被拒**（假阳性）："
            "`type Pair<T> = tuple<T, T>` + `type Triple<T> = Pair<Pair<T>>` 之后"
            " `let ok: Triple<int> = ((1, 2), (3, 4))` 报 "
            "`Type mismatch: expected Pair[Pair[int]], got tuple[tuple[int, int], tuple[int, int]]`"
        ),
        "detail": _detail_join(
            [
                f"身份隔离（先证不是别家改动带来的）：`.fist-loop-20260929/logs/{ISOLATION.name}` —— "
                f"把本轮新加的 `_check_container_elements`  monkeypatch 成空操作再跑同一形状，"
                f"诊断逐字不变（{R['iso_cases']} 形全等 identical={R['iso_identical']}）"
                "⇒ 这条假阳性在本轮改动之前就存在，与本单的容器判定无关。",
                "假阳性文案（逐字，取自该件 `Triple_ok.with_new_judge_off[0]`）："
                + R["fp_verbatim"],
                "正向对照：同一件里 `type Pair<T> = tuple<T, T>` + `let ok: Pair<int> = (1, 2)` 是 0 诊断"
                "⇒ 只有一层别名没事，**套娃**那一层没解开。",
                "机制：`cypyc/analyzer/type_checker.py` 的 `_substitute_type` 处理 `GenericType` 时"
                "直接 `Type(type_node.name, generic_params=…)`，右端里出现的**其它别名**名字被原样保留"
                "⇒ 得到 `Pair[Pair[int]]` 这种「没有展开成 `tuple<…>`」的半成品，"
                "再与字面量的 `tuple<tuple<int,int>, tuple<int,int>>` 比 `!=` ⇒ 判错。",
                "修法：`_substitute_type` 增加 `_expand_nested_alias`，把右端里出现的别名展开到底"
                "（带 `_alias_stack` 名链守卫，`type Loop<T> = Loop<T>` 这类自指停在原地不递归成 "
                "RecursionError）；实参个数不符仍交回既有 arity 诊断，不重复记账。",
                "本单验证形状：`N01_nested_alias_ok` 由红转绿（假阳性消失），"
                "`N02_nested_alias_wrong`（内层元素真错）由粗报文转成精确的 "
                "`Element 2 type mismatch: expected int, got str`，"
                "`N03_scalar_alias_in_alias`/`N04_self_alias_no_hang` 一起进锁。",
            ]
        ),
    },
    {
        "key": "R13-UNION-SHAPED-ALIAS-NO-SUBST",
        "severity": "medium",
        "summary": (
            "[generics:alias] 联合形态的泛型别名整条不代入 ⇒ 任意值都放行："
            '`type Maybe<T> = T | None` + `let bad: Maybe<int> = "s"` 0 诊断；'
            "`type ListOrSet<T> = list<T> | set<T>` 的元素位同样无从判起"
        ),
        "detail": _detail_join(
            [
                "实测：`.fist-loop-20260929/probe_r13_container.py` 的 `U01_maybe_wrong` 改动前 errors=0"
                "（改动后转红：`Type mismatch: expected Union[int, None], got str`）。",
                "机制：`_substitute_type` 只认 `Name`/`PointerType`/`GenericType` 三种节点，"
                "`UnionType` 落到函数末尾的 `hasattr(type_node,'id')` 分支之外 ⇒ 返回 ``None`` ⇒ "
                "`_substitute_generic_alias` 返回 ``None`` ⇒ 注解位声明类型为空 ⇒ "
                "`_visit_LetStmt` 整条 `if declared_type and value_type` 不成立，任何值都登记为声明名。",
                "影响面不是纸上的：`examples/demos/data_structures/type_alias_demo.cypy:36` 就写着"
                " `type ListOrSet<T> = list<T> | set<T>`，:49/:50 两处使用 ⇒ 这份 demo 一直是"
                "「因为什么都不判所以通过」。",
                "修法：`_substitute_type` 补 `UnionType` 分支，与 `_get_type_from_node:3968` 同形"
                '（`Type("object", union_members=[…])`），成员先各自代入再交给 `_type_in_union`。',
                '未覆盖（本单不粉饰）：`U04_listorset_elem_wrong`（`ListOrSet<int> ← ["s"]`）'
                "改动后**仍静默** —— `_type_in_union` 只比成员 `.name`，容器元素位不参与判定；"
                "这条要动 `_type_in_union` 的语义，半径明显大于本单其余三条，已另计入开项。",
            ]
        ),
    },
]


def refused(res) -> bool:
    txt = json.dumps(res, ensure_ascii=False)
    return "__error__" in txt or txt.startswith("RPC-ERROR") or "RPC-ERROR" in txt


def main() -> int:
    tag = sys.argv[1] if len(sys.argv) > 1 else "a1"
    globals()["OUT"] = HERE / OUT_TMPL.format(tag=tag)
    started = utc_z()
    before_text = LEDGER.read_text(encoding="utf-8")
    rep = {
        "started_z": started,
        "ns": NS,
        "readings": {k: v for k, v in R.items() if k != "fp_verbatim"},
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
        # 未插值占位只可能是 `{标识符}`；正文里合法的花括号（`{"a": 1}` 这类源码片段、
        # `{param_name: concrete_type}` 这种文档里的映射写法）都不在该形状内 ——
        # 早先用"有没有花括号"当针，会把一条正常正文拦下。
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
        print(f"{card['key']} -> {rec['reply_verbatim'][:200]}")

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
    rep["summaries_in_bug_list"] = {
        card["key"]: any(
            card["summary"][:36] in json.dumps(b, ensure_ascii=False) for b in (bugs or [])
        )
        for card in CARDS
        if card["key"] not in present
    }
    # 库在仓库根（`run_r13_ring.py` 用的是 ROOT/"fist-mbt.db"）：早先写成 HERE ⇒ 文件不存在时
    # 这一栏键整个不落，而三向门又没数它 ⇒ "three_way_ok=True" 里其实只有两向。
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
    # 三向都要有基数：md 段数 / bug_list 计数 / call_log 行数，任一栏缺失即视为门坏（不是"没有就算过"）
    need = "call_log_report_bug_rows" in rep and "bug_list_count" in rep
    ok = (
        need
        and not rep["refusals"]
        and len(new_ids) == len(rep["filed"])
        and all(rep["summaries_in_bug_list"].values())
        and rep["after"]["headers"] == rep["before"]["headers"] + len(rep["filed"])
        and rep["bug_list_count"] == rep["after"]["headers"]
        and rep["call_log_report_bug_rows"] >= len(rep["filed"])
    )
    print(
        f"CONCLUSION r13_filed tag={tag} filed={len(rep['filed'])} "
        f"skipped={len(rep['skipped_existing'])} refused={len(rep['refusals'])} "
        f"new_ids={new_ids} bug_list_count={rep['bug_list_count']} "
        f"headers={rep['before']['headers']}->{rep['after']['headers']} "
        f"report_bug_rows={rep.get('call_log_report_bug_rows')} db={rep.get('db_path')} "
        f"three_way_ok={ok} out={OUT.name}"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
