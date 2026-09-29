"""R12 寻虫腿入账：本轮开门时撞见的两张新单（先取号，`report_bug` 自己写台账）。

两张都是**这一轮的改动揭出来的**，不是存量混淆：
 · BUG-134 的误导文案由新增的注解位判定第一次暴露（原来注解位根本不判，走不到那条消息）；
 · BUG-135 的推断空档在写语料时被成对样本钉出来（`One(v="s")` 0 诊断 ⇒ 若我把它写成"违界必红"
   就是伪造关闭，所以按"不判的一面"进 corpus 并立单）。
口径沿用 R11：错误行按 `call_log.ok=0` 取数；幂等按 reported_key；两张都挂 [判据面]/[analyzer] 前缀，
让引用核验能把它们归到对的栏，而不是混进产品面开口数。
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
OUT = HERE / "file_r12_bugs.json"
NS = "cypy-loop-20260929"
AGENT = "cypy-selfdrive-agent"

CARDS = [
    {
        "key": "R12-BOUND-DIAG-NOT-A-CALL",
        "severity": "low",
        "summary": ("[判据面·诊断文案] 注解位的违界诊断自称「in call to '<unknown>'」："
                    "联合界/命名界走 `_check_bound_satisfaction` 取 `node.func.id` 当被调方，"
                    "注解位节点没有 func ⇒ 落成 '<unknown>'，而同一个注解位的 trait 界走另一条分支，"
                    "文案是另一种形状（`... for parameter 'T' at L:C`）"),
        "detail": (
            "实测（`corpus/cypy.generic.bounds.json` 的两条违界格，逐字）：\n"
            " (a) `class Num<T: int | float>` + `let x: Num<str> = Num(1)` ⇒\n"
            "  `Generic constraint violation: type 'str' does not satisfy constraint 'int | float' "
            "(allowed: int | float) for parameter 'T', in call to '<unknown>', reported at line 10, col 12`\n"
            " (b) `class Only<T: Show>` + `let x: Only<int> = Only(1)` ⇒\n"
            "  `Generic constraint violation: type 'int' does not implement trait 'Show' for parameter 'T' "
            "at 13:12`\n"
            " —— 同一使用位、同一类事实，两类界给出两种形状，其中 (a) 还把自己说成一次调用。\n"
            "机制：`cypyc/analyzer/type_checker.py` 里 `_check_bound_satisfaction` 用 "
            "`getattr(getattr(node, 'func', None), 'id', None)` 推 callee，取不到就写 "
            "`in call to '<unknown>'`；trait 分支与 typeclass 分支各拼一份 `{line}:{col}` 尾巴"
            "（消息合成点不止一处 ⇒ 正是本轮在别处用「共用一份」消掉的形状）。\n"
            "影响与判据缺口：本轮语料只钉了 `reported at line \\d+, col \\d+`（定位正确性），"
            "所以「in call to」这句误导**没有任何判据在拦** ⇒ 属于文案级缺陷，不是假阴性。"
            "修法二选一交裁决：① 给非调用位传使用位标签（`at type annotation of 'Num<str>'`），"
            "② 把 callee 段改成中性且只在真是调用时出现；两者都会动到 C-5.x 钉住的既有文案，"
            "需与 `corpus/cypy.generic.callsite.json`、`tests/test_type_inference.py` 的锁同批改。\n"
            "证据件：`.fist-loop-20260929/make_corpus_r12.py`（两类界的成对样本）、"
            "`corpus/cypy.generic.bounds.json`、`.fist-loop-20260929/logs/r12_gate_a1.log`。"),
    },
    {
        "key": "R12-CTOR-NO-GENERIC-INFERENCE",
        "severity": "medium",
        "summary": ("[analyzer] class/struct 构造位不写类型实参时不做类型参数推断："
                    "`One(v=\"s\")` 对 `T: int` 的声明界 0 诊断，且成员类型也不代入（退化成未参数化的类）"),
        "detail": (
            "实测（同一程序的三种写法，逐字见 `.fist-loop-20260929/logs/r12_probe_a2.out`）：\n"
            " `struct One<T: int>:\\n    v: T` + `b = One(v=\"s\")` ⇒ 违界诊断 0 条；\n"
            " 同一行写成 `let a: One<str> = One(v=\"s\")` ⇒ 1 条（由**注解位**判下，不是由实参推断判下）；\n"
            " 写成 `b = One<str>(v=\"s\")` ⇒ 1 条（显式实参位）。\n"
            "机制：`_visit_Call` 的泛型分支以 `func_name in self.func_defs` 为闸门"
            "（`cypyc/analyzer/type_checker.py` 的 1375 区与 2946 区两处同样闸门），"
            "struct/class 名不在 `func_defs` ⇒ 既不跑 `_infer_generic_types`，也不回填 `generic_params`；"
            "`_visit_StructLiteral` 那份推断只服务 StructLiteral 节点，而 `One(v=\"s\")` 解析成 "
            "`Call(func=Name, args=[('v', Constant)], type_args=[])`（AST 实测，见探针件）。\n"
            "定性：[真缺陷·承诺半落地] —— 手册「使用泛型类」段落只给了显式实参形态，"
            "推断形态从未被承诺，但用户直觉会认为 `One(v=\"s\")` 就是 `T=str`。"
            "与 BUG-128（struct 方法不代入）同族：都卡在「类/结构体的类型参数没有被推断出来」这一层。\n"
            "半径与处置：本轮**不修**，改为把「不判」钉成语料格（`INFER_NOT_YET` 那条 expected.errors=0）"
            "与锁 `test_inferred_constructor_position_still_unjudged` ⇒ 将来修它时必须同时改这两处，"
            "不许静默翻面。修它需要构造位实参→类型参数的统一化推断 + 字段类型代入，"
            "会把「方法调用从不判」那一类程序打红（BUG-128 同一半径），须与语料同批。\n"
            "证据件：`.fist-loop-20260929/probe_r12_ctor_inference.py`、"
            "`corpus/cypy.generic.bounds.json`（laws 第 3 条写明不判面）。"),
    },
]


def utc_z() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def refused(res) -> bool:
    if isinstance(res, dict):
        if "__error__" in res or "error" in res or res.get("ok") is False:
            return True
        if str(res.get("code", "")).startswith("-32"):
            return True
    return False


def main() -> int:
    started = utc_z()
    before = LEDGER.read_text(encoding="utf-8")
    before_ids = re.findall(r"(?m)^## (BUG-\d+)", before)
    rep = {"started_z": started, "ns": NS,
           "ledger_ids_before": [before_ids[0], before_ids[-1], len(before_ids)],
           "filed": [], "skipped_existing": [], "refusals": []}
    todo = [c for c in CARDS if c["key"] not in before]
    for c in CARDS:
        if c["key"] in before:
            rep["skipped_existing"].append({"key": c["key"], "why": "账本已含 reported_key ⇒ 不重发"})
    if not todo:
        OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"CONCLUSION filed=0 refused=0 skipped={len(CARDS)} （幂等守卫命中）")
        return 0

    sys.path.insert(0, str(ROOT / "scripts"))
    os.environ["FIST_NAMESPACE"] = NS
    os.environ["FIST_SERVER_CWD"] = str(ROOT).replace("\\", "/")
    import fist  # noqa: PLC0415

    c = fist.FistClient(timeout=240)
    for card in todo:
        res = c.call("report_bug", {"project_dir": ".", "summary": card["summary"],
                                    "severity": card["severity"],
                                    "detail": card["detail"] + f"\n- reported_key: {card['key']}",
                                    "reported_by": AGENT, "publish_task": False})
        rec = {"key": card["key"], "reply_verbatim": json.dumps(res, ensure_ascii=False)[:400]}
        (rep["refusals"] if refused(res) else rep["filed"]).append(rec)
    lst = c.call("bug_list", {"project_dir": ".", "limit": 400})
    rep["bug_list_rows"] = len(lst) if isinstance(lst, list) else json.dumps(lst, ensure_ascii=False)[:200]
    if isinstance(lst, list):
        rep["bug_list_found"] = {cc["key"]: any(cc["summary"][:24] in json.dumps(x, ensure_ascii=False)
                                               for x in lst) for cc in CARDS}
    c.close()

    after = LEDGER.read_text(encoding="utf-8")
    after_ids = re.findall(r"(?m)^## (BUG-\d+)", after)
    rep["ledger_ids_after"] = [after_ids[0], after_ids[-1], len(after_ids)]
    rep["new_ids"] = [i for i in after_ids if i not in before_ids]
    rep["keys_present_after"] = {card["key"]: card["key"] in after for card in CARDS}
    con = sqlite3.connect(f"file:{ROOT / 'fist-mbt.db'}?mode=ro", uri=True)
    rep["call_log"] = {"rows": con.execute("select count(*) from call_log where ts>=?", (started,)).fetchone()[0],
                       "error_rows_ok_needle": con.execute(
                           "select count(*) from call_log where ts>=? and ok=0", (started,)).fetchone()[0],
                       "report_bug_rows": con.execute(
                           "select count(*) from call_log where ts>=? and tool='report_bug'",
                           (started,)).fetchone()[0]}
    con.close()
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in rep["filed"]:
        print("FILED", r["key"], "|", r["reply_verbatim"][:200])
    for r in rep["refusals"]:
        print("REFUSED", r["key"], "|", r["reply_verbatim"][:200])
    print("NEW_IDS", json.dumps(rep["new_ids"], ensure_ascii=False))
    print(f"CONCLUSION filed={len(rep['filed'])} refused={len(rep['refusals'])} "
          f"skipped={len(rep['skipped_existing'])} new_ids={len(rep['new_ids'])} "
          f"headers={len(after_ids)} call_log={json.dumps(rep['call_log'], ensure_ascii=False)}")
    return 0 if not rep["refusals"] and len(rep["filed"]) == len(rep["new_ids"]) == len(todo) else 1


if __name__ == "__main__":
    sys.exit(main())
