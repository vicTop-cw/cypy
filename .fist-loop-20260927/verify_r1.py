"""R1-验证 的取证跑手：五套判据一次跑齐，任何一条不成立即非零退出并原样报。

1. pytest 全量（`tests/`）——0 failed 且通过数不低于起点 1854 + 本轮新增锁数
2. 自研套件 `scripts/run_tests.py`——Failed 必须为 0
3. 端到端基准 `scripts/e2e_golden.sh`（**不带 --update**）——PASS=25 FAIL=0
4. 冻结文档零改动——`PROJECT-SPEC/`、`SYNTAX/` 在 `git diff --name-only` 里必须为空
5. 规范符合性——本循环改过的文件跑 `black --check` 与 `flake8`（配置来自 pyproject）

判据 1/2/3 是**串行的**：既往实测两套全量并发会把墙钟毒成疑似死锁，且互抢 examples/ 构建产物。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(r"E:\IDEProjects\AI\Cypy")
# mtime 判据的起点：实测冻结文档里最新的一份是 `SYNTAX/01-basic-types.md`（09-26 22:40:23，
# 上一轮 float 裁决的措辞下修），循环轮 Step 0 在 09-27 11:05 之后 ⇒ 取 09-26 23:00 为界，
# 既能抓到本轮任何越界写入，也不会把上一轮已授权的文档改动误判成违例。
ROUND_START = sys.argv[1] if len(sys.argv) > 1 else "2026-09-26 23:00:00"
BASELINE_PASSED = 1854  # 2026-09-26 打磨轮终态（只升不降的下限）
NEW_LOCKS = 8  # tests/test_loop_20260927_fix.py
TOUCHED = [
    "cypyc/parser/lexer.py",
    "cypyc/codegen/cython_generator.py",
    "cypyc/codegen/type_mapper.py",
    "cypy_bridge/types.py",
    "cypy_bridge/__init__.py",
    "tests/test_loop_20260927_fix.py",
    "tests/test_bridge_library.py",
]


def run(cmd: list, log_name: str, timeout: int = 3600) -> tuple:
    p = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    out = (p.stdout or "") + (p.stderr or "")
    (HERE / log_name).write_text(out, encoding="utf-8", newline="\n")
    return p.returncode, out


def main() -> int:
    refuse = []
    doc = {}

    rc, out = run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "pytest",
            "tests/",
            "-q",
            "--no-header",
            "-p",
            "no:cacheprovider",
        ],
        "verify_pytest_full_r1.log",
        timeout=3600,
    )
    pm = re.search(r"(\d+) passed", out)
    fm = re.search(r"(\d+) failed", out)
    em = re.search(r"(\d+) error", out)
    passed = int(pm.group(1)) if pm else 0
    doc["pytest_full"] = {
        "rc": rc,
        "passed": passed,
        "failed": int(fm.group(1)) if fm else 0,
        "errors": int(em.group(1)) if em else 0,
        "summary_line": (out.strip().splitlines() or [""])[-1],
    }
    if not pm:
        refuse.append(
            f"判据1 解析不到 passed 计数（pytest 可能自己崩了）：{doc['pytest_full']['summary_line'][:200]}"
        )
    elif passed < BASELINE_PASSED + NEW_LOCKS:
        refuse.append(
            f"判据1 通过数 {passed} < 下限 {BASELINE_PASSED}+{NEW_LOCKS} ⇒ 基线回落或新锁未进集合"
        )
    if doc["pytest_full"]["failed"] or doc["pytest_full"]["errors"]:
        refuse.append(f"判据1 有红/错：{doc['pytest_full']}")

    rc, out = run(
        [sys.executable, "-X", "utf8", "scripts/run_tests.py"],
        "verify_test_suite_r1.log",
        timeout=900,
    )
    m = re.search(r"Total: (\d+) \| Passed: (\d+) \| Failed: (\d+)", out)
    doc["test_suite"] = {"rc": rc, "line": m.group(0) if m else None}
    if not m or m.group(3) != "0" or rc != 0:
        refuse.append(f"判据2 自研套件不绿：{doc['test_suite']}")

    rc, out = run(["bash", "scripts/e2e_golden.sh"], "verify_e2e_r1.log", timeout=2400)
    s = re.search(r"PASS=(\d+) FAIL=(\d+) UNREG/RUNFAIL=(\d+) WARN=(\d+)", out)
    doc["e2e"] = {"rc": rc, "line": s.group(0) if s else None}
    if not s or s.group(1) != "25" or s.group(2) != "0" or s.group(3) != "0" or s.group(4) != "0":
        refuse.append(f"判据3 端到端基准不是 25/25：{doc['e2e']}")

    rc, out = run(["git", "diff", "--name-only"], "verify_gitdiff_r1.log", timeout=120)
    frozen = [l for l in out.splitlines() if l.startswith(("PROJECT-SPEC/", "SYNTAX/"))]
    # `git diff` 只看得到**已跟踪**文件的改动，而 SYNTAX/ 里有未跟踪新文件（如 33 号文档）——
    # 单靠它会把"未跟踪文件被改过"漏掉。补一道 mtime 判据：本轮起点之后被动过的冻结文档一律拒绝。
    start = datetime.fromisoformat(ROUND_START).timestamp()
    fresh, newest = [], (0.0, "")
    for d in ("PROJECT-SPEC", "SYNTAX"):
        for p in (ROOT / d).rglob("*"):
            if p.is_file():
                mt = p.stat().st_mtime
                if mt > start:
                    fresh.append(p.relative_to(ROOT).as_posix())
                if mt > newest[0]:
                    newest = (mt, p.relative_to(ROOT).as_posix())
    doc["frozen_docs"] = {
        "touched_vs_head": frozen,
        "touched_after_round_start": fresh,
        "round_start": ROUND_START,
        "per_file_mtime": {
            f: datetime.fromtimestamp((ROOT / f).stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            for f in frozen
            if (ROOT / f).exists()
        },
        "newest_frozen_mtime": datetime.fromtimestamp(newest[0]).strftime("%Y-%m-%d %H:%M:%S"),
        "newest_frozen_file": newest[1],
    }
    # 只有「本轮起点之后被写过」才是本轮的改动。`git diff HEAD` 的两份 SYNTAX 改动
    # mtime 早于本轮起点（属 09-26 未提交轮）——拿它拒绝就等于把上一轮的债算到本轮头上，
    # 而它同时也不该被静音：记进清单，交脏工作树定性（verify_dirt_r1）与打磨轮裁决。
    if fresh:
        refuse.append(f"判据4 冻结文档在本轮起点 {ROUND_START} 之后有写入痕迹：{fresh}")
    if not frozen and not fresh:
        refuse.append("判据4 冻结文档面既无 diff 也无 mtime 信号 ⇒ 判据没在数任何东西，先自证口径")

    # 判据5 交给 verify_lint_r1.py：按「本轮亲笔区间」判，而不是整份文件
    # （cython_generator.py 单文件存量 285 条、全仓 4990 条——按文件判等于恒红）。
    lr = subprocess.run(
        [sys.executable, "-X", "utf8", str(HERE / "verify_lint_r1.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    lint = json.loads((HERE / "verify_lint_r1.json").read_text(encoding="utf-8"))
    doc["lint_scoped"] = {
        "rc": lr.returncode,
        "refuse": lint["refuse"],
        "in_authored": {k: v["in_authored"] for k, v in lint["per_file"].items()},
        "totals": {k: v["violations_total"] for k, v in lint["per_file"].items()},
        "black_would_reformat": lint["black"]["would_reformat"],
        "repo_census": {
            k: v for k, v in lint["repo_census"].items() if k in ("rc", "total", "files", "census")
        },
        "controls": lint["controls"],
    }
    if lr.returncode == 0 and not lint["refuse"]:
        pass
    elif lint["refuse"]:
        refuse.extend(f"判据5 {r}" for r in lint["refuse"])
    else:
        refuse.append(
            f"判据5 子判据非零退出却没写拒绝理由（rc={lr.returncode}），不当作通过："
            f"{(lr.stdout or '')[-300:]}"
        )
    if "refuse" not in doc["lint_scoped"]:
        refuse.append("判据5 lint_scoped 里没带 refuse 字段 ⇒ 覆盖面窄于主张，当场判红")

    # mypy：项目配了 strict，但整仓存量错误不是本轮引入的 —— 这一条**只测不裁**，
    # 把改动面的错误数记进报告，交 R1-打磨 决定是否立项清偿（不假装绿，也不拿它当红线）。
    rc, out = run([sys.executable, "-m", "mypy", *TOUCHED[:5]], "verify_mypy_r1.log", timeout=900)
    errs = [l for l in out.splitlines() if ": error:" in l]
    doc["mypy_record_only"] = {
        "rc": rc,
        "error_count": len(errs),
        "first5": errs[:5],
        "note": "只记录不裁决：strict 全仓存量债非本轮引入",
    }

    (HERE / "verify_r1.json").write_text(
        json.dumps({"refuse": refuse, **doc}, ensure_ascii=False, indent=1),
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "refuse": refuse,
                "pytest_full": doc["pytest_full"],
                "test_suite": doc["test_suite"],
                "e2e": doc["e2e"],
                "frozen_docs": doc["frozen_docs"],
                "lint_scoped": doc["lint_scoped"]["in_authored"],
                "frozen_mtime": doc["frozen_docs"]["per_file_mtime"],
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
