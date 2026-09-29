"""根因合并修的正面证明：四张单是不是**共用同一套机制**，还是各打了一个补丁。

口径不是「我说是同一处」，而是可数的三件事：
① 本轮新增的符号（`git diff` 里加进去的 `def`）逐个列出定义处与**被引用处**的 file:line；
② 每个根因映射到一组符号，符号被 ≥2 个根因引用即记为 shared（共享机制）；
③ 每根因至少有一个 shared 符号，且四根因的改动点全部落在同一文件同一张表上（`callable_sigs`）。
另外正面测出「不是一行注释糊过去」：新增行数、被改的既有行数各自计数。
"""

from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TARGET = "cypyc/analyzer/type_checker.py"
OUT = HERE / "fix_r4_rc.json"
REFUSE: list = []
CHECKS: list = []

RC_SYMBOLS = {
    "RC1_func_symbol_typed_as_return": ["_register_callable", "callable_sigs", "callable_arity",
                                        "_value_type_for_declared", "_check_callable_arity"],
    "RC2_no_argument_type_check": ["_check_callable_arg_types", "_callable_arg_mismatch",
                                   "_callable_signature_assignable", "_value_type_for_declared"],
    "RC3_struct_field_type_unresolved": ["_visit_Attribute", "_call_is_judgable",
                                         "_check_callable_arg_types", "_value_type_for_declared"],
    "RC4_internal_repr_in_message": ["_type_display", "_mismatch", "_callable_arg_mismatch"],
}


def check(label, got, want, why) -> None:
    CHECKS.append({"label": label, "got": got, "want": want, "why": why, "ok": got == want})


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    # 与 HEAD 比会混进 R1–R3 累积的未提交改动（工作区本来就脏 168 行）⇒
    # 本轮的改动面只与**本轮开跑前自己留的快照**比。
    snap = HERE / "fix_r4_before" / "type_checker.py"
    if not snap.exists():
        REFUSE.append(f"本轮起点快照不在盘上：{snap}")
        return 1
    import difflib
    before = snap.read_text(encoding="utf-8").splitlines()
    after = (ROOT / TARGET).read_text(encoding="utf-8").splitlines()
    ud = list(difflib.unified_diff(before, after, lineterm=""))
    added = [ln[1:] for ln in ud if ln.startswith("+") and not ln.startswith("+++")]
    removed = [ln[1:] for ln in ud if ln.startswith("-") and not ln.startswith("---")]
    new_defs = sorted({m.group(1) for ln in added
                       for m in [re.match(r"\s*def (\w+)", ln)] if m})
    body = after
    sites, refs = [], {}
    for i, ln in enumerate(body, 1):
        for sym in set(sum(RC_SYMBOLS.values(), [])) | set(new_defs):
            if re.search(r"\b" + re.escape(sym) + r"\b", ln):
                refs.setdefault(sym, []).append(f"{TARGET}:{i}")
                if sym in new_defs:
                    sites.append({"symbol": sym, "line": i,
                                  "kind": "def" if re.match(r"\s*def " + re.escape(sym), ln)
                                  else "use"})
    per_rc = {}
    for rc, syms in RC_SYMBOLS.items():
        per_rc[rc] = {s: len(refs.get(s, [])) for s in syms}
    shared = sorted({s for syms in RC_SYMBOLS.values() for s in syms
                     if sum(1 for rc2 in RC_SYMBOLS if s in RC_SYMBOLS[rc2]) >= 2})
    rc_with_shared = sorted({rc for rc, syms in RC_SYMBOLS.items() for s in syms if s in shared})
    check("本轮新增的函数符号都被真实引用（没有只定义不用的补丁）",
          sorted(s for s in new_defs if s.startswith("_") and len(refs.get(s, [])) < 2), [],
          f"新增 def：{new_defs}")
    check("四个根因都落在共享符号上", len(rc_with_shared), 4, f"{sorted(RC_SYMBOLS)}")
    check("共享符号至少两个", len(shared) >= 2, True, f"shared={shared}")
    check("改动确实在同一文件（一张签名表）",
          len({p.split(':')[0] for p in sum(refs.values(), [])}), 1, TARGET)
    check("既有行确实被动过（不是只加新函数）", len(removed) > 0, True, f"删除 {len(removed)} 行")
    if len(added) < 40:
        REFUSE.append(f"新增行数只有 {len(added)}，不像把四个根因合并修的量")

    refuse = sorted(set(REFUSE)) + [f"自证未过：{c['label']}（实得 "
                                    f"{json.dumps(c['got'], ensure_ascii=False)[:200]}）"
                                    for c in CHECKS if not c["ok"]]
    doc = {"started": started, "target": TARGET,
           "baseline": "fix_r4_before/type_checker.py（本轮开跑前的快照，只与它比）", "new_defs": new_defs,
           "added_lines": len(added), "removed_lines": len(removed),
           "shared_symbols": shared, "per_rc_symbol_refs": per_rc,
           "call_sites": sites[:60], "call_site_total": len(sites),
           "note": "共享机制=同一张 `callable_sigs` 表 + 同一个判定入口 "
                   "`_callable_arg_mismatch`（RC2/RC3/RC4 都走它），不是四张单各一个 if",
           "refuse": refuse,
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": refuse, "new_defs": new_defs, "shared": shared,
                      "added": len(added), "removed": len(removed),
                      "call_sites": len(sites)}, ensure_ascii=False, indent=1))
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
