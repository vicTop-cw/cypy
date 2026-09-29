"""R3-推进 法 2/4：新锁的「回退必红」证明 + 语料零新增红（两态对表）。

底树 = 盘上内容快照（tracked + untracked，禁 commit 时 HEAD 不含本轮改动）。
每只 mutation 只动一处，期望：**该组点名的锁变红、其余锁仍绿**；另有「只改注释」对照组必须全绿。
语料扫描在**同一棵快照树的两种状态**下各跑一次（摘掉元数判定 / 复原），逐档对表；
对表口径是"新增的错误只能是 arity 行"，且真实语料里一条新增都没有。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SNAP = HERE / "tmp_advance" / f"snap_{os.getpid()}"
LOGDIR = HERE / "advance_r3_logs"
LOCK_FILE = "tests/test_loop_20260927_advance_r3.py"
PRODUCT_FILE = "cypyc/analyzer/type_checker.py"
PY = sys.executable
KEEP_ROOTS = {"cypyc", "cypy_hook", "cypy_bridge", "tests", "docs", "scripts", "examples"}
SCAN_DIRS = ["examples", "tests", "docs", "scripts", "cypyc", "cypy_hook", "cypy_bridge"]
IDENTITY_MODULES = ["cypy_hook.hook", "cypyc.analyzer.type_checker", "cypyc.cli", "cypyc.parser.parser"]
REFUSE: list = []

G1_NEEDLE = "                        self._check_callable_arity(node, args)\n"
G1_REPL = ""
G2_NEEDLE = ('        declared = self._callable_declared_params(args)\n'
             '        if declared is None:\n            return\n')
# 把"解不出声明表"当成零参 ⇒ 裸 Callable / Callable[int] 这类未声明形状会被误判。
# （早先我把锚点放在 `_callable_declared_params` 的兜底 return 上，实测那一组什么都没打红：
#  那两个形状在 `len(args) < 2` 就返回了，压根走不到我改的那一行。）
G2_REPL = "        declared = self._callable_declared_params(args) or []\n"
G3_NEEDLE = ("        positional = []\n        for a in node.args:\n"
             "            if isinstance(a, tuple) and len(a) == 2 and isinstance(a[0], str):\n"
             "                return\n            positional.append(a)\n")
G3_REPL = ("        positional = [a for a in node.args\n"
            "                    if not (isinstance(a, tuple) and len(a) == 2)]\n")
C1_NEEDLE = ('        declared = self._callable_declared_params(args)\n'
             '        if declared is None:\n')
C1_REPL = ('        declared = self._callable_declared_params(args)\n'
           '        # 只加一行注释：证明锁不抓文档噪声\n'
           '        if declared is None:\n')
# G4：把"最后一项是返回类型"忘掉 ⇒ 判定过严，正确调用也被flag。这是成对锁另一边
# （"正确必不报"）的承重证明：没有这一组，那两条 clean 锁就只是"当前恰好没人碰它们"。
G4_NEEDLE = ('        declared = self._callable_declared_params(args)\n'
             '        if declared is None:\n            return\n')
G4_REPL = ('        declared = list(args)\n'
           '        if declared is None:\n            return\n')

VIOLATION_LOCKS = ["test_advance_callable_arity_violation_reported",
                   "test_advance_callable_arity_zero_args_passed_reported",
                   "test_advance_alias_form_is_also_checked",
                   "test_advance_arity_and_return_errors_coexist"]
GREEN_LOCKS = ["test_advance_unrecognized_callable_shape_is_not_judged",
               "test_advance_correct_single_arg_call_stays_clean",
               "test_advance_two_arg_and_zero_arg_forms_match",
               "test_advance_keyword_arg_call_is_skipped",
               "test_advance_codegen_object_fallback_unchanged"]

# 实测后这里是**空表**：G1–G4 四组的 must_red 并集已经覆盖 9 条锁（G4 是"判定过严"的宽爆破组，
# 连产物回退那条都被打红）。留这个判据是为了防"以后加锁忘了配 mutation"——名单一多就当场拒。
NAMED_UNCOVERED: list = []
W_OK = "examples/_advance_r3_witness_ok.cypy"
W_BAD = "examples/_advance_r3_witness_bad.cypy"

GROUPS = [
    {"name": "G1 摘掉元数判定的调用点", "needle": G1_NEEDLE, "repl": G1_REPL, "expect": 1,
     "must_red": VIOLATION_LOCKS,
     "must_stay_green": ["test_advance_unrecognized_callable_shape_is_not_judged",
                         "test_advance_correct_single_arg_call_stays_clean",
                         "test_advance_keyword_arg_call_is_skipped",
                         "test_advance_codegen_object_fallback_unchanged"],
     "scan": True,
     "note": "本环主张就是这一行调用；摘掉后 4 条违例锁必须红"},
    {"name": "G2 把不认识的形状当零参判定", "needle": G2_NEEDLE, "repl": G2_REPL, "expect": 1,
     "must_red": ["test_advance_unrecognized_callable_shape_is_not_judged"],
     "must_stay_green": VIOLATION_LOCKS + GREEN_LOCKS[1:],
     "note": "『宁可不判也不误判』这条主张的承重证明：兜底当成零参 ⇒ 只有那一条红，其余 8 条不该被牵连"},
    {"name": "G3 关键字实参不再跳过", "needle": G3_NEEDLE, "repl": G3_REPL, "expect": 1,
     "must_red": ["test_advance_keyword_arg_call_is_skipped"],
     "must_stay_green": VIOLATION_LOCKS + ["test_advance_unrecognized_callable_shape_is_not_judged"],
     "note": "还原成上一版那个只按 len==2 剔的过滤器 ⇒ 会把 ('x', 1) 当 0 个实参而误报"},
    {"name": "G4 判定过严（忘掉最后一项是返回类型）", "needle": G4_NEEDLE, "repl": G4_REPL,
     "expect": 1,
     "must_red": VIOLATION_LOCKS + GREEN_LOCKS, "must_stay_green": [],
     "note": "成对锁另一边的承重证明：把声明表读宽一格 ⇒ 正确调用、关键字跳过、产物回退三条也必红"
             "（实测这一组是宽爆破：9 条全红，说明 9 条都在盯着这条判定链，没有一条是摆设）"},
    {"name": "C1 对照：只改注释", "needle": C1_NEEDLE, "repl": C1_REPL, "expect": 1,
     "must_red": [], "must_green_all": True, "note": "只加一行注释 ⇒ 9 条全绿，否则锁钉在字面噪声上"},
]


def now_s() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sh(cmd, cwd=None, timeout=1800):
    p = subprocess.run(cmd, cwd=str(cwd or ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_snapshot() -> dict:
    info = {"dir": str(SNAP), "copied": 0, "untracked_copied": 0, "markers_ok": True,
            "missing_on_disk": [], "at_utc": now_s()}
    if SNAP.exists():
        shutil.rmtree(SNAP)
    SNAP.mkdir(parents=True, exist_ok=True)
    listing = subprocess.run(["git", "ls-files", "-z"], cwd=str(ROOT), capture_output=True, timeout=300)
    tracked = [t.decode("utf-8", "replace") for t in listing.stdout.split(b"\0") if t]
    for rel in tracked:
        if rel.split("/")[0] not in KEEP_ROOTS:
            continue
        src = ROOT / rel
        if not src.is_file():
            info["missing_on_disk"].append(rel)
            continue
        dst = SNAP / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src, dst)
            info["copied"] += 1
        except OSError as exc:
            info.setdefault("copy_errors", []).append({"file": rel, "reason": str(exc)[:80]})
    others = subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "-z"],
                            cwd=str(ROOT), capture_output=True, timeout=300)
    for rel in [x.decode("utf-8", "replace") for x in others.stdout.split(b"\0") if x]:
        if rel.split("/")[0] not in KEEP_ROOTS or "__pycache__" in set(Path(rel).parts):
            continue
        src = ROOT / rel
        if not src.is_file():
            continue
        dst = SNAP / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src, dst)
            info["untracked_copied"] += 1
        except OSError:
            pass
    markers = [PRODUCT_FILE, LOCK_FILE, "cypy_hook/hook.py", "cypyc/cli.py"]
    gone = [m for m in markers if not (SNAP / m).exists()]
    if gone:
        info["markers_ok"] = False
        REFUSE.append(f"快照树缺标记文件：{gone}")
    return info


def identity_probe() -> list:
    """证明跑的是快照树里的码，不是工作区/已安装副本（身份探针必须是能红的）。"""
    code = ("import sys, json;sys.path.insert(0,%r);"
            "import cypy_hook.hook as h, cypyc.analyzer.type_checker as tc;"
            "import cypyc.cli as cli, cypyc.parser.parser as pp;"
            "print(json.dumps([h.__file__, tc.__file__, cli.__file__, pp.__file__]))"
            % str(SNAP))
    rc, out = sh([PY, "-X", "utf8", "-c", code], SNAP, 300)
    if rc != 0:
        REFUSE.append(f"身份探针没跑成（快照树不可导入）：rc={rc} {out[-200:]}")
        return []
    files = json.loads(out.strip().splitlines()[-1])
    snap_pos = str(SNAP).replace("\\", "/")
    outside = [f for f in files if not Path(os.path.abspath(f)).as_posix().startswith(snap_pos)]
    if outside:
        REFUSE.append(f"身份探针发现模块取自快照树之外：{outside}")
        return []
    return [f for f in files]


def run_locks(cwd=None):
    rc, out = sh([PY, "-X", "utf8", "-m", "pytest", LOCK_FILE, "-q", "-p", "no:cacheprovider",
                  "--no-header", "-o", "addopts=", "-rA", "--tb=line"], cwd or SNAP, 1200)
    passed = int(re.search(r"(\d+) passed", out).group(1)) if re.search(r"(\d+) passed", out) else 0
    reds = sorted({ln.split("::")[-1].split(" ")[0]
                   for ln in out.splitlines() if ln.startswith(("FAILED", "ERROR"))})
    return {"rc": rc, "passed": passed, "reds": reds, "total_seen": passed + len(reds), "out": out}


def write_witnesses() -> dict:
    """往快照树的 examples/ 里放两份"见证夹具"，给语料扫描器一个能看见 arity 行的靶子。

    敏感性对照第一次跑出来是 0 变化——真实语料里只有 `type Callback = Callable[[int], str]` 两行声明、
    **没有任何经由它的调用点**，所以"真实语料零新增红"这句话本身没有观察力。夹具只进快照树（随树删除），
    工作区的 examples 一个字节都不动。
    """
    ok = ("type Callback = Callable[[int], str]\n"
          "def apply_it(cb: Callback, n: int) -> str:\n    return cb(n)\n")
    bad = ("type TwoArg = Callable[[int, str], bool]\n"
           "def run_it(f: TwoArg, a: int) -> bool:\n    return f(a)\n")
    made = {}
    for name, text in (("_advance_r3_witness_ok.cypy", ok), ("_advance_r3_witness_bad.cypy", bad)):
        p = SNAP / "examples" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
        made[name] = {"sha16": sha(p)[:16], "path": str(p.relative_to(ROOT)).replace("\\", "/")}
    return made


def apply_mutation(needle, repl, expect):
    text = (SNAP / PRODUCT_FILE).read_text(encoding="utf-8", newline="")
    got_lf, got_crlf = text.count(needle), text.count(needle.replace("\n", "\r\n"))
    if not (got_lf == expect and got_crlf == 0) and not (got_crlf == expect and got_lf == 0):
        REFUSE.append(f"mutation 锚点计数不符：lf={got_lf} crlf={got_crlf} 期望 {expect}")
        return None
    body = text.replace(needle.replace("\n", "\r\n"), repl.replace("\n", "\r\n"), expect) \
        if got_crlf else text.replace(needle, repl, expect)
    if body == text:
        REFUSE.append("mutation 后文本没变 ⇒ 这组证明不成立")
        return None
    (SNAP / PRODUCT_FILE).write_text(body, encoding="utf-8", newline="")
    return text


def corpus_scan(tag):
    rc, out = sh([PY, "-X", "utf8", str(HERE / "advance_r3_corpus_scan.py"), str(SNAP), tag],
                 SNAP, 1800)
    if rc != 0:
        REFUSE.append(f"语料扫描失败（{tag}）：rc={rc} {out[-200:]}")
        return {}
    doc = json.loads(out.strip().splitlines()[-1])
    return {r["file"]: r["errors"] for r in doc["rows"]}, doc["files"]


def main() -> int:
    LOGDIR.mkdir(exist_ok=True)
    workspace_before = {rel: sha(ROOT / rel) for rel in (PRODUCT_FILE, LOCK_FILE)}
    doc = {"refuse": [], "groups": {}, "started_at_utc": now_s()}
    info = build_snapshot()
    doc["snapshot"] = info
    if REFUSE:
        doc["refuse"] = REFUSE
        (HERE / "advance_r3_lockproof.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        print(json.dumps({"refuse": REFUSE, "snapshot": info}, ensure_ascii=False))
        return 1
    doc["identity"] = identity_probe()
    doc["witnesses"] = write_witnesses()
    premise = run_locks()
    (LOGDIR / "premise.log").write_text(premise["out"], encoding="utf-8", newline="\n")
    doc["premise"] = {k: premise[k] for k in ("rc", "passed", "reds", "total_seen")}
    if premise["total_seen"] != 9 or premise["reds"]:
        REFUSE.append(f"前提不成立：快照里 {LOCK_FILE} 跑到 {premise['total_seen']} 条、红 {premise['reds']}")
    scans = {}
    for grp in GROUPS:
        entry = {"expect": grp["expect"], "applied": False, "reds": [], "expected": grp["must_red"],
                 "ok": False, "note": grp["note"], "restored": False, "compiled": True,
                 "must_stay_green": grp.get("must_stay_green", [])}
        before = {rel: sha(SNAP / rel) for rel in (PRODUCT_FILE,)}
        original = apply_mutation(grp["needle"], grp["repl"], grp["expect"])
        if original is None:
            doc["groups"][grp["name"]] = entry
            continue
        entry["applied"] = True
        rc_c, out_c = sh([PY, "-X", "utf8", "-m", "py_compile", PRODUCT_FILE], SNAP, 300)
        entry["compiled"] = rc_c == 0
        if rc_c:
            REFUSE.append(f"{grp['name']} mutation 后编译不过：{out_c[-200:]}")
        res = run_locks()
        (LOGDIR / f"{grp['name'][:6]}.log").write_text(res["out"], encoding="utf-8", newline="\n")
        entry["reds"] = res["reds"]
        entry["total_seen"] = res["total_seen"]
        missing = [x for x in grp["must_red"] if x not in res["reds"]]
        if missing:
            REFUSE.append(f"{grp['name']}：期望变红的锁没红 {missing}")
        unexpected = [x for x in res["reds"] if x not in grp["must_red"]
                      and x not in grp.get("allowed_reds", [])]
        if unexpected:
            REFUSE.append(f"{grp['name']}：出现计划外的红 {unexpected}")
        stayed = [x for x in entry["must_stay_green"] if x not in res["reds"]]
        entry["must_stay_green_ok"] = len(stayed) == len(entry["must_stay_green"])
        if not entry["must_stay_green_ok"]:
            REFUSE.append(f"{grp['name']}：不该受牵连的锁被连带打红 "
                          f"{[x for x in entry['must_stay_green'] if x not in stayed]}")
        if grp["must_red"] == [] and res["reds"]:
            REFUSE.append(f"{grp['name']}：对照组出现红 ⇒ 锁钉在字面噪声上")
        if grp.get("scan"):
            scans["with_mutation"] = corpus_scan("mutation")
        restore_ok = True
        (SNAP / PRODUCT_FILE).write_text(original, encoding="utf-8", newline="")
        entry["restored"] = sha(SNAP / PRODUCT_FILE) == before[PRODUCT_FILE]
        if not entry["restored"]:
            restore_ok = False
            REFUSE.append(f"{grp['name']}：mutation 后文件没逐字复原（sha 不等）")
        entry["ok"] = (entry["applied"] and entry["compiled"] and entry["restored"]
                       and not missing and not unexpected and entry["must_stay_green_ok"]
                       and restore_ok)
        doc["groups"][grp["name"]] = entry
    # 复原后再扫一遍语料，与 mutation 态对表
    scans["restored"] = corpus_scan("restored")
    doc["corpus"] = {}
    if scans.get("with_mutation") and scans.get("restored"):
        m_rows, m_files = scans["with_mutation"]
        r_rows, r_files = scans["restored"]
        if m_files != r_files:
            REFUSE.append(f"两态扫描的文件数不等（{m_files} vs {r_files}）⇒ 口径不稳，不作数")
        changed = {}
        for f in sorted(set(m_rows) | set(r_rows)):
            if f in (W_OK, W_BAD):
                continue        # 夹具单独走下面的观察力对照，不混进"真实语料"这一栏
            a, b = m_rows.get(f, []), r_rows.get(f, [])
            if a != b:
                changed[f] = {"mutation_state": a, "restored_state": b}
        wit = {"ok_in_scan": W_OK in r_rows, "bad_in_scan": W_BAD in r_rows,
               "ok_restored": r_rows.get(W_OK, []), "bad_restored": r_rows.get(W_BAD, []),
               "ok_mutation": m_rows.get(W_OK, []), "bad_mutation": m_rows.get(W_BAD, [])}
        if not (wit["ok_in_scan"] and wit["bad_in_scan"]):
            REFUSE.append(f"见证夹具没被扫描器扫到（ok={wit['ok_in_scan']} bad={wit['bad_in_scan']}）"
                          "⇒ 观察力对照不成立，'零新增红'这句话没有靶子")
        if not any("arity" in e for e in wit["bad_restored"]):
            REFUSE.append(f"违例夹具在复原态没报 arity 错：{wit['bad_restored']} ⇒ 判定没作用到语料路径")
        if any("arity" in e for e in wit["ok_mutation"]) or any("arity" in e for e in wit["ok_restored"]):
            REFUSE.append("合规夹具里出现了 arity 报错 ⇒ 判定过严，夹具与真实语料都不安全")
        if any("arity" in e for e in wit["bad_mutation"]):
            REFUSE.append("摘掉判定的 mutation 态里违例夹具仍报 arity ⇒ 两态没分开，对表不作数")
        new_errors = {f: sorted(set(v["restored_state"]) - set(v["mutation_state"]))
                      for f, v in changed.items()}
        new_flat = [e for v in new_errors.values() for e in v]
        doc["corpus"] = {"files_scanned": r_files, "samples_scanned": r_files,
                         "files_changed": len(changed),
                         "witness": wit,
                         "changed": {k: v for k, v in list(changed.items())[:20]},
                         "new_errors_outside_locks": [e for e in new_flat if "arity" not in e],
                         "arity_errors_after": sum(1 for e in new_flat if "arity" in e),
                         "changes_only_through_the_check": all("arity" in e for e in new_flat)}
        if doc["corpus"]["new_errors_outside_locks"]:
            REFUSE.append(f"语料里出现了非 arity 的新错误 ⇒ 本环改动漏到了别处："
                          f"{doc['corpus']['new_errors_outside_locks'][:6]}")
        if [f for f in changed if f.startswith(("examples/", "tests/", "docs/", "scripts/"))
            and any("arity" in e for e in changed[f]["restored_state"])
            and not any("arity" in e for e in changed[f]["mutation_state"])]:
            REFUSE.append("真实语料里出现了新增 arity 报错 ⇒ 要么判定过严要么语料本身有违例，须逐档裁决")
        if m_files < 40:
            REFUSE.append(f"语料只扫到 {m_files} 个 .cypy（下限 40）⇒ 扫描口径可疑")
    # 敏感性对照：把判定改宽（G4 那一档）再扫同一棵树 ⇒ 扫描器必须看得见 arity 行。
    # 没有这一条，"两态差集为空"就可能是"扫描器压根不产 arity 行"造成的恒绿格。
    g4 = next(g for g in GROUPS if g["name"].startswith("G4"))
    p_sha = sha(SNAP / PRODUCT_FILE)
    orig4 = apply_mutation(g4["needle"], g4["repl"], g4["expect"])
    if orig4 is not None:
        scans["over_strict"] = corpus_scan("over_strict")
        (SNAP / PRODUCT_FILE).write_text(orig4, encoding="utf-8", newline="")
        if sha(SNAP / PRODUCT_FILE) != p_sha:
            REFUSE.append("敏感性对照跑完没把快照复原（sha 不等）")
    if scans.get("over_strict") and scans.get("restored"):
        o_rows, o_files = scans["over_strict"]
        r_rows, r_files = scans["restored"]
        if o_files != r_files:
            REFUSE.append(f"敏感性对照扫到 {o_files} 档，主扫描 {r_files} 档 ⇒ 口径不稳")
        extra = sorted({e for f in o_rows for e in set(o_rows[f]) - set(r_rows.get(f, []))})
        doc["corpus"]["sensitivity_probe"] = {
            "files_scanned": o_files, "new_error_kinds": len(extra),
            "witness_ok_gained": sorted(set(o_rows.get(W_OK, [])) - set(r_rows.get(W_OK, []))),
            "all_through_the_check": all("arity" in e for e in extra), "sample": extra[:3]}
        if not extra:
            REFUSE.append("改成过严判定后语料仍然零变化 ⇒ 扫描器看不见 arity 行，'零新增红'是恒绿格")
        elif not all("arity" in e for e in extra):
            REFUSE.append(f"敏感性对照里冒出非 arity 的新错误：{[e for e in extra if 'arity' not in e][:3]}")
    final = run_locks(ROOT)
    doc["after_restore"] = {k: final[k] for k in ("rc", "passed", "reds", "total_seen")}
    if final["reds"] or final["total_seen"] != 9:
        REFUSE.append(f"复原后在工作区跑锁应当全绿却异常：{doc['after_restore']}")
    doc["workspace_untouched"] = all(sha(ROOT / r) == v for r, v in workspace_before.items())
    if not doc["workspace_untouched"]:
        REFUSE.append("工作区被驱动改动（快照隔离失效）")
    left = []
    try:
        shutil.rmtree(SNAP)
        info["removed"] = True
    except OSError as exc:
        info["removed"] = False
        REFUSE.append(f"快照临时树没删掉：{exc}")
    left = sorted(p.name for p in (HERE / "tmp_advance").glob("snap_*")) if (HERE / "tmp_advance").exists() else []
    doc["snap_left"] = left
    if left:
        REFUSE.append(f"本环快照树残留：{left}")
    doc["groups_total"] = len(GROUPS)
    doc["groups_ok"] = sum(1 for v in doc["groups"].values() if v["ok"])
    all_locks = sorted(set(re.findall(r"^def (test_\w+)",
                                      (ROOT / LOCK_FILE).read_text(encoding="utf-8", newline=""),
                                      flags=re.M)))
    covered = sorted({x for v in doc["groups"].values() for x in v["expected"]})
    uncovered = sorted(set(all_locks) - set(covered))
    doc["lock_names_total"], doc["revert_covered"] = len(all_locks), covered
    doc["revert_uncovered_locks"] = uncovered
    if uncovered != NAMED_UNCOVERED:
        REFUSE.append(f"未被任何 mutation 打红过的锁必须**恰好等于**点名的例外，实得 {uncovered}；"
                      f"名单外有漏 ⇒ '每条锁都承重'这句话不作数")
    doc["refuse"] = REFUSE
    doc["finished_at_utc"] = now_s()
    (HERE / "advance_r3_lockproof.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    locks_payload = {"refuse": REFUSE, "new_locks": 9, "lock_file": LOCK_FILE,
                     "premise": doc["premise"], "groups_total": doc["groups_total"],
                     "groups_ok": doc["groups_ok"],
                     "lock_names_total": doc["lock_names_total"],
                     "revert_covered": len(doc["revert_covered"]),
                     "revert_uncovered_locks": doc["revert_uncovered_locks"],
                     "revert_uncovered_reason": "空表=9 条锁全被某组 mutation 打红过；非空时逐条点名并给替代承重件",
                     "each_new_lock_red_when_reverted": sorted({x for v in doc["groups"].values()
                                                               for x in v["expected"]}),
                     "control_group_green": any(v["expected"] == [] and v["ok"]
                                                for v in doc["groups"].values()),
                     "narrowness_asserts": len([v for v in doc["groups"].values()
                                                if "must_stay_green_ok" in v]),
                     "must_stay_green_all_ok": all(v.get("must_stay_green_ok", True)
                                                   for v in doc["groups"].values()),
                     "identity": doc["identity"], "snap_left": left,
                     "after_restore": doc["after_restore"], "workspace_untouched":
                     doc["workspace_untouched"], "at_utc": now_s()}
    (HERE / "advance_r3_locks.json").write_text(
        json.dumps(locks_payload, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    corpus_payload = dict(doc.get("corpus") or {})
    corpus_payload["refuse"] = REFUSE
    corpus_payload["scan_dirs"] = SCAN_DIRS
    corpus_payload["scan_script"] = ".fist-loop-20260927/advance_r3_corpus_scan.py"
    corpus_payload["at_utc"] = now_s()
    (HERE / "advance_r3_corpus.json").write_text(
        json.dumps(corpus_payload, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": REFUSE, "groups_ok": doc["groups_ok"],
                      "groups_total": doc["groups_total"], "premise": doc["premise"],
                      "corpus": corpus_payload, "identity": doc["identity"],
                      "after_restore": doc["after_restore"], "snap_left": left},
                     ensure_ascii=False, indent=1))
    return 1 if REFUSE else 0


if __name__ == "__main__":
    sys.exit(main())
