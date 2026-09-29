"""R1-打磨 law2/3/4/5 的取证扫描：把「可以打磨什么」变成可数的清单，而不是印象。

四条判据各自的自证要求（缺一条就当场拒绝出报告）：
 law2 skip/xfail/expectedFailure 逐条定性：每条必须给出 (a) 标记原文 (b) 它引用的缺陷号
       或缺陷号在 bug_list 里的真实状态 ⇒ 「真不适用」还是「掩盖失效」由数据判，不靠读语气。
 law3 mypy strict 的可裁边界：按文件分组数 error，并单独数**本轮循环新建/新改的文件**——
       边界提案只能是「新文件 0 error、存量按目录分批」这种能被复算的形状。
 law4 TODO/FIXME/HACK/XXX 技术债标记：逐条给出行原文；命中数过少（< 全集的一半）时先怀疑扫描口径。
 law5 死代码/重复分支候选：F811（同名重复定义）、F601（dict 重复键）、F841（赋值未用）、E722（裸 except）。
       每条候选都要给出**两处位置**，并说明删哪一处才不改语义（Python 里后定义覆盖前定义 ⇒ 前一处是死的）。
       本脚本**不自动改代码**：清理动作留给单独一步，且改完必须过双套基线。
"""

from __future__ import annotations

import ast
import codecs
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(r"E:\IDEProjects\AI\Cypy")
sys.path.insert(0, str(HERE))
import lfist_lib  # noqa: E402

SCAN_DIRS = ["cypyc", "cypy_bridge", "scripts", "tests"]
DEBT_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX|NOTE:|临时|待实现|未实现|暂缓)\b")
MARK_RE = re.compile(r"@pytest\.mark\.(skip|skipif|xfail)|pytest\.skip\(|expectedFailure")
LOOP_NEW = [
    "tests/test_loop_20260927_fix.py",
    "cypyc/codegen/cython_generator.py",
    "cypyc/parser/lexer.py",
    "cypy_bridge/types.py",
    "cypy_bridge/__init__.py",
]


ERR_RE = re.compile(
    r"^(?P<f>.*?):(?P<ln>\d+)(?::\d+)?: error: (?P<msg>.*?)\s*\[(?P<code>[\w-]+)\]$"
)


def comment_tokens(text: str) -> list:
    """只取真注释（tokenize 的 COMMENT），字符串里的同名词不算技术债标记。

    第一版逐行正则扫，把 `assert not content.startswith("# TODO"), f"...仍是 TODO 占位"`
    这条**关于 TODO 的断言**数成了 1 处技术债 ⇒ 判据命中的是它自己在检查的东西。
    """
    import io
    import tokenize as tk

    out = []
    try:
        for tok in tk.generate_tokens(io.StringIO(text).readline):
            if tok.type == tk.COMMENT:
                out.append((tok.start[0], tok.string))
            elif tok.type == tk.STRING and DEBT_RE.search(tok.string):
                out_string_hits.append((tok.start[0], tok.string[:120]))
    except (tk.TokenError, SyntaxError, ValueError):
        for i, ln in enumerate(text.splitlines(), 1):
            if ln.lstrip().startswith("#"):
                out.append((i, ln.strip()))
    return out


def debt_control() -> dict:
    """成对对照：真注释里的 TODO 必被抓；字符串里的同名词必不被当债。"""
    global out_string_hits
    out_string_hits = []
    caught = comment_tokens("x = 1  # TODO: 这块还没做完")
    hits = [(i, s) for i, s in caught if DEBT_RE.search(s)]
    out_string_hits = []
    str_only = comment_tokens('assert not c.startswith("# TODO"), f"demo: 仍是 TODO 占位"')
    str_hits = [(i, s) for i, s in str_only if DEBT_RE.search(s)]
    mentioned = list(out_string_hits)
    return {
        "comment_caught": len(hits),
        "string_not_counted": len(str_hits) == 0,
        "string_mention_recorded": len(mentioned) >= 1,
    }


def sh(cmd: list) -> str:
    return subprocess.run(
        cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace"
    ).stdout


def py_files() -> list:
    out = []
    for d in SCAN_DIRS:
        out += [
            p
            for p in (ROOT / d).rglob("*.py")
            if "__pycache__" not in p.parts and ".venv" not in p.parts
        ]
    return sorted(out)


def main() -> int:
    refuse = []
    files = py_files()
    if len(files) < 50:
        refuse.append(f"扫描口径可疑：只找到 {len(files)} 个 .py（期望覆盖 4 个目录的全部源文件）")

    # ---- law2：skip 类标记逐条定性 ----
    # 引用哪条缺陷只能按**所属函数自己的函数体**取号：第一版用 ±4 行的文本窗口，
    # 把下一个测试函数头上的 `# ---- BUG-6` 注释算进了前一个 skip 的理由 ⇒ 差点把
    # 一条合法的平台型 skip 判成"掩盖失效"（这是"计数命中的是别人的注释"那一族）。
    marks = []
    bom_files, unparsable = [], []
    for p in files:
        rel = p.relative_to(ROOT).as_posix()
        raw = p.read_bytes()
        if raw[:3] == codecs.BOM_UTF8:
            bom_files.append(rel)
        text = raw.decode("utf-8-sig", errors="replace")
        lines = text.splitlines()
        try:
            tree = ast.parse(text)
        except SyntaxError as e:
            unparsable.append({"where": rel, "err": f"{e.msg} @ line {e.lineno}"})
            continue
        for i, ln in enumerate(lines, start=1):
            if not MARK_RE.search(ln):
                continue
            enclosing = [
                n
                for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.lineno <= i <= (n.end_lineno or n.lineno)
            ]
            enclosing.sort(key=lambda n: (n.end_lineno or n.lineno) - n.lineno)
            ids = sorted(
                set(re.findall(r"BUG-\d+", ast.unparse(enclosing[-1]) if enclosing else ""))
            )
            marks.append(
                {
                    "where": f"{rel}:{i}",
                    "line": ln.strip()[:170],
                    "bug_ids": ids,
                    "in_function": enclosing[-1].name if enclosing else None,
                    "attribution": "所属函数体内文本（含装饰器与 docstring）",
                }
            )
    # 引用到的缺陷号去 bug_list 查真实状态（"已修完还被 skip" 才是掩盖失效）
    wanted = sorted({b for m in marks for b in m["bug_ids"]})
    status, fixed_ledger = {}, {}
    bugs_md = (ROOT / "memory" / "bugs.md").read_text(encoding="utf-8", errors="replace")
    for blk in re.split(r"(?m)^## ", bugs_md):
        m = re.match(r"BUG-(\d+)", blk)
        if m:
            fixed_ledger[f"BUG-{m.group(1)}"] = bool(re.search(r"(?m)^### FIXED", blk))
    if wanted:
        c = lfist_lib.Client(timeout=240)
        c._send(
            "initialize",
            {
                "protocolVersion": lfist_lib.PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": lfist_lib.CLIENT_INFO,
            },
        )
        bl = c.call("bug_list", {"project_dir": "."})
        c.close()
        idx = {b.get("id"): b.get("status") for b in (bl.get("bugs") or []) if isinstance(b, dict)}
        status = {b: idx.get(b, "不在账本") for b in wanted}
        if len(idx) < 30:
            refuse.append(f"bug_list 只回显 {len(idx)} 条，与账本规模不符 ⇒ 状态判据读的是残缺表")
    verdicts = []
    for m in marks:
        # db 的 status 不是"已修"的权威源：账本无 close API，修完只会在 memory/bugs.md 追加
        # `### FIXED` 段（gotcha #26/#43）⇒ 只看 status 会把"已修但仍 OPEN"误判成"真不适用"。
        refs = {b: {"db": status.get(b), "ledger_fixed": fixed_ledger.get(b)} for b in m["bug_ids"]}
        if not m["bug_ids"]:
            v = "无缺陷号引用 ⇒ 需人工读用途（不自动定性）"
        elif any(r["ledger_fixed"] is None for r in refs.values()):
            v = "引用的缺陷号在账本里查不到 ⇒ 标记钉的是不存在的依据"
            refuse.append(
                f"law2 {m['where']} 钉的缺陷号查不到：{[b for b, r in refs.items() if r['ledger_fixed'] is None]}"
            )
        elif any(r["ledger_fixed"] for r in refs.values()):
            v = "账本里该缺陷已 FIXED ⇒ 掩盖失效嫌疑（该重新跑起来或换更窄的跳过条件）"
        else:
            v = "缺陷仍 OPEN（账本无 FIXED 段）⇒ 真不适用，标记与缺陷一致"
        verdicts.append({**m, "refs": refs, "verdict": v})
    if marks and len(verdicts) != len(marks):
        refuse.append("law2 定性条数与标记条数不等 ⇒ 有标记没被定性")

    # ---- law4：技术债标记（只数真注释；同名词出现在字符串里另列一档） ----
    ctl = debt_control()
    if (
        ctl["comment_caught"] != 1
        or not ctl["string_not_counted"]
        or not ctl["string_mention_recorded"]
    ):
        refuse.append(f"判据4 的成对对照失败（真注释必被抓 / 字符串提及不得算债）：{ctl}")
    debt, mentions = [], list()
    global out_string_hits
    for p in files:
        rel = p.relative_to(ROOT).as_posix()
        text = p.read_bytes().decode("utf-8-sig", errors="replace")
        out_string_hits = []
        for i, c in comment_tokens(text):
            m = DEBT_RE.search(c)
            if m:
                debt.append({"where": f"{rel}:{i}", "kind": m.group(1), "line": c.strip()[:150]})
        mentions += [{"where": f"{rel}:{i}", "text": s} for i, s in out_string_hits]

    # ---- law5：死代码候选（flake8 的 F811/F601/F841/E722 + 两处位置） ----
    fl = sh([sys.executable, "-X", "utf8", "-m", "flake8", "--max-line-length=100", *SCAN_DIRS])
    hits = {}
    for ln in fl.splitlines():
        m = re.match(r"^(.+?):(\d+):(\d+): (F811|F601|F841|E722) (.*)$", ln)
        if m:
            hits.setdefault(m.group(4), []).append(
                {"where": f"{m.group(1)}:{m.group(2)}", "msg": m.group(5)[:150]}
            )
    dup_defs = []
    for h in hits.get("F811", []):
        rel, num = h["where"].rsplit(":", 1)
        p = ROOT / rel
        if not p.exists():
            continue
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        later = lines[int(num) - 1].strip()
        m = re.search(r"from line (\d+)", h["msg"])
        earlier = (
            lines[int(m.group(1)) - 1].strip() if m and int(m.group(1)) <= len(lines) else None
        )
        dup_defs.append(
            {
                "where": h["where"],
                "msg": h["msg"],
                "effective_def": later,
                "shadowed_def": earlier,
                "reading": "Python 里后定义覆盖前定义 ⇒ 前一处（shadowed）是死代码；"
                "删除它不改语义，删除后一处会改语义",
            }
        )

    # ---- law3：mypy 边界（必须先分辨"跑成了 N 条"与"根本没跑成"） ----
    my = sh([sys.executable, "-X", "utf8", "-m", "mypy", *LOOP_NEW[:5]])
    aborted = "errors prevented further checking" in my
    rows = [m.groupdict() for m in (ERR_RE.match(l) for l in my.splitlines()) if m]
    per_file, per_code = {}, {}
    for r_ in rows:
        f = r_["f"].replace("\\", "/")
        per_file[f] = per_file.get(f, 0) + 1
        per_code[r_["code"]] = per_code.get(r_["code"], 0) + 1
    tail = [l for l in my.strip().splitlines() if l.strip()][-2:]
    new_file_errs = {f: n for f, n in per_file.items() if "test_loop" in f}
    if aborted:
        refuse.append(
            "判据3 mypy 被中断（声明的 python_version=3.9 与依赖里的 3.10 语法冲突）"
            "⇒ 这道门在测试树上跑不起来，给的条数不是边界而是事故；已入账 BUG-43。原文："
            + " | ".join(t[:170] for t in tail)
        )
    elif not rows:
        refuse.append(
            "判据3 mypy 既没 error 行也没中断宣告 ⇒ 判据空转（先查输入是否被 exclude 掉）："
            + " | ".join(t[:170] for t in tail)
        )
    if per_code.get("syntax"):
        refuse.append(
            f"判据3 error 分类里出现 [syntax]，通常意味着版本口径不一致而非存量类型债：{per_code}"
        )

    doc = {
        "refuse": refuse,
        "scan": {
            "py_files": len(files),
            "dirs": SCAN_DIRS,
            "bom_py_files": bom_files,
            "unparsable_py_files": unparsable,
        },
        "law2_skip_marks": verdicts,
        "law2_bug_status": status,
        "law4_control": ctl,
        "law4_string_mentions": mentions[:12],
        "law4_debt": {
            "total": len(debt),
            "by_kind": {
                k: sum(1 for d in debt if d["kind"] == k) for k in {d["kind"] for d in debt}
            },
            "sample": debt[:25],
        },
        "law5_candidates": {
            "counts": {k: len(v) for k, v in hits.items()},
            "dup_defs": dup_defs,
            "f601": hits.get("F601", []),
            "e722": hits.get("E722", []),
        },
        "law3_mypy": {
            "total_errors": len(rows),
            "aborted": aborted,
            "per_file": per_file,
            "per_code": per_code,
            "tail_lines": tail,
            "loop_new_file_errors": new_file_errs,
        },
    }
    if not hits:
        refuse.append("law5 一条候选都没扫到 ⇒ 先怀疑 flake8 调用口径，不是代码真干净")
    doc["law3_mypy"]["tail_lines"] = tail
    doc["law3_mypy"]["aborted"] = aborted
    (HERE / "polish_scan_r1.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "refuse": refuse,
                "scan": doc["scan"],
                "law2": [(v["where"], v["verdict"][:34]) for v in verdicts],
                "law2_bug_status": status,
                "law4": doc["law4_debt"]["total"],
                "law4_kinds": doc["law4_debt"]["by_kind"],
                "law5_counts": doc["law5_candidates"]["counts"],
                "law3_total": doc["law3_mypy"]["total_errors"],
                "law3_new": doc["law3_mypy"]["loop_new_file_errors"],
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
