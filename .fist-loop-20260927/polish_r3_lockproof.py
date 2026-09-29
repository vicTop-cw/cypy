"""R3-打磨 法 1/2：新锁的「回退必红」证明（含只改注释的正向对照）。

底树 = 盘上内容快照（`git ls-files` 全集 + 本轮新增测试），原因见 R3-验证 §六 第 1 条。
每组 mutation 只动一处，期望：**该组指定的锁变红**，其余锁不受牵连；
另有「只改注释」的对照组，期望**全绿**（证明锁钉的是语义不是字面噪声）。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SNAP = HERE / "tmp_polish" / f"snap_{os.getpid()}"
LOGDIR = HERE / "r3polish_logs"
LOCK_FILES = ["tests/test_loop_20260927_polish_r3.py", "tests/test_loop_20260927_fix_r3.py"]
PY = sys.executable
REFUSE: list = []


def now_s() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sh(cmd, cwd, timeout=900):
    p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", newline="")


def build_snapshot() -> dict:
    info = {"dir": str(SNAP), "copied": 0, "missing_on_disk": [], "markers_ok": True, "at_utc": now_s()}
    if SNAP.exists():
        shutil.rmtree(SNAP)
    SNAP.mkdir(parents=True, exist_ok=True)
    listing = subprocess.run(["git", "ls-files", "-z"], cwd=str(ROOT), capture_output=True, timeout=300)
    tracked = [t.decode("utf-8", "replace") for t in listing.stdout.split(b"\0") if t]
    for rel in tracked:
        src = ROOT / rel
        if not src.is_file():
            info["missing_on_disk"].append(rel)
            continue
        dst = SNAP / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src, dst)
        except OSError as exc:
            info.setdefault("copy_errors", []).append(
                {"file": rel, "reason": f"{type(exc).__name__}: {exc}"[:90]})
            continue
        info["copied"] += 1
    # 本轮新增的锁文件还是 untracked（禁 commit）⇒ 只按 ls-files 复制会把它们整个漏掉，
    # 标记自证因此拒跑。补一次 untracked（排除 gitignore）复制，快照才算等于盘面。
    others = subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "-z"],
                            cwd=str(ROOT), capture_output=True, timeout=300)
    untracked_copied, untracked_skipped = 0, []
    keep_roots = {"cypyc", "cypy_hook", "cypy_bridge", "tests", "docs", "scripts", "examples"}
    for rel in [x.decode("utf-8", "replace") for x in others.stdout.split(b"\0") if x]:
        if rel.split("/")[0] not in keep_roots:   # dist/、build/ 这类产物不进快照（也常因被占用而拒读）
            continue
        src = ROOT / rel
        if not src.is_file() or "__pycache__" in set(Path(rel).parts):
            continue
        dst = SNAP / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src, dst)
        except OSError as exc:
            untracked_skipped.append({"file": rel, "reason": f"{type(exc).__name__}: {exc}"[:90]})
            continue
        untracked_copied += 1
    info["untracked_copied"] = untracked_copied
    info["untracked_skipped"] = untracked_skipped
    markers = ["cypyc/cli.py", "cypy_hook/hook.py", "cypy_bridge/__init__.py", "docs/USAGE.md"] + LOCK_FILES
    gone = [m for m in markers if not (SNAP / m).exists()]
    if gone:
        info["markers_ok"] = False
        REFUSE.append(f"快照树缺标记文件：{gone}")
    return info


def run_locks(cwd=SNAP):
    rc, out = sh([PY, "-X", "utf8", "-m", "pytest", *LOCK_FILES, "-q", "-p", "no:cacheprovider",
                  "--no-header", "-o", "addopts=", "--tb=line"], cwd, 1200)
    passed = int(out.split(" passed")[0].rsplit()[-1]) if " passed" in out else 0
    reds = sorted({ln.split("::")[-1].split(" ")[0]
                   for ln in out.splitlines() if ln.startswith(("FAILED", "ERROR"))})
    return {"rc": rc, "passed": passed, "reds": reds,
            "total_seen": passed + len(reds), "out": out}


def apply_mutation(patches):
    """patches: [(rel, needle, repl, expect_count)]；返回 {rel: 原文} 或 None（锚点不符）。"""
    originals = {}
    for rel, _n, _r, _e in patches:
        originals.setdefault(rel, read(SNAP / rel))
    work = dict(originals)
    for rel, needle, repl, expect in patches:
        for nd, rp in ((needle, repl), (needle.replace("\n", "\r\n"), repl.replace("\n", "\r\n"))):
            if work[rel].count(nd) == expect and expect > 0:
                work[rel] = work[rel].replace(nd, rp, expect)
                break
        else:
            REFUSE.append(f"锚点不符（{rel}）：lf={work[rel].count(needle)} "
                          f"crlf={work[rel].count(needle.replace(chr(10), chr(13) + chr(10)))} 期望 {expect}")
            return None
    for rel in originals:
        (SNAP / rel).write_text(work[rel], encoding="utf-8", newline="")
    return originals


def restore(originals):
    for rel, text in originals.items():
        (SNAP / rel).write_text(text, encoding="utf-8", newline="")


# 每组：name / patches / 期望变红的锁（子串即可）/ 是否要求其余锁全绿 / 说明
GROUPS = [
    {"name": "G1 夹具退回非冻结形",
     "patches": [("tests/test_loop_20260927_fix_r3.py",
                  'tree = _parse("struct Box<T>:\\n    value: T\\n")',
                  'tree = _parse("generic struct Box<T>:\\n    value: T\\n")', 1)],
     "must_red": ["test_polish_generic_fixture_in_fix_r3_uses_frozen_form"],
     "note": "锁 1 钉的是『夹具用冻结形』"},
    {"name": "G2 撤回 --emit-code 文档行",
     "patches": [("docs/USAGE.md",
                  "cypyc transpile demo.cypy --emit-code       # 打印生成的代码（Cython 模式下与 --emit-cython 同义）\n",
                  "", 1)],
     "must_red": ["test_polish_transpile_and_build_flags_three_way_sync"],
     "must_stay_green": ["test_polish_every_documented_cypyc_flag_is_real",
                         "test_polish_bridge_generate_setup_writes_parseable_setup"],
     "note": "argparse 有旗标没进文档 ⇒ 完整性方向红；"
             "反方向（文档里的旗标是否都真实）不该被这次 mutation 影响，故钉成 must_stay_green"},
    {"name": "G3 CLI 退回直调私有",
     "patches": [("cypyc/cli.py", "_, errors = hook.analyze_only(text)",
                  "_, errors = hook._parse_and_analyze(text)", 1)],
     "must_red": ["test_polish_cli_no_longer_calls_private_analyzer"],
     "note": "锁 7 钉调用面不再依赖下划线方法"},
    {"name": "G4 摘掉公开 analyze_only 门面",
     "patches": [("cypy_hook/hook.py",
                  "    def analyze_only(self, source: str) -> Tuple[Any, List[str]]:",
                  "    def _analyze_only_removed(self, source: str) -> Tuple[Any, List[str]]:", 1)],
     "must_red": ["test_polish_cypy_hook_exposes_public_analyze_only"],
     "must_stay_green": ["test_polish_cli_no_longer_calls_private_analyzer"],
     "allowed_reds": {
         "test_bug56_check_only_reports_and_generates_nothing":
             "CLI 的 --check-only 走这个门面，摘掉必然 AttributeError ⇒ 同因连带，非跨件污染",
         "test_bug56_check_only_fails_on_broken_source":
             "同上：同一调用面的第二条锁"},
     "note": "门面消失 ⇒ 锁 6 红；两条 BUG-56 check-only 锁同因连带（白名单记原因）；"
             "锁 7 只读 cli.py 文本，本组不动它 ⇒ 必须仍绿（证明 mutation 是窄的）"},
    {"name": "G5 让同名函数重新遮蔽子模块",
     "patches": [("cypy_bridge/__init__.py",
                  "from . import union  # noqa: E402  显式把名字绑定回子模块",
                  "from . import union  # noqa: E402  显式把名字绑定回子模块\nfrom .union import union  # 故意遮蔽（模拟旧 __init__）", 1)],
     "must_red": ["test_polish_union_submodule_reachable_via_importlib"],
     "allowed_reds": {
         "test_bug57_union_docstrings_advertise_only_runnable_shapes":
             "该锁写 `from cypy_bridge import union as union_mod` 后按模块取 doc ⇒ 遮蔽一复发它就红（同因）"},
     "note": "锁 5 钉的是『包级名字仍是模块』；同一条遮蔽也解释了为什么 R3-验证 的 run1 会假红"},
    {"name": "G6 摘掉 bridge 模式的 generate-setup 接线",
     "patches": [("cypyc/cli.py",
                  "            if args.generate_setup:\n"
                  "                return _transpile_generate_setup(args.output, c_path)\n"
                  "\n"
                  "            return 0",
                  "            return 0", 1)],
     "must_red": ["test_polish_bridge_generate_setup_writes_parseable_setup"],
     "note": "锁 3 是新补的调用面缺口"},
    {"name": "G7 摘掉 bridge 对 emit-cython 的明确 decline",
     "patches": [("cypyc/cli.py",
                  "            if args.emit_cython:\n"
                  '                print_info("--emit-cython does not apply in --bridge mode; "\n'
                  '                           "the emitted language is C")\n'
                  "\n",
                  "", 1)],
     "must_red": ["test_polish_bridge_emit_cython_declines_explicitly"],
     "note": "锁 4 要求『明确说不适用』而不是静默"},
    {"name": "C1 对照：只改注释",
     "patches": [("cypyc/cli.py",
                  '    """`--check-only`：只做静态分析，不落任何产物（帮助文本承诺的口径）。"""',
                  '    """`--check-only`：只做静态分析，不落任何产物（帮助文本承诺的口径）。\n'
                  '    这是一行纯粹的注释补充，用来证明锁不抓文档噪声。"""', 1)],
     "must_red": [],
     "must_green_all": True,
     "note": "正向对照：只加注释必须全绿，否则说明锁钉在了字面噪声上"},
]


def cleanup_snapshot(info) -> list:
    """临时树必须自己收掉：留着既占盘，又让下一环分不清是哪次跑剩的。"""
    try:
        shutil.rmtree(SNAP)
        info["removed"] = True
    except OSError as exc:
        info["removed"] = False
        REFUSE.append(f"快照临时树没删掉：{exc}")
    return sorted(p.name for p in (HERE / "tmp_polish").glob("snap_*")) if (HERE / "tmp_polish").exists() else []


def main() -> int:
    LOGDIR.mkdir(exist_ok=True)
    before = {rel: sha(ROOT / rel) for rel in
              ["cypyc/cli.py", "cypy_hook/hook.py", "cypy_bridge/__init__.py", "docs/USAGE.md"] + LOCK_FILES}
    info = build_snapshot()
    doc = {"refuse": [], "snapshot": info, "groups": {}, "started_at_utc": now_s()}
    if REFUSE:
        doc["snap_left"] = cleanup_snapshot(info)
        doc["refuse"] = REFUSE
        (HERE / "polish_r3_lockproof.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        print(json.dumps({"refuse": REFUSE, "snapshot": info}, ensure_ascii=False, indent=1))
        return 1
    premise = run_locks()
    (LOGDIR / "premise.log").write_text(premise["out"], encoding="utf-8", newline="\n")
    doc["premise"] = {k: premise[k] for k in ("rc", "passed", "reds", "total_seen")}
    if premise["total_seen"] != 26 or premise["reds"]:
        REFUSE.append(f"前提不成立：快照里 2 个锁文件跑到 {premise['total_seen']} 条、红 {premise['reds']}")
    for grp in GROUPS:
        entry = {"patches": len(grp["patches"]), "applied": False, "reds": [], "expected": grp["must_red"],
                 "ok": False, "note": grp["note"], "restored": False, "compiled": True}
        originals = apply_mutation(grp["patches"])
        if originals is None:
            doc["groups"][grp["name"]] = entry
            continue
        entry["applied"] = True
        for rel in originals:
            if (SNAP / rel).suffix == ".py":
                rc, out = sh([PY, "-X", "utf8", "-m", "py_compile", rel], SNAP, 300)
                if rc != 0:
                    entry["compiled"] = False
                    REFUSE.append(f"[{grp['name']}] mutation 后 {rel} 无法编译：{out[-140:]}")
        res = run_locks()
        (LOGDIR / f"{grp['name']}.log").write_text(res["out"], encoding="utf-8", newline="\n")
        entry["reds"] = res["reds"]
        entry["total_seen"] = res["total_seen"]
        if not entry["compiled"]:
            restore(originals)
            doc["groups"][grp["name"]] = entry
            continue
        missing = [x for x in grp["must_red"] if x not in res["reds"]]
        if missing:
            REFUSE.append(f"[{grp['name']}] 期望变红的锁没红：{missing}（实际红 {res['reds']}）")
        allowed = grp.get("allowed_reds", {})
        extra = [x for x in res["reds"] if x not in grp["must_red"] and x not in allowed]
        entry["same_cause_reds"] = {x: allowed[x] for x in res["reds"] if x in allowed}
        entry["unexplained_reds"] = [x for x in res["reds"] if x not in grp["must_red"]]
        stayed = [x for x in grp.get("must_stay_green", []) if x not in res["reds"]]
        if len(stayed) != len(grp.get("must_stay_green", [])):
            REFUSE.append(f"[{grp['name']}] 声明『不该动』的锁被动了："
                          f"{[x for x in grp['must_stay_green'] if x not in stayed]}")
        entry["must_stay_green_ok"] = len(stayed) == len(grp.get("must_stay_green", []))
        if grp.get("must_green_all"):
            if res["reds"]:
                REFUSE.append(f"[{grp['name']}] 只改注释的对照出现红：{res['reds']}")
        elif extra:
            REFUSE.append(f"[{grp['name']}] 出现了无法归因的红（跨件连带）：{extra}"
                          f"（同因白名单：{sorted(allowed)}）")
        entry["unexpected_reds"] = extra
        restore(originals)
        entry["restored"] = all(sha(SNAP / rel) == before[rel] for rel in originals)
        if not entry["restored"]:
            REFUSE.append(f"[{grp['name']}] mutation 后未能逐字复原")
        entry["ok"] = (not missing and entry["restored"] and entry["compiled"]
                       and entry["total_seen"] == 26)
        doc["groups"][grp["name"]] = entry
    doc["groups_total"] = len(GROUPS)
    doc["groups_ok"] = sum(1 for v in doc["groups"].values() if v["ok"])
    doc["revert_groups_ok"] = sum(1 for v in doc["groups"].values() if v["ok"] and v["expected"])
    doc["control_groups_ok"] = sum(1 for v in doc["groups"].values() if v["ok"] and v["expected"] == [])
    doc["workspace_untouched"] = all(sha(ROOT / rel) == before[rel] for rel in before)
    if not doc["workspace_untouched"]:
        REFUSE.append("工作区文件被本驱动改动（快照隔离失效）")
    final = run_locks()
    doc["after_restore"] = {k: final[k] for k in ("passed", "reds", "total_seen")}
    if final["reds"] or final["total_seen"] != 26:
        REFUSE.append(f"全部复原后锁不应全绿却异常：{doc['after_restore']}")
    snap_left = cleanup_snapshot(info)
    if snap_left:
        REFUSE.append(f"本环快照临时树没清干净：{snap_left}")
    doc["snap_left"] = snap_left
    doc["workspace_untouched"] = all(sha(ROOT / rel) == before[rel] for rel in before)
    if not doc["workspace_untouched"]:
        REFUSE.append("收尾复算发现工作区被动过（快照隔离失效）")
    doc["finished_at_utc"] = now_s()
    doc["refuse"] = REFUSE
    (HERE / "polish_r3_lockproof.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps({k: doc[k] for k in ("refuse", "premise", "groups_total", "groups_ok",
                                          "revert_groups_ok", "control_groups_ok",
                                          "workspace_untouched", "after_restore",
                                          "started_at_utc", "finished_at_utc")},
                     ensure_ascii=False, indent=1))
    return 1 if REFUSE else 0


if __name__ == "__main__":
    sys.exit(main())
