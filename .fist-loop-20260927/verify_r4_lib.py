"""R4-验证 的公共件：快照树、身份探针、判据跑。

验证环的一切「摘回修前」的动作都只发生在 `.fist-loop-20260927/verify_r4_snap/` 里，
工作区一根手指都不碰；每棵树跑之前先做身份探针——「跑的是快照不是工作区」这件事
不能靠嘴说，要靠 `cypyc.__file__` 的实读路径来钉。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SNAP = HERE / "verify_r4_snap"
SNAP2 = HERE / "verify_r4_prefix_snap"
NOISE = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv", "venv",
         "build", "dist", "node_modules", ".idea", ".vscode"}
CARRY = ["cypyc", "cypy_bridge", "cypy_hook", "tests", "docs", "SYNTAX", "PROJECT-SPEC",
         "scripts", "examples", "pyproject.toml", "README.md"]


def copy_into_snap(extra_files: list | None = None, dest: Path = SNAP) -> Path:
    """把 CARRY 清单从工作区整份拷进快照树（先清后拷，剔除缓存目录）。"""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for name in CARRY + list(extra_files or []):
        src = ROOT / name
        if not src.exists():
            continue
        dst = dest / name
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*NOISE))
        else:
            shutil.copy2(src, dst)
    return dest


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity_probe(cwd: Path) -> dict:
    """实读 `cypyc.__file__`：证明这条命令吃的是快照树而不是工作区。"""
    code = ("import json,cypyc,cypyc.analyzer.type_checker as tc;"
            "print(json.dumps({'pkg':cypyc.__file__,'mod':tc.__file__},"
            "ensure_ascii=False))")
    r = run_py(code, cwd)
    got = {}
    try:
        got = json.loads(r["stdout"].strip().splitlines()[-1])
    except Exception:
        got = {"raw": r["stdout"][-300:], "err": r["stderr"][-300:]}
    under = bool(got.get("mod")) and Path(got["mod"]).resolve().is_relative_to(cwd.resolve())
    return {"cwd": str(cwd), "loaded": got, "under_snapshot": under,
            "rc": r["rc"], "workspace_leak": not under}


def run_py(code: str, cwd: Path, timeout: int = 120) -> dict:
    env = dict(os.environ, PYTHONPATH=str(cwd), PYTHONDONTWRITEBYTECODE="1")
    p = subprocess.run([sys.executable, "-X", "utf8", "-c", code], cwd=str(cwd),
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=env, timeout=timeout)
    return {"rc": p.returncode, "stdout": p.stdout or "", "stderr": p.stderr or ""}


FAILED_RE = re.compile(r"^(?:FAILED|ERROR) (\S+)", re.M)


def collect_count(nodeid: str, cwd: Path) -> int:
    """`--collect-only -q` 数用例 id 的行数：拿它当「应跑几条」的正面测量。"""
    env = dict(os.environ, PYTHONPATH=str(cwd), PYTHONDONTWRITEBYTECODE="1")
    p = subprocess.run([sys.executable, "-X", "utf8", "-m", "pytest", nodeid,
                        "--collect-only", "-q", "-p", "no:cacheprovider", "--no-header",
                        "-o", "addopts="],
                       cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env, timeout=300)
    text = (p.stdout or "") + (p.stderr or "")
    return sum(1 for ln in text.splitlines() if "::" in ln)


COUNT_RE = re.compile(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed)")
ALIAS = {"passed": "passed", "failed": "failed", "errors": "errors", "error": "errors",
         "skipped": "skipped", "xfailed": "xfailed", "xpassed": "xpassed"}


def parse_counts(text: str) -> dict:
    """从 pytest 的收尾汇总行反解计数。

    `-q` 的汇总行是 `53 passed in 13.88s` 这种「数在前、词在后」的形状，
    用 `key=value` 的正则去数会一律得 0——那会让「failed==0」这种门变成恒真。
    """
    line = next((ln for ln in reversed(text.splitlines())
                 if re.search(r"\d+ (passed|failed|error)", ln)), "")
    fields: dict = {}
    for num, word in COUNT_RE.findall(line):
        key = ALIAS[word]
        fields[key] = fields.get(key, 0) + int(num)
    return {"summary_line": line, "fields": fields}


def run_pytest(nodeids: list, cwd: Path, timeout: int = 900) -> dict:
    """在快照树里跑 pytest，回 rc / 汇总字段 / 失败用例名 / 是否收集期就炸。"""
    env = dict(os.environ, PYTHONPATH=str(cwd), PYTHONDONTWRITEBYTECODE="1")
    cmd = [sys.executable, "-X", "utf8", "-m", "pytest", *nodeids, "-q", "-p", "no:cacheprovider",
           "--no-header", "-o", "addopts=", "--tb=no"]
    p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env, timeout=timeout)
    text = (p.stdout or "") + (p.stderr or "")
    parsed = parse_counts(text)
    fields = parsed["fields"]
    for word in ("passed", "failed", "errors", "skipped"):
        fields.setdefault(word, 0)
    names = sorted({m.group(1) for m in FAILED_RE.finditer(text)})
    # 收集期就炸（模块 import 失败）：有 errors 计数、或压根没有汇总行，都算「跑不动」而非「跑红」
    collect_error = fields["errors"] > 0 or not parsed["summary_line"] or "Interrupted" in text
    return {"cmd": " ".join(["pytest", *nodeids]), "rc": p.returncode, "fields": fields,
            "failed_names": names, "collect_error": collect_error,
            "summary_line": parsed["summary_line"],
            "tail": text[-400:]}
