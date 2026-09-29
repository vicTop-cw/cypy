"""R4-验证 法⑦：锁的「必红」复核——今天的绿灯不能当明天的证据。

三棵树同一批跑，每个结论都由「另一棵树上的反例」撑着：

· `work`：工作区（本轮终态码 + 当前测试）⇒ R4 锁必须全绿；
· `pre_r4`：工作区码，只把 `cypyc/analyzer/type_checker.py` 换回 R4-修复 前的文本
  ⇒ R4 锁必须红，且红的基本就是本轮四单的形状（混因列进 `collateral_causes`）；
· `head_code`：HEAD 的 `cypyc/ + cypy_hook/ + cypy_bridge/` 配上当前测试
  ⇒ 更旧的码，锁同样必须红；这一档同时给出「HEAD 落后多少」的混因分栏。

每棵树跑前都做身份探针（实读 `cypyc.analyzer.type_checker.__file__`），
「跑的是快照不是工作区」不许靠嘴说。
"""

from __future__ import annotations

import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import verify_r4_lib as V  # noqa: E402

TARGET = "tests/test_loop_20260927_fix_r4.py"
REL = Path("cypyc") / "analyzer" / "type_checker.py"
BEFORE_TC = HERE / "fix_r4_before" / "type_checker.py"
PACKAGES = ["cypyc", "cypy_hook", "cypy_bridge"]
OUT = HERE / "verify_r4_lockproof.json"
CHECKS: list = []
REFUSE: list = []


def check(label, got, want, why) -> None:
    CHECKS.append({"label": label, "got": got, "want": want, "why": why, "ok": got == want})
    if got != want:
        REFUSE.append(f"{label}: got={got!r} want={want!r}（{why}）")


def head_blob(path: str) -> bytes:
    r = subprocess.run(["git", "show", f"HEAD:{path}"], cwd=str(ROOT), capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"git show HEAD:{path} 失败 rc={r.returncode} {r.stderr[:200]}")
    return r.stdout


def tree_hash(dir_path: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(dir_path.rglob("*.py")):
        if "__pycache__" in f.parts:
            continue
        h.update(str(f.relative_to(dir_path)).encode())
        h.update(f.read_bytes())
    return h.hexdigest()[:16]


def build_head_code(dest: Path) -> dict:
    snap = V.copy_into_snap(dest=dest)
    replaced, missing = 0, []
    for pkg in PACKAGES:
        r = subprocess.run(["git", "ls-tree", "-r", "--name-only", "HEAD", "--", pkg],
                           cwd=str(ROOT), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        for line in r.stdout.splitlines():
            if not line.endswith(".py"):
                continue
            try:
                (snap / line).write_bytes(head_blob(line))
                replaced += 1
            except RuntimeError:
                missing.append(line)
    return {"snapshot": str(snap), "head_py_files_written": replaced,
            "missing_in_head": missing, "tree_hash": tree_hash(snap / "cypyc")}


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    runs = []
    heads = build_head_code(HERE / "verify_r4_head_snap")
    # 修前码那棵树复用 callsite 件建好的 SNAP2（同一份 fix_r4_before 文本，不重复拷仓）
    if not V.SNAP2.exists():
        V.copy_into_snap(dest=V.SNAP2)
    (V.SNAP2 / REL).write_bytes(BEFORE_TC.read_bytes())
    pre = {"snapshot": str(V.SNAP2), "type_checker_sha": V.sha256(V.SNAP2 / REL)}

    lanes = [
        {"lane": "work", "cwd": ROOT, "expect": "green",
         "note": "工作区=本轮终态码 + 当前测试"},
        {"lane": "pre_r4", "cwd": Path(pre["snapshot"]), "expect": "red", **pre},
        {"lane": "head_code", "cwd": Path(heads["snapshot"]), "expect": "red", **heads},
    ]
    for lane in lanes:
        cwd = lane["cwd"]
        ident = V.identity_probe(cwd)
        run = V.run_pytest([TARGET], cwd, timeout=1200)
        red = run["failed_names"]
        by_kind = {"target_red_count": len(red), "summary": run["summary_line"],
                   "rc": run["rc"]}
        achieved = ("green" if not red and run["rc"] == 0 and not run["collect_error"]
                    else "red" if red or run["collect_error"] else "ambiguous")
        runs.append({"lane": lane["lane"], "expect": lane["expect"], "achieved": achieved,
                     "identity": ident, "run": run, "detail": {k: v for k, v in lane.items()
                                                               if k not in ("cwd", "expect")},
                     **by_kind,
                     "failed_names_sample": red[:6],
                     "r4_shape_hits": sorted({n for n in red
                                              if "C0" in n or "call_face" in n
                                              or "internal_repr" in n})})
        if lane["lane"] != "work":
            check(f"{lane['lane']} 身份探针必须证明吃的是快照树", ident["under_snapshot"], True,
                  f"loaded={ident['loaded'].get('mod')}")
        else:
            mod = ident["loaded"].get("mod", "")
            check("work 身份探针必须证明吃的是工作区（不是快照）",
                  bool(mod) and Path(mod).resolve().is_relative_to(ROOT.resolve()), True,
                  f"loaded={mod}")

    by_lane = {r["lane"]: r for r in runs}
    check("work 档：R4 锁必须全绿（本轮终态的自证）", by_lane["work"]["achieved"], "green",
          by_lane["work"]["summary"])
    check("pre_r4 档：只回退产品码就必须让锁变红（今天的绿不等于明天的绿）",
          by_lane["pre_r4"]["achieved"], "red", by_lane["pre_r4"]["summary"])
    check("head_code 档：HEAD 码 + 当前测试也必须红",
          by_lane["head_code"]["achieved"], "red", by_lane["head_code"]["summary"])
    check("pre_r4 档红起来必须认得出本轮四单的形状（不是随便什么红）",
          len(by_lane["pre_r4"]["r4_shape_hits"]) >= 4, True,
          f"hits={by_lane['pre_r4']['r4_shape_hits'][:8]}")
    check("head_code 档同样要红在本轮形状上",
          len(by_lane["head_code"]["r4_shape_hits"]) >= 4, True,
          f"hits={by_lane['head_code']['r4_shape_hits'][:8]}")
    # 反向对照：三档跑的是同一份测试文件，红/绿差异只能来自产品码
    same_tests = len({hashlib.sha256((p / TARGET).read_bytes()).hexdigest()
                      for p in [ROOT, Path(pre["snapshot"]), Path(heads["snapshot"])]})
    check("三档的测试文件必须逐字相同（否则红绿差异不是产品码造成的）", same_tests, 1,
          "同一 sha 才算同一份测试")

    doc = {"started": started, "target_lock": TARGET, "runs": runs,
           "identity": [r["identity"] for r in runs],
           "head_lane": heads, "pre_lane": pre,
           "note": "同一份测试在三棵树上跑：绿→红 的差异只能来自产品码；"
                   "「红得认得出本轮形状」是防「随便一个红冒充证据」的那道门",
           "self_checks": CHECKS, "refuse": sorted(set(REFUSE)),
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({
        "lanes": {r["lane"]: {"achieved": r["achieved"], "summary": r["summary"],
                              "shape_hits": len(r["r4_shape_hits"]),
                              "under_snapshot": r["identity"]["under_snapshot"]} for r in runs},
        "head_files_written": heads.get("head_py_files_written"),
        "refuse": doc["refuse"]}, ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
