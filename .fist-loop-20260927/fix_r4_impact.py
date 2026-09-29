"""语义变更影响面：同一批语料，**修前分析器 vs 修后分析器**逐档对拍。

判据不是「跑通了没」，而是「有没有让**存量合法程序**开始报错」：
- `newly_rejected` = 修前零诊断、修后有诊断的档案 ⇒ 每一条都要有裁决条目，没裁决就是未结；
- `newly_accepted` = 修前有诊断、修后没了 ⇒ 也要点名（放松了不该放松的东西）；
- `unchanged_with_errors` = 两态都报且内容相同 ⇒ 与本次改动无关。

两态用同一份 AST 各跑一遍（修前类从 `fix_r4_before/type_checker.py` 现加载），
差别只允许在产品码；加载失败/身份不对就整栏拒绝，不降级成「没影响」。
"""

from __future__ import annotations

import datetime
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BEFORE = HERE / "fix_r4_before" / "type_checker.py"
OUT = HERE / "fix_r4_impact.json"
SKIP_DIRS = {".git", "__pycache__", "build", "dist", ".fist-loop-20260927",
             ".fist-polish-20260926", ".fist-hunt-20260926", "node_modules", ".pytest_cache"}
REFUSE: list = []
CHECKS: list = []


def check(label, got, want, why) -> None:
    CHECKS.append({"label": label, "got": got, "want": want, "why": why, "ok": got == want})


def load_before_checker():
    spec = importlib.util.spec_from_file_location("cypy_before_r4_type_checker", str(BEFORE))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod.TypeChecker


def analyze(cls, source: str):
    """与 CypyHook._parse_and_analyze 同一条前段（预处理→词法→语法），只差分析器换类。"""
    from cypyc.parser.lexer import Lexer
    from cypyc.parser.parser import Parser
    from cypyc.parser.preprocessor import Preprocessor

    text = Preprocessor().process(source)
    try:
        tree = Parser(list(Lexer(text).tokenize())).parse()
    except Exception as exc:
        return {"parse_error": f"{type(exc).__name__}: {exc}", "errors": []}
    tc = cls()
    try:
        tc.check(tree)
    except Exception as exc:
        return {"checker_crash": f"{type(exc).__name__}: {exc}", "errors": []}
    return {"errors": sorted(tc.errors or [])}


def corpus():
    files = []
    for p in ROOT.rglob("*.cypy"):
        if set(p.relative_to(ROOT).parts) & SKIP_DIRS:
            continue
        files.append(p)
    return sorted(files)


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    if not BEFORE.exists():
        print(json.dumps({"refuse": [f"修前快照不在盘上：{BEFORE}"]}, ensure_ascii=False))
        return 1
    Before = load_before_checker()
    from cypyc.analyzer.type_checker import TypeChecker as After

    check("两态是**不同**的分析器类（同一个类对拍=恒等式）",
          Before is After, False, f"before={Before.__module__} after={After.__module__}")
    check("修前快照确实没有可调用签名注册表（正面证明它是修前的码）",
          hasattr(Before(), "callable_sigs"), False, "属性探针")

    rows, newly_rejected, newly_accepted = [], [], []
    for path in corpus():
        src = path.read_text(encoding="utf-8", errors="replace")
        b, a = analyze(Before, src), analyze(After, src)
        bset, aset = set(b["errors"]), set(a["errors"])
        added, dropped = sorted(aset - bset), sorted(bset - aset)
        row = {"file": path.relative_to(ROOT).as_posix(),
               "before_errors": len(b["errors"]), "after_errors": len(a["errors"]),
               "added": added, "dropped": dropped,
               "parse_error": b.get("parse_error") or a.get("parse_error"),
               "checker_crash": a.get("checker_crash") or b.get("checker_crash")}
        rows.append(row)
        if not b["errors"] and a["errors"]:
            newly_rejected.append(row)
        if b["errors"] and not a["errors"]:
            newly_accepted.append(row)

    crashed = [r["file"] for r in rows if r["checker_crash"]]
    if crashed:
        REFUSE.append(f"修后分析器在真实语料上崩溃：{crashed[:5]}")
    unparsed = sum(1 for r in rows if r["parse_error"])
    # 未结 = 新增诊断里没被逐条裁决的；本轮裁决口径：修复环**不接受**任何存量合法程序被新拒，
    # 出现即挂账交人工（不许为了绿而放宽），因此这里必须为空才算结。
    unadjudicated = [{"file": r["file"], "added": r["added"]} for r in newly_rejected]
    check("语料不为空（.cypy 至少 20 档）", len(rows) >= 20, True, f"实测 {len(rows)} 档")
    check("对拍两侧都真跑过（每档都有 before/after 计数）",
          all(isinstance(r["before_errors"], int) and isinstance(r["after_errors"], int)
              for r in rows), True, f"{len(rows)} 行")
    check("修后不得让存量零诊断的档案变成有诊断（有就挂账，本栏必须为空）",
          unadjudicated, [], "newly_rejected 明细")
    check("修后也不得悄悄放松掉既有诊断", [r["file"] for r in newly_accepted], [],
          "newly_accepted 明细")

    refuse = sorted(set(REFUSE)) + [f"自证未过：{c['label']}（实得 "
                                    f"{json.dumps(c['got'], ensure_ascii=False)[:200]}）"
                                    for c in CHECKS if not c["ok"]]
    doc = {"started": started, "corpus": len(rows), "corpus_unparsed": unparsed,
           "rows": rows, "newly_rejected": newly_rejected,
           "newly_accepted": newly_accepted, "unadjudicated": unadjudicated,
           "note": "对照的是**同一批 AST**上两个版本的 TypeChecker；parse_error 只说明该档"
                   "本来就解析不动（两侧一致），不计入影响面",
           "refuse": refuse,
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"corpus": len(rows), "refuse": refuse,
                      "newly_rejected": [r["file"] for r in newly_rejected],
                      "newly_accepted": [r["file"] for r in newly_accepted],
                      "added_total": sum(len(r["added"]) for r in rows),
                      "dropped_total": sum(len(r["dropped"]) for r in rows)},
                     ensure_ascii=False, indent=1))
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
