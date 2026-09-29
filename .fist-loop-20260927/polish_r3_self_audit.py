"""R3-打磨 的自我审计：拿审计上一环的同一把尺子量本轮报告。

两态判据（默认态不能写死）：**按仓库事实自动选态** —— 收口件在盘上就跑 post（含页脚 closure 格），
不在就跑 pre（只量判据件与散文），并把选到的态打进正文；不许"两态"退化成一态加一个猜测。

每条主张都用**独立重算**去反解（重新读盘、重新 git、重新 AST），而不是把判据件里的数再抄一遍；
另外专设两格防止"判据不会失败"：门禁里 `min: 0` 的格数必须为 0（那种格恒绿），
以及报告正文里不允许残留 `‹未解析›` 占位。
"""

from __future__ import annotations

import ast
import calendar
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
SPEC_NAME = "report_spec_r3_polish.json"
CLOSE_STAGE = "close_r3_polish.out.json"
CLOSE_ROOT = "close_r3_polish_root.out.json"
ROOT_OUT = "root_r3_polish.out.json"
EXPECTED_HEAD = "17d68b4"
PREV_PYTEST_FLOOR = 1920
STAGE_START_UTC = datetime.datetime(2026, 9, 27, 17, 37, 27, tzinfo=datetime.timezone.utc)
STAGE_START_EPOCH = calendar.timegm(STAGE_START_UTC.timetuple())
RADIUS_DIRS = ["cypyc", "cypy_hook", "cypy_bridge", "tests", "docs", "scripts", "examples"]
LOCK_FILES = ["tests/test_loop_20260927_polish_r3.py", "tests/test_loop_20260927_fix_r3.py"]
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
    return p.returncode, p.stdout.decode("utf-8", "replace")


def touched_now():
    out = set()
    for d in RADIUS_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            if {"__pycache__", ".egg-info"} & set(p.parts):
                continue
            if p.suffix not in (".py", ".md", ".cypy", ".sh", ".toml"):
                continue
            if p.stat().st_mtime >= STAGE_START_EPOCH:
                out.add(str(p.relative_to(ROOT)).replace("\\", "/"))
    return out


def main() -> int:
    post = (HERE / CLOSE_ROOT).exists() and (HERE / CLOSE_STAGE).exists() and (HERE / ROOT_OUT).exists()
    mode = "post-close" if post else "pre-close"
    spec = art(SPEC_NAME)
    report = ROOT / "memory" / "reviews" / f"{spec['name']}.md"
    if not report.exists():
        REFUSE.append(f"报告 {report.relative_to(ROOT)} 不在盘上 ⇒ 自审没有可量的对象")
        return 1
    text = report.read_text(encoding="utf-8")

    locks = art("polish_r3_locks.json")
    api = art("polish_r3_api.json")
    docs = art("polish_r3_docs.json")
    lint = art("polish_r3_lint.json")
    eol = art("polish_r3_eol.json")
    proof = art("polish_r3_lockproof.json")
    base = art("polish_r3_baselines.json")
    irr = art("polish_r3_irreversible.json")
    pre = art("r3_polish_pre_baseline.json")

    for name in ("polish_r3_evidence.json", "polish_r3_lockproof.json",
                 "polish_r3_baselines.json", "polish_r3_irreversible.json"):
        rec = art(name)
        if rec.get("refuse"):
            REFUSE.append(f"{name} 自带拒绝，报告不许在拒状态下放行：{rec['refuse'][:2]}")

    # 1) 锁清单：从盘上重新数 def test_，不抄件里的数
    flat = [n for f in LOCK_FILES
            for n in re.findall(r"^def (test_\w+)", (ROOT / f).read_text(encoding="utf-8", newline=""),
                                flags=re.M)]
    check("locks.declared_total", locks["declared_total"], len(flat), "盘上 re.findall(def test_)")
    check("locks.collected_and_passed == 声明数", locks["collected_and_passed"], len(flat),
          "polish_r3_locks.json vs 盘上重数", ok=locks["collected_and_passed"] == len(flat))
    check("locks.new_locks == polish 文件里的 def test_", locks["polish_locks"],
          len(re.findall(r"^def (test_\w+)", (ROOT / LOCK_FILES[0]).read_text(encoding="utf-8", newline=""),
                         flags=re.M)), "盘上重数")
    check("锁文件 sha 与盘面一致", locks["lock_file_sha256"][LOCK_FILES[0]],
          hashlib.sha256((ROOT / LOCK_FILES[0]).read_bytes()).hexdigest()[:16],
          "盘上 sha256 前 16 位（证据与回退矩阵必须同一棵树）")

    # 2) 回退矩阵形状
    check("lockproof.groups_ok == groups_total", proof["groups_ok"], proof["groups_total"],
          "polish_r3_lockproof.json", ok=proof["groups_ok"] == proof["groups_total"] == 8)
    check("lockproof 前提/收尾条数相等", proof["premise"]["passed"], proof["after_restore"]["passed"],
          "premise.passed vs after_restore.passed")
    check("对照组的期望红为空", 0, len([g for g in proof["groups"].values()
                                   if g["expected"] == [] and g["reds"]]),
          "『只改注释』组不得有红", ok=all(not g["reds"] for g in proof["groups"].values()
                                        if g["expected"] == []))
    left = [p.name for p in (HERE / "tmp_polish").glob("snap_*")] if (HERE / "tmp_polish").exists() else []
    left += [p.name for p in (HERE / "tmp_verify").glob("snap_*")] if (HERE / "tmp_verify").exists() else []
    check("盘上临时快照树", proof["snap_left"], left, "文件系统重数（tmp_polish + tmp_verify）",
          ok=(not left and proof["snap_left"] == [] and base["git"]["temp_snapshots_gone"]))

    # 3) API 门面：AST 独立重看
    hook_tree = ast.parse((ROOT / "cypy_hook" / "hook.py").read_text(encoding="utf-8", newline=""))
    cls = next(n for n in ast.walk(hook_tree)
               if isinstance(n, ast.ClassDef) and n.name == "CypyHook")
    methods = {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}
    check("api.public_added", api["public_added"], "analyze_only" in methods,
          "AST 重看 CypyHook 方法集", ok=("analyze_only" in methods) == api["public_added"])
    cli_src = (ROOT / "cypyc" / "cli.py").read_text(encoding="utf-8", newline="")
    check("api.cli_private_occurrences", api["cli_private_occurrences"],
          cli_src.count("_parse_and_analyze"), "盘上 count()")

    # 4) 文档三向：把 per_subcommand 的 argparse 栏用 AST 再取一遍
    fn = next(n for n in ast.walk(ast.parse(cli_src))
              if isinstance(n, ast.FunctionDef) and n.name == "parse_args")
    cur, table = "GLOBAL", {}
    calls = [x for x in ast.walk(fn) if isinstance(x, ast.Call)]
    for call in sorted(calls, key=lambda x: x.lineno):
        attr = getattr(call.func, "attr", None)
        if attr == "add_parser" and call.args and isinstance(call.args[0], ast.Constant):
            cur = call.args[0].value
            table.setdefault(cur, set())
        elif attr == "add_argument":
            for a in call.args:
                if isinstance(a, ast.Constant) and isinstance(a.value, str) and a.value.startswith("--"):
                    table.setdefault(cur, set()).add(a.value.split()[0])
    mismatched = [sub for sub, row in docs["per_subcommand"].items()
                  if sorted(table.get(sub, set())) != row["argparse"]]
    check("docs.per_subcommand 的 argparse 栏", len(docs["per_subcommand"]), len(mismatched) and mismatched
          or len(docs["per_subcommand"]), "AST 逐子命令重取后对表", ok=not mismatched)

    # 5) lint：件之间三方对齐（基线自求和 == 声明总量 == 现值）
    check("pre-baseline 自求和", sum(pre["e501_by_file"].values()), pre["e501_total"],
          "r3_polish_pre_baseline.json")
    check("lint.e501_total_now == 基线（只减不增，本环持平）", lint["e501_total_now"],
          pre["e501_total"], "polish_r3_lint.json vs pre-baseline",
          ok=lint["e501_total_now"] <= pre["e501_total"])
    check("lint.reduced_by 与两侧总量差一致", lint["reduced_by"],
          pre["e501_total"] - lint["e501_total_now"], "反解")
    own_rc, own_out = sh([PY, "-X", "utf8", "-m", "flake8", "--max-line-length", "100",
                          LOCK_FILES[0]], 300)
    own_lines = [ln for ln in own_out.splitlines() if ln.strip()]
    check("亲笔新文件当场再跑一次 flake8", lint["own_file_clean"], not own_lines,
          f"flake8 rc={own_rc} 输出 {own_lines[:2]}", ok=(not own_lines) == lint["own_file_clean"])

    # 6) 行尾与单档改动行数：从改前快照独立重算
    recount = {}
    for rel in eol["changed_lines_per_file"]:
        btext = (HERE / "tmp_polish" / "before" / Path(rel).name).read_text(encoding="utf-8", newline="")
        atext = (ROOT / rel).read_text(encoding="utf-8", newline="")
        recount[rel] = len([ln for ln in difflib.unified_diff(btext.splitlines(), atext.splitlines(), n=0)
                           if ln[:1] in ("+", "-") and ln[:3] not in ("+++", "---")])
    check("eol.changed_lines_per_file", eol["changed_lines_per_file"], recount,
          "tmp_polish/before 与盘面重新 difflib")
    new_bytes = (ROOT / LOCK_FILES[0]).read_bytes()
    check("新文件行尾类别当场重算", eol["new_file_profile"]["class"],
          "crlf" if new_bytes.count(b"\r\n") and not new_bytes.count(b"\n") - new_bytes.count(b"\r\n")
          else "lf" if new_bytes.count(b"\n") - new_bytes.count(b"\r\n") else "empty",
          "盘上字节重算")

    # 7) 三套体系与红线（当场重跑 git / 反解 pytest 计数）
    check("baselines.pytest.passed ≥ 下限", base["pytest"]["passed"],
          PREV_PYTEST_FLOOR + locks["new_locks"], "上一环地板 + 本轮新锁条数",
          ok=base["pytest"]["passed"] >= PREV_PYTEST_FLOOR + locks["new_locks"])
    check("pytest passed == collected", base["pytest"]["passed"], base["pytest"]["collected"],
          "polish_r3_baselines.json")
    check("全量收集里的新锁条数", base["pytest"]["polish_locks_collected"], locks["polish_locks"],
          "baselines vs locks", ok=base["pytest"]["polish_locks_collected"] == locks["polish_locks"])
    sf, ef = base["suite"]["fields"], base["e2e"]["fields"]
    check("自研套件 47/47", f"{sf.get('Passed')}/{sf.get('Total')}", "47/47", "baselines.suite.fields")
    check("e2e 三格为零", f"{ef.get('FAIL')}{ef.get('WARN')}{ef.get('UNREG/RUNFAIL')}", "000",
          "baselines.e2e.fields")
    rc, head = sh(["git", "rev-parse", "--short", "HEAD"])
    check("HEAD 当场重读", base["git"]["head"], head.strip(), "git rev-parse", ok=head.strip() == EXPECTED_HEAD)
    rc2, dirty = sh(["git", "status", "--porcelain"])
    deleted_now = len([ln for ln in dirty.splitlines() if ln.startswith((" D", "AD"))])
    check("删档行数三方对齐（baselines / irreversible / 盘上）",
          f"{base['git']['deleted_tracked']}/{irr['detail'][7]['evidence']['deleted_rows_now']}",
          f"{deleted_now}/{deleted_now}", "git status --porcelain 现算",
          ok=base["git"]["deleted_tracked"] == deleted_now == irr["detail"][7]["evidence"]["deleted_rows_now"])
    check("半径文件集合当场重算", sorted(base["radius"]["files"][i]["file"] for i in range(base["radius"]["count"])),
          sorted(touched_now()), "mtime ≥ 开工时刻的文件集合")

    # 8) 不可逆面
    kinds = {}
    for d in irr["detail"]:
        kinds[d["method"]] = kinds.get(d["method"], 0) + 1
    check("irreversible.items == len(detail)", irr["items"], len(irr["detail"]), "现件")
    check("分类计数与 detail 一致",
          f"live{irr['live_probe_items']}/derived{irr['derived_items']}/manifest{irr['manifest_items']}",
          f"live{kinds.get('live_probe', 0)}/derived{kinds.get('derived', 0)}/manifest{kinds.get('manifest', 0)}",
          "detail.method 重新统计")
    check("被执行清单为空", irr["executed"], [], "irreversible.executed", ok=irr["executed"] == [])
    rc, out = sh([PY, "-X", "utf8", "-c",
                  "import sqlite3;db=sqlite3.connect('file:fist-mbt.db?mode=ro',uri=True);"
                  "print(db.execute('select count(*) from call_log').fetchone()[0])"])
    check("call_log 只增不减（当场重读）", irr["detail"][11]["evidence"]["call_log_rows_now"],
          out.strip(), "sqlite 只读现算",
          ok=int(out.strip() or -1) >= irr["detail"][11]["evidence"]["call_log_rows_at_prev_closure"])

    # 9) 报告与 spec 的自洽：门禁不许有恒绿格
    vacuous = [g["label"] for g in spec["gates"] if g.get("min") == 0]
    check("恒绿门禁格数（min:0）必须为 0", len(vacuous), 0, f"report_spec_r3_polish.json：{vacuous}")
    nojudge = [g["label"] for g in spec["gates"]
               if not any(k in g for k in ("min", "equals", "truthy"))]
    check("每格都写了 min/equals/truthy", len(nojudge), 0, f"缺判据形状的门禁：{nojudge}")
    check("正文占位全部解析成功", text.count("‹未解析›"), 0, "报告正文里不许留未解析占位")
    frag = (HERE / "r3_polish_body.md").read_text(encoding="utf-8")
    sec = frag.split("## 六、本环自身缺陷", 1)
    if len(sec) != 2:
        REFUSE.append("散文片段缺《六》段 ⇒ 缺陷计数反解不出来")
        judge_n = op_n = -1
    else:
        body6 = sec[1].split("## ", 1)[0]
        halves = re.split(r"操作[与和类]*[：:]", body6)
        judge_n = len(re.findall(r"^\d+\. ", halves[0], flags=re.M))
        op_n = len(re.findall(r"^\d+\. ", halves[1], flags=re.M)) if len(halves) > 1 else -1
        check("《六》段两栏都能数出来", f"{judge_n}/{op_n}", f"{judge_n}/{op_n}",
              "散文中 `^\\d+\\. ` 条数", ok=judge_n > 0 and op_n > 0)

    # 10) 本环不产生缺陷卡（主张与账本对齐）
    db = sqlite3.connect(f"file:{ROOT / 'fist-mbt.db'}?mode=ro", uri=True)
    n_bugs = db.execute("select count(*) from tasks where ns='bugs' and description like ?",
                        ("%R3-打磨%",)).fetchone()[0]
    db.close()
    check("打磨环不产生 BUG 卡", 0, n_bugs, "sqlite ns=bugs 里含 [loop:R3-打磨] 的条数")

    foot = {}
    if mode == "post-close":
        m = re.search(r"\[selfdrive-polish\][^\n]*", text)
        if not m:
            REFUSE.append("报告里找不到 [selfdrive-polish] 页脚")
        else:
            foot = dict(re.findall(r"([\w-]+)=([^\s]+)", m.group(0)))
            root_close = art(CLOSE_ROOT)
            root_out = art(ROOT_OUT)
            stage_out = art(CLOSE_STAGE)
            refused = root_close.get("refused") or []
            check("页脚 root", foot.get("root"), root_out["root"], f"{ROOT_OUT}:root")
            check("页脚 gates", foot.get("gates"), len(spec["gates"]), "spec 门禁条数")
            check("页脚 refused", foot.get("refused"), len(refused), f"{CLOSE_ROOT}:refused")
            check("页脚 leaves", foot.get("leaves"), root_close["leaves_done"], f"{CLOSE_ROOT}:leaves_done")
            check("页脚 new_locks", foot.get("new_locks"), locks["new_locks"], "polish_r3_locks.json")
            check("页脚 revert_groups", foot.get("revert_groups"),
                  f"{proof['revert_groups_ok']}/{proof['groups_total']}", "lockproof")
            check("页脚 control_green", foot.get("control_green"),
                  "yes" if proof["control_groups_ok"] == 1 else "no", "lockproof 对照组")
            check("页脚 pytest", foot.get("pytest"), base["pytest"]["passed"], "baselines")
            check("页脚 pytest_collected", foot.get("pytest_collected"), base["pytest"]["collected"], "baselines")
            check("页脚 locks_green_now", foot.get("locks_green_now"),
                  f"{locks['collected_and_passed']}/{locks['declared_total']}", "locks 件")
            check("页脚 suite", foot.get("suite"), f"{sf.get('Passed')}/{sf.get('Total')}", "baselines")
            check("页脚 e2e_zero", foot.get("e2e_zero"),
                  f"{ef.get('FAIL')}{ef.get('WARN')}{ef.get('UNREG/RUNFAIL')}", "baselines")
            check("页脚 radius", foot.get("radius"), base["radius"]["count"], "baselines")
            check("页脚 e501", foot.get("e501"), f"{lint['e501_total_now']}/{lint['e501_total_before']}", "lint 件")
            check("页脚 irreversible", foot.get("irreversible"),
                  f"{irr['items']}(live={irr['live_probe_items']},derived={irr['derived_items']},"
                  f"manifest={irr['manifest_items']})", "irreversible 件")
            check("页脚 executed", foot.get("executed"), "none", "irreversible.executed")
            check("页脚 judge-defects", foot.get("judge-defects"), judge_n, "散文《六》段")
            check("页脚 op-defects", foot.get("op-defects"), op_n, "散文《六》段")
            check("页脚 decisions", foot.get("decisions"),
                  len(re.findall(r"[；;]", frag.split("要谁裁决：", 1)[1].split("## ", 1)[0])) + 1,
                  "散文《七》段按分号数")
            check("页脚 uncovered 条数", foot.get("uncovered"), len(locks["revert_uncovered_locks"]),
                  "locks 件（无回退证明的新锁）")
            check("页脚 api_public", foot.get("api_public"), "yes" if api["public_added"] else "no", "api 件")
            check("页脚 api_cli_private", foot.get("api_cli_private"), cli_src.count("_parse_and_analyze"),
                  "盘上 count() 现算")
            check("页脚 docs_three_way", foot.get("docs_three_way"),
                  "yes" if docs["flags_three_way"] else "no", "docs 件")
            check("页脚 lint_hard", foot.get("lint_hard"),
                  f"{lint['hard_violations']['E9']}/{lint['hard_violations']['W605']}/"
                  f"{lint['hard_violations']['F821']}", "lint 件三格")
            check("页脚 reduced", foot.get("reduced"), lint["reduced_by"], "lint 件（持平＝0，不许写成改善）")
            check("页脚 eol_mixed", foot.get("eol_mixed"), eol["mixed_files_now_count"], "eol 件")
            check("页脚 eol_drift", foot.get("eol_drift"), len(eol["line_ending_class_drift"]), "eol 件")
            check("页脚 radius_unexpected", foot.get("radius_unexpected"),
                  len(base["radius"]["unexpected"]), "baselines 件")
            check("页脚 pytest_locks_collected", foot.get("pytest_locks_collected"),
                  base["pytest"]["polish_locks_collected"], "baselines 件",
                  ok=str(foot.get("pytest_locks_collected")) == str(locks["polish_locks"]))
            check("页脚 audit_selftest", foot.get("audit_selftest"), irr["self_test"]["caught"],
                  "irreversible 件（注入假违例必须被抓住）")
            check("页脚 refusal_kinds", foot.get("refusal_kinds"), len(refused),
                  f"{CLOSE_ROOT}:refused 条数")
            check("根任务已归档", root_close.get("root_final"), "已归档", f"{CLOSE_ROOT}:root_final")
            check("叶失败为空", len(stage_out.get("failed") or []), 0, f"{CLOSE_STAGE}:failed")
    else:
        ROWS.append({"claim": "closure 格（root/gates/refused/leaves）", "stored": "pre-close",
                     "recomputed": "收口件未落盘，本轮跳过 closure 反解；post 态会全部重算",
                     "source": "mode 自动选择", "equal": True})

    doc = {"refuse": REFUSE, "mode": mode, "mode_reason":
           f"收口件存在={ (HERE / CLOSE_ROOT).exists() } ⇒ 选 {mode}；两态各自跑、各留一份，默认态不写死",
           "checks": len(ROWS),
           "counts_all_equal": 1 if all(r["equal"] for r in ROWS) and ROWS and not REFUSE else 0,
           "mismatched": [r["claim"] for r in ROWS if not r["equal"]],
           "artifacts_audited": ["polish_r3_locks.json", "polish_r3_api.json", "polish_r3_docs.json",
                                 "polish_r3_lint.json", "polish_r3_eol.json", "polish_r3_lockproof.json",
                                 "polish_r3_baselines.json", "polish_r3_irreversible.json",
                                 "r3_polish_pre_baseline.json"],
           "report": f"memory/reviews/{spec['name']}.md",
           "gates_in_spec": len(spec["gates"]),
           "vacuous_gates": vacuous,
           "defect_counts": {"judge": judge_n, "op": op_n},
           "footer_raw": foot,
           "started_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    (HERE / "polish_r3_self_audit.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": REFUSE, "mode": mode, "checks": doc["checks"],
                      "counts_all_equal": doc["counts_all_equal"],
                      "mismatched": doc["mismatched"], "vacuous_gates": vacuous},
                     ensure_ascii=False, indent=1))
    return 1 if REFUSE else 0


if __name__ == "__main__":
    sys.exit(main())
