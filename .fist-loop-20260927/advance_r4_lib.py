"""R4-推进 的公共件：两棵树（改前/改后）与 CLI 调用面跑。

本环的产品改动只有两档分析器文件，改前字节已经整档存进 `advance_r4_tmp/`，
所以「改前态」可以在**复制树**里逐字重建（把两档文件换回改前字节），工作区一根手指都不碰。
每棵树跑之前先做身份探针：`cypyc.__file__` 与 `cypyc.analyzer.scope_analyzer.__file__`
必须落在那棵树里，否则「跑的是改前态」这句话就是嘴说的。
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ANSI = re.compile(r"\x1b\[[0-9;]*m")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TMP = HERE / "advance_r4_tmp"
BEFORE_TREE = HERE / "advance_r4_before_tree"
AFTER_TREE = HERE / "advance_r4_after_tree"
PROBE = HERE / "advance_r4_probe"
CARRY = ["cypyc", "cypy_hook", "cypy_bridge", "pyproject.toml", "README.md"]
NOISE = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv", "venv",
         "build", "dist", "node_modules", ".idea", ".vscode"}
EDITED = ["cypyc/analyzer/scope_analyzer.py", "cypyc/analyzer/type_checker.py"]
# 时间戳类行：改前/改后必然不同，比对时按整行剔除（不是放宽判据，而是这些行本来就不是语义）
VOLATILE_PREFIX = ("__compile_time__", "__generated_at__", "# Generated at", "__generated__")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def build_tree(dest: Path, revert: bool) -> dict:
    """把 CARRY 清单整份拷进 dest；revert=True 时把两档分析器换回改前字节。"""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    files = 0
    for name in CARRY:
        src = ROOT / name
        if not src.exists():
            continue
        dst = dest / name
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*NOISE))
        else:
            shutil.copy2(src, dst)
    for rel in EDITED:
        p = dest / rel
        if not p.exists():
            raise FileNotFoundError(f"复制树里缺 {rel}：{p}")
        if revert:
            before = TMP / Path(rel).name
            p.write_bytes(before.read_bytes())
    for f in dest.rglob("*.py"):
        files += 1
    return {"tree": dest.as_posix(), "py_files": files,
            "edited_shas": {Path(r).name: sha(dest / r) for r in EDITED}}


def identity_probe(tree: Path) -> dict:
    code = ("import json,cypyc,sys;"
            "from cypyc.analyzer import scope_analyzer as sa;"
            "print(json.dumps({'cypyc':cypyc.__file__,'scope':sa.__file__,"
            "'exe':sys.executable}))")
    r = subprocess.run([sys.executable, "-X", "utf8", "-c", code], cwd=str(tree),
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=_env(tree), timeout=180)
    try:
        got = json.loads((r.stdout or "").strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        got = {"error": (r.stderr or r.stdout or "")[:200]}
    # 只查「被测包是否落在这棵树里」；sys.executable 指向的是解释器安装目录，不该参与判定，
    # 把它混进 inside 会让这条探针恒假（第一版就这么被自己打回过一次）。
    inside = all(str(tree) in str(got.get(k, "")) for k in ("cypyc", "scope"))
    return {"tree": tree.as_posix(), "inside": bool(inside), **got}


def stage_probe(tree: Path, src: Path) -> str:
    """把复现夹具复制进树内并用**相对路径**喂 CLI：
    CLI 读绝对 Windows 路径时实测报「读取文件错误」（见 §失效），相对路径是它支持的形态。"""
    d = tree / "advance_probe"
    d.mkdir(parents=True, exist_ok=True)
    dst = d / src.name
    shutil.copy2(src, dst)
    return f"advance_probe/{src.name}"


def _env(tree: Path) -> dict:
    import os
    e = dict(os.environ)
    e["PYTHONPATH"] = str(tree) + (os.pathsep + e["PYTHONPATH"] if e.get("PYTHONPATH") else "")
    e["PYTHONIOENCODING"] = "utf-8"
    return e


def transpile(src: Path, tree: Path, out: Path) -> dict:
    """打 CLI 调用面：`python -m cypyc transpile`，退出码直接取（不接管道，免得读到 tail 的）。"""
    out.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([sys.executable, "-X", "utf8", "-m", "cypyc", "transpile", str(src),
                        "-o", str(out)], cwd=str(tree), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=_env(tree), timeout=600)
    text = ANSI.sub("", (r.stdout or "") + (r.stderr or ""))
    lines = text.splitlines()
    undef = [ln.strip() for ln in lines if "Undefined name" in ln]
    errs = sorted({u.split(" - ")[-1] for u in undef})
    prods = sorted(p.relative_to(out).as_posix() for p in out.rglob("*")
                   if p.is_file() and p.suffix in {".pyx", ".pxd", ".c", ".h"})
    return {"rc": r.returncode, "undefined_names": errs, "duplicate_error_lines": len(undef),
            "products": prods, "stdout_tail": lines[-3:], "pyx_has_error_banner":
                "[FAIL]" in text}


def strip_volatile(text: str) -> list:
    return [ln for ln in text.splitlines() if not ln.startswith(VOLATILE_PREFIX)]


def pyx_of(out_dir: Path) -> str:
    p = sorted(out_dir.rglob("*.pyx"))
    return p[0].read_text(encoding="utf-8", errors="replace") if p else ""


def cleanup() -> None:
    for d in (BEFORE_TREE, AFTER_TREE):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
