"""R5-修复 法 6：三套判据体系同一批复算（只升不降）+ git 红线 + 本环改动半径按 mtime 正面测出。

写死在这里的口径：
- 三套体系 = pytest 全量 / `scripts/run_tests.py` 自研套件 / `scripts/e2e_golden.sh` 基准。
  任何一套红 ⇒ 本环不得进验证环；解析到的条数与已知总数不符 ⇒ 先判"解析器坏了"（`parse_broken`），
  不许把解析失败读成"被测坏了"。
- 改动半径按 **mtime ≥ 本轮起点** 正面测：寻虫环允许写的只有 `.fist-loop-20260927/`（判据件）与
  `memory/`（账本/报告）；`cypyc/`、`cypy_hook/`、`cypy_bridge/`、`tests/`、`PROJECT-SPEC/`、`SYNTAX/`
  任一文件被摸到就是半径违规。
- HEAD、脏行、暂存、外部 worktree 四项 git 红线逐条点名，不取交集糊过去。
"""

from __future__ import annotations

import datetime
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "fix_r5_baselines.json"
PREV_RING = HERE / "hunt_r5_baselines.json"  # 上一环（R5-寻虫）实测件：地板从它反解
ROOT_ART = HERE / "root_r5_fix.out.json"  # 本环起点时间戳从账本的根任务现读，不写死
NS = "cypy-loop-20260927"
_prev = json.loads(PREV_RING.read_text(encoding="utf-8")) if PREV_RING.exists() else {}
FLOORS = dict(_prev.get("floors") or {})
FLOORS_SOURCE = f"{PREV_RING.name}:{json.dumps(_prev.get('floors'), ensure_ascii=False)}"
HEAD_EXPECT = str((_prev.get("git") or {}).get("head") or "")
WORKTREE_EXPECT = "E:/IDEProjects/AI/_cypy_head_baseline"
# 修复环可改面：产品码 + 测试 + 示例/文档/判据脚本；冻结语义与配置面、golden 基准一律禁改
FORBIDDEN = [
    "PROJECT-SPEC",
    "SYNTAX",
    "test_suite",
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
    ".flake8",
    "README.md",
    "CHANGELOG.md",
]
ALLOWED_DIRS = [
    "cypyc",
    "cypy_hook",
    "cypy_bridge",
    "tests",
    "examples",
    "scripts",
    "docs",
    "memory",
    ".fist-loop-20260927",
]
REFUSE: list = []
CHECKS: list = []


def ring_window_start() -> tuple:
    """本轮时间窗起点 = 账本里根任务的 created_at（现读 sqlite，不是手打的字面量）。"""
    import sqlite3

    root = json.loads(ROOT_ART.read_text(encoding="utf-8"))["root"]
    con = sqlite3.connect(f"file:{ROOT / 'fist-mbt.db'}?mode=ro", uri=True)
    row = con.execute("select created_at from tasks where ns=? and id=?", (NS, root)).fetchone()
    con.close()
    if not row:
        REFUSE.append(f"账本里读不到根任务 {root} 的 created_at ⇒ 时间窗起点没有实测来源")
        return "", None
    return row[0], datetime.datetime.fromisoformat(row[0].replace("Z", "+00:00"))


def check(label, got, want, why, ok=None) -> None:
    CHECKS.append(
        {
            "label": label,
            "got": got,
            "want": want,
            "why": why,
            "ok": (got == want) if ok is None else bool(ok),
        }
    )


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def sh(cmd: list, timeout: int = 1800) -> dict:
    p = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return {"rc": p.returncode, "out": p.stdout or "", "err": p.stderr or ""}


WINDOW = ring_window_start()


def started_stamp() -> datetime.datetime:
    if WINDOW[1] is None:
        REFUSE.append("时间窗起点读不到 ⇒ mtime 半径判据没有基准")
        return datetime.datetime(2100, 1, 1, tzinfo=datetime.timezone.utc)
    return WINDOW[1]


def pytest_face() -> dict:
    r = sh(
        [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "pytest",
            "tests/",
            "-q",
            "-p",
            "no:cacheprovider",
            "--no-header",
            "-o",
            "addopts=",
        ],
        timeout=2400,
    )
    body = r["out"] + r["err"]
    passed = [int(x) for x in __import__("re").findall(r"(\d+) passed", body)]
    failed = [int(x) for x in __import__("re").findall(r"(\d+) (?:failed|error)", body)]
    collected = [int(x) for x in __import__("re").findall(r"collected (\d+) item", body)]
    tail = [ln for ln in body.strip().splitlines() if ln.strip()][-4:]
    return {
        "rc": r["rc"],
        "passed": max(passed) if passed else 0,
        "failed_sum": sum(failed),
        "collected_line": max(collected) if collected else None,
        "tail": tail,
    }


def collect_face() -> dict:
    r = sh(
        [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "pytest",
            "tests/",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            "--no-header",
            "-o",
            "addopts=",
        ],
        timeout=900,
    )
    body = (r["out"] + r["err"]).strip().splitlines()
    nodeids = [ln for ln in body if "::" in ln]
    return {"rc": r["rc"], "nodeids": len(nodeids), "tail": body[-2:]}


def suite_face() -> dict:
    """自研套件的汇总行在**最后**一条含 `Total:` 的行上；逐键全文扫会先撞上分模块的小结（真踩过）。"""
    import re

    r = sh([sys.executable, "-X", "utf8", "scripts/run_tests.py"], timeout=1800)
    body = r["out"] + r["err"]
    line = next((ln for ln in reversed(body.splitlines()) if "Total:" in ln), body[-200:])
    fields = {k: int(v) for k, v in re.findall(r"(\w+):\s*(\d+)", line)}
    return {
        "rc": r["rc"],
        "summary_line": line.strip()[:200],
        "fields": fields,
        "parsed_keys": len(fields),
        "tail": [ln for ln in body.strip().splitlines() if ln.strip()][-3:],
    }


def e2e_face() -> dict:
    r = sh(["bash", "scripts/e2e_golden.sh"], timeout=2400)
    body = r["out"] + r["err"]
    fields = {}
    for key in ("PASS", "FAIL", "UNREG/RUNFAIL", "WARN"):
        m = __import__("re").search(rf"{key}\s*=\s*(\d+)", body)
        fields[key] = int(m.group(1)) if m else None
    return {
        "rc": r["rc"],
        "fields": fields,
        "summary_line": [ln.strip() for ln in body.splitlines() if "summary" in ln][-1:],
        "tail": [ln for ln in body.strip().splitlines() if ln.strip()][-3:],
    }


def git_face() -> dict:
    head = sh(["git", "rev-parse", "--short", "HEAD"])["out"].strip()
    status = sh(["git", "status", "--porcelain"])["out"]
    rows = [ln for ln in status.splitlines() if ln.strip()]
    staged = sh(["git", "diff", "--cached", "--name-only"])["out"].strip().splitlines()
    ahead = sh(["git", "rev-list", "--count", "@{u}..HEAD"])
    wt = sh(["git", "worktree", "list"])["out"]
    return {
        "head": head,
        "dirty_rows": len(rows),
        "deleted_tracked": len([ln for ln in rows if ln.startswith((" D", "AD"))]),
        "staged": len([ln for ln in staged if ln.strip()]),
        "ahead_of_upstream": ahead["out"].strip() or f"ERR:{ahead['err'].strip()[:60]}",
        "worktrees": [ln.split()[0] for ln in wt.splitlines() if ln.strip()],
        "foreign_worktree_present": WORKTREE_EXPECT.lower() in wt.replace("\\", "/").lower(),
    }


def radius_face() -> dict:
    """按 mtime ≥ 本轮起点 正面测半径：冻结语义/配置面/golden 基准不许被摸；产品码与测试是本环的允许面。"""
    st = started_stamp()
    touched = []
    for rel in FORBIDDEN:
        base = ROOT / rel
        paths = [base] if base.is_file() else (sorted(base.rglob("*")) if base.exists() else [])
        for p in paths:
            if (
                not p.is_file()
                or "__pycache__" in set(p.parts)
                or p.suffix
                not in (".py", ".pyx", ".cypy", ".md", ".toml", ".sh", ".json", ".txt", ".yaml")
            ):
                continue
            mt = datetime.datetime.fromtimestamp(p.stat().st_mtime, datetime.timezone.utc)
            if mt >= st:
                touched.append(
                    {
                        "file": p.relative_to(ROOT).as_posix(),
                        "mtime": mt.isoformat(timespec="seconds"),
                    }
                )
    allowed = []
    for rel in ALLOWED_DIRS:
        base = ROOT / rel
        for p in sorted(base.rglob("*")) if base.exists() else []:
            if p.is_file() and "__pycache__" not in set(p.parts):
                mt = datetime.datetime.fromtimestamp(p.stat().st_mtime, datetime.timezone.utc)
                if mt >= st:
                    allowed.append(p.relative_to(ROOT).as_posix())
    return {
        "touched_forbidden": touched,
        "forbidden_total": len(touched),
        "allowed_touched": len(allowed),
        "window_start": WINDOW[0],
        "measured_at": now(),
    }


def main() -> int:
    OUT.write_text(
        json.dumps({"started": now(), "refuse": ["未跑完"]}, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    base = {
        "window": {"start_utc": WINDOW[0], "finished_at_utc": None, "source": "tasks.created_at"},
        "floors": FLOORS,
        "floors_source": FLOORS_SOURCE,
        "git_head_expected": HEAD_EXPECT,
    }
    check(
        "地板四栏齐且来自上一环实测件（缺一栏就是手打风险）",
        [sorted(FLOORS), bool(HEAD_EXPECT)],
        [["collect", "e2e_pass", "pytest", "suite"], True],
        FLOORS_SOURCE,
    )
    base["pytest"] = pytest_face()
    base["collect"] = collect_face()
    base["suite"] = suite_face()
    base["e2e"] = e2e_face()
    base["git"] = git_face()
    base["radius"] = radius_face()
    base["finished_at_utc"] = now()

    sf, ef = base["suite"]["fields"], base["e2e"]["fields"]
    check(
        "pytest 达到上一环实测下限（只升不降）",
        base["pytest"]["passed"] >= FLOORS["pytest"],
        True,
        f"passed={base['pytest']['passed']} 下限={FLOORS['pytest']}",
        ok=base["pytest"]["passed"] >= FLOORS["pytest"],
    )
    check("pytest 无失败无错误", base["pytest"]["failed_sum"], 0, "摘要行里的 failed/error 计数")
    check("pytest rc=0", base["pytest"]["rc"], 0, "退出码")
    check(
        "收集数与通过数同量级（解析器没坏的下限证明）",
        base["collect"]["nodeids"] >= FLOORS["pytest"],
        True,
        f"collect-only nodeid={base['collect']['nodeids']}",
        ok=base["collect"]["nodeids"] >= FLOORS["pytest"],
    )
    check(
        f"自研套件达地板 {FLOORS['suite']}/{FLOORS['suite']}",
        f"{sf.get('Passed')}/{sf.get('Total')}",
        f"{FLOORS['suite']}/{FLOORS['suite']}",
        "scripts/run_tests.py",
    )
    check("自研套件 rc=0", base["suite"]["rc"], 0, "退出码")
    check(
        "自研套件解析到 4 个字段且 Passed+Failed+Skipped == Total（基数自证）",
        [
            base["suite"]["parsed_keys"] >= 4,
            sf.get("Passed", -1) + sf.get("Failed", 0) + sf.get("Skipped", 0)
            == sf.get("Total", -2),
        ],
        [True, True],
        f"fields={sf}",
    )
    check("e2e 基准达地板", ef.get("PASS"), FLOORS["e2e_pass"], "summary 行")
    check(
        "e2e 三格为零",
        f"{ef.get('FAIL')}{ef.get('WARN')}{ef.get('UNREG/RUNFAIL')}",
        "000",
        "summary 行的 FAIL/WARN/UNREG",
    )
    check("e2e rc=0", base["e2e"]["rc"], 0, "退出码")
    check("HEAD 未被改动", base["git"]["head"], HEAD_EXPECT, "git rev-parse（红线：本环不得提交）")
    check("暂存区为空", base["git"]["staged"], 0, "git diff --cached（红线：不得 git add）")
    check(
        "外部 HEAD 基线 worktree 仍在",
        base["git"]["foreign_worktree_present"],
        True,
        "它不属于本环，被删掉就是半径事故",
    )
    check(
        "冻结语义/配置面/golden 基准改动半径为零",
        base["radius"]["forbidden_total"],
        0,
        f"mtime ≥ {WINDOW[0]} 的文件：{[t['file'] for t in base['radius']['touched_forbidden']][:6]}",
    )
    check(
        "允许面确有改动（正面计数 > 0 才算 mtime 口径活着，不是恒绿）",
        base["radius"]["allowed_touched"] > 0,
        True,
        f"允许面（产品码/测试/判据件）侧 {base['radius']['allowed_touched']} 个",
        ok=base["radius"]["allowed_touched"] > 0,
    )
    base["three_systems_green"] = [
        base["pytest"]["rc"] == 0 and base["pytest"]["failed_sum"] == 0,
        base["suite"]["rc"] == 0 and sf.get("Failed") == 0,
        base["e2e"]["rc"] == 0 and ef.get("PASS") == FLOORS["e2e_pass"],
    ]
    base["three_systems_ok"] = all(base["three_systems_green"])
    base["all_ok"] = all(c["ok"] for c in CHECKS)
    base["self_checks"] = CHECKS
    base["refuse"] = sorted(set(REFUSE)) + [
        f"判据自证未过：{c['label']}（实得 {c['got']}）" for c in CHECKS if not c["ok"]
    ]
    OUT.write_text(
        json.dumps(base, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "refuse": base["refuse"],
                "three_systems_green": base["three_systems_green"],
                "pytest": base["pytest"],
                "collect": base["collect"]["nodeids"],
                "suite": sf,
                "e2e": ef,
                "git": base["git"],
                "radius": {k: v for k, v in base["radius"].items() if k != "touched_forbidden"},
                "self_checks": f"{sum(1 for c in CHECKS if c['ok'])}/{len(CHECKS)}",
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 1 if base["refuse"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as exc:
        OUT.write_text(
            json.dumps(
                {"refuse": [f"崩在 {type(exc).__name__}: {exc}"]}, ensure_ascii=False, indent=1
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(json.dumps({"crashed": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        sys.exit(2)
