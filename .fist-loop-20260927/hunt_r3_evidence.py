#!/usr/bin/env python3
"""R3-寻虫 的四件台账：清点 / 定位声明 / 一键复现 / 子代理主张对账。

口径（为什么分四件）：
- `hunt_r3_scan.json`：**先清点再取虫**——狩猎面的符号台账 + CLI 对外承诺（`--help` 实际输出），
  否则"没找到"和"没找"分不清；
- `hunt_r3_declared.json`：每条候选**先读它自己的定位声明**（模块/类 docstring、SYNTAX 状态表、
  `--help`）——前几轮反复出现"覆盖少/词撞/硬编码"其实是设计，一轮撤回 5 条；
- `hunt_r3_repro.json`：入账件里承诺的复现命令必须**真跑过**，退出码三态（0 现形 / 1 不现形 /
  2 夹具坏）；v1 的 detail 里塞的是嵌套引号 `python -c "..."`，在本平台根本跑不动；
- `hunt_r3_subagent_claims.json`：子代理给的 8 条主张逐条与我**亲测**结果对账，
  含我自己两版探针的误判（同进程改 PYTHONHASHSEED 假绿、把模块 docstring 读成类 docstring）。
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

HUNT_DIRS = ["cypyc/transformer", "cypyc/analyzer", "cypyc/project", "cypy_bridge", "cypyc/cli.py"]
CONFIRM = json.loads((HERE / "hunt_r3_confirm.json").read_text(encoding="utf-8"))
BY_ID = {c["id"]: c for c in CONFIRM["cases"]}
IDS = [c["id"] for c in CONFIRM["cases"]]

SUBAGENT_CLAIMS = {
    "C1": "GenericTransformer matches an attribute no generic node has … collects zero generic definitions",
    "C2": "comptime ignores Param.default_value … evaluate_comptime degrades it to None (silent drop)",
    "C3": "transpile flags documented in its own help text are unreachable",
    "C4": "CUnion's own docstring example crashes",
    "C5": "realloc lies about its return type … frees ptr and return None for size <= 0",
    "C6": "get_compilation_order is nondeterministic and contradicts its docstring … Also zero callers repo-wide",
    "C7": "Dead in-degree computation … first 8 lines unreachable in effect",
    "C8": "BuildBlockChecker docstring rule #2 is unimplemented … Checker is wired live at cypy_hook/hook.py:272-275",
}
# 我自己探针的历史版本结论（不是子代理说的，是我说的，说错了要认）
MY_OWN_MISJUDGEMENTS = {
    "C6": "v1 在同进程里改 os.environ['PYTHONHASHSEED'] 跑 5 次 ⇒ distinct=1，判成'不现形'；"
          "字符串哈希在解释器启动时就定，同进程改环境变量根本改不了它 ⇒ 必须起子进程（v2 起 5 个种子，distinct=4）。",
    "C7": "v1 用 `in_degree_assigned_again`/窗口文本猜死码，v2 换成 AST 口径（pass-only 循环 + Load 计数）"
          "后实测 pass_only_loops=[]、in_degree_loads=6 ⇒ 子代理那条**不成立**，撤回、不入账。",
    "C8": "v3 读 inspect.getdoc(类) 找规则清单 ⇒ 规则其实写在**模块** docstring，读空之后把 'pos 不成立' "
          "误判成 REJECTED（差点漏掉一条真缺陷）。v4 改读 sys.modules[...].__doc__ 才现形。",
}


def sh(cmd, timeout=240, env=None):
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout, env=env)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def scan() -> dict:
    rows = []
    for rel in HUNT_DIRS:
        base = ROOT / rel
        files = [base] if base.is_file() else sorted(p for p in base.rglob("*.py")
                                                    if "__pycache__" not in p.parts)
        for p in files:
            try:
                tree = ast.parse(p.read_text(encoding="utf-8"))
            except SyntaxError as exc:
                rows.append({"file": str(p.relative_to(ROOT)).replace("\\", "/"), "parse_error": str(exc)})
                continue
            classes = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
            funcs = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
            rows.append({
                "file": str(p.relative_to(ROOT)).replace("\\", "/"),
                "classes": len(classes),
                "module_funcs": len(funcs),
                "public_symbols": len([n for n in classes + funcs if not n.startswith("_")]),
                "module_doc_declared_rules": [l.strip() for l in (ast.get_docstring(tree) or "").split("\n")
                                              if re.match(r"^\s*\d+\.\s", l)],
            })
    rc, help_txt = sh([sys.executable, "-X", "utf8", "-m", "cypyc", "--help"])
    rc2, tp_help = sh([sys.executable, "-X", "utf8", "-m", "cypyc", "transpile", "--help"])
    flags = re.findall(r"--[a-z][a-z-]+", tp_help)
    return {
        "hunt_dirs": HUNT_DIRS,
        "files": len(rows),
        "rows": rows,
        "cli_declared": {
            "top_help_rc": rc,
            "subcommands": re.findall(r"\{([a-z,]+)\}", help_txt)[:1],
            "transpile_help_rc": rc2,
            "transpile_flags": sorted(set(flags)),
        },
        "candidates_total": len(IDS),
        "confirmed_ids": CONFIRM["confirmed"],
        "refuse": [],
    }


def declared() -> dict:
    rows = []
    for cid in IDS:
        case = BY_ID[cid]
        rows.append({
            "id": cid,
            "declared_scope_read": case.get("declared"),
            "claim": case["claim"],
            "verdict": case["verdict"],
            "own_text_evidence": case["ctl"]["observed"],
        })
    syntax_notes = []
    for rel in ["SYNTAX/19-comptime.md", "SYNTAX/11-generics.md"]:
        p = ROOT / rel
        if p.exists():
            txt = p.read_text(encoding="utf-8").split("\n")
            syntax_notes.append({"file": rel,
                                 "lines": [f"{i+1}:{l.strip()}" for i, l in enumerate(txt)
                                           if "未实现" in l or "当前仅" in l][:6]})
    return {"per_candidate": rows, "syntax_self_declared": syntax_notes, "refuse": []}


def repro() -> dict:
    rows, refuse = [], []
    for cid in IDS:
        rc, out = sh([sys.executable, "-X", "utf8", str(HERE / "hunt_r3_repro.py"), cid], timeout=420)
        try:
            parsed = json.loads(out.strip().split("\n")[-1])
        except json.JSONDecodeError:
            parsed = {"raw": out[-200:]}
        rows.append({"id": cid, "rc": rc, "observed": parsed})
        verdict = BY_ID[cid]["verdict"]
        if rc == 2:
            refuse.append(f"{cid} 复现脚本自己跑不动（rc=2）")
        elif verdict == "CONFIRMED" and rc != 0:
            refuse.append(f"{cid} 已 CONFIRMED 但复现退出码 {rc}⇒ 入账件里的'可复跑'是假的")
        elif verdict == "REJECTED" and rc != 1:
            refuse.append(f"{cid} 已 REJECTED 但复现退出码 {rc}（要 1=不现形）")
        # DESIGN（自述未实现 ⇒ 撤回）不锁退出码：缺陷形状在不在都对，重点是它不该占号
    return {"per_id": rows, "refuse": refuse}


def claims() -> dict:
    rows = []
    for cid in IDS:
        rows.append({
            "id": cid,
            "subagent_claim_verbatim": SUBAGENT_CLAIMS[cid],
            "my_measured_verdict": BY_ID[cid]["verdict"],
            "pos_ok": BY_ID[cid]["pos"]["ok"],
            "ctl_ok": BY_ID[cid]["ctl"]["ok"],
            "my_probe_history": MY_OWN_MISJUDGEMENTS.get(cid, ""),
        })
    agree = [r for r in rows if r["subagent_claim_verbatim"] and r["my_measured_verdict"] == "CONFIRMED"]
    return {
        "rows": rows,
        "subagent_confirmed_by_me": [r["id"] for r in agree],
        "withdrawn": [{"id": r["id"], "v": r["my_measured_verdict"]} for r in rows
                      if r["my_measured_verdict"] != "CONFIRMED"],
        "refuse": [],
    }


def main() -> int:
    products = {"hunt_r3_scan.json": scan(), "hunt_r3_declared.json": declared(),
                "hunt_r3_repro.json": repro(), "hunt_r3_subagent_claims.json": claims()}
    refuse = []
    for name, doc in products.items():
        if not doc.get("rows") and not doc.get("per_id") and not doc.get("per_candidate") \
                and not doc.get("files"):
            refuse.append(f"{name} 空台账")
        if doc.get("refuse"):
            refuse.extend(f"{name}: {m}" for m in doc["refuse"])
        (HERE / name).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                                 encoding="utf-8", newline="\n")
    summary = {
        "scan_files": products["hunt_r3_scan.json"]["files"],
        "cli_flags_transpile": products["hunt_r3_scan.json"]["cli_declared"]["transpile_flags"],
        "repro_rcs": {r["id"]: r["rc"] for r in products["hunt_r3_repro.json"]["per_id"]},
        "withdrawn": products["hunt_r3_subagent_claims.json"]["withdrawn"],
        "refuse": refuse,
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
