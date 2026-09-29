#!/usr/bin/env python3
"""R1-寻虫 · 路 1「对抗样例构造」+ 路 5「模式化读码」的实跑件。

期望先行（写在每条用例的 expect 里，来自 SYNTAX/ 与 CLI 的既有契约）：
编译器对任何输入只能有三种正当结局——① 带行列的结构化诊断；② 正常产物；
③ 已声明的异常类型（IncludeError / CompileError 等）。
未声明的 Python 异常逃逸到调用方（IndexError / KeyError / TypeError / AttributeError /
RecursionError / UnicodeDecodeError / StopIteration …）就是「编译器崩了而不是拒绝了输入」，即候选。

产物：.fist-loop-20260927/hunts/adv_r1.json（逐条判定）与 adv_r1.md（人读摘要）。
本件只找不修，判定权在指挥官复核后的入账脚本。
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

ROOT = Path(r"E:\IDEProjects\AI\Cypy")
sys.path.insert(0, str(ROOT))
HERE = Path(__file__).resolve().parent
OUT = HERE / "hunts"

from cypyc.parser.lexer import Lexer  # noqa: E402
from cypyc.parser.parser import Parser  # noqa: E402
from cypyc.parser.preprocessor import IncludeError  # noqa: E402
from cypyc.analyzer.type_checker import TypeChecker  # noqa: E402
from cypyc.analyzer.scope_analyzer import ScopeAnalyzer  # noqa: E402
from cypyc.codegen.cython_generator import CythonGenerator  # noqa: E402

DECLARED = (IncludeError,)  # 真·已声明的编译期异常
DIAG_MARKS = ("line", "Line", "行", "列", "[E", "E0", "E1", "error", "Error:")


def pipeline(src: str) -> dict:
    """跑「词法→语法→类型检查→作用域→代码生成」，把结局结构化返回。"""
    r = {
        "exception": None,
        "trace_tail": "",
        "diagnostics": [],
        "artifact_len": 0,
        "artifact_head": "",
    }
    try:
        tokens = list(Lexer(src).tokenize())
        ast = Parser(tokens).parse()
        tc = TypeChecker()
        tc.check(ast)
        r["diagnostics"] += [str(d) for d in (getattr(tc, "errors", None) or [])][:6]
        sa = ScopeAnalyzer()
        sa.analyze(ast)
        r["diagnostics"] += [str(d) for d in (getattr(sa, "errors", None) or [])][:6]
        code = CythonGenerator().generate(ast)
        r["artifact_len"] = len(code or "")
        r["artifact_head"] = "\n".join((code or "").splitlines()[8:16])
    except BaseException as exc:  # noqa: BLE001 — 分类需要看所有逃逸
        r["exception"] = type(exc).__name__
        r["declared"] = isinstance(exc, DECLARED)
        r["diag_like"] = any(m in str(exc) for m in DIAG_MARKS)
        r["trace_tail"] = traceback.format_exc().strip().splitlines()[-3:]
        r["msg"] = str(exc)[:220]
    return r


CASES = [
    ("adv_01_empty", "", "空文件：应正常产出模块头或给诊断，不得抛"),
    ("adv_02_comments_only", "# 只有注释\n\n# 再来一行\n", "同上"),
    (
        "adv_03_unterminated_string",
        'def main() -> int:\n    s: str = "abc\n    return 0\n',
        "未闭合字符串：语法诊断（带行列），不得裸 SyntaxError/IndexError",
    ),
    (
        "adv_04_non_utf8_bytes",
        "def main() -> int:\n    # 中文注释 GBK 风险面\n    return 0\n",
        "含非 ASCII 注释：应能处理或诊断；不得 UnicodeDecodeError",
    ),
    (
        "adv_05_deep_nesting",
        "def main() -> int:\n    return " + "(" * 200 + "1" + ")" * 200 + "\n",
        "200 层括号：应诊断或成功，不得 RecursionError",
    ),
    (
        "adv_06_dup_def",
        "def a() -> int:\n    return 1\n\ndef a() -> int:\n    return 2\n",
        "SYNTAX/33 C-3.1：同名 def 应作为作用域诊断上报",
    ),
    (
        "adv_07_subtype_vs_class",
        "subtype Meter of float\n\nclass Meter:\n    x: int = 1\n",
        "C-3.1：subtype 撞 class 名应诊断（BUG-11 修过的上送面）",
    ),
    (
        "adv_08_type_vs_constraint",
        "type Len = float\n\nconstraint Len = int | float\n",
        "C-3.1：type 撞 constraint 名应诊断",
    ),
    (
        "adv_09_empty_struct",
        "struct Empty:\n    pass\n\ndef main() -> int:\n    return 0\n",
        "空 struct：应成功或诊断",
    ),
    (
        "adv_10_slice_step_zero",
        "def main() -> int:\n    xs: [int] = [1, 2, 3]\n" "    ys = xs[0:3:0]\n    return 0\n",
        "step=0 切片：应诊断，不得把 ZeroDivisionError 留给运行期或编译期裸抛",
    ),
    (
        "adv_11_const_div_zero",
        "def main() -> int:\n    a: int = 1\n    b: int = a / 0\n    return 0\n",
        "常量除零：诊断或产物内保护，不得编译期裸抛",
    ),
    (
        "adv_12_huge_int_literal",
        "def main() -> int:\n    n: int = 99999999999999999999999\n    return 0\n",
        "超 int64 字面量赋给 int：应诊断宽度溢出（SYNTAX/01 宽度面）",
    ),
    ("adv_13_undefined_name", "def main() -> int:\n    return notdefined\n", "未定义名：应诊断"),
    (
        "adv_14_cast_to_nontype",
        "def main() -> int:\n    x: int = 1\n    y = x as NotAType\n    return 0\n",
        "as 到未知类型：应诊断，不得 KeyError 于类型表",
    ),
    (
        "adv_15_include_missing",
        'include "does_not_exist_anywhere.cypy"\n\ndef main() -> int:\n    return 0\n',
        "include 不存在：IncludeNotFound 或诊断（不得静默 skip 后成功）",
    ),
    (
        "adv_16_defer_top_level",
        "defer print(1)\n\ndef main() -> int:\n    return 0\n",
        "顶层 defer：应诊断位置非法",
    ),
    (
        "adv_17_pipe_to_nonfunc",
        "def main() -> int:\n    r = 5 |> 3\n    return 0\n",
        "pipe 右端不是可调用：应诊断",
    ),
    (
        "adv_18_nested_fstring",
        'def main() -> int:\n    print(f"a{f"b{1}"}c")\n    return 0\n',
        "嵌套 f-string：应诊断或成功，不得切片越界",
    ),
    (
        "adv_19_negative_index_const",
        "def main() -> int:\n    xs: [int] = []\n    return xs[-1]\n",
        "空列表取 -1：诊断或运行期保护，不得编译期崩",
    ),
    (
        "adv_20_unbalanced_bracket",
        "def main() -> int:\n    xs = [1, 2, 3\n    return 0\n",
        "未闭合中括号：语法诊断，不得 IndexError",
    ),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for cid, src, expect in CASES:
        sample = OUT / f"{cid}.cypy"
        sample.write_text(src, encoding="utf-8", newline="\n")
        res = pipeline(src)
        exc = res.get("exception")
        if exc is None:
            cls = "静默成功" if not res["diagnostics"] else "带诊断产出"
        elif res.get("declared"):
            cls = "已声明异常"
        elif exc == "ValueError" and res.get("diag_like"):
            cls = "诊断式上抛（待研判）"  # 文案像诊断，不算崩溃，但也不默认放过
        else:
            cls = "候选：未声明异常逃逸"
        rows.append(
            {
                "id": cid,
                "sample": sample.relative_to(ROOT).as_posix(),
                "expect": expect,
                "outcome_class": cls,
                "exception": exc,
                "msg": res.get("msg"),
                "diagnostics": res["diagnostics"],
                "artifact_len": res["artifact_len"],
                "trace_tail": res.get("trace_tail"),
            }
        )
    (OUT / "adv_r1.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    cands = [r for r in rows if r["outcome_class"].startswith("候选")]
    from collections import Counter

    tally = Counter(r["outcome_class"] for r in rows)
    lines = [
        "# R1 路 1 对抗样例实跑",
        "",
        f"用例 {len(rows)} 条；" + "；".join(f"{k} {v}" for k, v in sorted(tally.items())),
        "",
        f"分类口径：只有「带行列的诊断文案 / 已声明异常 / 正常产物」算正当结局；"
        "裸 traceback 一律候选，文案像诊断的 ValueError 单列「待研判」而不默认放过。",
        "",
    ]
    for r in rows:
        lines.append(
            f"- `{r['id']}` → **{r['outcome_class']}**"
            + (
                f"（{r['exception']}: {str(r['msg'])[:120]}）"
                if r["exception"]
                else f"（诊断 {len(r['diagnostics'])} 条，产物 {r['artifact_len']} 字节）"
            )
        )
        if r["outcome_class"].startswith("候选"):
            for t in r["trace_tail"] or []:
                lines.append(f"    `{t}`")
    (OUT / "adv_r1.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(lines))
    print(f"cands={[r['id'] for r in cands]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
