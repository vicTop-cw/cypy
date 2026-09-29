"""R10 寻虫腿入账：5 张新缺陷单走 `report_bug`（issue_up 面），并双向核对本地账本。

纪律（都是既往轮的教训）：
- 先取号再写台账：`report_bug` 之前不手写 `## BUG-NN`，编号由服务端定；
- 幂等守卫：起跑先按 summary needle 查账本，已存在 ⇒ 只指认不重发（同轮二次运行只留 `### DUPLICATE`）；
- 拒绝逐字入账：`__error__` 形态按形状识别，不看 `ok` 字面；
- 读取通道自证：`bug_list` 回读条数必须 >0，否则"没查到"会被读成"没重复"。
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
OUT = HERE / "file_r10_bugs.json"
NS = "cypy-loop-20260929"
AGENT = "cypy-selfdrive-agent"

CARDS = [
    {
        "key": "R10-CALLSITE-CHECKER",
        "severity": "high",
        "summary": ("[generics:callsite] 调用点 f<T>(x) 被当成 <checker> 参数检查站：产物插入对类型名的零参调用、"
                    "多类型实参直接解析失败、显式实参从不参与判定"),
        "detail": (
            "同一根因的三个现形面（实测件 `.fist-loop-20260929/probe_r10_generics.py`，"
            "逐字输出 `logs/r10_generics_probe1.out`）：\n"
            " (a) 静默错误产物：`struct Foo: value: int` + `identity<Foo>(v)` 的产物是 "
            "`return (Foo(), identity(v))[1]`（`cypyc/codegen/cython_generator.py:3816-3817` 的逗号表达式），"
            "运行期含义是把类型名当零参函数调用一次 ⇒ 带必填字段的 struct/class 必抛 TypeError，"
            "而 `--check-only` 与生成阶段均 0 诊断。全仓 13 处用该形态"
            "（`.fist-loop-20260929/baseline_r10_typeargs.json`：generic_func 11 / generic_struct 2），"
            "含 `examples/demos/traits_duck/duck_basic.cypy:143,147`（`display_name<NamedItem>(item)`、"
            "`resize<SizedBox>(box, 20)`）。\n"
            " (b) 文档承诺的形态解析失败：SYNTAX/11:23 的 `pair<int, str>(42, \"answer\")` 报 "
            "`Unexpected token COMMA at 6:34`，因 `parser.py:3856-3874` 只收单个 IDENTIFIER。\n"
            " (c) 显式实参不参与判定：`identity<int>(\"Alice\")` 赋给 str 得 0 诊断，"
            "`pair<int>(42)` 对 `<T, U>` 无元数诊断（`type_checker.py:1306-1337` 只按实参统一化推断）。\n"
            "声明面冲突：SYNTAX/11「泛型函数 / 多类型参数 / 泛型类」承诺 `f<A,B>(…)`；"
            "而 `<checker>` 检查站是定义侧形态且 SYNTAX/33:519（P-1.8）已判 v1 不支持 ⇒ "
            "调用点尖括号不存在第二种合法解释。定性：[真缺陷·产品面]。"
        ),
    },
    {
        "key": "R10-GENERIC-CLASS-PARSE",
        "severity": "high",
        "summary": "[parser] 泛型类 `class Box<T>:`（SYNTAX/11:107-125 承诺）解析拒收 Expected COLON, got LT，而 struct Box<T> 可用",
        "detail": (
            "实测：`class Box<T>:\\n    def __init__(self, content: T):` 形态在 `typecheck` 与 `codegen` 两面均 "
            "`stage=parse`、`Expected COLON, got LT at 1:10`（探针件 `probe_r10_generics.py` 的 G6/B1）；"
            "同一份类型参数写法换成 `struct Wrap<T>: value: T` 则解析通过并出码（G14/B2，产物 "
            "`cdef class Wrap:`，字段 `value` 退化为 object）。"
            "SYNTAX/11:107-125 明确给出 `class Box<T>:` 与 `Box<int>(42)` 用法，:133 特性表又声称「泛型类：类可以是泛型的」⇒ "
            "文档承诺与解析器能力直接矛盾。定性：[真缺陷·文档/实现分叉]。本轮未修的理由：泛型类要动 "
            "ClassDef 节点签名、`_visit_ClassDef` 的类型参数登记、codegen 的 class 出码与 scope 名字空间四处，"
            "与本环「调用点类型实参」半径不同，另轮收。"
        ),
    },
    {
        "key": "R10-TRAIT-ABSTRACT-PARSE",
        "severity": "medium",
        "summary": "[parser] trait 的无体抽象方法（SYNTAX/11:47-51、89-91 的 `def get(self, index: int) -> T:`）解析拒收 Expected increased indentation",
        "detail": (
            "实测（`probe_r10_generics.py` 的 F1/F2、G10）：`trait Foo:\\n    def bar(self) -> int:` 报 "
            "`Expected increased indentation at line 3. Expected 8, got 0`；泛型 `trait Foo<T>:` 同形。"
            "非泛型也炸 ⇒ 不是泛型专属，是 trait 体形态与文档分叉。SYNTAX/11「定义泛型特质」与「特质约束」两处范例"
            "（:47-51、:89-91）都写成无体签名 ⇒ 按手册抄的代码进不了编译器。定性：[真缺陷·文档/实现分叉]。"
            "待裁决项：是补「抽象方法必须有体（`...`/`pass`）」的文档条款，还是让解析器接受无体签名——本轮只做留痕，不改判据也不改文档。"
        ),
    },
    {
        "key": "R10-BRACKET-CALLSITE",
        "severity": "high",
        "summary": "[generics:callsite] 方括号形态 f[T](x) 被解析成「下标后调用」并原样进产物，运行期必抛 TypeError 而编译期 0 诊断",
        "detail": (
            "实测：`identity[list[int]](xs)` 与 `identity[Box](v)` 在 `--check-only` 与 codegen 两面 errors=0，"
            "产物逐字保留 `y: list = identity[list[int]](xs)`（探针 G13/A3）。运行期含义是 `function.__getitem__` ⇒ "
            "`TypeError: 'function' object is not subscriptable`。本环按 SYNTAX/11 修的是尖括号形态（`<>` = 类型实参表，"
            "产物擦除），方括号形态文档从未承诺 ⇒ 属「能吃但无人管」的第二类：要么解析级硬拒（像 dispatch 的 P-1.8 那样），"
            "要么并入类型实参表。交下一轮裁决后修，本轮不改判据也不放开门禁。定性：[真缺陷·静默错误产物]。"
        ),
    },
    {
        "key": "R10-TYPEARG-NOT-VISITED",
        "severity": "medium",
        "summary": "[analyzer] 类型实参子树不被 visit：f<Undefined>(x) 里未定义的类型名静默降级为 object，无诊断",
        "detail": (
            "本环代入实现 `TypeChecker._bind_explicit_type_args`（`cypyc/analyzer/type_checker.py:1273-1303`）只做 "
            "`_get_type_from_node(arg_node)` 的形态转换，不调 `self._visit()` ⇒ 类型实参里的名字不做存在性判定。"
            "实测：`mk<Undefined>(1)`（mk 为泛型函数）产 0 诊断，返回类型退化为 object。"
            "为什么本轮不顺手补：`_visit` 在类型节点上会牵出 `Undefined name` 模板对 `list<int>`/`int | float` 这类"
            "复合形态的连带判定，属于既有诊断面的扩大，必须与 BUG-109（注解位缺类型表达式产生器）同批裁决。"
            "定性：[真缺陷·本轮亲笔限制的留痕]，判据面已在 `corpus/cypy.generic.callsite.json` 之外由本单钉住。"
        ),
    },
]


def refused(res) -> bool:
    blob = json.dumps(res, ensure_ascii=False)
    return "__error__" in blob or blob.startswith("RPC-ERROR") or (res or {}).get("ok") is False


def headers() -> tuple:
    t = LEDGER.read_text(encoding="utf-8")
    return t, sorted({int(m) for m in re.findall(r"(?m)^## BUG-(\d+) ", t)})


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    before_text, before_ids = headers()
    rep = {"started_z": started, "ledger_ids_before": [before_ids[0], before_ids[-1], len(before_ids)],
           "ledger_bytes_before": len(before_text.encode("utf-8")),
           "filed": [], "skipped_existing": [], "refusals": [], "probe": {}}

    for card in CARDS:
        if card["key"] in before_text or card["summary"][:60] in before_text:
            rep["skipped_existing"].append({"key": card["key"], "needle": card["summary"][:60]})

    sys.path.insert(0, str(ROOT / "scripts"))
    os.environ["FIST_NAMESPACE"] = NS
    os.environ["FIST_SERVER_CWD"] = str(ROOT).replace("\\", "/")
    import fist  # noqa: PLC0415

    c = fist.FistClient(timeout=180)
    bl = c.call("bug_list", {"project_dir": ".", "namespace": "bugs", "limit": 400})
    rows = bl.get("bugs") if isinstance(bl, dict) else bl
    rep["probe"]["bug_list_shape"] = sorted(bl)[:10] if isinstance(bl, dict) else type(bl).__name__
    rep["probe"]["bug_list_rows"] = len(rows or [])
    if not rows:
        rep["probe"]["reply_verbatim"] = json.dumps(bl, ensure_ascii=False)[:400]

    for card in CARDS:
        if card["key"] in before_text or card["summary"][:60] in before_text:
            continue
        res = c.call("report_bug", {"project_dir": ".", "summary": card["summary"], "severity": card["severity"],
                                   "detail": card["detail"] + f"\n- reported_key: {card['key']}",
                                   "reported_by": AGENT, "publish_task": False})
        rec = {"key": card["key"], "reply_verbatim": json.dumps(res, ensure_ascii=False)[:400]}
        (rep["refusals"] if refused(res) else rep["filed"]).append(rec)
    c.close()

    after_text, after_ids = headers()
    rep["ledger_ids_after"] = [after_ids[0], after_ids[-1], len(after_ids)]
    rep["new_ids"] = [i for i in after_ids if i not in before_ids]
    rep["ledger_grew_by_report_bug"] = len(after_text) > len(before_text)
    rep["keys_present_after"] = {card["key"]: card["key"] in after_text for card in CARDS}
    con = sqlite3.connect(f"file:{ROOT / 'fist-mbt.db'}?mode=ro", uri=True)
    rep["call_log_error_rows"] = con.execute(
        "select count(*) from call_log where ts>=? and result_json like '%__error__%'", (started,)).fetchone()[0]
    con.close()

    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print("PROBE", json.dumps(rep["probe"], ensure_ascii=False))
    for r in rep["filed"]:
        print("FILED", r["key"], "|", r["reply_verbatim"][:180])
    for r in rep["skipped_existing"]:
        print("SKIP(existing)", r["key"], r["needle"])
    for r in rep["refusals"]:
        print("REFUSED", r["key"], "|", r["reply_verbatim"][:220])
    print(f"CONCLUSION filed={len(rep['filed'])} skipped={len(rep['skipped_existing'])} "
          f"refused={len(rep['refusals'])} new_ids={rep['new_ids']} "
          f"ids_before={rep['ledger_ids_before']} ids_after={rep['ledger_ids_after']} "
          f"append_by_tool={rep['ledger_grew_by_report_bug']} error_rows={rep['call_log_error_rows']}")
    return 0 if not rep["refusals"] and rep["filed"] else 1


if __name__ == "__main__":
    sys.exit(main())
