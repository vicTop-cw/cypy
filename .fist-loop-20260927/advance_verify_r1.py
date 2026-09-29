"""R1-推进 law1：把「已声明未实现」清单从子代理的推断**改成我自己实测**。

每条候选要同时过两关，否则不进清单：
 A. 声明关（doc）：`SYNTAX/*.md` 指定行号 ±3 行内必须真的出现该语法的声明句原文——
    文档没写的形状不算"已声明未实现"（上一轮的教训：形状推断会把无关表格行当成承诺）；
 B. 实现关（probe）：把一条最小 .cypy 源码打到 **CLI 调用面**
    （`python -m cypyc transpile … -o <探针输出目录>`），按 rc 与**产物文本**分类：
      - `gap-parse`：rc≠0（今天直接解析失败）
      - `gap-silent`：rc=0 但产物里没有声明所承诺的结构（静默丢弃型，最危险）
      - `works`：rc=0 且产物里有该结构 ⇒ **不是缺口**，从清单里摘掉
      - `not-declared`：A 关没过

每个"产物里有该结构"的判据都配**成对对照**：一段必然匹配的正例 + 当前产物必然不匹配的反例；
matcher 两条里任何一条不按预期 ⇒ 该条判据作废并拒绝出 JSON（宁可不出清单，不出假清单）。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(r"E:\IDEProjects\AI\Cypy")
PROBE_DIR = HERE / "probes"
OUT_DIR = PROBE_DIR / "out"
REFUSE = []


def doc_lines(rel: str, line: int, span: int = 3) -> str:
    p = ROOT / rel
    if not p.exists():
        return ""
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    lo, hi = max(0, line - 1 - span), min(len(lines), line + span)
    return "\n".join(lines[lo:hi])


def transpile(name: str, src: str) -> dict:
    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sp = PROBE_DIR / f"{name}.cypy"
    sp.write_text(src, encoding="utf-8", newline="\n")
    r = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "cypyc", "transpile", str(sp), "-o", str(OUT_DIR)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    out = (r.stdout or "") + (r.stderr or "")
    pyx = OUT_DIR / (sp.stem + ".pyx")
    code = pyx.read_text(encoding="utf-8", errors="replace") if pyx.exists() else ""
    err = [ln for ln in out.splitlines() if "rror" in ln or "xpect" in ln or "nexpected" in ln]
    return {
        "rc": r.returncode,
        "source_rel": sp.relative_to(ROOT).as_posix(),
        "emit_rel": pyx.relative_to(ROOT).as_posix() if pyx.exists() else None,
        "emit": code,
        "cli_error_first": err[0][:200] if err else "",
        "ok_banner": "[OK] Transpiled successfully" in out,
    }


def match(pairs: list) -> dict:
    """成对对照：(正例必抓, 反例必不抓)。返回每条 matcher 的通过情况。"""
    res = []
    for pat, pos, neg in pairs:
        rx = re.compile(pat)
        ok_pos = bool(rx.search(pos))
        ok_neg = not rx.search(neg)
        res.append({"pat": pat, "catches_positive": ok_pos, "misses_negative": ok_neg})
        if not (ok_pos and ok_neg):
            REFUSE.append(f"matcher 不可信（对照不过）：{pat} pos={ok_pos} neg={ok_neg}")
    return {"pairs": res}


CANDS = [
    {
        "id": 1,
        "name": "raise X from e（异常链）",
        "docs": [("SYNTAX/16-exceptions.md", 111, "from e")],
        "src": (
            "def load() -> int:\n"
            "    try:\n"
            '        raise FileNotFoundError("nope")\n'
            "    except FileNotFoundError as e:\n"
            '        raise RuntimeError("Failed to load data") from e\n'
            "    return 0\n"
        ),
        "want": r"raise\s+\w+\([^)]*\)\s+from\s+\w+",
        "neg_before_fix": "raise RuntimeError('Failed to load data')",
    },
    {
        "id": 2,
        "name": "枚举内自定义方法",
        "docs": [("SYNTAX/06-enum.md", 79, "自定义方法")],
        "src": (
            "enum Operation:\n"
            "    ADD\n"
            "    SUBTRACT\n"
            "\n"
            "    def label(self) -> str:\n"
            '        return "op"\n'
        ),
        "want": r"def\s+label\s*\(",
        "neg_before_fix": "cpdef enum Operation:",
    },
    {
        "id": 3,
        "name": "struct 里的 @staticmethod",
        "docs": [("SYNTAX/06d-builtin-magic-traits.md", 49, "@staticmethod")],
        "src": (
            "struct Point:\n"
            "    x: int\n"
            "\n"
            "    @staticmethod\n"
            "    def origin() -> Point:\n"
            "        return Point(x=0)\n"
        ),
        "want": r"def\s+origin\(\s*\)",
        "want_pos": "def origin() -> Point:",
        "neg_before_fix": "def origin(self):",
    },
    {
        "id": 4,
        "name": "__implicit_default__ 隐式默认填充",
        "docs": [("SYNTAX/06d-builtin-magic-traits.md", 53, "__implicit_default__")],
        "src": (
            "struct Config:\n"
            "    timeout: int\n"
            "    debug: bool\n"
            "\n"
            "    @staticmethod\n"
            "    def __implicit_default__() -> Config:\n"
            "        return Config(timeout=30, debug=False)\n"
            "\n"
            "def process(cfg: Config = __implicit_default__) -> int:\n"
            "    return cfg.timeout\n"
        ),
        "want": r"__implicit_default__\s*\(\s*\)",
        "want_pos": "def process(cfg=__implicit_default__()):",
        "neg_before_fix": "def process(cfg=__implicit_default__):",
    },
    {
        "id": 5,
        "name": "let x =:（变量构建块）",
        "docs": [("SYNTAX/13-build-blocks.md", 74, "let result =:")],
        "src": (
            "let result =:\n"
            "    let x: int = 10\n"
            "    let y: int = 20\n"
            "    x + y\n"
            "\n"
            "print(result)\n"
        ),
        "want_pos": "result = _bb_0()",
        "want": r"(?m)^result\s*=\s*_bb_\d+\(\)$",
        "neg_before_fix": "result = def _bb_0():    x: int = 10    return x + y",
    },
    {
        "id": 6,
        "name": "guard <cond>（action 可省）",
        "docs": [("SYNTAX/appendix-A-keywords.md", 41, "guard <cond> [: <action>]")],
        "src": ("def f(x: int) -> int:\n" "    guard x > 0\n" "    return x\n"),
        "want": r"guard",
        "neg_before_fix": "«解析失败，无产物»",
    },
    {
        "id": 7,
        "name": "f(name~ value) 调用形波浪",
        "docs": [("SYNTAX/appendix-B-operators.md", 187, "f(name~")],
        "src": ("def g(x: int) -> int:\n" "    return x\n" "\n" "let v: int = g(x~)\n"),
        "want": r"~",
        "neg_before_fix": "«解析失败，无产物»",
    },
    {
        "id": 8,
        "name": "def f(..args) 具名可变参数",
        "docs": [("SYNTAX/appendix-B-operators.md", 167, "def f(..args)")],
        "src": ("def f(..args) -> int:\n" "    return 1\n"),
        "want": r"args",
        "neg_before_fix": "«解析失败，无产物»",
    },
    {
        "id": 9,
        "name": "case Point(x=0, y=0) 结构体关键字模式",
        "docs": [("SYNTAX/17-pattern-matching.md", 118, "case Point(x=0, y=0)")],
        "src": (
            "struct Point:\n"
            "    x: int\n"
            "    y: int\n"
            "\n"
            "def q(p: Point) -> str:\n"
            "    match p:\n"
            "        case Point(x=0, y=0):\n"
            '            return "origin"\n'
            "        case _:\n"
            '            return "other"\n'
        ),
        "want": r"\.\_?_f\d|x\s*==\s*0",
        "want_pos": "if p.__f0 == 0:",
        "neg_before_fix": "«解析失败，无产物»",
    },
]


def main() -> int:
    rows = []
    for c in CANDS:
        declared = []
        for rel, ln, needle in c["docs"]:
            txt = doc_lines(rel, ln)
            declared.append(
                {
                    "where": f"{rel}:{ln}",
                    "needle": needle,
                    "found": needle in txt,
                    "quoted_line": next(
                        (ln.strip()[:160] for ln in txt.splitlines() if needle in ln), ""
                    ),
                }
            )
        dec_ok = all(d["found"] for d in declared)
        pr = transpile(f"adv_c{c['id']}", c["src"])
        emit = pr.pop("emit")
        # matcher 对照：正例=声明所承诺的形状，反例=**固定的"修复前形状"**（写在候选表里）。
        # 不用本次产物当反例：产物会随修复变化，拿它当对照等于"判据跟着结论改"，
        # 上一版就是这条错把已经修好的 #1 判成 matcher 不可信。产物只用于分类，不参与对照。
        ctl = match([(c["want"], c.get("want_pos", c["src"]), c["neg_before_fix"])])
        emit_matched = bool(re.search(c["want"], emit)) if emit else False
        if pr["rc"] != 0:
            verdict = "gap-parse"
        elif not emit:
            verdict = "gap-no-artifact"
        elif emit_matched:
            verdict = "works"
        else:
            verdict = "gap-silent"
        if not dec_ok:
            verdict = "not-declared"
        rows.append(
            {
                "id": c["id"],
                "name": c["name"],
                "declared": dec_ok,
                "doc_evidence": declared,
                "probe": {**pr, "emit_lines": len(emit.splitlines())},
                "matcher_control": ctl,
                "emit_matched": emit_matched,
                "verdict": verdict,
            }
        )
        if not ctl["pairs"]:
            REFUSE.append(f"候选 #{c['id']} 没有对照，判据不成立")

    gaps = [r["id"] for r in rows if r["verdict"].startswith("gap")]
    works = [r["id"] for r in rows if r["verdict"] == "works"]
    undecl = [r["id"] for r in rows if r["verdict"] == "not-declared"]
    if not gaps:
        REFUSE.append("一条缺口都没复现出来 ⇒ 要么清单全错，要么探针坏了，须人工看")
    for r in rows:
        if r["verdict"].startswith("gap") and not r["probe"]["source_rel"]:
            REFUSE.append(f"候选 #{r['id']} 判成 gap 却没有探针源码")

    doc = {
        "refuse": REFUSE,
        "counts": {"candidates": len(rows), "gaps": gaps, "works": works, "not_declared": undecl},
        "rows": rows,
    }
    (HERE / "advance_verify_r1.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    slim = [
        {
            "id": r["id"],
            "name": r["name"],
            "verdict": r["verdict"],
            "rc": r["probe"]["rc"],
            "err": r["probe"]["cli_error_first"][:90],
            "doc": r["doc_evidence"][0]["where"],
        }
        for r in rows
    ]
    print(json.dumps({"refuse": REFUSE, "rows": slim}, ensure_ascii=False, indent=1))
    return 1 if REFUSE else 0


if __name__ == "__main__":
    sys.exit(main())
