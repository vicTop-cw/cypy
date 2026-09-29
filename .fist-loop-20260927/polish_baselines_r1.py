"""R1-打磨 law7：改完产品码（去掉 3 个重复 dict 键）后，三套基线必须**不回落**。

判据形状与验证环一致（各数各自实测、末行原文落盘、解析条数自证）：
 - pytest 全量：`passed ≥ 1862`（= 1854 起点 + 8 本轮锁）且 failed/errors = 0；
 - 自研套件：末行逐字段解析（total=47、passed=total、failed=0、skipped=0）；
 - 端到端基准（不带 --update）：`PASS=25 FAIL=0`。
任何一条不成立 ⇒ 非零退出，报告不落盘（打磨环节不动语义，回落就说明动错了）。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

HERE = Path(__file__).resolve().parent
ROOT = Path(r"E:\IDEProjects\AI\Cypy")
FLOOR = 1862
SUITE_CASES = 47
REFUSE = []


def load_snapshot() -> dict:
    """负载快照走 lane_load（能同时认出 python.exe 与 python3.13.exe，并按父链分本/外来 lane）。
    旧版用 `tasklist /FI IMAGENAME eq python.exe` 数——本机自己的解释器常叫 python3.13.exe，
    那个过滤器会把自己整棵子树漏掉，属于'恒报零负载'的坏探针。"""
    try:
        import lane_load

        return lane_load.snapshot()
    except Exception as exc:  # noqa: BLE001 - 探针坏了要显式承认，不能当成"没负载"
        return {"measured": False, "reason": f"探针异常：{type(exc).__name__}: {exc}"}


SUITE_RE = re.compile(
    r"^Total:\s*(?P<total>\d+)\s*\|\s*Passed:\s*(?P<passed>\d+)\s*\|"
    r"\s*Failed:\s*(?P<failed>\d+)\s*\|\s*Skipped:\s*(?P<skipped>\d+)$"
)


def suite_verdict(line: str) -> tuple:
    """自研套件末行：逐字段解析，不钉整行字面量。

    钉整行曾把这条判据做成恒红——`test_suite/core/runner.py:134` 的末行本来就带
    `| Skipped: N` 第四段。解析不出形状 ⇒ 弃权并给出原因，而不是当成绿。
    """
    m = SUITE_RE.match(line.strip())
    if not m:
        return False, "末行不符合 `Total: N | Passed: N | Failed: N | Skipped: N`，判据无法证明绿"
    f = {k: int(v) for k, v in m.groupdict().items()}
    if f["total"] != SUITE_CASES:
        return False, f"用例总数 {f['total']} ≠ {SUITE_CASES}（套件用例面被改动）"
    if f["passed"] != f["total"]:
        return False, f"passed {f['passed']} < total {f['total']}"
    if f["failed"] or f["skipped"]:
        return False, f"failed={f['failed']} skipped={f['skipped']}（跳过也不算绿：见 law2 口径）"
    return True, ""


def suite_selftest() -> list:
    """成对控制：真绿不许误报，四类必红不许漏抓。"""
    out = []
    ok, why = suite_verdict("Total: 47 | Passed: 47 | Failed: 0 | Skipped: 0")
    if not ok:
        out.append(f"判据7b 自检失败：真绿行被误判 ⇒ {why}")
    for bad, tag in [
        ("Total: 47 | Passed: 46 | Failed: 1 | Skipped: 0", "有红"),
        ("Total: 47 | Passed: 46 | Failed: 0 | Skipped: 1", "有跳过"),
        ("Total: 46 | Passed: 46 | Failed: 0 | Skipped: 0", "用例面缩水"),
        ("Total: 47 | Passed: 47 | Failed: 0", "缺 Skipped 段（格式漂移）"),
    ]:
        if suite_verdict(bad)[0]:
            out.append(f"判据7b 自检失败：坏行未被抓 ⇒ {tag}：{bad}")
    return out


def main() -> int:
    REFUSE.extend(suite_selftest())

    load_before = load_snapshot()
    rc, out = run(
        [sys.executable, "-X", "utf8", "-m", "pytest", "tests/", "-q", "-p", "no:cacheprovider"],
        "polish_pytest_r1.log",
    )
    load_after = load_snapshot()
    m = re.search(r"(\d+) passed", out)
    bad = re.findall(r"(\d+) (?:failed|error)", out)
    summary = [l for l in out.splitlines() if " passed" in l or " failed" in l]
    failed_tests = re.findall(r"^FAILED (\S+)", out, flags=re.M)
    doc = {
        "load": {"before": load_before, "after": load_after},
        "pytest": {
            "rc": rc,
            "passed": int(m.group(1)) if m else None,
            "failed_or_error": bad,
            "failed_tests": failed_tests,
            "skipped_marker_lines": out.count("SKIPPED"),
            "summary_line": summary[-1][:200] if summary else "",
        },
    }
    if not m:
        REFUSE.append(
            f"判据7a 解析不到 passed 计数（先看解析器是否坏了）：{doc['pytest']['summary_line'][:160]}"
        )
    elif doc["pytest"]["passed"] < FLOOR:
        REFUSE.append(f"判据7a 通过数 {doc['pytest']['passed']} < 下限 {FLOOR} ⇒ 基线回落")
    if bad:
        REFUSE.append(f"判据7a 有红/错：{bad}")

    rc, out = run(
        [sys.executable, "-X", "utf8", "scripts/run_tests.py"], "polish_suite_r1.log", 1800
    )
    line = next((l for l in out.splitlines() if l.startswith("Total:")), "")
    ok, why = suite_verdict(line)
    doc["suite"] = {"rc": rc, "line": line, "green": ok, "verdict": why or "绿"}
    if not ok:
        REFUSE.append(f"判据7b 自研套件不绿：{line!r}（原因：{why}）rc={rc}")
    if rc != 0:
        REFUSE.append(f"判据7b 自研套件退出码非零：rc={rc}")

    rc, out = run(["bash", "scripts/e2e_golden.sh"], "polish_e2e_r1.log", 2400)
    gline = next((l for l in out.splitlines() if "PASS=" in l), "")
    doc["e2e"] = {"rc": rc, "line": gline}
    if "PASS=25 FAIL=0" not in gline:
        REFUSE.append(f"判据7c 端到端基准不是 25/25：{gline!r} rc={rc}")

    # 本轮改动的针对性复核：去掉重复键后 math.* 的类型表逐项等价
    doc["quickwin_recheck"] = {
        "file": "cypyc/analyzer/type_checker.py",
        "f601_now": subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                "-m",
                "flake8",
                "--max-line-length=100",
                "--select=F601",
                "--",
                "cypyc/analyzer/type_checker.py",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        ).stdout.strip(),
    }
    if doc["quickwin_recheck"]["f601_now"]:
        REFUSE.append(f"判据7d quick win 后仍有 F601：{doc['quickwin_recheck']['f601_now'][:200]}")

    (HERE / "polish_baselines_r1.json").write_text(
        json.dumps({"refuse": REFUSE, **doc}, ensure_ascii=False, indent=1),
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "refuse": REFUSE,
                "pytest": doc["pytest"],
                "suite": doc["suite"],
                "e2e": doc["e2e"],
                "f601": doc["quickwin_recheck"]["f601_now"],
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 1 if REFUSE else 0


if __name__ == "__main__":
    sys.exit(main())
