"""R11 寻虫腿入账：4 张新缺陷单走 `report_bug`（issue_up 面），并三向核对本地账本。

纪律（沿用既往轮）：
 · 先取号再写台账 —— 编号由服务端定，脚本不手写 `## BUG-NN`；
 · 幂等守卫：起跑先按 reported_key 查账本，已存在 ⇒ 只指认不重发；
 · 拒绝按形状识别（`__error__` / RPC-ERROR），不看 `ok` 字面；
 · 三向对照：md 条目 ↔ `bug_list` 回读 ↔ `call_log` 的 report_bug 行。
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
OUT = HERE / "file_r11_bugs.json"
NS = "cypy-loop-20260929"
AGENT = "cypy-selfdrive-agent"

CARDS = [
    {
        "key": "R11-DIAG-LINE-OFF-BY-ONE",
        "severity": "medium",
        "summary": ("[diagnostics] Return type mismatch 一类诊断的行号恒等于实际行 +1，"
                    "2 行文件会报 3:1（超出文件末尾）"),
        "detail": (
            "实测（本轮 `.fist-loop-20260929/measure_r11_substitution.py` 的 `logs/r11_subst2.out`，"
            "另用最小样例复核）：\n"
            " (a) `def f() -> str:\\n    return 1`（共 2 行）报 "
            "`Return type mismatch: expected str, got int at 3:1`；\n"
            " (b) `def g() -> int:\\n    return 1\\n\\n\\ndef f() -> str:\\n    return g()`（共 6 行）报 "
            "`at 7:1`；\n"
            " (c) 同一程序在 `return` 前多留/少留一个空行时，报告行号随之 +1，而 `return` 的真实行号分别是 "
            "9/10 ⇒ 偏移恒定 1，不是排版巧合。\n"
            "定性：既有缺陷（module-level 函数即可复现，与本轮泛型类改动无关）。影响面：本仓多条验收口径写着"
            "「诊断带行列」（含 BUG-118/119 的闭合文案与本环 corpus 的 matches 断言），行号 +1 会让用户按报告"
            "找不到那一行；修它要同时过一遍所有钉死 `at L:C` 的既有锁 ⇒ 本轮只留痕，改动交另轮带判据收。\n"
            "证据件：`.fist-loop-20260929/measure_r11_substitution.py`、`logs/r11_subst1.out`、"
            "`logs/r11_subst2.out`。"),
    },
    {
        "key": "R11-CDEF-CLASS-MISPARSE",
        "severity": "low",
        "summary": ("[parser] `cdef class Box:` 不是本门面的语法却不被拒：解析成 ExprStmt(Name('cdef')) + "
                    "普通 ClassDef，`ClassDef.is_cdef` 从解析器恒 False，codegen 的 cdef-class 分支不可达"),
        "detail": (
            "实测（`.fist-loop-20260929/logs/r11_generics_probe2.out` 的 C6，以及最小对照）：\n"
            " `cdef class Box:` 与 `cdef class Box<T>:` 解析后 `AST body kinds=['ExprStmt', 'ClassDef']`、"
            "`is_cdef=False`，类型检查报 `Undefined name 'cdef' at 1:1`（而不是「不支持的声明前缀」），"
            "类体本身仍被收下并入产物。\n"
            "机制：`_parse_class_def(is_cdef=True)` 全仓只有一个调用点（`cypyc/parser/parser.py:1218`，不带实参）"
            "⇒ `is_cdef` 永远取默认 False；`cypyc/codegen/cython_generator.py:4212` 起的 "
            "`if is_cdef: … cdef class X:` 分支对 class 不可达（对照：泛型 struct 出码确为 `cdef class Wrap:`，"
            "走的是 StructDef 那条路径）。\n"
            "定位声明核对：SYNTAX 里 `cdef class` 只以注释形态出现在 `SYNTAX/25-compatibility.md:158`，"
            "手册从未把它列为门面 ⇒ 定性不是「文档/实现分叉」，而是"
            "「误导性诊断 + 不可达产物分支」。修法二选一（接受该前缀并置位 is_cdef，或显式硬拒并删死分支），"
            "交裁决。\n"
            "证据件：`logs/r11_generics_probe2.out`、`logs/r11_generics_probe4.out`（同形复现）。"),
    },
    {
        "key": "R11-STRUCT-METHOD-NO-SUBST",
        "severity": "medium",
        "summary": ("[analyzer] 泛型 struct 的方法调用不做接收者代入：struct 分支只遍历 .fields，"
                    "`Wrap<str>.get()` 被判成未知而 0 诊断，与本轮 class 分支形成同一事实两个读法"),
        "detail": (
            "实测（同形对照，一条红一条绿）：\n"
            " `struct Wrap<T>: value: T; def get(self) -> T` + `let w: Wrap<str> = Wrap(\"s\")` + "
            "`def f() -> int: return w.get()` ⇒ **0 诊断**（应为 expected int, got str）；\n"
            " 换成 `class Box<T>` 同形 ⇒ `Return type mismatch: expected int, got str`（本轮 L4 修复面）。\n"
            "机制：`cypyc/analyzer/type_checker.py` 的 `_visit_Attribute` 里 struct 分支只扫 "
            "`struct_def.fields`，方法名落空后返回 `Type(\"object\")`（:2489-2500 区），"
            "class 分支本轮补齐了方法代入（:2512 起）。\n"
            "定性：[真缺陷·假阴性]。收紧它会把「方法调用从不判」的既有程序打红（面比 class 大），"
            "需要与判据/语料同批做 ⇒ 本轮只留痕，不在同一轮里顺手推广（R9 的 BUG-99 教训：越界推广打红既有锁）。"
        ),
    },
    {
        "key": "R11-DECLARED-CONSTRAINT-NOT-CHECKED",
        "severity": "medium",
        "summary": ("[analyzer] 定义侧类型约束 `T: int | float` 在注解位与实例化位都不判："
                    "`Num<str>` 违反声明界却 0 诊断（class 与 struct 两形同）"),
        "detail": (
            "实测（最小对照）：\n"
            " `class Num<T: int | float>: v: T` + `let x: Num<str> = Num(\"a\")` ⇒ errors=[]；\n"
            " `struct NumS<T: int | float>: v: T` + `let x: NumS<str> = NumS(1)` ⇒ errors=[]。\n"
            "机制：约束只在结构体**字面量**路径上被消费（`_visit_StructLiteral` 读 "
            "`struct_def.generic_constraints` 并发 `Generic constraint violation`），"
            "注解位/泛型构造调用不读该表；本轮新增的 `ClassDef.generic_constraints` 同样没有消费点。\n"
            "对照已闭环的一面：函数调用位是判的（`corpus/cypy.generic.callsite.json` 里 "
            "`Generic constraint violation` 那格，100% 通过率）⇒ 同一份声明界在三条路径上"
            "只有一条消费，属于「同一事实多处读取」的分叉。\n"
            "定性：[真缺陷·承诺半落地]。SYNTAX/11「类型约束」与本轮「泛型类」规则都引用了声明界，"
            "补齐需要把函数那条路径的判定抽成共用函数并处理 `Comparable` 的特质界 ⇒ 另轮收。\n"
            "证据件：本轮 `logs/r11_generics_probe2.out`（C3_constrained 只证解析收下，不证判定）。"),
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


def headers():
    text = LEDGER.read_text(encoding="utf-8")
    return text, re.findall(r"(?m)^## (BUG-\d+)", text)


def main() -> int:
    started = utc_z()
    before_text, before_ids = headers()
    rep = {"started_z": started, "ns": NS, "ledger_ids_before": [before_ids[0], before_ids[-1], len(before_ids)],
           "filed": [], "skipped_existing": [], "refusals": []}

    for card in CARDS:
        if card["key"] in before_text:
            rep["skipped_existing"].append({"key": card["key"], "why": "账本已含该 reported_key ⇒ 不重发"})
    if len(rep["skipped_existing"]) == len(CARDS):
        print("CONCLUSION refused=0 filed=0 skipped=all（幂等：四张已入账）")
        OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        return 0

    sys.path.insert(0, str(ROOT / "scripts"))
    os.environ["FIST_NAMESPACE"] = NS
    os.environ["FIST_SERVER_CWD"] = str(ROOT).replace("\\", "/")
    import fist  # noqa: PLC0415

    c = fist.FistClient(timeout=240)
    for card in CARDS:
        if card["key"] in before_text:
            continue
        res = c.call("report_bug", {"project_dir": ".", "summary": card["summary"],
                                    "severity": card["severity"],
                                    "detail": card["detail"] + f"\n- reported_key: {card['key']}",
                                    "reported_by": AGENT, "publish_task": False})
        rec = {"key": card["key"], "reply_verbatim": json.dumps(res, ensure_ascii=False)[:400]}
        (rep["refusals"] if refused(res) else rep["filed"]).append(rec)
    lst = c.call("bug_list", {"project_dir": ".", "limit": 400})
    rep["bug_list_rows"] = len(lst) if isinstance(lst, list) else json.dumps(lst, ensure_ascii=False)[:200]
    rep["bug_list_probe"] = [json.dumps(x, ensure_ascii=False)[:120] for x in
                             (lst if isinstance(lst, list) else [])[:2]]
    c.close()

    after_text, after_ids = headers()
    rep["ledger_ids_after"] = [after_ids[0], after_ids[-1], len(after_ids)]
    rep["new_ids"] = [i for i in after_ids if i not in before_ids]
    rep["keys_present_after"] = {card["key"]: card["key"] in after_text for card in CARDS}
    blocks = re.split(r"(?m)^## (BUG-\d+)", after_text)
    closed = r"(?m)^### (FIXED|DUPLICATE|OUT|WONT)"
    open_ids = [blocks[i] for i in range(1, len(blocks) - 1, 2) if not re.search(closed, blocks[i + 1])]
    rep["ledger_open_blocks_narrow"] = len(open_ids)
    rep["ledger_headers_total"] = len(after_ids)
    rep["ledger_unique_ids"] = len(set(after_ids))
    con = sqlite3.connect(f"file:{ROOT / 'fist-mbt.db'}?mode=ro", uri=True)
    rep["call_log_error_rows"] = con.execute(
        "select count(*) from call_log where ts>=? and result_json like '%__error__%'", (started,)).fetchone()[0]
    rep["tasks_ns_bugs_rows"] = con.execute(
        "select count(*) from tasks where ns='bugs' and created_at>=?", (started,)).fetchone()[0]
    con.close()

    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in rep["filed"]:
        print("FILED", r["key"], "|", r["reply_verbatim"][:200])
    for r in rep["refusals"]:
        print("REFUSED", r["key"], "|", r["reply_verbatim"][:200])
    print("NEW_IDS", json.dumps(rep["new_ids"], ensure_ascii=False))
    print("KEYS_PRESENT_AFTER", json.dumps(rep["keys_present_after"], ensure_ascii=False))
    print(f"CONCLUSION filed={len(rep['filed'])} refused={len(rep['refusals'])} "
          f"new_ids={len(rep['new_ids'])} headers={rep['ledger_headers_total']} "
          f"unique={rep['ledger_unique_ids']} open_narrow={rep['ledger_open_blocks_narrow']} "
          f"call_log_error_rows={rep['call_log_error_rows']} tasks_bugs_rows={rep['tasks_ns_bugs_rows']}")
    return 0 if not rep["refusals"] and len(rep["filed"]) == len(rep["new_ids"]) else 1


if __name__ == "__main__":
    sys.exit(main())
