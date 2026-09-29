"""R4-修复 的基线复算：三套判据体系同一批跑，且**只升不降**；冻结面与 git 红线正面测。

地板不是手填的：`floors` 取上一环（R4-寻虫）实测件的数字，本轮数字必须 ≥ 它。
`radius` 按 mtime ≥ 本轮起点正面测出改了哪些文件，并按类别分栏——
产品码改了哪些、测试改了哪些、文档改了哪些、**冻结面必须为 0**。
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "fix_r4_baselines.json"
PREV = HERE / "hunt_r4_baselines.json"
START_UTC = "2026-09-27T21:16:43+00:00"   # 根任务 T0r85 发布时刻（task_plan_deep 的 decided_at）
FROZEN_DIRS = ["PROJECT-SPEC", "SYNTAX"]
GOLDEN = ["tests/golden", "scripts/e2e_golden.sh"]
CHECKS: list = []
REFUSE: list = []


def check(label, got, want, why) -> None:
    CHECKS.append({"label": label, "got": got, "want": want, "why": why, "ok": got == want})


def run(cmd: list, timeout: int = 1500) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def tail_fields(text: str, labels: list) -> dict:
    line = next((ln for ln in reversed(text.splitlines())
                 if any(lbl in ln for lbl in labels)), "")
    return {k: int(v) for k, v in re.findall(r"(\w+)[=:]\s*(\d+)", line)}


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    prev = json.loads(PREV.read_text(encoding="utf-8"))
    floors = {"pytest": prev["pytest"]["passed"], "collect": prev["collect"]["nodeids"],
              "suite": prev["suite"]["fields"]["Total"], "e2e_pass": prev["e2e"]["fields"]["PASS"]}

    p = run([sys.executable, "-X", "utf8", "-m", "pytest", "tests/", "-q",
             "-p", "no:cacheprovider", "--no-header", "-o", "addopts=",
             "--tb=line", "-rf"], timeout=2400)
    ptext = (p.stdout or "") + (p.stderr or "")

    def num_of(pat):
        m = re.search(pat, ptext)
        return int(m.group(1)) if m else 0
    passed, failed = num_of(r"(\d+) passed"), num_of(r"(\d+) failed")
    errors = num_of(r"(\d+) error")
    c = run([sys.executable, "-X", "utf8", "-m", "pytest", "tests/", "--collect-only", "-q",
             "-p", "no:cacheprovider", "--no-header", "-o", "addopts="], timeout=600)
    ctext = (c.stdout or "") + (c.stderr or "")
    collected = int(re.search(r"(\d+) tests? collected", ctext).group(1)) \
        if re.search(r"(\d+) tests? collected", ctext) else 0

    s = run([sys.executable, "-X", "utf8", "scripts/run_tests.py"], timeout=1500)
    stext = (s.stdout or "") + (s.stderr or "")
    line = next((ln for ln in reversed(stext.splitlines()) if "Total:" in ln), "")
    suite = {k: int(v) for k, v in re.findall(r"(\w+):\s*(\d+)", line)}

    e = run(["bash", "scripts/e2e_golden.sh"], timeout=1500)
    etext = (e.stdout or "") + (e.stderr or "")
    eline = next((ln for ln in reversed(etext.splitlines()) if "PASS" in ln), "")
    e2e = {k: int(v) for k, v in re.findall(r"(\w+)[=:]\s*(\d+)", eline)}

    g = run(["git", "status", "--porcelain"])
    rows = [ln for ln in (g.stdout or "").splitlines() if ln.strip()]
    head = run(["git", "rev-parse", "--short", "HEAD"]).stdout.strip()
    # porcelain 的第 0 位是**索引**状态，第 1 位是工作区状态；上一版把 " M"/" D" 也算成
    # staged ⇒ 本轮开局就注定 91 行"暂存"，红线被读成违例。
    staged = sum(1 for ln in rows if ln[:1] not in (" ", "?"))
    wt = run(["git", "worktree", "list"]).stdout or ""

    start = datetime.datetime.fromisoformat(START_UTC)
    radius = {"product": [], "tests": [], "docs": [], "frozen": [], "loop": [],
              "ledger": [], "other": []}
    # 上一版的跳过条件是「任何以 . 开头的首段目录」⇒ `.fist-loop-20260927/` 整个被吞掉，
    # loop 栏永远是空，"按类别分栏"就成了恒真装饰。这里只跳真正的噪声目录。
    noise = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
             ".venv", "venv", "build", "dist", "node_modules", ".idea", ".vscode"}
    scanned_total = 0
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(ROOT).parts
        if any(part in noise or part.endswith(".egg-info") for part in rel_parts[:-1]):
            continue
        scanned_total += 1
        m = datetime.datetime.fromtimestamp(path.stat().st_mtime, datetime.timezone.utc)
        if m < start:
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(("cypyc/", "cypy_hook/", "cypy_bridge/")):
            radius["product"].append(rel)
        elif rel.startswith("tests/"):
            radius["tests"].append(rel)
        elif rel.startswith("docs/"):
            radius["docs"].append(rel)
        elif rel.startswith(("PROJECT-SPEC", "SYNTAX")):
            radius["frozen"].append(rel)
        elif rel.startswith(".fist-loop-20260927/"):
            radius["loop"].append(rel)
        elif rel.startswith("memory/"):
            radius["ledger"].append(rel)
        else:
            radius["other"].append(rel)
    radius = {k: sorted(v) for k, v in radius.items()}

    frozen_sha = {}
    for d in FROZEN_DIRS:
        for f in sorted((ROOT / d).rglob("*.md")):
            frozen_sha[f.relative_to(ROOT).as_posix()] = \
                hashlib.sha256(f.read_bytes()).hexdigest()[:12]
    docs_art = json.loads((HERE / "fix_r4_docs.json").read_text(encoding="utf-8"))
    anchor_rel = "SYNTAX/appendix-C-features.md"
    anchor_now = hashlib.sha256((ROOT / anchor_rel).read_bytes()).hexdigest()[:12]
    anchor_then = docs_art.get("frozen_bytes_sha")

    three_green = failed == 0 and errors == 0 and suite.get("Failed", -1) == 0 \
        and e2e.get("PASS", -1) >= floors["e2e_pass"] and e2e.get("FAIL", 0) == 0
    check("pytest 通过数不低于上一环实测", passed >= floors["pytest"], True,
          f"{passed} vs 地板 {floors['pytest']}")
    check("pytest 零失败零错误", [failed, errors], [0, 0], ptext[-260:])
    check("收集数不低于上一环", collected >= floors["collect"], True,
          f"{collected} vs {floors['collect']}")
    check("自研套件 Total 与地板同为 47", suite.get("Total"), floors["suite"], line)
    check("自研套件全绿", [suite.get("Passed"), suite.get("Failed")],
          [floors["suite"], 0], line)
    check("e2e golden PASS 不低于地板", e2e.get("PASS", 0) >= floors["e2e_pass"], True,
          json.dumps(e2e, ensure_ascii=False))
    check("e2e golden 零失败零警告", [e2e.get("FAIL", -1), e2e.get("WARN", -1)], [0, 0],
          json.dumps(e2e, ensure_ascii=False))
    check("HEAD 未动（本环不 commit）", head, "17d68b4", "git rev-parse")
    check("暂存区为空（没有 git add）", staged, 0, f"{staged} 行")
    check("外部基线 worktree 仍在", "E:/IDEProjects/AI/_cypy_head_baseline" in wt, True,
          wt.strip().splitlines()[:2])
    check("冻结面 mtime 为空", radius["frozen"], [], "PROJECT-SPEC/ 与 SYNTAX/ 未被触碰")
    check("冻结面自本环锚点未变（对 HEAD 比是错的锚：本轮之前工作区就与 HEAD 分道）",
          anchor_now, anchor_then, f"{anchor_rel} sha {anchor_then} → {anchor_now}")
    check("golden 脚本与目录未被改",
          [p for p in radius["product"] + radius["tests"] + radius["other"]
           if any(g in p for g in ("e2e_golden", "golden/"))], [], "golden 面")
    check("产品码改动集非空（正面证明本轮真改了码）", len(radius["product"]) >= 1, True,
          json.dumps(radius["product"], ensure_ascii=False))
    check("扫描面非空（否则整个半径栏是装饰）", scanned_total >= 1000, True,
          f"实扫 {scanned_total} 个文件")
    check("dot 目录不再被吞：loop 栏必须收到本轮驱动件",
          len(radius["loop"]) >= 20, True, f"loop {len(radius['loop'])} 个")
    check("账面文件单独成栏并且真的在窗口内", "memory/bugs.md" in radius["ledger"], True,
          json.dumps(radius["ledger"], ensure_ascii=False)[:200])
    if radius["product"] and len(radius["product"]) > 3:
        REFUSE.append(f"产品码改动面 {len(radius['product'])} 个文件，超出认领范围：{radius['product']}")

    refuse = sorted(set(REFUSE)) + [f"自证未过：{c2['label']}（实得 "
                                    f"{json.dumps(c2['got'], ensure_ascii=False)[:200]}）"
                                    for c2 in CHECKS if not c2["ok"]]
    doc = {"started": started, "window": {"start_utc": START_UTC, "finished_at_utc": started},
           "floors": floors,
           "pytest": {"passed": passed, "failed": failed, "errors": errors,
                      "failed_names": sorted({m.group(1) for m in re.finditer(
                          r"^(?:FAILED|ERROR) (\S+)", ptext, re.M)}),
                      "tail": ptext.strip().splitlines()[-4:]},
           "collect": {"nodeids": collected},
           "suite": {"fields": suite, "line": line},
           "e2e": {"fields": e2e, "line": eline},
           "git": {"head": head, "staged": staged, "dirty_rows": len(rows),
                   "worktrees": [ln.split()[1] for ln in wt.splitlines() if len(ln.split()) > 1],
                   "foreign_worktree_present": "E:/IDEProjects/AI/_cypy_head_baseline" in wt},
           "radius": radius, "frozen_sha": frozen_sha,
           "frozen_total": len(frozen_sha),
           "three_systems_green": three_green,
           "self_checks": CHECKS, "refuse": refuse,
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": refuse, "pytest": [passed, failed, errors], "collect": collected,
                      "suite": suite, "e2e": e2e, "git_head": head,
                      "radius": {k: len(v) for k, v in radius.items()},
                      "three_green": three_green}, ensure_ascii=False, indent=1))
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
