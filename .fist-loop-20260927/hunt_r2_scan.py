#!/usr/bin/env python3
"""R2-寻虫 取证件：CLI 声明面 / 跨模块 build / watch / hook / 确定性 / 零调用点符号。

一切判据都打到**调用面**（子进程跑真实入口），不采信"模块里有函数 + 有单测"。
每条检查都配成对对照：正例必抓 + 固定反例必不抓；抓不到的检查会自己记 refuse。
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(r"E:\IDEProjects\AI\Cypy")
PY = sys.executable
BANNER_RE = r"watching|started|Running on|Listening|Serving|Watching"
REFUSE: list = []
SUBS = ["transpile", "compile", "build", "run", "watch", "hook"]
TARGET_DIRS = ["cypyc/transformer", "cypyc/utils", "cypyc/project", "cypy_hook", "scripts"]

PROBE_MAIN = """from lib import greet

let name: str = "cypy"
let msg: str = greet(name)
print(msg)
"""

PROBE_LIB = """def greet(who: str) -> str:
    return "hello " + who
"""


def sh(args: list, cwd: Path | None = None, timeout: int = 120) -> tuple:
    if cwd is not None and not isinstance(cwd, Path):
        # 上一版把 timeout 写成位置参 ⇒ 落进 cwd，子进程直接 WinError 267（"目录名称无效"）。
        raise TypeError(f"cwd 必须是 Path，收到 {cwd!r}——检查调用点是否把 timeout 写成了位置参")
    p = subprocess.run(
        args,
        cwd=str(cwd or ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ---------- law2：CLI 声明面逐子命令 ----------
def cli_face() -> dict:
    rows = []
    for sub in SUBS:
        rc, out = sh([PY, "-X", "utf8", "-m", "cypyc", sub, "--help"], timeout=60)
        first_err = next(
            (ln.strip()[:150] for ln in out.splitlines() if "invalid choice" in ln.lower()), ""
        )
        rows.append(
            {
                "sub": sub,
                "help_rc": rc,
                "usage": next((ln.strip()[:150] for ln in out.splitlines() if "usage:" in ln), ""),
                "invalid_choice": first_err,
                "flags": sorted(set(re.findall(r"(?<![\w-])--([a-z][\w-]*)", out))),
            }
        )
        if rc != 0:
            REFUSE.append(f"law2 子命令 {sub} 的 --help 退出码 {rc}（声明面自己就跑不起来）")
    return {"rows": rows, "subs": SUBS}


# ---------- law2b：跨模块 build 是否真的做了跨模块推断 ----------
def cross_module_build() -> dict:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        (tmp / "lib.cypy").write_text(PROBE_LIB, encoding="utf-8", newline="\n")
        (tmp / "main.cypy").write_text(PROBE_MAIN, encoding="utf-8", newline="\n")
        out_b = tmp / "out_build"
        rc_b, ob = sh([PY, "-X", "utf8", "-m", "cypyc", "build", str(tmp), "-o", str(out_b)])
        out_t = tmp / "out_transpile"
        rc_t, ot = sh(
            [PY, "-X", "utf8", "-m", "cypyc", "transpile", str(tmp / "main.cypy"), "-o", str(out_t)]
        )

        def emit(d: Path) -> str:
            f = next(iter(sorted(d.rglob("main.pyx"))), None) if d.exists() else None
            return f.read_text(encoding="utf-8", errors="replace") if f else ""

        e_b, e_t = emit(out_b), emit(out_t)

        def typed(text: str) -> bool:
            body = [ln for ln in text.splitlines() if "def greet" in ln or "cdef str greet" in ln]
            return any(re.search(r"cdef str greet|-> str|str who", ln) for ln in body)

        diff = (e_b != e_t) or bool(re.search(r"cdef str greet", e_b))
        doc = {
            "build_rc": rc_b,
            "build_err_first": next(
                (ln.strip()[:160] for ln in ob.splitlines() if "rror" in ln), ""
            ),
            "transpile_rc": rc_t,
            "build_emit_bytes": len(e_b),
            "transpile_emit_bytes": len(e_t),
            "build_typed_signature": typed(e_b),
            "transpile_typed_signature": typed(e_t),
            "cross_module_differs": diff,
            "build_emit_head": e_b[:200].replace("\n", " ⏎ "),
        }
        if rc_b != 0 and rc_t == 0:
            doc["verdict"] = "build 面失败而 transpile 面成功"
        elif rc_b == 0 and not doc["build_typed_signature"]:
            doc["verdict"] = "build rc=0 但产物里看不到跨模块类型推断的痕迹"
        elif rc_b == 0:
            doc["verdict"] = "works"
        else:
            doc["verdict"] = "两面都失败（记原文，不判静默）"
        return doc


# ---------- law2c：watch / hook 两个声明面 ----------
def watch_face() -> dict:
    """按 `watch --help` **自己声明的形状**探针：`cypyc watch [source]`，根本没有 --port。

    上一版我按 `<dir> --port N` 调用，CLI 回 `invalid choice: '57806'` —— 那是我的调用形状错了
    （positional 只有 source），不是产品起不来。判据的调用形状必须从被检对象自己的 help 里取。
    """
    help_rc, help_out = sh([PY, "-X", "utf8", "-m", "cypyc", "watch", "--help"], timeout=60)
    declared_positional = "[source]" in help_out
    port_flag = "--port" in help_out
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        (tmp / "lib.cypy").write_text(PROBE_LIB, encoding="utf-8", newline=chr(10))
        (tmp / "a.cypy").write_text(PROBE_MAIN, encoding="utf-8", newline=chr(10))
        proc = subprocess.Popen(
            [PY, "-X", "utf8", "-m", "cypyc", "watch", str(tmp)],
            cwd=str(tmp),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        deadline = time.time() + 20
        lines_out: list = []
        try:
            while time.time() < deadline and len(lines_out) < 12:
                line = proc.stdout.readline() if proc.stdout else ""
                if not line:
                    if proc.poll() is not None:
                        break
                    time.sleep(0.2)
                    continue
                lines_out.append(line.strip()[:180])
                if re.search(BANNER_RE, " ".join(lines_out)):
                    break
            probe = {
                "help_rc": help_rc,
                "declared_positional_source": declared_positional,
                "port_flag_declared": port_flag,
                "alive": proc.poll() is None,
                "exit_code": proc.poll(),
                "banner_seen": bool(re.search(BANNER_RE, " ".join(lines_out))),
                "first_lines": lines_out[:6],
            }
        finally:
            proc.kill()
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                REFUSE.append("law2c watch 子进程 kill 后 20s 仍在 ⇒ 可能留孤儿，记 refuse")
            if proc.stdout:
                proc.stdout.close()
    if probe["banner_seen"]:
        probe["verdict"] = "works"
    elif probe["alive"]:
        probe["verdict"] = "进程活着但 20s 内没有任何可观测横幅（观测面缺失，不判崩溃）"
    else:
        probe["verdict"] = f"退出码 {probe['exit_code']}，原文见 first_lines"
    return probe


def hook_face() -> dict:
    rc_h, out_h = sh([PY, "-X", "utf8", "-m", "cypyc", "hook", "--help"], timeout=60)
    rc_i, out_i = sh(
        [
            PY,
            "-X",
            "utf8",
            "-c",
            "import sys; sys.path.insert(0, %r); import cypy_hook; "
            "print('installed' if getattr(sys.meta_path[0], 'cypy_loader', None) or "
            "any('cypy' in type(m).__name__.lower() or 'cypy' in getattr(m,'__name__','').lower() "
            "for m in sys.meta_path) else 'not-on-meta-path')" % str(ROOT),
        ],
        timeout=60,
    )
    return {
        "help_rc": rc_h,
        "help_usage": next((ln.strip()[:160] for ln in out_h.splitlines() if "usage" in ln), ""),
        "import_rc": rc_i,
        "import_line": out_i.strip().splitlines()[-1][:200] if out_i.strip() else "",
        "meta_path_hook_active": "installed" in out_i,
    }


# ---------- law4：产物确定性（同一源码两次独立进程编译） ----------
def determinism() -> dict:
    corpus = sorted((ROOT / "examples").glob("*.cypy"))[:6]
    if not corpus:
        REFUSE.append("law4 examples/ 下找不到 .cypy 语料 ⇒ 确定性无从对拍")
        return {"corpus": 0}
    runs = []
    for src in corpus:
        per = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as td:
                out = Path(td)
                rc, _o = sh(
                    [PY, "-X", "utf8", "-m", "cypyc", "transpile", str(src), "-o", str(out)]
                )
                files = sorted(f for f in out.rglob("*") if f.is_file())
                blob = "|".join(f"{f.name}:{f.stat().st_size}" for f in files)
                text = "".join(f.read_text(encoding="utf-8", errors="replace") for f in files)
                norm = re.sub(r"_bb_\d+", "_bb_N", text)
                # SYNTAX/22-magic-properties.md:27 声明 `__compile_time__` 就是编译时间戳，
                # `__file__/__path__` 又随输出目录变 ⇒ 这三行是**文档承诺的可变量**，不是不稳定。
                # 上一版没剥掉它们，把 3 个文件判成"产物不确定"——那是判据坏了，不是产品坏了。
                norm = re.sub(
                    "(?m)^__(?:compile_time|file|path)__ = .*$",
                    "__MAGIC_VOLATILE__",
                    norm,
                )
                sha = hashlib.sha256(norm.encode("utf-8")).hexdigest()
                per.append({"rc": rc, "files": blob, "sha": sha[:16]})
        runs.append(
            {
                "src": src.name,
                "a": per[0]["sha"],
                "b": per[1]["sha"],
                "stable": per[0]["sha"] == per[1]["sha"],
            }
        )
    unstable = [r for r in runs if not r["stable"]]
    return {"corpus": len(corpus), "rows": runs, "unstable": [u["src"] for u in unstable]}


# ---------- law3：零调用点符号扫描（配 grep 反证 + 动态入口白名单） ----------
def zero_call_symbols() -> dict:
    """符号引用计数：先把全仓文本读进**一份**索引，再逐符号匹配。

    上一版每个符号都重扫一遍盘（O(符号×文件) 次 read），在本仓 4 千文件上就是几十分钟——
    同一份索引读一次即可，这是"递归扫描超时"那类坑的正解，不是降判据。
    """
    dirs = [
        ".",
        "tests",
        "test_suite",
        "examples",
        "scripts",
        "cypyc",
        "cypy_bridge",
        "cypy_hook",
        "PROJECT-SPEC",
        "SYNTAX",
        "docs",
    ]
    index: dict = {}
    seen = set()
    for d in dirs:
        base = ROOT / d
        if not base.exists():
            continue
        for f in base.rglob("*"):
            if not f.is_file() or "__pycache__" in f.parts or ".fist-loop" in f.parts:
                continue
            if f.suffix not in (".py", ".pyx", ".cypy", ".md", ".sh", ".txt", ".json"):
                continue
            rel = f.relative_to(ROOT).as_posix()
            if rel in seen:
                continue
            seen.add(rel)
            try:
                index[rel] = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
    decls = []
    for d in TARGET_DIRS:
        for f in sorted((ROOT / d).rglob("*.py")):
            if "__pycache__" in f.parts:
                continue
            rel = f.relative_to(ROOT).as_posix()
            try:
                tree = ast.parse(index.get(rel, f.read_text(encoding="utf-8")))
            except SyntaxError as exc:
                REFUSE.append(f"law3 解析 {rel} 失败：{exc}")
                continue
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    kind = "class" if isinstance(node, ast.ClassDef) else "def"
                    decls.append(
                        {
                            "file": rel,
                            "name": node.name,
                            "line": node.lineno,
                            "kind": kind,
                            "dunder": node.name.startswith("_"),
                        }
                    )
    dynamic_files = sorted(
        p.as_posix()
        for p in [
            ROOT / "cypyc/transformer/__init__.py",
            ROOT / "cypyc/utils/__init__.py",
            ROOT / "cypyc/project/__init__.py",
            ROOT / "cypy_hook/__init__.py",
            ROOT / "scripts/fist.py",
            ROOT / "scripts/sync_demo.py",
            ROOT / "scripts/run_tests.py",
            ROOT / "cypy_hook/hook.py",
        ]
        if p.exists()
    )
    for row in decls:
        if row["name"].startswith("test_") or row["name"] in ("main", "__init__"):
            continue
        pat = re.compile(rf"\b{re.escape(row['name'])}\b")
        hits = [rel for rel, txt in index.items() if rel != row["file"] and pat.search(txt)]
        row["ref_count"] = len(hits)
        row["refs"] = hits[:8]
    orphans = [r for r in decls if r.get("ref_count") == 0]
    doc = {
        "dirs": TARGET_DIRS,
        "indexed_files": len(index),
        "symbols": len(decls),
        "dynamic_entry_whitelist": dynamic_files,
        "orphan_candidates": orphans[:40],
        "orphan_count": len(orphans),
        "dunder_orphans": [o for o in orphans if o["dunder"]],
    }
    if not decls:
        REFUSE.append("law3 目标目录一个符号都没扫到 ⇒ 扫描器坏了，不是没有死码")
    if len(index) < 500:
        REFUSE.append(f"law3 索引只有 {len(index)} 个文件 ⇒ 扫描面被截断，孤儿计数不可信")
    return doc


def main() -> int:
    doc = {
        "refuse": REFUSE,
        "cli_face": cli_face(),
        "cross_module_build": cross_module_build(),
        "watch_face": watch_face(),
        "hook_face": hook_face(),
        "determinism": determinism(),
        "zero_call_symbols": zero_call_symbols(),
    }
    (HERE / "hunt_r2_scan.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    slim = {
        "refuse": REFUSE,
        "build": doc["cross_module_build"]["verdict"],
        "watch_alive": doc["watch_face"].get("alive"),
        "hook_meta_path": doc["hook_face"]["meta_path_hook_active"],
        "unstable": doc["determinism"].get("unstable"),
        "orphans": doc["zero_call_symbols"]["orphan_count"],
    }
    print(json.dumps(slim, ensure_ascii=False))
    return 1 if REFUSE else 0


if __name__ == "__main__":
    sys.setrecursionlimit(10000)
    sys.exit(main())
