"""R4-推进 法①：`Never` 类型名在分析器名称面落地，且只有文档声明的形状被放行。

承重方式三件：① 文档自己给出的工作例（`SYNTAX/02-type-annotations.md:125-133`）逐字复现并真跑
CLI；② 负对照——`NeverX` 这种**没在文档里**的名字必须仍然报 `Undefined name`，否则白名单等于放开；
③ 两棵树对照——同一份源在改前树必红、在改后树必绿，且产物签名 `-> NoReturn` 与既有 codegen
实现一致（本环没动 codegen，红只可能来自名称表）。
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import advance_r4_lib as LIB  # noqa: E402
from loop_kit import record  # noqa: E402

OUT = HERE / "advance_r4_never.json"
DOC = ROOT / "SYNTAX" / "02-type-annotations.md"
CASES = [("doc_worked_example", "a4_doc_never.cypy", "expect_green", 125, 133),
         ("never_min_return", "a4_never_min.cypy", "expect_green", None, None),
         ("never_in_param_position", "a4_never_param.cypy", "expect_green_no_claim", None, None),
         ("bogus_type_name_control", "a4_neg_bogus_type.cypy", "expect_red_undefined", None, None),
         ("bogus_function_control", "a4_neg_bogus_fn.cypy", "expect_red_undefined", None, None)]
CHECKS: list = []
REFUSE: list = []


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    doc_lines = DOC.read_text(encoding="utf-8", errors="replace").splitlines()
    quote = "\n".join(doc_lines[121:133])
    before = LIB.build_tree(LIB.BEFORE_TREE, revert=True)
    after = LIB.build_tree(LIB.AFTER_TREE, revert=False)
    idb, ida = LIB.identity_probe(LIB.BEFORE_TREE), LIB.identity_probe(LIB.AFTER_TREE)
    if not (idb["inside"] and ida["inside"]):
        REFUSE.append(f"身份探针失败：before={idb.get('scope')} after={ida.get('scope')}")

    rows = []
    for name, fname, expect, dl, dr in CASES:
        src = LIB.PROBE / fname
        rel_b, rel_a = LIB.stage_probe(LIB.BEFORE_TREE, src), LIB.stage_probe(LIB.AFTER_TREE, src)
        same_bytes = ((LIB.BEFORE_TREE / rel_b).read_bytes()
                      == (LIB.AFTER_TREE / rel_a).read_bytes())
        if not same_bytes:
            REFUSE.append(f"两棵树读的夹具字节不一致：{fname}")
        ob = LIB.TMP / f"out_{name}_before"
        oa = LIB.TMP / f"out_{name}_after"
        rb = LIB.transpile(LIB.BEFORE_TREE / rel_b, LIB.BEFORE_TREE, ob)
        ra = LIB.transpile(LIB.AFTER_TREE / rel_a, LIB.AFTER_TREE, oa)
        pyx = LIB.pyx_of(oa)
        rows.append({"case": name, "probe": f".fist-loop-20260927/advance_r4_probe/{fname}",
                     "doc_lines": [dl, dr] if dl else [], "expect": expect,
                     "before": {k: rb[k] for k in ("rc", "undefined_names",
                                                   "duplicate_error_lines")},
                     "after": {k: ra[k] for k in ("rc", "undefined_names",
                                                  "duplicate_error_lines")},
                     "after_pyx_signature": next((ln.strip() for ln in pyx.splitlines()
                                                  if "def " in ln), "")})
        if expect == "expect_green":
            record(CHECKS, REFUSE, f"{name}：改后必绿", ra["rc"], 0,
                   f"undefined={ra['undefined_names']}")
            record(CHECKS, REFUSE, f"{name}：改前必红（红在 Undefined name 上）",
                   rb["rc"] != 0 and any("Undefined name" in x for x in rb["undefined_names"]),
                   True, f"before={rb}")
        if expect == "expect_red_undefined":
            record(CHECKS, REFUSE, f"{name}：没在文档里的名字改后仍须被拒",
                   ra["rc"] != 0 and len(ra["undefined_names"]) >= 1, True,
                   f"after={ra['undefined_names']}")
        if expect == "expect_green_no_claim":
            record(CHECKS, REFUSE, f"{name}：名称面放行后不再报 Undefined name",
                   ra["rc"], 0, f"undefined={ra['undefined_names']}")
            rows[-1]["annotation_kept_in_pyx"] = "Never" in pyx

    never_rows = [r for r in rows if r["expect"].startswith("expect_green")]
    doc_row = next(r for r in rows if r["case"] == "doc_worked_example")
    doc_pyx = LIB.pyx_of(LIB.TMP / "out_doc_worked_example_after")
    record(CHECKS, REFUSE, "文档工作例的产物签名必须映射成 NoReturn（codegen 未动）",
           "NoReturn" in doc_pyx, True,
           f"产物 {doc_row['after_pyx_signature'] or '（未生成）'}；"
           "codegen 侧 type_mapper 早已支持 Never→NoReturn，本环只在名称面补齐")

    green_now = bool(never_rows) and all(r["after"]["rc"] == 0 for r in never_rows)
    bogus_still_red = all(r["after"]["rc"] != 0 for r in rows
                          if r["expect"] == "expect_red_undefined")
    canary = {"never_now_accepted": green_now,
              "bogus_names_still_rejected": bogus_still_red,
              "red_moves_only_in_name_table": all(
                  r["before"]["rc"] != 0 and r["before"]["undefined_names"]
                  for r in never_rows)}
    record(CHECKS, REFUSE, "canary：两格必须同时成立（放行新名 + 不放行任意名）",
           [green_now, bogus_still_red], [True, True], json.dumps(canary, ensure_ascii=False))

    dup = [r["after"]["duplicate_error_lines"] - len(r["after"]["undefined_names"]) for r in rows]
    LIB.cleanup()
    doc = {"started": started, "law": "Never 类型名在分析器名称面落地（含文档工作例与负对照）",
           "doc_quote": quote, "doc_source": "SYNTAX/02-type-annotations.md",
           "edited_files": [{"path": p, "before_sha": LIB.sha(LIB.TMP / Path(p).name),
                             "after_sha": LIB.sha(ROOT / p)} for p in LIB.EDITED],
           "trees": {"before": before, "after": after,
                     "identity_before": idb, "identity_after": ida},
           "cases": rows, "negative_controls": [r for r in rows
                                                if r["expect"] == "expect_red_undefined"],
           "worked_example_from_doc": next(r for r in rows if r["case"] == "doc_worked_example"),
           "duplicate_error_lines_delta": dup,
           "canary": canary, "self_checks": CHECKS, "refuse": sorted(set(REFUSE)),
           "note": "参数位只判「名称面不再报 Undefined name」，产物是否保留注解按实测记录"
                   "（annotation_kept_in_pyx），不写成「已支持参数位 Never」的语义主张",
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": doc["refuse"], "cases": len(rows),
                      "canary": canary,
                      "rc_after": [r["after"]["rc"] for r in rows],
                      "rc_before": [r["before"]["rc"] for r in rows]},
                     ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
