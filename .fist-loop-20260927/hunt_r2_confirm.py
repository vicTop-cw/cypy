#!/usr/bin/env python3
"""R2-寻虫 确诊件：把 build / hook / watch 三个声明面按**文档自己声明的形状**打到调用面。

每条候选都给三样东西：
 1) 声明句原文（file:line + 逐字引用）——没有声明句的"缺失"不算缺口；
 2) 调用面实测（子进程 rc + 产物文本 + 关键行）；
 3) 成对对照：正例必抓 + 一个"修复前/错误形状"的固定反例，证明 matcher 不是恒真。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(r"E:\IDEProjects\AI\Cypy")
PY = sys.executable
REFUSE: list = []

PROBE_LIB = """def greet(who: str) -> str:
    return "hello " + who
"""
PROBE_MAIN = """from lib import greet

let name: str = "cypy"
let msg: str = greet(name)
print(msg)
"""


def sh(args: list, cwd: Path, timeout: int = 180) -> tuple:
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


def quote_decl(where: str, needle: str, span: int = 3) -> dict:
    """声明句核对：needle 必须落在指定行 ±span 内，否则记 refuse（判据自己坏了）。"""
    rel, ln = where.rsplit(":", 1)
    lines = (ROOT / rel).read_text(encoding="utf-8", errors="replace").splitlines()
    lo, hi = max(0, int(ln) - 1 - span), min(len(lines), int(ln) + span)
    win = lines[lo:hi]
    hit = next((row.strip()[:200] for row in win if needle in row), "")
    if not hit:
        REFUSE.append(f"声明核对失败：{where} 附近 ±{span} 行内找不到 {needle!r}")
    return {"where": where, "needle": needle, "quoted": hit}


def collect(d: Path) -> dict:
    files = sorted(f for f in d.rglob("*") if f.is_file())
    out = {}
    for f in files:
        if f.suffix in (".pyx", ".py", ".c", ".pxd"):
            out[f.name] = f.read_text(encoding="utf-8", errors="replace")
    return {"files": [f.name for f in files], "text": out}


def build_case() -> dict:
    import tempfile

    docs = quote_decl("README.md:1", "build", 0)  # 只用于证明读文件通道没坏；真正的声明句在下面
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        (tmp / "lib.cypy").write_text(PROBE_LIB, encoding="utf-8", newline=chr(10))
        (tmp / "main.cypy").write_text(PROBE_MAIN, encoding="utf-8", newline=chr(10))
        out_b = tmp / "ob"
        rc_b, ob = sh([PY, "-X", "utf8", "-m", "cypyc", "build", str(tmp), "-o", str(out_b)], tmp)
        got_b = collect(out_b)
        out_t = tmp / "ot"
        rc_t, ot = sh(
            [PY, "-X", "utf8", "-m", "cypyc", "transpile", str(tmp / "lib.cypy"), "-o", str(out_t)],
            tmp,
        )
        got_t = collect(out_t)

        def typed_in(bundle: dict) -> list:
            hits = []
            for name, text in bundle["text"].items():
                for ln in text.splitlines():
                    if re.search(r"greet", ln) and re.search(r"\bstr\b", ln):
                        hits.append(f"{name}: {ln.strip()[:120]}")
            return hits

        b_hits, t_hits = typed_in(got_b), typed_in(got_t)
        # 反例（必不抓）：完全没有 greet 痕迹的产物文本，用来证明 matcher 不是恒真
        neg = "def unrelated():\n    return 1\n"
        neg_hit = any(
            re.search(r"greet", ln) and re.search(r"\bstr\b", ln) for ln in neg.splitlines()
        )
        if neg_hit:
            REFUSE.append("对照失效：反例里也命中了 typed matcher")
        return {
            "doc_read_probe": docs,
            "build_rc": rc_b,
            "build_stdout_tail": ob.strip().splitlines()[-3:],
            "build_artifacts": got_b["files"],
            "build_typed_lines": b_hits[:6],
            "lib_alone_transpile_rc": rc_t,
            "lib_alone_typed_lines": t_hits[:6],
            "negative_control_matches": neg_hit,
            "note": "lib 单独 transpile 是否带 str 签名 = 基线；build 产物里是否比基线更多信息 = 跨模块推断",
        }


def hook_case() -> dict:
    import tempfile

    decl = quote_decl("docs/USAGE.md:121", "cypyc hook install", 3)
    rc_h, out_h = sh([PY, "-X", "utf8", "-m", "cypyc", "hook", "--help"], ROOT)
    flags = sorted(set(re.findall(r"--([a-z][\w-]*)", out_h)))
    # docs/USAGE.md:121-124 声明了四个子命令形态：install / uninstall / status / clear-cache。
    # 逐条按声明的形状调用，rc 与 stderr 原文都留档——"help 里没有"不等于"跑不了"。
    subs = {}
    for sub in ("install", "uninstall", "status", "clear-cache"):
        rc_s, out_s = sh([PY, "-X", "utf8", "-m", "cypyc", "hook", sub], ROOT, timeout=90)
        subs[sub] = {
            "rc": rc_s,
            "first_error": next(
                (ln.strip()[:170] for ln in out_s.splitlines() if "error" in ln.lower()), ""
            ),
            "tail": out_s.strip().splitlines()[-2:],
        }
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        (tmp / "lib.cypy").write_text(PROBE_LIB, encoding="utf-8", newline=chr(10))
        (tmp / "main.cypy").write_text(PROBE_MAIN, encoding="utf-8", newline=chr(10))
        rc, out = sh([PY, "-X", "utf8", "-m", "cypyc", "hook", "--transpile-only"], tmp)
        emitted = sorted(f.name for f in tmp.rglob("*") if f.suffix == ".pyx")
        meta = sh(
            [
                PY,
                "-X",
                "utf8",
                "-c",
                "import sys; sys.path.insert(0, %r); import cypy_hook; "
                "print('hooks=', [type(m).__name__ for m in sys.meta_path])" % str(ROOT),
            ],
            ROOT,
        )
        api = sh(
            [
                PY,
                "-X",
                "utf8",
                "-c",
                "import cypy_hook; print([n for n in ('install_hook','uninstall_hook'"
                ",'is_hook_installed','CypyHook') if hasattr(cypy_hook, n)])",
            ],
            ROOT,
        )
        return {
            "declared_quoted": decl["quoted"],
            "help_rc": rc_h,
            "flags": flags,
            "declared_subcommands": subs,
            "documented_api_present": api[1].strip().splitlines()[-1][:200],
            "transpile_only_rc": rc,
            "transpile_only_tail": out.strip().splitlines()[-3:],
            "pyx_emitted": emitted,
            "meta_path_after_import": meta[1].strip().splitlines()[-1][:220],
            "finder_installed": "Cypy" in meta[1] or "cypy" in meta[1].lower(),
        }


def watch_case() -> dict:
    """热重载的**功能**核对：起进程 → 改源 → 看是否真的重编译出新产物（而不是只看横幅）。"""
    import shutil
    import tempfile

    work = Path(tempfile.mkdtemp(prefix="r2watch_"))
    try:
        (work / "lib.cypy").write_text(PROBE_LIB, encoding="utf-8", newline=chr(10))
        (work / "a.cypy").write_text(PROBE_MAIN, encoding="utf-8", newline=chr(10))
        proc = subprocess.Popen(
            [PY, "-X", "utf8", "-m", "cypyc", "watch", str(work)],
            cwd=str(work),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        time.sleep(8)
        before = sorted(p.name for p in work.rglob("*.pyx"))
        (work / "b.cypy").write_text(
            "let n: int = 1\nprint(n)\n", encoding="utf-8", newline=chr(10)
        )
        deadline = time.time() + 25
        after = list(before)
        while time.time() < deadline:
            after = sorted(p.name for p in work.rglob("*.pyx"))
            if "b.pyx" in after:
                break
            if proc.poll() is not None:
                break
            time.sleep(1)
        tail = []
        try:
            proc.kill()
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            REFUSE.append("watch 子进程 kill 后 15s 未退出（可能留孤儿）")
        if proc.stdout:
            tail = proc.stdout.read().splitlines()[-6:]
            proc.stdout.close()
        return {
            "alive_after_8s": proc.poll() is None or "（已 kill）",
            "pyx_before_change": before,
            "pyx_after_change": after,
            "new_module_picked_up": "b.pyx" in after,
            "output_tail": [t.strip()[:170] for t in tail],
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main() -> int:
    doc = {
        "refuse": REFUSE,
        "build": build_case(),
        "hook": hook_case(),
        "watch": watch_case(),
    }
    (HERE / "hunt_r2_confirm.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "refuse": REFUSE,
                "build_typed": doc["build"]["build_typed_lines"],
                "lib_alone_typed": doc["build"]["lib_alone_typed_lines"],
                "hook_finder": doc["hook"]["finder_installed"],
                "watch_pickup": doc["watch"]["new_module_picked_up"],
            },
            ensure_ascii=False,
        )
    )
    return 1 if REFUSE else 0


if __name__ == "__main__":
    sys.exit(main())
