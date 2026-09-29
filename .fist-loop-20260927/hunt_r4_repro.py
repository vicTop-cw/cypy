"""R4-寻虫 法 4：一键复现台账。`python -X utf8 hunt_r4_repro.py <KEY>` 的退出码只有三种读法：

    0 = 现象现形（缺陷复现成功）
    1 = 现象不现形（要么已修好，要么当初的确诊不成立）
    2 = 夹具/工具坏了（跑不动、跑错树、期望本身缺失）——**这个码不许被当成"没问题"**

每个 KEY 就是一张待入账单复现命令的正文；`hunt_r4_filed.json` 里承诺的命令必须与这里逐字一致。
"""

from __future__ import annotations

import datetime
import json
import subprocess
import sys
from pathlib import Path

import hunt_r4_cards as K

HERE = Path(__file__).resolve().parent
OUT = HERE / "hunt_r4_repro.json"
DECLARED = json.loads((HERE / "hunt_r4_declared.json").read_text(encoding="utf-8"))
DECL_BY_ID = {r["id"]: r for r in DECLARED["rows"]}

# 代码面：直接复用候选表，逐条重测
CODE_KEYS = {
    "RC1_func_symbol_typed_as_return": ["C01", "C02", "C03", "C04", "C05"],
    "RC2_no_argument_type_check": ["C06", "C07", "C08"],
    "RC3_struct_field_type_unresolved": ["C09", "C10", "C11"],
    "RC4_internal_repr_in_message": ["C12"],
}
# 文档/CLI/bridge 面：每条用一个"当场可判定"的检查函数
DOC_KEYS = {
    "DOC_status_stale_rows": ["D01", "D02", "D04", "D05", "D07", "D13", "D14"],
    "DOC_cli_face_mismatch": ["D06", "D08", "D09", "D10"],
    "DOC_example_fails": ["D11", "D12"],
    "BRIDGE_cache_side_effect": ["D16"],
    "BRIDGE_c_not_equivalent": ["D17"],
    "SPEC_file_size_redline": ["D15"],
}


def check_code(ids: list) -> dict:
    by_id = {c["id"]: c for c in K.CANDIDATES}
    batch = K.run_batch([by_id[i]["src"] for i in ids])
    out = []
    for i, errs in zip(ids, batch["rows"]):
        cand = by_id[i]
        obs = K.observed_kind(errs)
        broke = any(e.startswith("RUNNER-EXC") for e in errs)
        out.append({"id": i, "case": cand["case"], "reproduces": K.defect_seen(obs, cand),
                    "fixture_broken": broke, "observed_errors": errs})
    return {"rows": out, "identity": batch["ident"]}


def check_doc(ids: list) -> dict:
    """文档/CLI/bridge 面：每条一个**显式**的"什么现象算现形"谓词（不复用 declared 的结论位）。"""
    PRED = {
        "D01": lambda m, rw: bool(m["arity_violation_reported"]),
        "D02": lambda m, rw: not m["errors"],
        "D04": lambda m, rw: bool(m["let_i32"]) and not m["i32_literal_in_compiler"],
        "D05": lambda m, rw: bool(m["mut_errors"]),
        "D06": lambda m, rw: (m["flag_compile"]["rc"] != 0 and m["build_incremental"]["rc"] != 0
                          and m["control_transpile_rc"] == 0),
        "D07": lambda m, rw: bool(m["eight_spaces"]) and m["four_spaces_clean"],
        "D08": lambda m, rw: any("cypyc = " in l and "cypy_hook.hook:main" not in l for l in m["pyproject_scripts"]),
        "D09": lambda m, rw: any("3.9" in l for l in m["pyproject_requires"]),
        "D10": lambda m, rw: bool(m["undocumented_options"]),
        "D11": lambda m, rw: (m.get("json") or {}).get("has_output_files") is False,
        "D12": lambda m, rw: not m["result_symbol_in_cypyc"] and bool(m["only_reader_in_hook"]),
        "D13": lambda m, rw: any(v == "已落地" for v in rw["split_note"].values()),
        "D14": lambda m, rw: bool(m["parser_hits"]) or bool(m["codegen_hits"]),
        "D15": lambda m, rw: m["parser"] > 3000,
        "D16": lambda m, rw: bool((m.get("json") or {}).get("created")),
        "D17": lambda m, rw: bool((m.get("json") or {}).get("module_level_if")),
    }
    out = []
    for i in ids:
        row = DECL_BY_ID.get(i)
        if row is None or i not in PRED:
            out.append({"id": i, "reproduces": False, "fixture_broken": True,
                        "why": "declared 件里没有这一条，或本脚本没给它显式谓词 ⇒ 期望缺失就是夹具坏"})
            continue
        m = row["measured"]
        err = None
        try:
            hit = bool(PRED[i](m, row))
            broke = False
        except (KeyError, TypeError) as exc:
            hit, broke = False, True
            err = f"{type(exc).__name__}: {exc}"
        out.append({"id": i, "verdict_on_disk": row["verdict"], "reproduces": hit,
                    "fixture_broken": broke, "pred_error": err,
                    "quote": row["doc"]["quote"][:120], "at_line": row["doc"]["line"]})
    return {"rows": out}


def selftest() -> int:
    """三态退出码自己也要被证明可达。挑一条**今天行为正确**的对照当复现项：
    它今天就是该报错并报了 ⇒ "缺陷现象=不报"不成立 ⇒ 脚本必须判 1（不现形）。
    若这里返回 0，就是在把正确程序宣布成"缺陷已复现"。"""
    ctl_name = "callback_arity_reported"
    src, spec = K.CTLS[ctl_name]
    pseudo = {"id": "SELFTEST", "kind": "false_negative", "case": ctl_name, "src": src}
    batch = K.run_batch([src])
    obs = K.observed_kind(batch["rows"][0])
    reproduced = K.defect_seen(obs, pseudo)
    print(json.dumps({"selftest": "把今天行为正确的对照塞进复现清单", "ctl": ctl_name,
                      "spec": spec, "observed_errors": obs["errors"],
                      "defect_phenomenon_reproduced": reproduced,
                      "must_be": False, "meaning": "返回 1 = rc=1 这一态可达"},
                     ensure_ascii=False))
    return 0 if reproduced else 1


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        return selftest()
    if len(sys.argv) > 1 and sys.argv[1] not in ("--all",):
        want = sys.argv[1]
        keys = [k for k in list(CODE_KEYS) + list(DOC_KEYS) if k == want]
        if not keys:
            print(json.dumps({"rc": 2, "why": f"未知 KEY {want}"}, ensure_ascii=False))
            return 2
    else:
        keys = list(CODE_KEYS) + list(DOC_KEYS)
    report = {"at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
              "keys": {}, "started": datetime.datetime.now(datetime.timezone.utc).isoformat(
                  timespec="seconds")}
    bad_fixture = False
    not_reproduced = []
    for key in keys:
        if key in CODE_KEYS:
            res = check_code(CODE_KEYS[key])
        else:
            res = check_doc(DOC_KEYS[key])
        rows = res["rows"]
        broke = [r["id"] for r in rows if r.get("fixture_broken")]
        misses = [r["id"] for r in rows if not r["reproduces"] and not r.get("fixture_broken")]
        report["keys"][key] = {"cases": len(rows), "reproduced": len(rows) - len(misses) - len(broke),
                               "not_reproduced": misses, "fixture_broken": broke,
                               "identity": res.get("identity"), "rows": rows,
                               "exit_code": 2 if broke else (0 if not misses else 1)}
        bad_fixture = bad_fixture or bool(broke)
        not_reproduced += [f"{key}/{m}" for m in misses]
    # 三态退出码**各自都要被证明可达**：1 由 selftest 现取，2 由未知键现取，0 由上面十条现取
    st1 = selftest()
    unknown = subprocess.run([sys.executable, "-X", "utf8", str(Path(__file__).name), "NOPE_KEY"],
                             capture_output=True, text=True, encoding="utf-8", timeout=120)
    zeros = sum(1 for v in report["keys"].values() if v["exit_code"] == 0)
    report["state_reached"] = {
        "0_all_reproduced": zeros,
        "1_not_reproduced_selftest_rc": st1,
        "2_fixture_broken_unknown_key_rc": unknown.returncode,
        "meaning": "0=全部现形 / 1=把今天正确的形状当复现项必判不现形 / 2=未知键或坏谓词必判夹具坏"}
    report["all_exit_codes_zero"] = (zeros == len(report["keys"]) and st1 == 1
                                    and unknown.returncode == 2)
    if not report["all_exit_codes_zero"]:
        report["refuse"] = ["三态退出码没有各自可达 ⇒ 这张台账不可信"]
    (HERE / "hunt_r4_repro.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"keys": {k: v["exit_code"] for k, v in report["keys"].items()},
                      "not_reproduced": not_reproduced, "fixture_broken": bad_fixture},
                     ensure_ascii=False, indent=1))
    if bad_fixture:
        return 2
    return 0 if not not_reproduced else 1


if __name__ == "__main__":
    sys.exit(main())
