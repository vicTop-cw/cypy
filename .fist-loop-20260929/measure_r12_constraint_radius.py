"""R12 推进腿：声明界（`T: int | float`）在注解位/实例化位开判的**存量半径**取数件。

形状：不在探针里复刻判据（复刻出来的差集会骗人 —— 那是我的探针在判，不是编译器在判），
而是把同一批源在两个树上各跑一遍，逐文件点名差集：
 · `--phase before` 只跑现树，落 `r12_radius_before.json`（每个源的错误集合 + 是否含带约束的泛型声明）；
 · `--phase after`  跑现树 + 改动树（`--tree` 指向副本），与 before 逐文件比集合，印出新红/消失的红；
 · 半径判据写成门：改动树必须 (a) 让本环准备的违例样本变红、(b) 对不含约束声明的源**一条不差**
   （不牵连 ⇒ 不是"顺手打红别人"）。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BEFORE = HERE / "r12_radius_before.json"
AFTER = HERE / "r12_radius_after.json"
SKIP_PARTS = {".git", "__pycache__", "node_modules", ".fist-loop-20260929", ".r12_tree"}

# 带约束的泛型声明：`def f<T: X>` / `class C<T: X>` / `struct S<T: X>`（约束里可含 `|` 与 `+`）
CONS_DECL = re.compile(r"(?:def|class|struct)\s+\w+\s*<[^<>]*:[^<>]*>")


def collect_sources() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for p in sorted(ROOT.rglob("*.cypy")):
        # 跳过历轮 scratch 树（`.fist-loop-*` 里多是上一轮的负例夹具与探针，混进来会把半径口径搞脏）
        if any(part in SKIP_PARTS or part.startswith(".fist-loop-") for part in p.parts):
            continue
        out.append((str(p.relative_to(ROOT)).replace("\\", "/"),
                    p.read_text(encoding="utf-8", errors="replace")))
    for p in sorted((ROOT / "corpus").glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        for i, t in enumerate(data.get("tests", [])):
            src = t.get("source") or ""
            if src:
                out.append((f"corpus/{p.name}#{i}:{t.get('name', '')}", src))
    return out


RUNNER = '''import json, sys
sys.path.insert(0, sys.argv[1])
from cypyc.analyzer.type_checker import TypeChecker
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
srcs = json.load(open(sys.argv[2], encoding="utf-8"))
out = {}
for label, src in srcs.items():
    try:
        ast = Parser(list(Lexer(src).tokenize())).parse()
    except ValueError as e:
        # 解析期硬拒是"诊断"而不是"崩"：历轮夹具里九成是这种，混进 crashes 会把尺子读成坏了
        out[label] = {"errors": [], "crash": "", "parse_refused": "ValueError: " + str(e)[:140]}
        continue
    except Exception as e:
        out[label] = {"errors": [], "crash": type(e).__name__ + ": " + str(e)[:140], "parse_refused": ""}
        continue
    tc = TypeChecker()
    try:
        tc.check(ast)
        out[label] = {"errors": list(tc.errors), "crash": "", "parse_refused": ""}
    except Exception as e:
        out[label] = {"errors": [], "crash": "check " + type(e).__name__ + ": " + str(e)[:140],
                      "parse_refused": ""}
json.dump(out, open(sys.argv[3], "w", encoding="utf-8"), ensure_ascii=False)
print("RUNNER tree=" + sys.argv[1] + " sources=" + str(len(out)))
'''


def snapshot(tree: Path) -> dict:
    """一棵树一个子进程跑全量：既避开 sys.modules 里已导入的旧副本，也不做 1100+ 次 spawn。"""
    import os
    import subprocess
    import tempfile

    srcs = dict(collect_sources())
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8",
                                     dir=str(HERE)) as mf, \
            tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8",
                                        dir=str(HERE)) as of:
        man, outp = mf.name, of.name
        json.dump(srcs, mf, ensure_ascii=False)
    rp = HERE / "_radius_runner.py"
    rp.write_text(RUNNER, encoding="utf-8")
    try:
        r = subprocess.run([sys.executable, "-X", "utf8", str(rp), str(tree), man, outp],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=1800)
        res = json.loads(Path(outp).read_text(encoding="utf-8")) if Path(outp).exists() else {}
    finally:
        for p in (man, outp):
            try:
                os.unlink(p)
            except OSError:
                pass
    if r.returncode != 0 or not res:
        raise SystemExit(f"取数子进程失败 rc={r.returncode} stderr={(r.stderr or '')[-400:]}")
    rows = {}
    for label, src in srcs.items():
        got = res.get(label) or {"errors": [], "crash": "(缺行)", "parse_refused": ""}
        rows[label] = {"errors": got["errors"], "crash": got.get("crash", ""),
                       "parse_refused": got.get("parse_refused", ""),
                       "cons_decls": len(CONS_DECL.findall(src))}
    return {"tree": str(tree).replace("\\", "/"), "n_sources": len(rows),
            "n_with_cons_decl": sum(1 for v in rows.values() if v["cons_decls"]),
            "cons_decl_total": sum(v["cons_decls"] for v in rows.values()),
            "crashes": [k for k, v in rows.items() if v["crash"]],
            "parse_refused": sum(1 for v in rows.values() if v["parse_refused"]),
            "runner_line": (r.stdout or "").strip()[-200:],
            "rows": rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["before", "after"], required=True)
    ap.add_argument("--tree", default=str(ROOT), help="after 阶段传改动树根目录（含 cypyc/）")
    args = ap.parse_args()

    snap = snapshot(Path(args.tree))
    if args.phase == "before":
        BEFORE.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"CONCLUSION phase=before sources={snap['n_sources']} with_cons={snap['n_with_cons_decl']} "
              f"decls={snap['cons_decl_total']} parse_refused={snap['parse_refused']} "
              f"real_crashes={len(snap['crashes'])} out={BEFORE.name}")
        return 0 if not snap["crashes"] else 1

    if not BEFORE.exists():
        raise SystemExit("before 快照不在 ⇒ 没有底树就不许报半径（差集无从谈起）")
    base = json.loads(BEFORE.read_text(encoding="utf-8"))["rows"]
    after = snap["rows"]
    new_red, gone_red, unchanged_noncons = [], [], 0
    for label, row in after.items():
        b = base.get(label)
        if b is None:
            continue
        added = [e for e in row["errors"] if e not in b["errors"]]
        removed = [e for e in b["errors"] if e not in row["errors"]]
        if added:
            new_red.append({"src": label, "cons_decls": row["cons_decls"], "added": added[:6]})
        if removed:
            gone_red.append({"src": label, "removed": removed[:6]})
        if not added and not removed and not b["cons_decls"] and not row["cons_decls"]:
            unchanged_noncons += 1
    AFTER.write_text(json.dumps({"snapshot": snap, "new_red": new_red, "gone_red": gone_red,
                                 "unchanged_non_constraint_sources": unchanged_noncons,
                                 "sources_before": len(base), "sources_after": len(after)},
                                ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"SCOPE before={len(base)} after={len(after)} crashes={len(snap['crashes'])}")
    for r in new_red:
        print("NEW_RED", r["src"], "| cons_decls=", r["cons_decls"], "|", " ; ".join(x[:110] for x in r["added"]))
    for r in gone_red:
        print("GONE_RED", r["src"], "|", " ; ".join(x[:110] for x in r["removed"]))
    touched = {r["src"] for r in new_red} | {r["src"] for r in gone_red}
    unexpected = [r for r in new_red if not r["cons_decls"]]
    print(f"SCOPE parse_refused={snap['parse_refused']}")
    print(f"CONCLUSION phase=after new_red_sources={len(new_red)} gone_red_sources={len(gone_red)} "
          f"touched={len(touched)} unchanged_non_cons={unchanged_noncons} "
          f"new_red_without_constraint_decl={len(unexpected)} real_crashes={len(snap['crashes'])}")
    return 0 if not unexpected and not snap["crashes"] else 1


if __name__ == "__main__":
    sys.exit(main())
