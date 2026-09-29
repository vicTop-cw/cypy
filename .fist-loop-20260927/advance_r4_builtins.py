"""R4-推进 法②：把文档里已经在用、此前只在名称表缺席的三个内建名 `repr`/`open`/`iter` 放行。

半径的两侧都要能红：
① 侧「声明面」——每个名字先由 `SYNTAX/**` 的**实测**引用行证明它属于「已声明未实现」，
   引用行号是量出来的（不是从注释里抄的），引用行本身不含 `name(` 时这条判据会红；
② 侧「未越界」——六个**文档没有声明**的内建名（chr/hex/pow/round/divmod/bytes）在同一棵改后树
   必须仍然报 `Undefined name`。若哪天有人把白名单整片放开，这一格立刻红。
两棵树读同一份夹具（字节自证），改前必红、改后必绿，红因只能在名称表。
"""

from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import advance_r4_lib as LIB  # noqa: E402
from loop_kit import record  # noqa: E402

OUT = HERE / "advance_r4_builtins.json"
# (名, 夹具, 文档引用 [路径, 行号]) —— 行号由本件重新 grep 实测核对，不接受手抄
ADDED = [("repr", "a4_repr_ok.cypy", ["SYNTAX/05-struct.md", 53]),
         ("open", "a4_open_ok.cypy", ["SYNTAX/14-syntax-sugar.md", 174]),
         ("iter", "a4_iter_ok.cypy", ["SYNTAX/06d-builtin-magic-traits.md", 264])]
NOT_ADDED = [("chr", "a4_chr.cypy"), ("hex", "a4_hex.cypy"), ("pow", "a4_pow.cypy"),
             ("round", "a4_round.cypy"), ("divmod", "a4_divmod.cypy"),
             ("bytes", "a4_bytes.cypy")]
CHECKS: list = []
REFUSE: list = []


def doc_hits(name: str) -> list:
    """在冻结语料（`SYNTAX/**` + `PROJECT-SPEC/**`）里实测 `name(` 的引用行。

    两个方向都要它：放行名必须**查得到**引用行，未放行的名必须**查不到** —— 所以口径是全集，
    不是只挑一处。
    """
    pat = re.compile(r"\b" + re.escape(name) + r"\s*\(")
    hits = []
    for base in ("SYNTAX", "PROJECT-SPEC"):
        for p in sorted((ROOT / base).rglob("*.md")):
            for i, ln in enumerate(
                    p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if pat.search(ln):
                    hits.append({"doc": p.relative_to(ROOT).as_posix(), "line": i,
                                 "text": ln.strip()[:90]})
    return hits


def mentions(name: str, errs: list) -> bool:
    return any(f"'{name}'" in x for x in errs)


def run_case(name: str, fname: str, tree_pair: bool = True) -> dict:
    src = LIB.PROBE / fname
    rel_b, rel_a = LIB.stage_probe(LIB.BEFORE_TREE, src), LIB.stage_probe(LIB.AFTER_TREE, src)
    if (LIB.BEFORE_TREE / rel_b).read_bytes() != (LIB.AFTER_TREE / rel_a).read_bytes():
        REFUSE.append(f"两棵树读的夹具字节不一致：{fname}")
    rb = LIB.transpile(LIB.BEFORE_TREE / rel_b, LIB.BEFORE_TREE, LIB.TMP / f"b4_{name}")
    ra = LIB.transpile(LIB.AFTER_TREE / rel_a, LIB.AFTER_TREE, LIB.TMP / f"af_{name}")
    return {"name": name, "probe": f".fist-loop-20260927/advance_r4_probe/{fname}",
            "before_rc": rb["rc"], "after_rc": ra["rc"],
            "before_undefined": rb["undefined_names"], "after_undefined": ra["undefined_names"],
            "before_mentions": mentions(name, rb["undefined_names"]),
            "after_mentions": mentions(name, ra["undefined_names"]),
            "after_products": ra["products"], "tree_pair": tree_pair}


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    before = LIB.build_tree(LIB.BEFORE_TREE, revert=True)
    after = LIB.build_tree(LIB.AFTER_TREE, revert=False)
    idb, ida = LIB.identity_probe(LIB.BEFORE_TREE), LIB.identity_probe(LIB.AFTER_TREE)
    if not (idb["inside"] and ida["inside"]):
        REFUSE.append(f"身份探针失败：before={idb.get('scope')} after={ida.get('scope')}")

    evidence = []
    for name, fname, cited in ADDED:
        hits = doc_hits(name)
        wanted = f"{Path(cited[0]).as_posix()}:{cited[1]}"
        measured = [h for h in hits if f"{h['doc']}:{h['line']}" == wanted]
        evidence.append({"name": name, "doc_hits_total": len(hits),
                         "cited": wanted, "cited_found": bool(measured),
                         "first_hit": (hits or [{}])[0],
                         "cited_text": (measured or [{}])[0].get("text", "")})
        record(CHECKS, REFUSE, f"{name}：文档声明面必须实测到引用行 {wanted}",
               [len(hits) >= 1, bool(measured)], [True, True],
               f"实得 {len(hits)} 处，引用行在档 {bool(measured)}")

    added_rows = [run_case(n, f) for n, f, _ in ADDED]
    for r in added_rows:
        record(CHECKS, REFUSE, f"{r['name']}：改后名称面放行（rc=0 且不再报 Undefined name）",
               [r["after_rc"], r["after_mentions"]], [0, False],
               f"after_undefined={r['after_undefined']}")
        record(CHECKS, REFUSE, f"{r['name']}：改前必红且红在该名上",
               [r["before_rc"] != 0, r["before_mentions"]], [True, True],
               f"before_rc={r['before_rc']} before_undefined={r['before_undefined']}")

    not_added_rows = [run_case(n, f) for n, f in NOT_ADDED]
    for r in not_added_rows:
        hits = doc_hits(r["name"])
        r["doc_call_sites"] = len(hits)
        r["doc_hits_sample"] = [f"{h['doc']}:{h['line']}" for h in hits[:2]]
        record(CHECKS, REFUSE, f"{r['name']}：文档未声明的主张要有实测支撑（冻结语料 0 处 `name(`）",
               len(hits), 0, f"实得 {r['doc_hits_sample']}")
        record(CHECKS, REFUSE, f"{r['name']}：文档未声明 ⇒ 改后仍须被拒（半径不外溢）",
               [r["after_rc"] != 0, r["after_mentions"]], [True, True],
               f"after_rc={r['after_rc']} after_undefined={r['after_undefined']}")

    canary = {
        "three_added_names_now_accepted": all(r["after_rc"] == 0 for r in added_rows),
        "six_undocumented_builtins_still_rejected": all(
            r["after_rc"] != 0 and r["after_mentions"] for r in not_added_rows),
        "red_moves_only_in_name_table": all(
            r["before_rc"] != 0 and r["before_mentions"] for r in added_rows),
        "doc_citation_lines_measured_not_copied": all(
            e["cited_found"] and f"{e['name']}(" in e["cited_text"] for e in evidence),
        "undocumented_names_have_zero_doc_call_sites": all(
            r["doc_call_sites"] == 0 for r in not_added_rows),
    }
    record(CHECKS, REFUSE, "canary 五格必须同时成立（条数也要钉住，空 canary 不算绿）",
           [len(canary), all(canary.values())], [5, True],
           json.dumps(canary, ensure_ascii=False))
    LIB.cleanup()

    doc = {"started": started,
           "law": "文档已用、名称表缺席的三个内建名（repr/open/iter）在分析器名称面补齐",
           "added": [r["name"] for r in added_rows],
           "not_added": [r["name"] for r in not_added_rows],
           "doc_evidence": evidence, "cases": added_rows + not_added_rows,
           "added_rows": added_rows, "not_added_rows": not_added_rows,
           "edited_files": [{"path": p, "before_sha": LIB.sha(LIB.TMP / Path(p).name),
                             "after_sha": LIB.sha(ROOT / p)} for p in LIB.EDITED],
           "trees": {"before": before, "after": after,
                     "identity_before": idb, "identity_after": ida},
           "canary": canary, "self_checks": CHECKS, "refuse": sorted(set(REFUSE)),
           "note": "只补名称面：产物里对这些调用的翻译沿用既有 codegen（本环未动 codegen）；"
                   "六个未声明名保持被拒，是本环「半径限已声明未实现」的反向证据",
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": doc["refuse"], "canary": canary,
                      "added": {r["name"]: [r["before_rc"], r["after_rc"]] for r in added_rows},
                      "not_added": {r["name"]: [r["before_rc"], r["after_rc"]]
                                    for r in not_added_rows}},
                     ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
