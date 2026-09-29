"""R3-打磨 法 1/2/4/5/6 的证据件：锁清单、公开 API、文档三向、lint 只减不增、行尾不动刀。

每个格子都带**自证**（解析行数 == 应得数、反方向必须不反应、改动行数上限），
不接受"看起来过了"。底树/快照事实来自 `polish_r3_lockproof.json`，本件不重复跑 mutation。
"""

from __future__ import annotations

import ast
import datetime
import difflib
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = sys.executable
LOCK_FILES = ["tests/test_loop_20260927_polish_r3.py", "tests/test_loop_20260927_fix_r3.py"]
POLISH_LOCKS_TOTAL = 9
FIX_LOCKS_TOTAL = 17
EXPECTED_SEEN = POLISH_LOCKS_TOTAL + FIX_LOCKS_TOTAL
BEFORE_DIR = HERE / "tmp_polish" / "before"
EDITED = {
    "cypyc/cli.py": "CLI 改走公开门面 analyze_only()",
    "cypy_hook/hook.py": "新增公开 analyze_only() 委托",
    "docs/USAGE.md": "补 --emit-code 文档行",
    "tests/test_loop_20260927_fix_r3.py": "BUG-55 夹具换冻结形",
}
NEW_FILE = "tests/test_loop_20260927_polish_r3.py"
MAX_CHANGED_LINES_PER_FILE = 40
RADIUS_DIRS = ["cypyc", "cypy_hook", "cypy_bridge", "tests", "docs", "scripts", "examples"]
LINT_CFG_MAX = 100
REFUSE: list = []


def now_s() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def sh(cmd, timeout=1200):
    p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", newline="")


def test_defs(rel: str) -> list:
    return re.findall(r"^def (test_\w+)", read(rel), flags=re.M)


# ------------------------------------------------------------------ 锁清单
def locks() -> dict:
    declared = {rel: test_defs(rel) for rel in LOCK_FILES}
    flat = [n for rel in LOCK_FILES for n in declared[rel]]
    rc, out = sh([PY, "-X", "utf8", "-m", "pytest", *LOCK_FILES, "-q", "-p", "no:cacheprovider",
                  "--no-header", "-o", "addopts=", "-rA", "--tb=line"])
    passed_names = sorted(set(re.findall(r"^PASSED \S+?::(\w+)", out, flags=re.M)))
    reds = sorted({ln.split("::")[-1].split(" ")[0]
                   for ln in out.splitlines() if ln.startswith(("FAILED", "ERROR"))})
    if len(flat) != EXPECTED_SEEN:
        REFUSE.append(f"两个锁文件里 def test_ 只有 {len(flat)} 条（期望 {EXPECTED_SEEN}）")
    if not passed_names and rc == 0:
        REFUSE.append("`-rA` 里一条 PASSED 都没解析到 ⇒ 解析口径坏了，不能据此说全绿")
    if set(passed_names) - set(flat):
        REFUSE.append(f"跑出来的用例名不在声明清单里（清单口径窄了）：{sorted(set(passed_names) - set(flat))[:6]}")
    if set(flat) - set(passed_names) - set(reds):
        REFUSE.append(f"声明了却没跑绿也没红的用例：{sorted(set(flat) - set(passed_names) - set(reds))[:6]}")
    if reds:
        REFUSE.append(f"锁文件里有红：{reds}")
    proof = json.loads((HERE / "polish_r3_lockproof.json").read_text(encoding="utf-8"))
    reverted_red_locks = sorted({x for g in proof["groups"].values() for x in g["expected"]})
    groups_ok = proof["groups_ok"]
    if groups_ok != proof["groups_total"]:
        REFUSE.append(f"回退矩阵 {groups_ok}/{proof['groups_total']} 组合格")
    control = [g for g in proof["groups"].values() if g["expected"] == []]
    if not control or not all(g["ok"] and not g["reds"] for g in control):
        REFUSE.append("『只改注释』正向对照没全绿 ⇒ 锁钉在了字面噪声上")
    green_pinned = [g for g in proof["groups"].values() if "must_stay_green_ok" in g]
    if any(not g["must_stay_green_ok"] for g in green_pinned):
        REFUSE.append("有 mutation 连带打红了不该受影响的锁 ⇒ 反向对照失守")
    # 9 条新锁里只有 7 条有"回退必红"证明；另外 2 条一件是现状探针、一件是反方向对照 ⇒ 点名不许含糊
    uncovered = sorted(set(declared[LOCK_FILES[0]]) - set(reverted_red_locks))
    expected_uncovered = ["test_polish_every_documented_cypyc_flag_is_real",
                          "test_polish_parser_currently_tolerates_non_frozen_keyword"]
    if uncovered != expected_uncovered:
        REFUSE.append(f"无回退证明的新锁与声明不符：实测 {uncovered} / 声明 {expected_uncovered}")
    if len(flat) != proof["premise"]["passed"]:
        REFUSE.append(f"声明清单 {len(flat)} 条与回退矩阵前提树 {proof['premise']['passed']} 条不等")
    return {
        "declared_total": len(flat),
        "collected_and_passed": len(passed_names),
        "fix_r3_locks": len(declared[LOCK_FILES[1]]),
        "polish_locks": len(declared[LOCK_FILES[0]]),
        "new_locks": len(declared[LOCK_FILES[0]]),
        "reds": reds,
        "frozen_fixture_swapped": 'struct Box<T>' in read(LOCK_FILES[1])
                                  and "generic struct Box<T>" not in read(LOCK_FILES[1]),
        "nonfrozen_control_kept": any("currently_tolerates_non_frozen" in n for n in flat),
        "each_new_lock_red_when_reverted": len(reverted_red_locks),
        "revert_uncovered_locks": uncovered,
        "revert_uncovered_reason": {
            "test_polish_every_documented_cypyc_flag_is_real":
                "反方向对照：G2 把它钉成 must_stay_green，证明 mutation 是窄的",
            "test_polish_parser_currently_tolerates_non_frozen_keyword":
                "现状探针：钉的是 parser 今天的容忍行为，定性留给 R4-寻虫，无对应回退面"},
        "locks_covered_by_revert_matrix": reverted_red_locks,
        "control_group_green": bool(control) and all(not g["reds"] for g in control),
        "narrowness_asserts": len(green_pinned),
        "must_stay_green_all_ok": all(g["must_stay_green_ok"] for g in green_pinned),
        "same_cause_whitelisted": sum(len(g.get("same_cause_reds", {})) for g in proof["groups"].values()),
        "run_line": next((ln for ln in reversed(out.splitlines()) if " passed" in ln), "")[:120],
        "lock_file_sha256": {rel: hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()[:16]
                             for rel in LOCK_FILES},
        "at_utc": now_s(),
    }


# ------------------------------------------------------------------ 公开 API
def api() -> dict:
    hook_src = read("cypy_hook/hook.py")
    cli_src = read("cypyc/cli.py")
    tree = ast.parse(hook_src)
    cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "CypyHook")
    methods = {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}
    cli_calls = [ln.strip() for ln in cli_src.splitlines() if "analyze_only" in ln]
    priv_in_cli = cli_src.count("_parse_and_analyze")
    sys.path.insert(0, str(ROOT))
    from cypy_hook.hook import CypyHook

    hook = CypyHook()
    good = hook.analyze_only("def add(a: int, b: int) -> int:\n    return a + b\n")
    bad = hook.analyze_only("def bad(a: int) -> int:\n    return\n")
    bad_priv = hook._parse_and_analyze("def bad(a: int) -> int:\n    return\n")
    if priv_in_cli:
        REFUSE.append(f"cypyc/cli.py 里仍有 {priv_in_cli} 处私有调用")
    if good[1] != []:
        REFUSE.append(f"干净源码经公开门面报错：{good[1][:2]}")
    if not bad[1]:
        REFUSE.append("坏源码经公开门面没报错 ⇒ 门面是空壳")
    if bad[1] != bad_priv[1]:
        REFUSE.append("公开门面与私有实现结果不一致 ⇒ 不是纯委托")
    if not cli_calls:
        REFUSE.append("CLI 里找不到 analyze_only 调用")
    if "analyze_only" not in methods:
        REFUSE.append("CypyHook 上没有 analyze_only 方法")
    (HERE / "tmp_polish").mkdir(exist_ok=True)
    (HERE / "tmp_polish" / "api_ok.cypy").write_text(
        "def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8", newline="\n")
    api_out = HERE / "tmp_polish" / "api_out"
    if api_out.exists():
        for stale in api_out.glob("*"):
            if stale.is_file():
                stale.unlink()
    rc, out = sh([PY, "-X", "utf8", "-m", "cypyc.cli", "transpile",
                  str(HERE / "tmp_polish" / "api_ok.cypy"), "-o",
                  str(HERE / "tmp_polish" / "api_out"), "--check-only"], 300)
    produced = sorted(p.name for p in (HERE / "tmp_polish" / "api_out").glob("*")) \
        if (HERE / "tmp_polish" / "api_out").exists() else []
    if rc != 0 or "Static analysis passed" not in out or produced:
        REFUSE.append(f"改走公开门面后 CLI --check-only 形态变了：rc={rc} 产物={produced}")
    return {"public_added": "analyze_only" in methods,
            "public_is_not_dunder": not any(m.startswith("_") for m in ["analyze_only"]),
            "cli_no_private_call": priv_in_cli == 0,
            "cli_private_occurrences": priv_in_cli,
            "delegation_equal_on_broken": bad[1] == bad_priv[1],
            "clean_errors": good[1], "broken_error_count": len(bad[1]),
            "cli_check_only_rc": rc, "cli_check_only_artifacts": produced,
            "cli_lines_touched": cli_calls, "at_utc": now_s()}


# ------------------------------------------------------------------ 文档三向
def docs() -> dict:
    usage = read("docs/USAGE.md")
    fn = next(n for n in ast.walk(ast.parse(read("cypyc/cli.py")))
              if isinstance(n, ast.FunctionDef) and n.name == "parse_args")
    cur, table = "GLOBAL", {}
    for call in sorted((x for x in ast.walk(fn) if isinstance(x, ast.Call)), key=lambda x: x.lineno):
        attr = getattr(call.func, "attr", None)
        if attr == "add_parser" and call.args and isinstance(call.args[0], ast.Constant):
            cur = call.args[0].value
            table.setdefault(cur, set())
        elif attr == "add_argument":
            for a in call.args:
                if isinstance(a, ast.Constant) and isinstance(a.value, str) and a.value.startswith("--"):
                    table.setdefault(cur, set()).add(a.value.split()[0])
    FR = re.compile(r"--[a-z][a-z0-9-]*")
    doc_per_sub = {}
    for line in usage.splitlines():
        s = line.strip().lstrip("$ ")
        m = re.match(r"^cypyc\s+(\w+)", s)
        if m:
            doc_per_sub.setdefault(m.group(1), set()).update(FR.findall(s))
    subs = ("transpile", "compile", "build", "run", "watch")
    rows, phantom, undocumented, help_mismatch = {}, [], [], []
    for sub in subs:
        declared = table.get(sub, set())
        documented = doc_per_sub.get(sub, set())
        rc, out = sh([PY, "-X", "utf8", "-m", "cypyc.cli", sub, "--help"], 300)
        advertised = set(FR.findall(out)) - {"--help"}
        rows[sub] = {"argparse": sorted(declared), "documented": sorted(documented),
                     "help": sorted(advertised)}
        phantom += [f"{sub}:{f}" for f in sorted(documented - declared)]
        undocumented += [f"{sub}:{f}" for f in sorted(declared - documented - {"--output", "--verbose"})]
        if advertised != declared:
            help_mismatch += [f"{sub}:{sorted(advertised ^ declared)}"]
    guard_rc, guard_out = sh([PY, "-X", "utf8", "-m", "pytest", LOCK_FILES[0], "-q",
                              "-p", "no:cacheprovider", "--no-header", "-o", "addopts=",
                              "-k", "flags_three_way_sync or documented_cypyc_flag"], 600)
    if phantom:
        REFUSE.append(f"文档写了 argparse 里不存在的旗标：{phantom}")
    if undocumented:
        REFUSE.append(f"argparse 有旗标没进文档（通用旗标 --output/--verbose 除外）：{undocumented}")
    if help_mismatch:
        REFUSE.append(f"--help 与 argparse 不一致：{help_mismatch}")
    if "2 passed" not in guard_out:
        REFUSE.append(f"文档守卫当场没跑绿（rc={guard_rc}）：{guard_out[-160:]}")
    third_party = re.findall(r"^\s*(twine|pip|python|pytest)[^\n]*--([a-z-]+)", usage, flags=re.M)
    return {"flags_three_way": not phantom and not undocumented and not help_mismatch,
            "per_subcommand": rows,
            "phantom": phantom, "undocumented": undocumented, "help_mismatch": help_mismatch,
            "universal_flags_documented_in_table":
                ("-o, --output" in usage) and ("-v, --verbose" in usage),
            "third_party_flag_lines_excluded": len(third_party),
            "guard_rerunnable": guard_rc == 0,
            "guard_run_line": next((ln for ln in reversed(guard_out.splitlines())
                                    if " passed" in ln), "")[:120],
            "at_utc": now_s()}


# ------------------------------------------------------------------ lint 只减不增
def lint() -> dict:
    pre = json.loads((HERE / "r3_polish_pre_baseline.json").read_text(encoding="utf-8"))
    raw_baseline = pre["e501_by_file"]
    # 键形状自证：基线落的是反斜杠路径，当场归一并核对总量，否则 .get(f, 0) 会让每个文件都"凭空上涨"
    baseline = {k.replace("\\", "/"): v for k, v in raw_baseline.items()}
    if sum(baseline.values()) != pre["e501_total"]:
        REFUSE.append(f"基线 e501_by_file 求和 {sum(baseline.values())} != e501_total "
                      f"{pre['e501_total']} ⇒ 基线件自己不自洽")
    if len(baseline) != pre["files_with_e501"]:
        REFUSE.append(f"基线文件数 {len(baseline)} != files_with_e501 {pre['files_with_e501']}")
    rc, out = sh([PY, "-X", "utf8", "-m", "flake8", "--max-line-length", str(LINT_CFG_MAX), *RADIUS_DIRS], 900)
    pat = re.compile(r"^(.+?):(\d+):(\d+): (\w+) ")
    lines = [ln for ln in out.splitlines() if ln.strip()]
    parsed = [(pat.match(ln), ln) for ln in lines]
    unparsed = [ln for m, ln in parsed if m is None]
    if unparsed:
        REFUSE.append(f"flake8 有 {len(unparsed)} 行解析不出来 ⇒ 判据坏：{unparsed[:3]}")
    if len(lines) != sum(1 for _ in parsed):
        REFUSE.append("解析行数 != 输出行数")
    now_counts, hard = {}, {"E9": 0, "W605": 0, "F821": 0}
    for m, _ln in parsed:
        if not m:
            continue
        code, f = m.group(4), m.group(1).replace("\\", "/")
        if code == "E501":
            now_counts[f] = now_counts.get(f, 0) + 1
        elif code in hard:
            hard[code] += 1
    known = set(baseline) & set(now_counts)
    if len(known) < 40:
        REFUSE.append(f"基线与现值的路径口径没对上（交集仅 {len(known)} 个）⇒ 比较不可信，不作数")
    grew = {f: {"before": baseline.get(f, 0), "after": n}
            for f, n in now_counts.items() if n > baseline.get(f, 0)}
    if grew:
        REFUSE.append(f"E501 存量上升（只准减不准增）：{grew}")
    if hard["E9"] or hard["W605"] or hard["F821"]:
        REFUSE.append(f"硬违例非零：{hard}")
    own = {}
    for rel in [NEW_FILE] + list(EDITED):
        if rel.endswith(".py"):
            own[rel] = now_counts.get(rel, 0)
    own_file_rc, own_out = sh([PY, "-X", "utf8", "-m", "flake8", "--max-line-length",
                               str(LINT_CFG_MAX), NEW_FILE], 300)
    own_viol = [ln for ln in own_out.splitlines() if ln.strip()]
    if own_viol:
        REFUSE.append(f"亲笔新文件 {NEW_FILE} 有违例：{own_viol[:3]}")
    if pre.get("yardstick_is_repo_config") is not True:
        REFUSE.append("基线口径与仓库 flake8 配置不一致，本格不可比")
    return {"hard_violations": hard,
            "e501_total_before": pre["e501_total"], "e501_total_now": sum(now_counts.values()),
            "e501_files_before": pre["files_with_e501"], "e501_files_now": len(now_counts),
            "baseline_path_style": "backslash" if any("\\" in k for k in raw_baseline) else "forward",
            "files_compared_against_baseline": len(known),
            "new_files_not_in_baseline": sorted(set(now_counts) - set(baseline)),
            "e501_within_baseline": not grew, "e501_grew": grew,
            "reduced_by": pre["e501_total"] - sum(now_counts.values()),
            "own_files_e501": own, "own_file_clean": not own_viol,
            "unparsed_lines": len(unparsed), "parsed_lines": len(lines),
            "at_utc": now_s()}


# ------------------------------------------------------------------ 行尾不动刀
def eol() -> dict:
    def profile(text: str) -> dict:
        crlf = text.count("\r\n")
        lf = text.count("\n") - crlf
        cls = ("mixed" if crlf and lf else "crlf" if crlf else "lf" if lf else "empty")
        return {"crlf": crlf, "lf": lf, "class": cls}

    rows, drift, changed = [], [], {}
    for rel, why in EDITED.items():
        before_path = BEFORE_DIR / Path(rel).name
        if not before_path.exists():
            REFUSE.append(f"缺修前快照 {before_path.name} ⇒ 无法证明行尾没漂")
            continue
        btext, atext = before_path.read_text(encoding="utf-8", newline=""), read(rel)
        pb, pa = profile(btext), profile(atext)
        diff = [ln for ln in difflib.unified_diff(btext.splitlines(), atext.splitlines(), n=0)
                if ln[:1] in ("+", "-") and ln[:3] not in ("+++", "---")]
        changed[rel] = len(diff)
        if changed[rel] > MAX_CHANGED_LINES_PER_FILE:
            REFUSE.append(f"{rel} 改动行数 {changed[rel]} 超上限 {MAX_CHANGED_LINES_PER_FILE}"
                          f" ⇒ 像整档重排，不像打磨")
        if pb["class"] != pa["class"]:
            drift.append({"file": rel, "before": pb["class"], "after": pa["class"]})
        rows.append({"file": rel, "why": why, "before": pb, "after": pa,
                     "changed_lines": len(diff)})
    if drift:
        REFUSE.append(f"工具把行尾类别改了（禁止静默换行尾）：{drift}")
    new_prof = profile(read(NEW_FILE))
    if new_prof["class"] != "lf":
        REFUSE.append(f"本轮新文件必须纯 LF，实测 {NEW_FILE} 是 {new_prof['class']}")
    pre = json.loads((HERE / "r3_polish_pre_baseline.json").read_text(encoding="utf-8"))
    now_mixed = []
    for d in RADIUS_DIRS:
        for path in (ROOT / d).rglob("*"):
            if not path.is_file() or path.suffix not in (".py", ".md", ".cypy", ".sh", ".toml"):
                continue
            if "__pycache__" in set(path.parts):
                continue
            raw = path.read_bytes()
            c = raw.count(b"\r\n")
            l = raw.count(b"\n") - c
            if c and l:
                now_mixed.append(str(path.relative_to(ROOT)).replace("\\", "/"))
    grew_mixed = sorted(set(now_mixed) - {m["file"] for m in pre["eol_manifest"]["mixed"]})
    if grew_mixed:
        REFUSE.append(f"出现了新的逐行混用文件（本环不该造）：{grew_mixed}")
    return {"mixed_files_manifest": pre["eol_manifest"]["mixed"],
            "eol_before_snapshot": {"crlf_only": pre["eol_manifest"]["crlf_only_count"],
                                    "lf_only": pre["eol_manifest"]["lf_only_count"],
                                    "mixed": pre["eol_manifest"]["mixed_count"]},
            "mixed_files_now_count": len(now_mixed),
            "no_bulk_reformat": all(v <= MAX_CHANGED_LINES_PER_FILE for v in changed.values()),
            "changed_lines_per_file": changed,
            "cap_per_file": MAX_CHANGED_LINES_PER_FILE,
            "edited_files": rows, "line_ending_class_drift": drift,
            "new_file_profile": new_prof, "at_utc": now_s()}


def main() -> int:
    (HERE / "tmp_polish").mkdir(exist_ok=True)
    doc = {"refuse": [], "started_at_utc": now_s()}
    doc["locks"] = locks()
    doc["api"] = api()
    doc["docs"] = docs()
    doc["lint"] = lint()
    doc["eol"] = eol()
    doc["refuse"] = REFUSE
    doc["finished_at_utc"] = now_s()
    for rel, key in (("polish_r3_locks.json", "locks"), ("polish_r3_api.json", "api"),
                     ("polish_r3_docs.json", "docs"), ("polish_r3_lint.json", "lint"),
                     ("polish_r3_eol.json", "eol")):
        payload = dict(doc[key])
        payload["refuse"] = REFUSE
        (HERE / rel).write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                                encoding="utf-8", newline="\n")
    (HERE / "polish_r3_evidence.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": REFUSE,
                      "locks": {k: doc["locks"][k] for k in
                                ("declared_total", "collected_and_passed", "new_locks",
                                 "frozen_fixture_swapped", "nonfrozen_control_kept",
                                 "each_new_lock_red_when_reverted", "control_group_green")},
                      "api": {k: doc["api"][k] for k in ("public_added", "cli_no_private_call",
                                                         "delegation_equal_on_broken")},
                      "docs": {k: doc["docs"][k] for k in ("flags_three_way", "guard_rerunnable",
                                                           "phantom", "undocumented", "help_mismatch")},
                      "lint": {k: doc["lint"][k] for k in ("hard_violations", "e501_within_baseline",
                                                           "reduced_by", "own_file_clean")},
                      "eol": {k: doc["eol"][k] for k in ("no_bulk_reformat", "changed_lines_per_file",
                                                         "line_ending_class_drift", "new_file_profile")}},
                     ensure_ascii=False, indent=1))
    return 1 if REFUSE else 0


if __name__ == "__main__":
    sys.exit(main())
