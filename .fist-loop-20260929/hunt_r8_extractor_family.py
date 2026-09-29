"""R8 寻虫：SYNTAX/17「模式匹配优先级系统」表里那 4 个提取器，文档示例能不能真跑通。

判据形状：逐条把文档代码块原样喂给 Lexer→Parser→TypeChecker→CythonGenerator，
四栏分开记（parse / analyze / codegen / 诊断逐字），并区分三种失败形态：
`OK` / `DIAGNOSTIC`（有编译期诊断，说明特性没实现但会说话）/ `PARSE-FAIL`（文档写法根本进不了语言）
/ `INTERNAL`（分析器或生成器抛栈，这是真缺陷）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "hunt_r8_extractor_family.json"
sys.path.insert(0, str(ROOT))

from cypyc.analyzer.type_checker import TypeChecker  # noqa: E402
from cypyc.codegen.cython_generator import CythonGenerator  # noqa: E402
from cypyc.parser.lexer import Lexer  # noqa: E402
from cypyc.parser.parser import Parser  # noqa: E402

CASES = [
    ("__unapply__ 元组提取器", '''struct Email:
    address: str

    def __unapply__(self) -> tuple<str, str> | None:
        parts = self.address.split('@')
        return (parts[0], parts[1])

def g(e: Email) -> str:
    match e:
        case Email(user, domain):
            return user
        case _:
            return "none"
'''),
    ("__unwarp__ 解包模式", '''struct Wrapper:
    value: int

    def __unwarp__(self) -> int:
        return self.value

def g(w: Wrapper) -> int:
    match w:
        case Wrapper(x):
            return x
        case _:
            return 0
'''),
    ("__unapply_seq__ 序列提取器（文档写法 tuple<int, ...> + case (x, y, ..)）", '''struct Numbers:
    values: list<int>

    def __unapply_seq__(self) -> tuple<int, ...> | None:
        return (1, 2)

def g(n: Numbers) -> int:
    match n:
        case Numbers(x, y, ..):
            return x
        case _:
            return 0
'''),
    ("__match_args__ 位置解构", '''struct Point:
    x: int
    y: int

    __match_args__ = ("x", "y")

def g(p: Point) -> int:
    match p:
        case Point(a, b):
            return a
        case _:
            return 0
'''),
    ("类型模式 case int x", '''def g(v: object) -> int:
    match v:
        case int x:
            return x
        case _:
            return 0
'''),
    ("OR 模式 case 1 | 2", '''def g(v: int) -> str:
    match v:
        case 1 | 2:
            return "small"
        case _:
            return "other"
'''),
]


def probe(src: str) -> dict:
    row: dict = {"parse": "OK", "analyze": "OK", "codegen": "OK",
                 "errors": [], "internal": "", "code_head": "",
                 "slot_types": {}, "unapply_in_code": False}
    try:
        ast = Parser(list(Lexer(src).tokenize())).parse()
    except Exception as exc:  # noqa: BLE001
        row["parse"] = "PARSE-FAIL"
        row["internal"] = f"{type(exc).__name__}: {exc}"
        return row
    try:
        ck = TypeChecker()
        ck.check(ast)
    except Exception as exc:  # noqa: BLE001
        row["analyze"] = "INTERNAL"
        row["internal"] = f"{type(exc).__name__}: {exc}"
        return row
    row["errors"] = [e for e in ck.errors if e.strip()]
    for tn in ("Email", "Wrapper", "Numbers", "Point"):
        got = [t.name for t in (ck._pattern_slot_types(tn) or [])]
        if got:
            row["slot_types"][tn] = got
    if row["errors"]:
        row["analyze"] = "DIAGNOSTIC" if not any("INTERNAL" in e for e in row["errors"]) else "INTERNAL"
    try:
        full = CythonGenerator().generate(ast)
        row["code_head"] = full[:120]
        row["unapply_in_code"] = ("__unapply__()" in full or "__unwarp__()" in full
                                  or "__unapply_seq__()" in full)
    except Exception as exc:  # noqa: BLE001
        row["codegen"] = "INTERNAL"
        row["internal"] = f"{type(exc).__name__}: {exc}"
    return row


def main() -> int:
    rows = []
    for name, src in CASES:
        r = probe(src)
        r["case"] = name
        r["verdict"] = ("OK" if r["parse"] == r["analyze"] == r["codegen"] == "OK"
                        else "INTERNAL" if "INTERNAL" in (r["parse"], r["analyze"], r["codegen"])
                        or any("INTERNAL" in e for e in r["errors"])
                        else "PARSE-FAIL" if r["parse"] != "OK" else "DIAGNOSTIC")
        rows.append(r)
        print(f"{r['case']:<58} {r['verdict']:<11} parse={r['parse']} analyze={r['analyze']} "
              f"codegen={r['codegen']}")
        if r["internal"]:
            print(f"    internal: {r['internal'][:150]}")
        if r["errors"]:
            print(f"    diag: {r['errors'][0][:150]}")
        print(f"    slot_types={r['slot_types']} extractor_called_in_code={r['unapply_in_code']}"
              f" phantom_f={'__f0' in (r['code_head'] or '')}")
    OUT.write_text(json.dumps({"rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    tally = {v: sum(1 for r in rows if r["verdict"] == v) for v in ("OK", "DIAGNOSTIC", "PARSE-FAIL", "INTERNAL")}
    print(f"CONCLUSION cases={len(rows)} {tally} rows_json={OUT.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
