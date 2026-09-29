#!/usr/bin/env python3
"""R2-寻虫 确诊件（轻量版）：把 build / hook / watch 按**文档声明的形状**打到调用面。

为什么单开这一件：hunt_r2_scan.py 的第一版把调用形状猜错了（给 watch 传了 `--port`，
CLI 回 `invalid choice`），而"CLI 报错"到底是产品坏还是我调用形状错，只能按被检对象
自己的 help / 文档声明重跑一次才分得开。本件只做三件事，每件都带成对对照。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(r"E:\IDEProjects\AI\Cypy")
PY = sys.executable
REFUSE: list = []

PROBE_LIB = 'def greet(who: str) -> str:\n    return "hello " + who\n'
PROBE_MAIN = (
    'from lib import greet\n\nlet name: str = "cypy"\nlet msg: str = greet(name)\nprint(msg)\n'
)
VOLATILE = "(?m)^__(?:compile_time|file|path)__ = .*$"


def sh(args: list, cwd: Path, timeout: int = 120) -> tuple:
    p = subprocess.run(
        args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def quote(where: str, needle: str, span: int = 4) -> dict:
    rel, ln = where.rsplit(":", 1)
    lines = (ROOT / rel).read_text(encoding="utf-8", errors="replace").splitlines()
    lo, hi = max(0, int(ln) - 1 - span), min(len(lines), int(ln) + span)
    hit = next((row.strip()[:180] for row in lines[lo:hi] if needle in row), "")
    if not hit:
        REFUSE.append(f"声明核对失败：{where} ±{span} 行内找不到 {needle!r}（引用面坏了）")
    return {"where": where, "needle": needle, "quoted": hit}


def deterministic_case() -> dict:
    """剥掉文档声明的可变量后，同一源码两次独立进程编译是否逐字节一致。"""
    import hashlib

    decl = quote("SYNTAX/22-magic-properties.md:27", "__compile_time__")
    srcs = sorted((ROOT / "examples").glob("*.cypy"))[:5]
    rows = []
    for src in srcs:
        shots = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as td:
                out = Path(td)
                rc, _o = sh(
                    [PY, "-X", "utf8", "-m", "cypyc", "transpile", str(src), "-o", str(out)], ROOT
                )
                text = "".join(
                    f.read_text(encoding="utf-8", errors="replace")
                    for f in sorted(out.rglob("*.pyx"))
                )
                norm = re.sub(VOLATILE, "__MAGIC_VOLATILE__", text)
                shots.append(hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16])
        rows.append(
            {
                "src": src.name,
                "rc": rc,
                "a": shots[0],
                "b": shots[1],
                "stable": shots[0] == shots[1],
            }
        )
    # 反例（必不抓）：不剥可变量时同一文件两次的 sha 一定不同 ⇒ 证明"剥掉后才相等"是真判据
    with tempfile.TemporaryDirectory() as td:
        raw = []
        for _ in range(2):
            out = Path(td) / str(len(raw))
            sh([PY, "-X", "utf8", "-m", "cypyc", "transpile", str(srcs[0]), "-o", str(out)], ROOT)
            t = "".join(
                f.read_text(encoding="utf-8", errors="replace") for f in sorted(out.rglob("*.pyx"))
            )
            raw.append(hashlib.sha256(t.encode("utf-8")).hexdigest()[:16])
    return {
        "declaration": decl,
        "rows": rows,
        "unstable_after_strip": [r["src"] for r in rows if not r["stable"]],
        "raw_unstripped_differs": raw[0] != raw[1],
        "raw_pair": raw,
    }


def build_case() -> dict:
    decl = quote("docs/USAGE.md:105", "跨模块类型推断")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        (tmp / "lib.cypy").write_text(PROBE_LIB, encoding="utf-8", newline=chr(10))
        (tmp / "main.cypy").write_text(PROBE_MAIN, encoding="utf-8", newline=chr(10))
        out_b = tmp / "ob"
        rc_b, ob = sh([PY, "-X", "utf8", "-m", "cypyc", "build", str(tmp), "-o", str(out_b)], tmp)
        art_b = sorted(f.name for f in out_b.rglob("*") if f.is_file()) if out_b.exists() else []
        text_b = {
            f.name: f.read_text(encoding="utf-8", errors="replace")
            for f in (out_b.rglob("*.pyx") if out_b.exists() else [])
        }
        out_t = tmp / "ot"
        rc_t, _ot = sh(
            [PY, "-X", "utf8", "-m", "cypyc", "transpile", str(tmp / "lib.cypy"), "-o", str(out_t)],
            tmp,
        )
        text_t = {
            f.name: f.read_text(encoding="utf-8", errors="replace")
            for f in (out_t.rglob("*.pyx") if out_t.exists() else [])
        }

        def typed(bundle: dict) -> list:
            hits = []
            for name, body in bundle.items():
                for line in body.splitlines():
                    if "greet" in line and re.search(r"\bstr\b", line):
                        hits.append(f"{name}: {line.strip()[:130]}")
            return hits

        b_hits, t_hits = typed(text_b), typed(text_t)
        neg = typed({"junk.pyx": "def unrelated():\n    return 1\n"})
        if neg:
            REFUSE.append("对照失效：typed matcher 在无关产物上也命中")
        return {
            "declaration": decl,
            "build_rc": rc_b,
            "build_tail": ob.strip().splitlines()[-3:],
            "build_artifacts": art_b,
            "build_typed_lines": b_hits[:6],
            "lib_alone_rc": rc_t,
            "lib_alone_typed_lines": t_hits[:6],
            "negative_control_empty": not neg,
        }


def hook_case() -> dict:
    decl = quote("docs/USAGE.md:121", "cypyc hook install")
    rc_h, out_h = sh([PY, "-X", "utf8", "-m", "cypyc", "hook", "--help"], ROOT)
    subs = {}
    for sub in ("install", "status", "uninstall", "clear-cache"):
        rc_s, out_s = sh([PY, "-X", "utf8", "-m", "cypyc", "hook", sub], ROOT, timeout=90)
        subs[sub] = {
            "rc": rc_s,
            "error_line": next(
                (row.strip()[:170] for row in out_s.splitlines() if "error" in row.lower()), ""
            ),
            "tail": out_s.strip().splitlines()[-2:],
        }
    api = sh(
        [
            PY,
            "-X",
            "utf8",
            "-c",
            "import cypy_hook; print([n for n in ('install_hook','uninstall_hook',"
            "'is_hook_installed','CypyHook') if hasattr(cypy_hook,n)])",
        ],
        ROOT,
    )
    return {
        "declaration": decl,
        "help_rc": rc_h,
        "help_usage": next((row.strip()[:170] for row in out_h.splitlines() if "usage" in row), ""),
        "declared_subcommands": subs,
        "documented_api_present": api[1].strip().splitlines()[-1][:200] if api[1].strip() else "",
        "api_rc": api[0],
    }


def watch_case() -> dict:
    decl = quote("docs/USAGE.md:112", "cypyc watch")
    work = Path(tempfile.mkdtemp(prefix="r2watch_"))
    try:
        (work / "lib.cypy").write_text(PROBE_LIB, encoding="utf-8", newline=chr(10))
        (work / "a.cypy").write_text(PROBE_MAIN, encoding="utf-8", newline=chr(10))
        proc = subprocess.Popen(
            [PY, "-X", "utf8", "-m", "cypyc", "watch", str(work), "--debounce", "0.2"],
            cwd=str(work),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        time.sleep(6)
        started_rc = proc.poll()
        (work / "b.cypy").write_text(
            "let n: int = 1\nprint(n)\n", encoding="utf-8", newline=chr(10)
        )
        picked = False
        deadline = time.time() + 18
        while time.time() < deadline:
            picked = (work / "b.pyx").exists() or any((work / "output").rglob("b.pyx"))
            if picked or proc.poll() is not None:
                break
            time.sleep(1)
        proc.kill()
        try:
            proc.wait(timeout=12)
        except subprocess.TimeoutExpired:
            REFUSE.append("watch 进程 kill 后 12s 未退出（可能留孤儿）")
        tail = []
        if proc.stdout:
            tail = [row.strip()[:170] for row in proc.stdout.read().splitlines()[-8:]]
            proc.stdout.close()
        return {
            "declaration": decl,
            "alive_after_6s": started_rc is None,
            "exited_early": started_rc,
            "new_module_picked_up": picked,
            "output_tail": tail,
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main() -> int:
    doc = {
        "refuse": REFUSE,
        "determinism": deterministic_case(),
        "build": build_case(),
        "hook": hook_case(),
        "watch": watch_case(),
    }
    (HERE / "hunt_r2_declared.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "refuse": REFUSE,
                "unstable_after_strip": doc["determinism"]["unstable_after_strip"],
                "raw_differs": doc["determinism"]["raw_unstripped_differs"],
                "build_typed": doc["build"]["build_typed_lines"],
                "lib_alone_typed": doc["build"]["lib_alone_typed_lines"],
                "hook_subs": {k: v["rc"] for k, v in doc["hook"]["declared_subcommands"].items()},
                "watch_pickup": doc["watch"]["new_module_picked_up"],
                "watch_alive": doc["watch"]["alive_after_6s"],
            },
            ensure_ascii=False,
        )
    )
    return 1 if REFUSE else 0


if __name__ == "__main__":
    sys.exit(main())
