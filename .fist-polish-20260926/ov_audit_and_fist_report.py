#!/usr/bin/env python3
"""Use §四's `output_validate` as the deliverable hard gate it is meant to be, retrospectively.

Part 1 — per-ticket L4 audit: for each closed fix ticket, feed the *recorded* deliverables (changed
files + locked regression case names, parsed out of the `### FIXED(...)` blocks this round appended
to memory/bugs.md) through `output_validate` as file artifacts. The verdict comes from the server
reading the real files under the Cypy root, so it is independent of my own call logs. A negative
control (an absent marker) proves the gate would actually have caught a missing deliverable rather
than rubber-stamping it.

Part 2 — file the single FIST-Mbt defect that survived discriminating controls. probe_output_
validate3.py established: `contains` / `not_contains` / `min_chars` all bind, but an unknown or
misspelled artifact key yields verdict=pass with detail 「OK（存在/非空/invariant 全部通过）」.
Root cause read at src/server/output_validate.mbt:63-90 — parse_artifact only does m.get() on the
five known keys with "" / 0 fallbacks and never inspects leftover keys. Landed in FIST-Mbt's own
ledger the way this lane's earlier findings were: server cwd = FIST root, project_dir=".",
publish_task=False, so no task is seeded on their production board.
"""
import json
import os
import re
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.abspath(os.path.join(HERE, ".."))
FIST_ROOT = r"E:\IDEProjects\AI\FIST-Mbt"
import pfist  # noqa: E402
from pfist import Client, utc_now  # noqa: E402

LED = os.path.join(ROOT, "memory", "bugs.md")
REG = "tests/test_polish_20260926.py"
CASE_RE = re.compile(r"tests/test_polish_20260926\.py::(test_\w+)(?:\[[^\]]*\])?")
BRACE_RE = re.compile(r"^([^,{]*)\{([^}]*)\}(.*)$")
ABSENT = "def test_zzz_marker_that_does_not_exist_anywhere"


def expand_paths(line):
    """`a/{b,c}_x.py` -> [a/b_x.py, a/c_x.py]; `d.py, e.py` -> [d.py, e.py] (backticks stripped).

    Braces are expanded *before* the comma split, otherwise the comma set inside `{...}` shreds the
    path (that mistake is what the first run's precheck caught).
    """
    out = []
    for token in re.findall(r"`([^`]*)`", line):
        m = BRACE_RE.match(token.strip())
        if m:
            pre, mid, post = m.groups()
            out += [f"{pre}{p.strip()}{post}" for p in mid.split(",")]
            continue
        out += [p.strip() for p in token.split(",") if p.strip()]
    return out


def parse_ledger():
    text = open(LED, encoding="utf-8").read()
    tickets = []
    for m in re.finditer(r"(?m)^## (BUG-\d+) \[[^\]]*\] \[[a-z]+\] OPEN\n(.*?)(?=^## BUG-\d+ |\Z)",
                         text, re.S):
        bid, body = m.group(1), m.group(2)
        fixed = re.search(r"^### FIXED\(verify=(\S+?)\)", body, re.M)
        task = re.search(r"^- 修复任务：`(\S+?)`", body, re.M) or re.search(r"^- task_id: (\S+)$",
                                                                           body, re.M)
        files = re.search(r"^- 改动文件：(.*)$", body, re.M)
        cases = re.search(r"^- 锁死回归（[^）]*）：(.*)$", body, re.M)
        tickets.append({
            "bug": bid,
            "task_id": task.group(1) if task else None,
            "files": expand_paths(files.group(1)) if files else [],
            "cases": CASE_RE.findall(cases.group(1)) if cases else [],
            "fixed": bool(fixed),
        })
    tickets.sort(key=lambda x: int(x["bug"].split("-")[1]))
    return tickets


def precheck(tickets):
    """Fail fast on anything the audit would otherwise silently skip over."""
    errs = []
    for t in tickets:
        if not t["fixed"]:
            continue
        if not t["files"]:
            errs.append(f"{t['bug']}  FIXED 块解析不到改动文件")
        if not t["cases"]:
            errs.append(f"{t['bug']}  FIXED 块解析不到锁死回归用例")
        for f in t["files"] + [REG]:
            if not os.path.exists(os.path.join(ROOT, f.replace("/", os.sep))):
                errs.append(f"{t['bug']}  账本记的文件不存在: {f}")
        for c in t["cases"]:
            if f"def {c}" not in open(os.path.join(ROOT, REG.replace("/", os.sep)),
                                      encoding="utf-8").read():
                errs.append(f"{t['bug']}  用例名在 {REG} 里没有 def: {c}")
    return errs


def artifacts_for(t):
    a = [{"path": f, "min_chars": 10} for f in t["files"]]
    a += [{"path": REG, "contains": f"def {c}"} for c in t["cases"]]
    a.append({"path": "memory/bugs.md", "contains": f"## {t['bug']} "})
    return a


def verdict_of(rep):
    if not isinstance(rep, dict):
        return {"verdict": "error", "raw": str(rep)[:200]}
    return {"verdict": rep.get("verdict"), "layer": rep.get("evidence_layer"),
            "passed": rep.get("passed"), "failed": rep.get("failed"),
            "failed_artifacts": [c.get("artifact") for c in rep.get("checks") or []
                                 if not c.get("ok")],
            "note": (rep.get("note") or "")[:160]}


def main() -> int:
    tickets = parse_ledger()
    closed = [t for t in tickets if t["fixed"]]
    open_ones = [t["bug"] for t in tickets if not t["fixed"]]
    print(f"tickets={len(tickets)} with_FIXED_block={len(closed)} without={open_ones}")
    errs = precheck(tickets)
    if errs:
        print("PRECHECK FAIL:")
        for e in errs:
            print("  " + e)
        return 2
    db = {r["id"]: dict(r) for r in []}
    con = sqlite3.connect("file:" + os.path.join(ROOT, "fist-mbt.db").replace("\\", "/") +
                          "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    ids = [t["task_id"] for t in closed]
    db = {r["id"]: dict(r) for r in con.execute(
        "select id, ns, status from tasks where id in (%s)" % ",".join("?" * len(ids)), ids)}
    con.close()

    c = Client(timeout=180)
    c._send("initialize", {"protocolVersion": "2026-07-28", "capabilities": {},
                           "clientInfo": {"name": "cypy-polish-ovaudit", "version": "1"}})
    audit = []
    for t in closed:
        rep = c.call("output_validate", {"artifacts": artifacts_for(t), "project_dir": ".",
                                         "now": utc_now()}, timeout=120)
        v = verdict_of(rep)
        row = {**t, "db_status": db.get(t["task_id"], {}).get("status"),
               "db_ns": db.get(t["task_id"], {}).get("ns"), "n_artifacts": len(artifacts_for(t)),
               **v}
        audit.append(row)
        print(f"[{v['verdict']:5s}] {t['bug']} {t['task_id']} db={row['db_status']} "
              f"{row['n_artifacts']} artifacts {v['note']}")
    neg = artifacts_for(closed[0]) + [{"path": REG, "contains": ABSENT}]
    nrep = c.call("output_validate", {"artifacts": neg, "project_dir": ".", "now": utc_now()},
                  timeout=120)
    nv = verdict_of(nrep)
    control = {"ticket": closed[0]["bug"], "expect": "fail", "got": nv["verdict"],
               "agree": nv["verdict"] == "fail", "detail_artifacts": nv["failed_artifacts"],
               "note": nv["note"]}
    print(f"[control] 负向对照 {closed[0]['bug']} + 一个不存在的路标: expect=fail got={nv['verdict']}")
    c.close()

    pass_n = sum(1 for a in audit if a["verdict"] == "pass")
    out = {"part1_audit": {
        "tickets_total": len(tickets), "audited": len(audit), "pass": pass_n,
        "not_pass": [a["bug"] for a in audit if a["verdict"] != "pass"],
        "control_negative": control, "rows": audit,
        "note": "BUG-13 无 FIXED 块（verify 未通过），本轮不纳入 L4 审计"},
        "part2_fist_report": None}

    pfist.SERVER_CWD = FIST_ROOT
    f = Client(timeout=180)
    f._send("initialize", {"protocolVersion": "2026-07-28", "capabilities": {},
                           "clientInfo": {"name": "cypy-polish-fistreport3", "version": "1"}})
    before = (f.call("bug_list", {"project_dir": "."}) or {}).get("bugs") or []
    summary = ("[contract] src/server/output_validate.mbt:63-90 parse_artifact 不校验未知字段："
               "拼错/臆造的 artifact 键被静默降级为「文件存在+非空」，verdict 仍是 pass，"
               "且 detail 断言「invariant 全部通过」——L4 硬门可被空检查满足")
    detail = (
        "现象（2026-09-26 实测，server cwd=E:/IDEProjects/AI/Cypy，"
        "证据 .fist-polish-20260926/probe_output_validate3.json）：\n"
        "  A) artifacts=[{path: tests/..., contans: <repo 里不存在的串>}] -> verdict=pass，"
        "detail 「OK（存在/非空/invariant 全部通过）」\n"
        "  B) artifacts=[{path: tests/..., invariant: 必须包含 <不存在的串>}] -> 同样 pass\n"
        "  C) 同一文件同一串改回正确键名 contains -> verdict=fail"
        "（detail 「文件缺少必需字符串: ...」）\n"
        "⇒ A/B 与 C 的差别只在**键名**，说明未知键没有被读取也没有被拒绝。\n"
        "根因：parse_artifact（output_validate.mbt:63-90）只对 path/check_key/contains/"
        "not_contains/min_chars 五个键做 m.get(...)，缺失即回落 \"\"/0，从不检查 m 里剩余键；"
        "check_file_artifact 的 invariant 分支又都以「非空字符串」为开关，于是未知键=没有 invariant"
        "=只要文件存在且非空就 ok=true。\n"
        "危害：output_validate 自称「证据梯 L4 硬门」「任一 artifact 失败即 verdict=fail」，"
        "调用方（尤其按 prompt 模板里 `artifacts 数组（path/check_key + invariant）` 这句话写的 "
        "agent，`invariant` 恰好不是被支持的键）会拿到一条**什么都没验过**的 pass，"
        "而 detail 还替他确认了 invariant 成立——假绿正好发生在最该拦住假绿的那一层。"
        "（注：contains/not_contains/min_chars 三样本轮实测均正常绑定，不是它们坏了。）\n"
        "修复建议：1) parse_artifact 计算 leftover = m 的键去掉上述五个，非空即返回失败 artifact，"
        "detail 写明「artifact 含未知字段 X；支持 contains/not_contains/min_chars/check_key」；"
        "2) pass 文案按**实际评估过的**不变量拼接（不含任何 invariant 时写「仅存在性/非空」），"
        "不要复用固定句「invariant 全部通过」；3) output_validate_test.mbt 补两条用例："
        "未知键必须 fail、纯 {path} 的 pass detail 不得出现 invariant 字样。")
    rep = f.call("report_bug", {"project_dir": ".", "summary": summary, "detail": detail,
                                "severity": "medium", "publish_task": False,
                                "now": utc_now()}, timeout=120)
    after = (f.call("bug_list", {"project_dir": "."}) or {}).get("bugs") or []
    f.close()
    out["part2_fist_report"] = {
        "server_cwd": FIST_ROOT, "publish_task": False,
        "ledger_before": len(before), "ledger_after": len(after),
        "reply": rep if isinstance(rep, dict) else str(rep)[:300], "summary": summary}
    print(f"[part2] FIST-Mbt 账本 {len(before)} -> {len(after)} reply="
          f"{json.dumps(out['part2_fist_report']['reply'], ensure_ascii=False)[:200]}")

    with open(os.path.join(HERE, "ov_audit_and_fist_report.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    bad = [a["bug"] for a in audit if a["verdict"] != "pass"] + ([] if control["agree"] else ["ctrl"])
    print(f"\nAUDIT pass={pass_n}/{len(audit)} 异常={bad}")
    return 0 if not bad and control["agree"] else 1


if __name__ == "__main__":
    sys.exit(main())
