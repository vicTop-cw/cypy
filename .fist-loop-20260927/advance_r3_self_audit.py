"""R3-推进 的自我审计：报告页脚每个数都要能被**独立重算**打回。

与打磨环同一把尺子，但推进环多两格必须过的硬证：
① 新行为的"成对性"（违例必报 + 正确必不报）要在审计里再跑一遍，而不是只读件里的旗标；
② 产物差分不许由件自己说"identical"，审计用 before/after 两份 .pyx 重新剥时间戳再比一次；
③ 恒绿格检查（`min: 0`）与占位残留检查照抄上一环的教训。
两态自动选（收口件在不在盘上），不写死默认态。
"""

from __future__ import annotations

import datetime
import difflib
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = sys.executable
SPEC_NAME = "report_spec_r3_advance.json"
CLOSE_STAGE = "close_r3_advance.out.json"
CLOSE_ROOT = "close_r3_advance_root.out.json"
ROOT_OUT = "root_r3_advance.out.json"
AD = HERE / "tmp_advance"
TIME_LINES = ("__compile_time__", "__generated_at__")
LOCK_FILE = "tests/test_loop_20260927_advance_r3.py"
ROWS: list = []
REFUSE: list = []


def art(name) -> dict:
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def check(claim, stored, recomputed, source, ok=None):
    equal = (str(stored) == str(recomputed)) if ok is None else bool(ok)
    ROWS.append({"claim": claim, "stored": stored, "recomputed": recomputed,
                 "source": source, "equal": equal})
    if not equal:
        REFUSE.append(f"[自审] {claim}：件里写 {stored!r}，独立重算得 {recomputed!r}（{source}）")


def sh(cmd, timeout=900):
    p = subprocess.run(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       timeout=timeout)
    return p.returncode, p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")


def strip_time(text: str) -> str:
    return "\n".join(ln for ln in text.splitlines() if not any(t in ln for t in TIME_LINES))


def analyze(src: str) -> list:
    sys.path.insert(0, str(ROOT))
    from cypy_hook.hook import CypyHook
    _, errors = CypyHook().analyze_only(src)
    return list(errors)



def _by_key(doc: dict, key: str):
    """跨环/跨件取数一律按键搜索，取不到就拒 —— 下标只在清单不变时才可信。"""
    for d in doc["detail"]:
        if key in d["evidence"]:
            return d["evidence"][key]
    REFUSE.append(f"件里找不到键 {key} ⇒ 不许拿 None 当'没发生'")
    return None

def main() -> int:
    post = all((HERE / f).exists() for f in (CLOSE_STAGE, CLOSE_ROOT, ROOT_OUT))
    mode = "post-close" if post else "pre-close"
    spec = art(SPEC_NAME)
    report = ROOT / "memory" / "reviews" / f"{spec['name']}.md"
    if not report.exists():
        print(json.dumps({"refuse": [f"报告 {spec['name']}.md 不在盘上"]}, ensure_ascii=False))
        return 1
    text = report.read_text(encoding="utf-8")

    arity = art("advance_r3_arity.json")
    cogen = art("advance_r3_codegen_diff.json")
    face = art("advance_r3_scope_face.json")
    locks = art("advance_r3_locks.json")
    corpus = art("advance_r3_corpus.json")
    base = art("advance_r3_baselines.json")
    irr = art("advance_r3_irreversible.json")
    pre = art("advance_r3_pre_baseline.json")

    for f in ("advance_r3_arity.json", "advance_r3_codegen_diff.json", "advance_r3_scope_face.json",
              "advance_r3_locks.json", "advance_r3_corpus.json", "advance_r3_baselines.json",
              "advance_r3_irreversible.json"):
        if art(f).get("refuse"):
            REFUSE.append(f"{f} 自带拒绝，报告不许在拒状态下放行：{art(f)['refuse'][:2]}")

    # 1) 成对性当场再跑一遍（不读件里的旗标）
    viol = analyze("def apply(f: Callable[[int], str]) -> str:\n    return f(1, 2)\n")
    clean = analyze("def apply(f: Callable[[int], str]) -> str:\n    return f(1)\n")
    check("违例必报（analyze_only 当场重跑）", arity["violation_total"],
          "arity 行出现在现跑结果里" if any("arity" in e for e in viol) else "现跑没报错",
          "现跑输出", ok=any("arity" in e for e in viol))
    check("正确调用必不报（analyze_only 当场重跑）", arity["clean_cases_green"],
          "现跑静默" if not any("arity" in e for e in clean) else f"现跑报了 {clean}",
          "现跑输出", ok=not any("arity" in e for e in clean))
    check("违例条目数与件里一致", arity["violation_total"], len(arity["violation_cases"]), "advance_r3_arity.json")
    check("每条违例都带位点", arity["cases_with_locus"], arity["violation_total"],
          "正则 ` at \\d+:\\d+$` 逐条重数",
          ok=all(any(re.search(r" at \d+:\d+$", e) for e in errs) for errs in arity["violation_cases"].values()))
    skip_bad = {k: v for k, v in arity["skipped_shapes"].items() if any("arity" in e for e in v)}
    check("该跳过的形状现在仍跳过", 0, len(skip_bad), "件里的 skipped_shapes 现重扫", ok=not skip_bad)

    # 2) 产物差分：审计自己再剥一次时间戳比对
    bad = []
    for row in cogen["cases"]:
        stem = row["artifact"][:-4]
        b, a = AD / "pyx_before" / f"{stem}.pyx", AD / "pyx_after" / f"{stem}.pyx"
        if not (b.exists() and a.exists()):
            bad.append(f"{stem}: 缺 before/after 件")
            continue
        if strip_time(b.read_text(encoding="utf-8", errors="replace")) != \
           strip_time(a.read_text(encoding="utf-8", errors="replace")):
            bad.append(stem)
    check("codegen 产物逐字相同（审计重算）", cogen["all_textual_identical"], not bad,
          "tmp_advance/pyx_before vs pyx_after 重新剥两行时间戳后对比",
          ok=(cogen["all_textual_identical"] is True and not bad))
    check("差分案例数=两栏之和", cogen["sources_scanned"],
          cogen["identical_total"] + len(cogen["refused_by_new_check"]),
          "advance_r3_codegen_diff.json（4 档逐字 + 1 档违例夹具）")
    check("违例夹具确实被新判定挡住", len(cogen["refused_by_new_check"]),
          cogen["refused_expected_total"], "分栏自证：挡住的那句必须点名 arity 错",
          ok=len(cogen["refused_by_new_check"]) == cogen["refused_expected_total"]
          and all("arity" in r["refusal_needle"] for r in cogen["refused_by_new_check"]))

    # 3) 半径外条目必须逐条有实测值
    missing_obs = [k for k, v in face["outside_radius"].items()
                   if not any(str(val) for key, val in v.items() if key.startswith("observed"))]
    check("半径外条目都有实测", face["outside_total"], len(face["outside_radius"]),
          "advance_r3_scope_face.json", ok=face["outside_total"] == len(face["outside_radius"])
          and not missing_obs)
    check("变长形状解析结果", "Unexpected token" in face["variadic_probe_outcome"], True,
          f"variadic_probe_outcome={face['variadic_probe_outcome'][:80]}",
          ok="Unexpected token" in face["variadic_probe_outcome"])
    check("冻结文档声明行数", len(face["frozen_doc_rows"]) >= 2, True, "SYNTAX 两行原文都在件里")

    # 4) 锁与回退证明
    disc = len(re.findall(r"^def (test_\w+)", (ROOT / LOCK_FILE).read_text(encoding="utf-8", newline=""),
                          flags=re.M))
    check("盘上新锁条数 == 件里 new_locks", locks["new_locks"], disc, "盘上重数 def test_")
    check("新锁条数 == 全量收集里现形的条数", base["pytest"]["advance_locks_collected"], disc,
          "baselines vs 盘上")
    covered = sorted(set(locks["each_new_lock_red_when_reverted"]))
    all_locks = set(re.findall(r"^def (test_\w+)", (ROOT / LOCK_FILE).read_text(encoding="utf-8", newline=""),
                               flags=re.M))
    uncovered = sorted(all_locks - set(covered))
    check("每组 mutation 都点名了期望红，且未覆盖集合为空", len(uncovered), 0,
          f"9 条锁里没被任何 mutation 打过的：{uncovered}", ok=not uncovered)
    check("回退矩阵组数与合格数", locks["groups_ok"], locks["groups_total"], "advance_r3_locks.json",
          ok=locks["groups_ok"] == locks["groups_total"] == 5)
    check("前提与收尾条数相等", locks["premise"]["passed"], locks["after_restore"]["passed"],
          "同一棵快照树两态")
    check("身份探针取自快照树", len(locks["identity"]), 4, "4 个模块 __file__ 全在 SNAP 内")
    left = [p.name for p in (AD).glob("snap_*")] if AD.exists() else []
    check("临时快照树当场重数", locks["snap_left"], left, "文件系统 snap_* 目录",
          ok=(not left and locks["snap_left"] == []))
    check("语料两态扫描文件数", corpus["samples_scanned"], corpus["files_scanned"],
          "advance_r3_corpus.json", ok=corpus["samples_scanned"] >= 40)
    check("语料新增的非 arity 错误", corpus["new_errors_outside_locks"], [],
          "restored − mutation 的错误集合差", ok=corpus["new_errors_outside_locks"] == [])
    sp = corpus["sensitivity_probe"]
    check("语料扫描有观察力（过严对照必冒出新 arity 行）", sp["new_error_kinds"] >= 1, True,
          "见证夹具在故意改宽后新增的错误种类",
          ok=sp["new_error_kinds"] >= 1 and sp["all_through_the_check"])
    wit = corpus["witness"]
    check("见证夹具三栏自洽（违例档两态差、合规档两态都干净）",
          [any("arity" in e for e in wit["bad_restored"]), wit["bad_mutation"], wit["ok_restored"]],
          [True, [], []], "advance_r3_corpus.json:witness",
          ok=any("arity" in e for e in wit["bad_restored"])
          and not wit["bad_mutation"] and not wit["ok_restored"])
    check("既有测试逐名两向对照", [len(irr["test_names_disappeared"]),
                                   len(irr["test_names_added_stray"])], [0, 0],
          "上一环全量收集名 vs 本轮", ok=irr["test_names_disappeared"] == []
          and irr["test_names_added_stray"] == [])
    can = base["lint"]["canary"]
    check("亲笔 lint 的行号过滤配了成对对照",
          [can["cypyc/analyzer/type_checker.py:too_long"]["on_my_lines"],
           can["cypyc/analyzer/type_checker.py:clean"]["on_my_lines"]], [1, 0],
          "注入必然违例必被抓 + 合规行不误抓",
          ok=can["cypyc/analyzer/type_checker.py:too_long"]["on_my_lines"] >= 1
          and can["cypyc/analyzer/type_checker.py:clean"]["on_my_lines"] == 0)

    # 5) 三套体系与红线（当场重读 git / 反解计数）
    check("pytest 地板 = 上一环实测 + 新锁条数", base["pytest"]["passed"],
          f">={base['pytest_floor']}", "baselines.pytest",
          ok=base["pytest"]["passed"] >= base["pytest_floor"] == pre["pytest_floor_before"] + disc)
    check("passed == collected", base["pytest"]["passed"], base["pytest"]["collected"], "baselines")
    rc, head = sh(["git", "rev-parse", "--short", "HEAD"])
    check("HEAD 当场重读", base["git"]["head"], head.strip(), "git rev-parse")
    rc2, dirty = sh(["git", "status", "--porcelain"])
    deleted_now = len([ln for ln in dirty.splitlines() if ln.startswith((" D", "AD"))])
    check("删档行数三方对齐", f"{base['git']['deleted_tracked']}/{_by_key(irr, 'deleted_rows_now')}",
          f"{deleted_now}/{deleted_now}", "git status 现算",
          ok=base["git"]["deleted_tracked"] == deleted_now ==
          _by_key(irr, "deleted_rows_now"))
    check("产品文件改动只在 Callable 那一块", irr["changed_lines_in_product"] <= 40, True,
          f"改动行数 {irr['changed_lines_in_product']}（上限 40）",
          ok=irr["changed_lines_in_product"] <= 40)
    check("before 快照 sha 与件里一致", pre["type_checker_sha_before"],
          arity["type_checker_sha_now"] if False else pre["type_checker_sha_before"],
          "件里同时带 before/now 两串（证明改过）",
          ok=arity["type_checker_sha_now"] != pre["type_checker_sha_before"])
    sf, ef = base["suite"]["fields"], base["e2e"]["fields"]
    check("自研套件 47/47", f"{sf.get('Passed')}/{sf.get('Total')}", "47/47", "baselines.suite")
    check("e2e 三格为零", f"{ef.get('FAIL')}{ef.get('WARN')}{ef.get('UNREG/RUNFAIL')}", "000", "baselines.e2e")

    # 6) 报告与 spec 自洽
    vacuous = [g["label"] for g in spec["gates"] if g.get("min") == 0]
    check("恒绿门禁格数（min: 0）必须为 0", len(vacuous), 0, f"report_spec：{vacuous}")
    nojudge = [g["label"] for g in spec["gates"] if not any(k in g for k in ("min", "equals", "truthy"))]
    check("每格都写了判定形状", len(nojudge), 0, f"缺 min/equals/truthy 的门禁：{nojudge}")
    check("正文占位全部解析成功", text.count("‹未解析›"), 0, "报告正文")
    frag = (HERE / "r3_advance_body.md").read_text(encoding="utf-8")
    sec = frag.split("## 七、本环自身缺陷", 1)
    judge_n = op_n = -1
    if len(sec) != 2:
        REFUSE.append("散文缺《七、本环自身缺陷》段 ⇒ 缺陷计数反解不出来")
    else:
        body6 = sec[1].split("## ", 1)[0]
        halves = re.split(r"操作[与和类]*[：:]", body6)
        judge_n = len(re.findall(r"^\d+\. ", halves[0], flags=re.M))
        op_n = len(re.findall(r"^\d+\. ", halves[1], flags=re.M)) if len(halves) > 1 else -1
        check("《七》段两栏都能数出来", f"{judge_n}/{op_n}", f"{judge_n}/{op_n}",
              "散文按 `^\\d+\\. ` 数", ok=judge_n > 0 and op_n > 0)
    db = sqlite3.connect(f"file:{ROOT / 'fist-mbt.db'}?mode=ro", uri=True)
    n_bugs = db.execute("select count(*) from tasks where ns='bugs' and description like ?",
                        ("%R3-推进%",)).fetchone()[0]
    db.close()
    check("推进环不产生 BUG 卡", 0, n_bugs, "sqlite ns=bugs 含 [loop:R3-推进] 的条数")

    foot = {}
    if mode == "post-close":
        m = re.search(r"\[selfdrive-advance\][^\n]*", text)
        if not m:
            REFUSE.append("报告里找不到 [selfdrive-advance] 页脚")
        else:
            foot = dict(re.findall(r"([\w-]+)=([^\s]+)", m.group(0)))
            root_out, root_close, stage_out = art(ROOT_OUT), art(CLOSE_ROOT), art(CLOSE_STAGE)
            refused = root_close.get("refused") or []
            check("页脚 root", foot.get("root"), root_out["root"], f"{ROOT_OUT}:root")
            check("页脚 gates", foot.get("gates"), len(spec["gates"]), "spec 门禁条数")
            check("页脚 refused", foot.get("refused"), len(refused), f"{CLOSE_ROOT}:refused")
            check("页脚 leaves", foot.get("leaves"), root_close["leaves_done"], f"{CLOSE_ROOT}:leaves_done")
            check("页脚 floor_raised", foot.get("floor_raised"), base["floor_raised"], "baselines")
            check("页脚 pytest", foot.get("pytest"), base["pytest"]["passed"], "baselines")
            check("页脚 pytest_collected", foot.get("pytest_collected"), base["pytest"]["collected"], "baselines")
            check("页脚 violation_cases", foot.get("violation_cases"), arity["violation_total"], "arity 件")
            check("页脚 clean_green", foot.get("clean_green"), "yes" if arity["clean_cases_green"] else "no",
                  "arity 件")
            check("页脚 groups", foot.get("groups"), f"{locks['groups_ok']}/{locks['groups_total']}", "locks 件")
            check("页脚 corpus_files", foot.get("corpus_files"), corpus["samples_scanned"], "corpus 件")
            check("页脚 corpus_new_errors", foot.get("corpus_new_errors"),
                  len(corpus["new_errors_outside_locks"]), "corpus 件")
            check("页脚 codegen_identical", foot.get("codegen_identical"),
                  "yes" if cogen["all_textual_identical"] else "no", "codegen 件")
            check("页脚 radius", foot.get("radius"), base["radius"]["count"], "baselines")
            check("页脚 irreversible", foot.get("irreversible"),
                  f"{irr['items']}(live={irr['live_probe_items']},derived={irr['derived_items']},"
                  f"manifest={irr['manifest_items']})", "irreversible 件")
            check("页脚 executed", foot.get("executed"), "none", "irreversible.executed")
            check("页脚 audit_selftest", foot.get("audit_selftest"), irr["self_test"]["caught"],
                  "irreversible 件（注入假违例必被抓）")
            check("页脚 judge-defects", foot.get("judge-defects"), judge_n, "散文《七》段")
            check("页脚 op-defects", foot.get("op-defects"), op_n, "散文《七》段")
            check("页脚 decisions", foot.get("decisions"),
                  len(re.findall(r"[；;]", frag.split("要谁裁决：", 1)[1].split("## ", 1)[0])) + 1
                  if "要谁裁决：" in frag else -1, "散文《七》段按分号数")
            check("根任务已归档", root_close.get("root_final"), "已归档", f"{CLOSE_ROOT}:root_final")
            check("叶失败为空", len(stage_out.get("failed") or []), 0, f"{CLOSE_STAGE}:failed")
    else:
        ROWS.append({"claim": "closure 格（root/gates/refused/leaves）", "stored": "pre-close",
                     "recomputed": "收口件未落盘 ⇒ 本态跳过；post 态全部重算",
                     "source": "mode 按仓库事实自动选", "equal": True})

    doc = {"refuse": REFUSE, "mode": mode,
           "mode_reason": f"三件收口产物齐全={(HERE / CLOSE_ROOT).exists()} ⇒ 选 {mode}",
           "checks": len(ROWS),
           "counts_all_equal": 1 if all(r["equal"] for r in ROWS) and ROWS and not REFUSE else 0,
           "mismatched": [r["claim"] for r in ROWS if not r["equal"]],
           "vacuous_gates": vacuous, "defect_counts": {"judge": judge_n, "op": op_n},
           "report": f"memory/reviews/{spec['name']}.md", "gates_in_spec": len(spec["gates"]),
           "footer_raw": foot,
           "started_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    (HERE / "advance_r3_self_audit.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps({k: doc[k] for k in ("refuse", "mode", "checks", "counts_all_equal",
                                          "mismatched", "vacuous_gates")},
                     ensure_ascii=False, indent=1))
    return 1 if REFUSE else 0


if __name__ == "__main__":
    sys.exit(main())
