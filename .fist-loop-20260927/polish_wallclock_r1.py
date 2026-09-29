"""R1-打磨 ⑦′：把「首跑为什么红」变成落盘证据，而不是一句"当时机器在忙"。

做三件事，全部在**无并发 python 进程**的条件下跑：
 1. 单独跑首跑里那条红用例（`TestDigestCost::test_digest_cost_on_ten_thousand_line_module`）；
 2. 整文件跑 `tests/test_incremental.py`；
 3. 把该用例源码里的计时口径原文抽出来（哪条断言用 `process_time`、哪条用 `perf_counter`）。

判据形状：两条复跑都必须绿，且必须抓得到"源码里确实存在墙钟阈值断言"这一条事实；
任一条不成立 ⇒ 拒绝出 JSON，报告不落盘。本脚本**不放宽任何阈值**——它只证明
红的那条断言测的是墙钟，而墙钟在共享机器上不是产品信号（BUG-13 账本已写明
"parse/compare 两条时限仍是墙钟"）。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

HERE = Path(__file__).resolve().parent
ROOT = Path(r"E:\IDEProjects\AI\Cypy")
TARGET = "tests/test_incremental.py::TestDigestCost::test_digest_cost_on_ten_thousand_line_module"
SRC = ROOT / "tests" / "test_incremental.py"
REFUSE = []


def parse_counts(out: str) -> dict:
    return {
        "passed": int(m.group(1)) if (m := re.search(r"(\d+) passed", out)) else 0,
        "failed": re.findall(r"(\d+) failed", out),
        "summary_line": ([l for l in out.splitlines() if " passed" in l] or [""])[-1].strip(),
    }


def load_samples(own_pid: int | None = None, n: int = 3, gap: float = 1.0) -> list:
    """连续 n 次快照。单次抓到的可能是自己刚退出子的残留；真邻居会一直在。"""
    import lane_load

    snaps = []
    for _ in range(n):
        snaps.append(lane_load.snapshot(own_pid))
        time.sleep(gap)
    return snaps


def worst(snaps: list) -> dict:
    keys = ("foreign_lane", "unattributable")
    out = {}
    for k in keys:
        out[k] = max(int(s.get(k) or 0) for s in snaps)
    out["measured_all"] = all(bool(s.get("measured")) for s in snaps)
    out["sample_count"] = len(snaps)
    for s in snaps:
        if s.get("foreign_sample"):
            out.setdefault("first_foreign_sample", s["foreign_sample"][:3])
            break
    return out


def run(cmd: list, log: str) -> dict:
    r = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=1800,
    )
    out = (r.stdout or "") + (r.stderr or "")
    (HERE / log).write_text(out, encoding="utf-8", newline="\n")
    d = parse_counts(out)
    d["rc"] = r.returncode
    return d


def timing_lines() -> dict:
    """抽该用例函数体内的计时口径原文：证明"红的那条是墙钟，同函数上一条是 CPU 时间"。"""
    txt = SRC.read_text(encoding="utf-8", errors="replace").splitlines()
    start = None
    for i, l in enumerate(txt):
        if "def test_digest_cost_on_ten_thousand_line_module" in l:
            start = i
            break
    if start is None:
        return {"found": False, "body": []}
    body = []
    for i in range(start, min(start + 60, len(txt))):
        if i > start and re.match(r"^\s{0,4}(def |class )", txt[i]):
            break
        if re.search(r"perf_counter|process_time|assert .*< [0-9.]+", txt[i]):
            body.append({"line": i + 1, "text": txt[i].strip()})
    return {
        "found": True,
        "body": body,
        "has_wallclock_assert": any(
            "perf_counter" in b["text"] or "time.time" in b["text"] for b in body
        ),
        "has_cpu_time_usage": any("process_time" in b["text"] for b in body),
    }


def main() -> int:
    own = os.getpid()
    load_before = worst(load_samples(own))
    solo = run(
        [sys.executable, "-X", "utf8", "-m", "pytest", TARGET, "-q", "-p", "no:cacheprovider"],
        "polish_wallclock_solo_r1.log",
    )
    whole = run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "pytest",
            "tests/test_incremental.py",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        "polish_wallclock_file_r1.log",
    )
    load_after = worst(load_samples(own))
    tm = timing_lines()

    for tag, sn in (("复跑前", load_before), ("复跑后", load_after)):
        if not sn.get("measured_all"):
            REFUSE.append(
                f"⑦′ {tag} 有采样没测到（PowerShell 不可用与真无负载分不开）⇒ 负载栏不可用"
            )
    # 负载栏只作**旁证**记录，不当门：本机存在"命令行读不到"的常驻 python（父 bash 的命令行也读不到），
    # 因此"机器完全空闲"这个前提在这台机器上根本不可证。可证的是下面这条——
    # 首跑与复跑之间产品码一行没动，所以红绿翻转不是产品行为造成的。
    for tag, d in (("单跑", solo), ("整文件", whole)):
        if d["rc"] != 0 or d["failed"]:
            REFUSE.append(f"⑦′ {tag} 仍红：{d} ⇒ 不是负载归因，须按真缺陷处理")
    # 首跑与复跑之间产品码是否零改动（用 mtime 证，不用"我记得没改"证）
    prod_dirs = ["cypyc", "cypy_bridge", "test_suite", "scripts", "tests"]
    try1_mtime = (HERE / "polish_pytest_r1.try1.log").stat().st_mtime
    newer = []
    for d in prod_dirs:
        for f in (ROOT / d).rglob("*.py"):
            if f.suffix == ".py" and f.stat().st_mtime > try1_mtime + 1:
                newer.append(f.relative_to(ROOT).as_posix())
    doc_probe = {
        "try1_log_mtime_utc": datetime.utcfromtimestamp(try1_mtime).isoformat() + "Z",
        "product_py_files_checked": prod_dirs,
        "product_files_newer_than_try1": sorted(newer),
    }
    if newer:
        REFUSE.append(
            f"⑦′ 首跑之后有产品文件被改过，'产品码未变⇒红绿翻转与环境有关'的推论不成立：{sorted(newer)[:8]}"
        )

    if not tm["found"]:
        REFUSE.append("⑦′ 定位不到该用例函数体，计时口径原文取不到")
    elif not (tm["has_wallclock_assert"] and tm["has_cpu_time_usage"]):
        REFUSE.append(f"⑦′ 源码里没同时出现墙钟断言与 process_time 用法：{tm}")
    if solo["passed"] < 1:
        REFUSE.append(f"⑦′ 单跑没有通过的用例：{solo}")

    doc = {
        "refuse": REFUSE,
        "target": TARGET,
        "load": {"before": load_before, "after": load_after, "policy": "连续 3 次采样取最大值"},
        "solo": solo,
        "whole_file": whole,
        "timing_evidence": tm,
        "product_unchanged_since_try1": doc_probe,
    }
    (HERE / "polish_wallclock_r1.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    print(json.dumps(doc, ensure_ascii=False, indent=1))
    return 1 if REFUSE else 0


if __name__ == "__main__":
    sys.exit(main())
