"""R4-打磨 法⑥：结构债与不可逆项只测量、只挂账，一个字节都不动。

三件债都在**不可逆**那一侧：3000 行红线（BUG-70）要拆文件、`type_checker.py` 体量要重写分支、
`hook.eval` 写侧要改产物形状。本环的半径是「措辞/测试/账面」，所以这里交付的是
**可复跑的测量 + 不动手证明**，不是修复。

不动手怎么不自说自话：谓词取「产品码文件的 mtime 早于本环起点」，
并配一条合成对照——刚写下的临时文件必须被同一谓词判为「碰过」。
删除/重命名另用 `git status --porcelain` 的第 0/1 位正面测（D/R 一律不许出现）。
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import loop_kit as KIT  # noqa: E402

OUT = HERE / "polish_r4_structural.json"
START = datetime.datetime(2026, 9, 28, 1, 41, 16, tzinfo=datetime.timezone.utc)
PRODUCT_DIRS = ("cypyc", "cypy_hook", "cypy_bridge")
REDLINE = 3000
CHECKS: list = []
REFUSE: list = []


def rec(label, got, want, why) -> None:
    KIT.record(CHECKS, REFUSE, label, got, want, why)


def code_lines(text: str) -> int:
    n = 0
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        n += 1
    return n


def touched_after(p: Path, cutoff: datetime.datetime) -> bool:
    m = datetime.datetime.fromtimestamp(p.stat().st_mtime, datetime.timezone.utc)
    return m >= cutoff


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    sizes, over = [], []
    for d in PRODUCT_DIRS:
        for f in sorted((ROOT / d).rglob("*.py")):
            if "__pycache__" in f.parts:
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
            cl = code_lines(text)
            sizes.append({"file": f.relative_to(ROOT).as_posix(), "total_lines":
                          len(text.splitlines()), "code_lines": cl})
            if cl > REDLINE:
                over.append(f.relative_to(ROOT).as_posix())
    over_sorted = sorted(over, key=lambda x: -[s["code_lines"] for s in sizes
                                               if s["file"] == x][0])
    rec("3000 行（不含注释）红线：超限文件要逐张点名", len(over) >= 1, True,
        json.dumps(over_sorted[:6]))
    tc = [s for s in sizes if s["file"].endswith("analyzer/type_checker.py")]
    rec("type_checker.py 在测量面上（否则「它的体量」这句没被测到）", len(tc), 1,
        json.dumps(tc))
    tc_src = (ROOT / "cypyc" / "analyzer" / "type_checker.py").read_text(encoding="utf-8")
    tc_funcs = sum(1 for ln in tc_src.splitlines() if ln.startswith("    def ")
                   or ln.startswith("def "))
    rec("type_checker.py 的方法数被实测记入账面", tc_funcs > 0, True, f"{tc_funcs} 个 def")

    hook_src = (ROOT / "cypy_hook" / "hook.py").read_text(encoding="utf-8", errors="replace")
    write_side = hook_src.count("__result__")
    all_side = sum(f.read_text(encoding="utf-8", errors="replace").count("__result__")
                   for d in PRODUCT_DIRS for f in (ROOT / d).rglob("*.py")
                   if "__pycache__" not in f.parts)
    rec("hook.eval 写侧标记的计数满足包含关系（产品面总数 ≥ hook 单文件数）",
        all_side >= write_side, True, f"hook={write_side} 全产品面={all_side}")
    rec("写侧标记至少在一个文件里字面存在（否则挂账理由要改写为「标记缺席」）",
        all_side >= 1, True, f"全产品面 {all_side} 次")

    untouched = [s["file"] for s in sizes
                 if touched_after(ROOT / s["file"], START)]
    rec("本环没有碰过任何产品码文件（mtime 全早于环节起点）", untouched, [],
        json.dumps(untouched[:6]))
    scratch = HERE / "verify_r4_tmp" / f"struct_canary_{os.getpid()}.py"
    scratch.write_text("x = 1\n", encoding="utf-8", newline="\n")
    try:
        caught = touched_after(scratch, START)
    finally:
        scratch.unlink(missing_ok=True)
    rec("canary：刚写下的文件必须被同一谓词判为「碰过」", caught, True, scratch.name)

    g = subprocess.run(["git", "status", "--porcelain"], cwd=str(ROOT), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    rows = [ln for ln in (g.stdout or "").splitlines() if ln.strip()]
    prev_git = json.loads((HERE / "verify_r4_baselines.json").read_text(encoding="utf-8"))["git"]
    delren = [ln for ln in rows if ln[0] in "DR" or ln[1] in "DR"]
    ren = [ln for ln in rows if "R" in ln[:2]]
    rec("重命名一律为零（R 状态在本环不许出现）", ren, [], json.dumps(ren[:4]))
    rec("删除数与上一环实测逐字相等（本环没新删东西；口径=计数一致，未逐名对照 ⇒ 记为上界一致）",
        len(delren), prev_git["deleted_tracked"],
        f"本环 {len(delren)} vs R4-验证 {prev_git['deleted_tracked']}")
    staged = [ln for ln in rows if ln[0] not in " ?"]
    rec("暂存区为空（没有 git add）", staged, [], json.dumps(staged[:4]))

    queue = [{"item": "3000 行红线拆分", "files": over_sorted,
              "why_不可逆": "拆文件会改导入面与既有测试路径，属结构重排 ⇒ 交人工",
              "measure": "code_lines 逐文件实测"},
             {"item": "type_checker.py 体量/分支重写", "files": [s["file"] for s in tc],
              "why_不可逆": "重写会移动语义判定点，需要 golden 重注册 ⇒ 交人工",
              "measure": f"{tc[0]['code_lines'] if tc else 0} 行 / {tc_funcs} 个方法"},
             {"item": "hook.eval 写侧 __result__ 形状", "files": ["cypy_hook/hook.py"],
              "why_不可逆": "改产物形状影响已发布扩展的读取面 ⇒ 交人工",
              "measure": f"字面出现 {write_side} 次"}]
    rec("挂账队列逐条带测量（不许只写标题）",
        all(q["measure"] and q["why_不可逆"] for q in queue), True, json.dumps(
            [q["item"] for q in queue], ensure_ascii=False))

    doc = {"started": started, "redline": REDLINE, "files_measured": len(sizes),
           "over_redline": over_sorted, "sizes": sizes,
           "type_checker": {"code_lines": tc[0]["code_lines"] if tc else None,
                            "methods": tc_funcs},
           "hook_eval_marker_count": write_side,
           "hook_eval_marker_product_face_total": all_side,
           "deleted_verbatim": delren, "renamed_verbatim": ren,
           "product_files_touched_this_ring": untouched,
           "canary": {"fresh_file_caught": caught, "scratch_removed": not scratch.exists()},
           "git": {"rows": len(rows), "deleted_or_renamed": delren, "staged": staged},
           "adjudication_queue": queue, "executed_irreversible": [],
           "self_checks": CHECKS, "refuse": sorted(set(REFUSE)),
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": doc["refuse"], "over": over_sorted,
                      "measured": len(sizes), "touched": untouched,
                      "canary": doc["canary"], "git": doc["git"],
                      "queue": len(queue)}, ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
