"""`.gitignore` 与「读它的消费者」之间的对表门（提交前跑）。

起因：本轮收口要把 12 轮的工具与证据一起入库，`.gitignore` 写了十几条排除规则。
第一版把 `Find_BUG/audit_2026q3/` 整个排掉了，而 `tests/test_golden_anchor_probes.py`
是直接**执行**那目录下两个探针的 —— 干净检出的仓库会让一条既有测试红掉，
而这条红看起来像"测试坏了"，不像"我刚才排错了一个目录"。

判据形状（成对，缺一边就是空转）：
  * 正向：从消费者源码里反解出路径串 ⇒ 落盘存在的路径**不得**被 ignore；
  * 负向（canary）：`fist-mbt.db` 必须被判成"已忽略" ⇒ 证明 `git check-ignore` 这条通道
    真的看得见东西，而不是恒返回"未忽略"（恒绿尺子的常见死法）。
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

CONSUMERS = ["tests", "scripts", ".fist-loop-20260929", ".fist-loop-20260927", "examples"]
CANARY_IGNORED = ["fist-mbt.db", "build", "dist"]
CANARY_TRACKED = ["cypyc/analyzer/type_checker.py", "tests/regression/test_corpus_pairs.py"]


def join_chain(nodes) -> str:
    parts = []
    for seg in nodes:
        s = str(seg).strip("/")
        if not s or s == "..":
            continue
        parts.append(s)
    return "/".join(parts)


def string_tokens(tree: ast.AST) -> set:
    """从 AST 里挖出「像仓库相对路径」的串：显式带斜杠的常量 + `a / "b" / "c"` 链 + os.path.join。"""
    out = set()

    def lit(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    def walk(node, acc):
        k = lit(node)
        if k is not None:
            acc.append(k)
            out.add(k)
            return
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            left, right = [], []
            walk(node.left, left)
            walk(node.right, right)
            joined = join_chain(left + right)
            if joined:
                out.add(joined)
            acc.extend(right)
            return
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "join"
        ):
            segs = []
            for a in node.args:
                found = []
                walk(a, found)
                segs.extend(found)
            joined = join_chain(segs)
            if joined:
                out.add(joined)
            return
        for child in ast.iter_child_nodes(node):
            walk(child, acc)

    walk(tree, [])
    return out


def candidate_paths(tok: str) -> list:
    """把一个串折成若干「可检验的仓库相对路径」（去掉前导 ./ 与绝对前缀）。"""
    t = tok.replace("\\", "/").strip()
    if not t or " " in t or len(t) > 120:
        return []
    cands = []
    if t.startswith("./"):
        cands.append(t[2:])
    elif t.startswith("/") or ":" in t[:3]:
        rel = t.split("Cypy/")[-1] if "Cypy/" in t else None
        if rel:
            cands.append(rel)
    else:
        cands.append(t)
    keep = []
    for c in cands:
        if not c or c.startswith(".") and "/" not in c:
            continue
        if (ROOT / c).exists():
            keep.append(c)
    return keep


def ignored_map(paths: list) -> set:
    """问 git 哪些路径被排除。

    Windows 坑（实测）：`text=True` 会把 stdin 里的 `\\n` 写成 `\\r\\n`，而 git 的
    `check-ignore --stdin` 不剥 CR ⇒ 每行都变成「不存在的文件名」，只有**最后一行**（无尾随换行）
    被判得出来。所以这里走字节入参，并且自带 canary 验这条通道看得见多条样本。
    """
    if not paths:
        return set()
    payload = ("\n".join(paths) + "\n").encode("utf-8")
    r = subprocess.run(
        ["git", "check-ignore", "--stdin"],
        cwd=str(ROOT),
        input=payload,
        capture_output=True,
    )
    out = (r.stdout or b"").decode("utf-8", "replace")
    return {ln.strip() for ln in out.splitlines() if ln.strip()}


def tokens_by_regex(text: str) -> set:
    """非 Python 消费者（`e2e_golden.sh` 等）与 BOM/坏语法件的兜底取面：按引号串挖路径。

    不这么办的代价实测过：60 份文件带 BOM 或是 shell 脚本，`ast.parse` 抛 SyntaxError 后被我
    原来那句 `continue` **静默跳过** ⇒ 它们引用的路径整批对门禁隐形（覆盖面窄于主张）。
    """
    out = set()
    for m in re.finditer(r"""['"]([^'"\n]{2,120})['"]""", text):
        s = m.group(1)
        if "/" in s or s.endswith((".py", ".md", ".json", ".sh", ".cypy")):
            out.add(s)
    return out


def refs_from(files: list) -> tuple:
    refs = {}
    skipped = []
    for p in files:
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        raw = p.read_text(encoding="utf-8", errors="replace")
        toks = set()
        fell_back = False
        try:
            toks |= string_tokens(ast.parse(raw))
        except SyntaxError:
            fell_back = True
            skipped.append(rel)
        if p.suffix != ".py" or fell_back:
            toks |= tokens_by_regex(raw)
        for tok in toks:
            for c in candidate_paths(tok):
                refs.setdefault(c, set()).add(rel)
    return refs, skipped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--canary", action="store_true", help="故意把一条已跟踪路径当被忽略来验针")
    ap.add_argument(
        "--drift-canary",
        action="store_true",
        help="故意在第二次取面时多塞一条路径，证明分母门会红",
    )
    ap.add_argument(
        "--drift-check",
        action="store_true",
        help="取面跑两遍并要求差集为空（每遍约 40s，收口时开一次；平时靠 --drift-canary 验针）",
    )
    args = ap.parse_args()

    files = []
    for d in CONSUMERS:
        base = ROOT / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file() or "__pycache__" in p.parts:
                continue
            if p.suffix in (".py", ".sh") or p.name == "e2e_golden.sh":
                files.append(p)
    if len(files) < 50:
        raise SystemExit(f"消费者清单只有 {len(files)} 份 ⇒ 取面可疑，拒绝出结论")

    refs, skipped = refs_from(files)
    drift = []
    if args.drift_check:
        refs2, _ = refs_from(files)
        drift = sorted(set(refs) ^ set(refs2))
    if args.drift_canary:
        drift = sorted(drift + ["__drift_canary__"])
    if drift and (args.drift_check or args.drift_canary):
        print(
            f"CONCLUSION ignore_vs_readers DRIFT 两次取面差集非空：{drift[:6]} "
            f"⇒ 分母不稳，本件结论不可签字 rc=1"
        )
        return 1

    hit_ignored = ignored_map(sorted(refs))
    bad = sorted(hit_ignored & set(refs))

    canary_hit = ignored_map(CANARY_IGNORED)
    missing_canary = [c for c in CANARY_IGNORED if c not in canary_hit]
    tracked_hit = ignored_map(CANARY_TRACKED)
    tracked_falsely_ignored = sorted(set(CANARY_TRACKED) & tracked_hit)

    if args.canary:
        bad = bad + [CANARY_TRACKED[0]]

    checks = {
        "consumer_files": len(files),
        "parse_skipped_to_regex": skipped,
        "distinct_referenced_paths": len(refs),
        "referenced_paths": sorted(refs),
        "referenced_but_ignored": bad,
        "canary_ignored_seen": sorted(canary_hit),
        "canary_missing": missing_canary,
        "tracked_falsely_ignored": tracked_falsely_ignored,
        "who_reads": {k: sorted(v) for k, v in sorted(refs.items())},
    }
    ok = not bad and not missing_canary and not tracked_falsely_ignored and not args.canary
    print(
        f"CONCLUSION ignore_vs_readers consumers={len(files)} regex_fallback={len(skipped)} "
        f"refs={len(refs)} violations={len(bad)} canary_missing={len(missing_canary)} "
        f"falsely_ignored={len(tracked_falsely_ignored)} canary_mode={args.canary} "
        f"rc={0 if ok else 1}"
    )
    for b in bad:
        print(f"  VIOLATION ignored-yet-read {b} <- {sorted(refs[b])[:3]}")
    if missing_canary:
        print(f"  CANARY-MISS {missing_canary} 未被判为忽略 ⇒ check-ignore 通道可疑")
    if tracked_falsely_ignored:
        print(f"  FALSELY-IGNORED {tracked_falsely_ignored} ⇒ 既有交付物被排除")
    (HERE / "check_ignore_vs_readers.json").write_text(
        __import__("json").dumps(checks, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main())
