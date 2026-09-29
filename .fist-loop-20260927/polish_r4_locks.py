"""R4-打磨 法⑤：新写的永久锁必须证承重——拿修前码与修前文档跑一遍，不红就是白写。

三条道：

* **A 工作区道**：当前产品码 + 新测试 ⇒ 20 条全绿（这是「绿」的那一半，单独不算证据）；
* **B 修前道**：把同一份测试文件复制进 `verify_r4_prefix_snap`（`type_checker.py`
  sha=27a3408faad2，R4 修法之前）与它的旧 `docs/USAGE.md` 一起跑 ⇒ 必须出现红，
  且红要落在「本轮新锁」的形状上（CLI 探针逐条 + 文档口径锁）；
* **C 合成违例道**：文档锁的谓词拿**归档的改前正文**判一次必须为假、拿现文判一次必须为真
  ——证明这条锁既能红也不是恒红。

身份探针打在每条道上（被测文件的 sha 与 `__file__` 前缀），避免「跑错树」那一类假结论。
既有测试一条不删不放宽：本件只数新增文件，并核对新增前后工作区收集数只升不降。
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
NEW_TEST = ROOT / "tests" / "test_loop_20260927_polish_r4.py"
SNAP = HERE / "verify_r4_prefix_snap"
WORK_CHECKER = ROOT / "cypyc" / "analyzer" / "type_checker.py"
USAGE = ROOT / "docs" / "USAGE.md"
USAGE_BEFORE = HERE / "verify_r4_tmp" / "USAGE.md.before_polish"
OUT = HERE / "polish_r4_locks.json"
CHECKS: list = []
REFUSE: list = []
OLD_CLAIM = "源未变会复用"
NEW_CLAIM = "每次都重编译"


def check(label, got, want, why) -> None:
    CHECKS.append({"label": label, "got": got, "want": want, "why": why, "ok": got == want})
    if got != want:
        REFUSE.append(f"{label}: got={got!r} want={want!r}（{why}）")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12] if p.exists() else "MISSING"


def run(tree: Path, target: str, timeout: int = 900) -> dict:
    p = subprocess.run([sys.executable, "-X", "utf8", "-m", "pytest", target, "-rA", "-q",
                        "-p", "no:cacheprovider", "--no-header", "-o", "addopts="],
                       cwd=str(tree), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    text = (p.stdout or "") + (p.stderr or "")
    m = re.search(r"(\d+) (passed|failed|error)", text)
    counts = {k: 0 for k in ("passed", "failed", "error")}
    for mm in re.finditer(r"(\d+) (passed|failed|errors?)", text):
        key = "error" if mm.group(2).startswith("error") else mm.group(2)
        counts[key] = max(counts[key], int(mm.group(1)))
    red = sorted({x.group(1).split("::")[-1] for x in
                  re.finditer(r"^(?:FAILED|ERROR) (\S+)", text, re.M)})
    return {"rc": p.returncode, "counts": counts, "summary": (m.group(0) if m else ""),
            "red": red, "tail": text.splitlines()[-3:]}


def doc_predicate(text: str) -> bool:
    """与测试里同一条谓词（旧口径不在 && 实测措辞在）。"""
    return OLD_CLAIM not in text and NEW_CLAIM in text


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    if not NEW_TEST.exists():
        REFUSE.append(f"新锁文件不在盘上：{NEW_TEST.name}")
        return finish(started)
    work_sha, snap_sha = sha(WORK_CHECKER), sha(SNAP / "cypyc" / "analyzer" / "type_checker.py")
    check("两条道的产品码必须是两棵树（身份探针）", work_sha != snap_sha, True,
          f"work={work_sha} snap={snap_sha}")
    check("新锁文件在仓库 tests/ 里（不是只活在 .fist-loop）",
          NEW_TEST.parent.name, "tests", "永久锁的位置")

    lane_a = run(ROOT, "tests/test_loop_20260927_polish_r4.py")
    check("A 工作区道：新锁全绿且恰 20 条",
          [lane_a["counts"]["passed"], lane_a["counts"]["failed"]], [20, 0],
          lane_a["summary"])

    dst = SNAP / "tests" / NEW_TEST.name
    shutil.copyfile(NEW_TEST, dst)
    try:
        lane_b = run(SNAP, f"tests/{NEW_TEST.name}")
    finally:
        dst.unlink(missing_ok=True)
    check("B 修前道：必须出现红（否则新锁不承重）", lane_b["counts"]["failed"] >= 1, True,
          json.dumps(lane_b["counts"]))
    probe_red = [x for x in lane_b["red"] if x.startswith("test_cli_check_only_face")]
    check("B 道的红要落在 CLI 探针上（逐条点名）", len(probe_red) >= 1, True,
          json.dumps(sorted(probe_red)[:8]))
    check("B 道的红里必须有文档口径锁（旧文档在那棵树里）",
          "test_usage_doc_does_not_claim_pyd_reuse" in lane_b["red"], True,
          json.dumps(sorted(lane_b["red"])[:8]))
    before_ok = doc_predicate(USAGE_BEFORE.read_text(encoding="utf-8")) \
        if USAGE_BEFORE.exists() else None
    after_ok = doc_predicate(USAGE.read_text(encoding="utf-8"))
    if before_ok is None:
        REFUSE.append("改前正文副本缺失 ⇒ 文档锁的合成违例道没跑")
    else:
        check("C 合成违例道：改前正文必须被谓词判假（锁能红）", before_ok, False,
              "归档 USAGE.md.before_polish")
    check("C 正例道：现文必须被谓词判真（不误抓）", after_ok, True, "docs/USAGE.md 现文")

    collect = subprocess.run([sys.executable, "-X", "utf8", "-m", "pytest", "tests/",
                              "--collect-only", "-q", "-p", "no:cacheprovider",
                              "--no-header", "-o", "addopts="],
                             cwd=str(ROOT), capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=900)
    ctext = (collect.stdout or "") + (collect.stderr or "")
    ids = [ln for ln in ctext.splitlines() if "::" in ln]
    floor = json.loads((HERE / "verify_r4_baselines.json").read_text(encoding="utf-8"))
    check("收集数只升不降（新锁确实进了仓库收集面）",
          len(ids) >= floor["floors"]["collect"] + 20, True,
          f"现收集 {len(ids)} / 上一环 {floor['floors']['collect']} + 新锁 20")
    new_only = sorted({ln.split("::")[0] for ln in ids if "polish_r4" in ln})
    check("新文件被收集到的 node 恰为 20", len([x for x in ids if "polish_r4" in x]), 20,
          json.dumps(new_only))
    return finish(started, work_sha, snap_sha, lane_a, lane_b, before_ok, after_ok,
                  len(ids), USAGE_BEFORE.exists(), floor["floors"]["collect"])


def finish(started, work_sha="", snap_sha="", lane_a=None, lane_b=None, before_ok=None,
           after_ok=None, collected=0, before_copy=False, prev_floor=0) -> int:
    doc = {"started": started, "new_test_file": NEW_TEST.relative_to(ROOT).as_posix(),
           "identity": {"work_type_checker_sha": work_sha, "snap_type_checker_sha": snap_sha,
                        "snap_tree": SNAP.relative_to(ROOT).as_posix()},
           "lane_work": lane_a, "lane_prefix_code": lane_b,
           "doc_predicate": {"before_text_fails": (None if before_ok is None
                                                   else not before_ok),
                             "current_text_passes": after_ok,
                             "before_copy_on_disk": before_copy},
           "collect_after_locks": collected, "previous_round_collect_floor": prev_floor,
           "self_checks": CHECKS, "refuse": sorted(set(REFUSE)),
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": doc["refuse"],
                      "lane_a": (lane_a or {}).get("counts"),
                      "lane_b": (lane_b or {}).get("counts"),
                      "lane_b_red": (lane_b or {}).get("red"),
                      "collected": collected,
                      "identity": doc["identity"]}, ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
