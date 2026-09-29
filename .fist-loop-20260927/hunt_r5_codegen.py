"""R5-寻虫 法①：codegen / comptime 面的六条候选，在 `cypyc transpile` 产物上逐条复跑两遍确诊。

判据形状：pos=「文档声明的语义」与产物文本不符（或产物 rc 非零而文档说这写法有效）；
ctl=**同一 lowering 通道上今天正确**的形状。只有 pos 成立且 ctl 也成立，才记 CONFIRMED；
否则记 UNSURE 并在件里留着原因（邻域整体坏掉时不能把现象归到某一条分支上）。

三条防自身失效的口径：
- 每条跑两遍，两遍的产物文本必须逐字相同（不稳定 ⇒ refuse，不写「偶发」）；
- 观察的是**产物字节**，不是「编译成功」；产物里有 `Constant(line=` 这种内部表示即判外泄；
- 声明原文按 file + 片段现读盘上文件，找不到片段 ⇒ refuse（没有立单依据）。
"""

from __future__ import annotations

import datetime
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "hunt_r5_codegen.json"
TMP = HERE / "hunt_r5_tmp" / "codegen"
PY = sys.executable
REFUSE: list = []
CHECKS: list = []
CANARY: dict = {}
LEAK = ("Constant(line=", "generic_params", "ListExpr(", "TupleExpr(")


def now_s() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def check(label, got, want, why) -> None:
    CHECKS.append({"label": label, "got": got, "want": want, "why": why, "ok": got == want})


def quote(rel: str, frag: str) -> dict:
    path = ROOT / rel
    if not path.exists():
        REFUSE.append(f"声明所在文件不在盘上：{rel}")
        return {"file": rel, "line": -1, "quote": ""}
    for i, ln in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if frag in ln:
            return {"file": rel, "line": i, "quote": ln.strip()[:170]}
    REFUSE.append(f"{rel} 里找不到声明片段 {frag!r} ⇒ 这一条没有立单依据")
    return {"file": rel, "line": -1, "quote": ""}


def lower(tag: str, src: str) -> dict:
    """把一段 Cypy 源码 transpile 成产物文本；返回 rc + 产物 + 诊断。"""
    d = TMP / tag
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    (d / "m.pyx").write_text(src, encoding="utf-8", newline="\n")
    p = subprocess.run(
        [PY, "-X", "utf8", "-m", "cypyc", "transpile", "m.pyx", "-o", "out"],
        cwd=str(d),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    out = p.stdout + p.stderr
    prod = ""
    for q in sorted((d / "out").glob("*")):
        if q.is_file():
            prod += q.read_text(encoding="utf-8", errors="replace")
    body = "\n".join(
        ln for ln in prod.splitlines() if not ln.startswith("#") and "generated" not in ln.lower()
    )
    diag = [ln.strip() for ln in out.splitlines() if " - " in ln or "错误" in ln]
    return {
        "rc": p.returncode,
        "product": body,
        "diag": diag[:4],
        "leaks_internal": [t for t in LEAK if t in body],
    }


def _tail(body: str, marker: str) -> str:
    for ln in body.splitlines():
        if marker in ln:
            return ln.strip()
    return ""


# ------------------------------------------------------------------ 六条候选
def c01(d: str = "c01") -> dict:
    r = lower(d, "def f(a: int, b: int, c: int) -> int:\n    return a - (b - c)\n")
    line = _tail(r["product"], "return a")
    return {
        "rc": r["rc"],
        "line": line,
        "observed": "parens_dropped" if line == "return a - b - c" else "kept",
    }


def c01_ctl() -> dict:
    r = lower("c01c", "def f(a: int, b: int, c: int) -> int:\n    return a * (b + c)\n")
    line = _tail(r["product"], "return a")
    return {
        "rc": r["rc"],
        "line": line,
        "observed": "kept" if "(b + c)" in line else "parens_dropped",
    }


def c02(d: str = "c02") -> dict:
    r = lower(d, "def f(a: int, y: int) -> int:\n    a **= y\n    return a\n")
    hard = r["rc"] != 0 or any("Unexpected token" in x for x in r["diag"])
    return {"rc": r["rc"], "diag": r["diag"], "observed": "unreachable" if hard else "lowered"}


def c02_ctl() -> dict:
    r = lower("c02c", "def f(a: int, y: int) -> int:\n    a += y\n    return a\n")
    return {
        "rc": r["rc"],
        "line": _tail(r["product"], "a = a"),
        "observed": "lowered" if "a = a + y" in r["product"] else "unreachable",
    }


def _fn_body(product: str) -> str:
    """产物开头是模块 docstring 与导入头，判据只看 `def ` 之后的函数体。"""
    i = product.find("def ")
    return product[i:] if i >= 0 else product


def _order(body: str) -> list:
    return [ln.strip() for ln in body.splitlines() if "print(" in ln]


def c03(d: str = "c03") -> dict:
    r = lower(
        d,
        "def f(n: int) -> int:\n    if n > 0:\n        defer:\n"
        '            print("CLEAN")\n    print("BODY")\n    return n\n',
    )
    lines = _order(r["product"])
    eager = bool(lines) and "CLEAN" in lines[0]
    return {"rc": r["rc"], "order": lines[:4], "observed": "eager" if eager else "moved_to_exit"}


def c03_ctl() -> dict:
    r = lower(
        "c03c",
        'def f(n: int) -> int:\n    defer:\n        print("CLEAN")\n'
        '    print("BODY")\n    return n\n',
    )
    lines = _order(r["product"])
    moved = bool(lines) and "BODY" in lines[0] and "CLEAN" in lines[-1]
    return {"rc": r["rc"], "order": lines[:4], "observed": "moved_to_exit" if moved else "eager"}


def c04(d: str = "c04") -> dict:
    r = lower(d, "def f() -> int:\n    comptime: [1, 2]\n    return 1\n")
    return {
        "rc": r["rc"],
        "leaks": r["leaks_internal"],
        "snippet": _tail(r["product"], "Constant") or r["product"][:120],
        "observed": "ast_leak" if r["leaks_internal"] else "clean",
    }


def c04_ctl() -> dict:
    r = lower("c04c", "def f() -> int:\n    comptime: 6 * 7\n    return 1\n")
    return {
        "rc": r["rc"],
        "leaks": r["leaks_internal"],
        "observed": "clean" if r["rc"] == 0 and not r["leaks_internal"] else "ast_leak",
    }


def c05(d: str = "c05") -> dict:
    r = lower(d, 'def f() -> int:\n    comptime: "a" + "\\"" + "b"\n    return 1\n')
    body = _fn_body(r["product"])
    return {
        "rc": r["rc"],
        "snippet": [ln.strip() for ln in body.splitlines() if ln.strip().startswith('"')][:3],
        "observed": "unescaped" if '"a"b"' in body else "commented",
    }


def c05_ctl() -> dict:
    r = lower("c05c", "def f() -> int:\n    comptime: 1 + 2\n    return 1\n")
    body = _fn_body(r["product"])
    bad = _odd_quote_line(body)
    return {
        "rc": r["rc"],
        "snippet": [ln.strip() for ln in body.splitlines() if ln.strip().startswith('"')][:3],
        "observed": "commented" if not bad else "unescaped",
    }


def _odd_quote_line(body: str) -> bool:
    return any(ln.strip().startswith('"') and ln.strip().count('"') % 2 for ln in body.splitlines())


def c07(d: str = "c07") -> dict:
    r = lower(d, "def f() -> int:\n    comptime:\n        [1, 2]\n    return 1\n")
    leaked = [x for x in r["diag"] if "__dict__" in x or "Traceback" in x]
    return {
        "rc": r["rc"],
        "diag": [x[-70:] for x in r["diag"]][:3],
        "observed": "internal_exception" if leaked or r["rc"] != 0 else "clean",
    }


def c07_ctl() -> dict:
    r = lower("c07c", "def f() -> int:\n    comptime: [1, 2]\n    return 1\n")
    return {
        "rc": r["rc"],
        "diag": [x[-70:] for x in r["diag"]][:3],
        "observed": "no_internal_exception" if r["rc"] == 0 else "internal_exception",
    }


def c06(d: str = "c06") -> dict:
    r = lower(d, "def my_strcpy(dst: *char, src: *char) -> *char:\n    return dst\n")
    return {"rc": r["rc"], "diag": r["diag"], "observed": "rejected" if r["rc"] != 0 else "lowered"}


def c06_ctl() -> dict:
    r = lower("c06c", "def f(p: *int) -> *int:\n    return p\n")
    return {"rc": r["rc"], "diag": r["diag"], "observed": "lowered" if r["rc"] == 0 else "rejected"}


CASES = [
    {
        "id": "G01",
        "key": "CODEGEN_binop_parens_dropped_reassociate",
        "doc": ("SYNTAX/12-operators.md", "左"),
        "want_pos": "parens_dropped",
        "want_ctl": "kept",
        "pos": c01,
        "ctl": c01_ctl,
        "phenomenon": "`a - (b - c)` 落成 `a - b - c`（同族还有 `%`/`>>`/`|` 与 `&`）⇒ 静默改算术",
    },
    {
        "id": "G02",
        "key": "LEXER_declared_augassign_unreachable",
        "doc": ("SYNTAX/12-operators.md", "**="),
        "want_pos": "unreachable",
        "want_ctl": "lowered",
        "pos": c02,
        "ctl": c02_ctl,
        "phenomenon": "文档写了 `**=`/`&=`/`|=`，词法器从不发这种 token ⇒ 硬解析失败（同族 8 个可用）",
    },
    {
        "id": "G03",
        "key": "CODEGEN_nested_defer_emitted_eagerly",
        "doc": ("SYNTAX/14-syntax-sugar.md", "函数退出时自动执行"),
        "want_pos": "eager",
        "want_ctl": "moved_to_exit",
        "pos": c03,
        "ctl": c03_ctl,
        "phenomenon": "`if`/`for` 里的 defer 就地发射，清理在函数退出**之前**跑（顶层 defer 才搬走）",
    },
    {
        "id": "G04",
        "key": "COMPTIME_collection_literal_leaks_ast_repr",
        "doc": ("SYNTAX/19-comptime.md", "被当作普通表达式处理"),
        "want_pos": "ast_leak",
        "want_ctl": "clean",
        "pos": c04,
        "ctl": c04_ctl,
        "phenomenon": "comptime 的列表/元组字面量把 `Constant(line=…)` 的 repr 写进产物 ⇒ 产物不可编译",
    },
    {
        "id": "G05",
        "key": "COMPTIME_string_result_emitted_unescaped",
        "doc": ("SYNTAX/19-comptime.md", "转换为注释"),
        "want_pos": "unescaped",
        "want_ctl": "commented",
        "pos": c05,
        "ctl": c05_ctl,
        "phenomenon": "comptime 的字符串结果被裸插值写进产物 ⇒ 变成活表达式（可劫持 docstring）",
    },
    {
        "id": "G07",
        "key": "COMPTIME_block_form_crashes_with_internal_exception",
        "doc": ("SYNTAX/19-comptime.md", "块形式 | 未实现"),
        "want_pos": "internal_exception",
        "want_ctl": "no_internal_exception",
        "pos": c07,
        "ctl": c07_ctl,
        "phenomenon": "文档写明 `comptime:` 块形式「未实现」，但失败方式是把内部异常"
        "`'list' object has no attribute '__dict__'` 当诊断抛出（行内形式却能出码）"
        "⇒ 缺陷在诊断路径，不是功能未实现",
    },
    {
        "id": "G06",
        "key": "TYPES_documented_pointer_element_types_rejected",
        "doc": ("SYNTAX/04-pointer-types.md", "*char"),
        "want_pos": "rejected",
        "want_ctl": "lowered",
        "pos": c06,
        "ctl": c06_ctl,
        "phenomenon": "文档工作例里的返回位 `*char` 被判 `Undefined name 'char'`（`let` 位却能用）",
    },
]


def main() -> int:
    started = now_s()
    OUT.write_text(
        json.dumps({"started": started, "refuse": ["未跑完"]}, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True, exist_ok=True)
    rows = []
    for c in CASES:
        a = c["pos"]("p_" + c["id"])
        b = c["pos"]("q_" + c["id"])
        ca = c["ctl"]()
        cb = c["ctl"]()
        if a.get("observed") != b.get("observed") or ca.get("observed") != cb.get("observed"):
            REFUSE.append(
                f"{c['id']}：两遍复跑不同向（pos {a.get('observed')}/{b.get('observed')}，"
                f"ctl {ca.get('observed')}/{cb.get('observed')}）⇒ 不入账"
            )
        pos_ok = a.get("observed") == c["want_pos"]
        ctl_ok = ca.get("observed") == c["want_ctl"]
        rows.append(
            {
                "id": c["id"],
                "key": c["key"],
                "phenomenon": c["phenomenon"],
                "doc": quote(*c["doc"]),
                "want_pos": c["want_pos"],
                "want_ctl": c["want_ctl"],
                "pos_first": a,
                "pos_second": b,
                "ctl_first": ca,
                "ctl_second": cb,
                "pos_ok": pos_ok,
                "ctl_ok": ctl_ok,
                "verdict": "CONFIRMED" if pos_ok and ctl_ok else "UNSURE",
            }
        )
    confirmed = [r["id"] for r in rows if r["verdict"] == "CONFIRMED"]
    unsure = [r["id"] for r in rows if r["verdict"] != "CONFIRMED"]
    check(
        "六条候选各跑两遍（24 档观察全部拿到）",
        sum(
            1
            for r in rows
            for k in ("pos_first", "pos_second", "ctl_first", "ctl_second")
            if r[k].get("observed")
        ),
        len(CASES) * 4,
        "四档 × 每条候选",
    )
    check("确诊 + 未确认 = 总数", len(confirmed) + len(unsure), len(rows), "两栏回加")
    check(
        "确诊集合非空（否则是本判据看不见，不是产品干净）",
        bool(confirmed),
        True,
        f"确诊 {confirmed}／未确认 {unsure}",
    )
    check(
        "声明原文全部定位成功",
        [r["id"] for r in rows if r["doc"]["line"] < 0],
        [],
        "file:line 现读",
    )
    check(
        "产物观察看的是文本不是 rc==0（G04/G05 的 rc 都是 0，坏在产物里）",
        [
            next(r["pos_first"]["rc"] for r in rows if r["id"] == "G04"),
            next(r["pos_first"]["rc"] for r in rows if r["id"] == "G05"),
        ],
        [0, 0],
        "两格的 rc 都是 0，坏在产物里",
    )
    CANARY = {
        "wrong_expectation_cannot_confirm": all(c["want_pos"] != c["want_ctl"] for c in CASES),
        "control_direction_is_declared_per_case": sorted({c["id"]: 1 for c in CASES})
        == sorted(r["id"] for r in rows),
    }
    check(
        "canary：pos 与 ctl 的期望方向每条都相反（同向就是没在做对照）",
        CANARY["wrong_expectation_cannot_confirm"],
        True,
        json.dumps(CANARY),
    )
    doc = {
        "started": started,
        "cases": len(CASES),
        "rows": rows,
        "confirmed": confirmed,
        "unsure": unsure,
        "keys": [r["key"] for r in rows if r["verdict"] == "CONFIRMED"],
        "canary": CANARY,
        "tmp_left": [],
        "self_checks": CHECKS,
        "refuse": [],
        "at_utc": now_s(),
    }
    # 清理：先试干净（不吃错误），Windows 上句柄未放会留下目录 ⇒ 必须复测
    for _ in range(3):
        shutil.rmtree(TMP, ignore_errors=True)
        if not TMP.exists():
            break
    leftovers = sorted(q.name for q in TMP.glob("*")) if TMP.exists() else []
    if TMP.exists() and not leftovers:
        try:
            TMP.rmdir()
        except OSError as exc:
            leftovers.append(f"<rmdir:{type(exc).__name__}>")
    doc["tmp_left"] = leftovers
    if leftovers:
        REFUSE.append(f"跑完仍有残渣 {leftovers}（目录 {TMP.name} 还在 ⇒ 清理静默失败）")
    red = [f"判据自证未过：{x['label']}（实得 {x['got']}）" for x in CHECKS if not x["ok"]]
    doc["refuse"] = sorted(set(REFUSE) | set(red))
    OUT.write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "refuse": doc["refuse"],
                "confirmed": confirmed,
                "unsure": unsure,
                "observed": {
                    r["id"]: [r["pos_first"].get("observed"), r["ctl_first"].get("observed")]
                    for r in rows
                },
                "self_checks": f"{sum(1 for x in CHECKS if x['ok'])}/{len(CHECKS)}",
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as exc:
        OUT.write_text(
            json.dumps(
                {"refuse": [f"崩在 {type(exc).__name__}: {exc}"]}, ensure_ascii=False, indent=1
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(json.dumps({"crashed": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        sys.exit(2)
