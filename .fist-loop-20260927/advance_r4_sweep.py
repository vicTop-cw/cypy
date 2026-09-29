"""R4-推进 法⑤＋法⑥：一次两棵树扫描，同时回答「产物动没动」和「语料有没有新增红」。

同一批 `examples/*.cypy` 在改前树与改后树各跑一遍 CLI，逐文件记两件事：
① 产物面（法⑤）：把时间戳一类必然漂移的行剔掉后，两边 `.pyx` 是否逐字相同；
   允许不同的只有**文本里出现了本环新放行名字**的文件 —— 这条是结构判据，不是长度地板。
② 语料面（法⑥）：改后相对改前**新增**的诊断行必须为零（`Never` 那类只可能少、不可能多）。

「零新增」这种结论最容易是空集蒙出来的，所以同一趟里放两支见证夹具：
用 `Never` 的夹具必须两态不同（尺子看得见被测形状），用 `NeverX` 的夹具必须两态都报（不是恒绿）。
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

OUT6 = HERE / "advance_r4_corpus.json"
OUT5 = HERE / "advance_r4_codegen_diff.json"
NEW_NAMES = ["Never", "repr", "open", "iter"]
WITNESS = [("witness_never", "a4_never_min.cypy"), ("witness_bogus", "a4_neg_bogus_type.cypy")]
CHECKS: list = []
REFUSE: list = []


def one(src: Path, tag: str) -> dict:
    """把同一个源文件按同一相对形状放进化前/改后两棵树，各跑一遍 CLI。"""
    out = {}
    for lane, tree in (("before", LIB.BEFORE_TREE), ("after", LIB.AFTER_TREE)):
        d = tree / "sweep"
        d.mkdir(parents=True, exist_ok=True)
        dst = d / (tag + ".cypy")
        dst.write_bytes(src.read_bytes())
        out_dir = LIB.TMP / f"sw_{lane}_{tag}"
        r = LIB.transpile(dst.relative_to(tree), tree, out_dir)
        out[lane] = {"rc": r["rc"], "errors": sorted(set(r["undefined_names"])),
                     "err_tail": r["stdout_tail"],
                     "pyx": LIB.strip_volatile(LIB.pyx_of(out_dir))}
    return out


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    before = LIB.build_tree(LIB.BEFORE_TREE, revert=True)
    after = LIB.build_tree(LIB.AFTER_TREE, revert=False)
    if before["edited_shas"] == after["edited_shas"]:
        REFUSE.append("两棵树的分析器 sha 相同 ⇒ 换码未生效，下面的差分是同一份码自比")

    files = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "examples").rglob("*.cypy"))
    rows, wit = [], []
    for i, rel in enumerate(files):
        g = one(ROOT / rel, "f%03d" % i)
        text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        uses_new = [n for n in NEW_NAMES if re.search(r"\b" + n + r"\s*\(", text)]
        new_err = sorted(set(g["after"]["errors"]) - set(g["before"]["errors"]))
        gone_err = sorted(set(g["before"]["errors"]) - set(g["after"]["errors"]))
        identical = g["before"]["pyx"] == g["after"]["pyx"]
        rows.append({"file": rel, "uses_new_names": uses_new,
                     "before_rc": g["before"]["rc"], "after_rc": g["after"]["rc"],
                     "new_error_lines": new_err, "gone_error_lines": gone_err,
                     "pyx_identical": identical,
                     "diff_lines": 0 if identical else
                     sum(1 for a, b in zip(g["before"]["pyx"], g["after"]["pyx"]) if a != b)
                     + abs(len(g["before"]["pyx"]) - len(g["after"]["pyx"]))})
    for key, name in WITNESS:
        g = one(LIB.PROBE / name, key)
        wit.append({"witness": key, "fixture": name,
                    "before_rc": g["before"]["rc"], "after_rc": g["after"]["rc"],
                    "before_errors": g["before"]["errors"], "after_errors": g["after"]["errors"],
                    "pyx_identical": g["before"]["pyx"] == g["after"]["pyx"]})

    new_err_files = [r["file"] for r in rows if r["new_error_lines"]]
    differ_unjustified = [r["file"] for r in rows
                          if not r["pyx_identical"] and not r["uses_new_names"]]
    never_row = next(r for r in wit if r["witness"] == "witness_never")
    bogus_row = next(r for r in wit if r["witness"] == "witness_bogus")

    record(CHECKS, REFUSE, "语料面：改后不得有任何文件新增诊断行", new_err_files, [],
           f"扫描 {len(rows)} 个文件")
    record(CHECKS, REFUSE, "语料基数：扫描数要等于 examples/*.cypy 的实际数",
           len(rows), 77, "少扫＝口径静默收窄（上一环 77 档是基线）")
    record(CHECKS, REFUSE, "产物面：不同之处只允许出现在文本用了新放行名的文件上",
           differ_unjustified, [], "否则就是本环动了 codegen 半径外的东西")
    record(CHECKS, REFUSE, "见证①：用 Never 的夹具必须两态不同（尺子看得见被测形状，0 才不是空集蒙的）",
           [never_row["pyx_identical"], never_row["before_rc"], never_row["after_rc"]],
           [False, 1, 0], "改前红、改后绿且产物确有变化")
    record(CHECKS, REFUSE, "见证②：用 NeverX 的夹具必须两态都报（白名单没有整片放开）",
           [bool(bogus_row["before_errors"]), bool(bogus_row["after_errors"]),
            bogus_row["pyx_identical"]], [True, True, True],
           f"before={bogus_row['before_errors']} after={bogus_row['after_errors']}")
    LIB.cleanup()

    common = {"started": started, "sweep": "同一趟两棵树扫描同时供法⑤与法⑥使用",
              "trees": {"before": before, "after": after}, "witnesses": wit,
              "new_names_whitelisted_this_ring": NEW_NAMES,
              "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    doc6 = dict(common, law="语料零新增红：77 档 examples 在两态下诊断集只减不增",
                samples_scanned=len(rows), files_with_new_errors=new_err_files,
                new_errors_outside_locks=len(new_err_files),
                files_with_errors_gone=[r["file"] for r in rows if r["gone_error_lines"]],
                rows=rows,
                self_checks=[c for c in CHECKS
                             if "语料" in c["label"] or "见证" in c["label"]],
                refuse=sorted(set(REFUSE)))
    doc5 = dict(common, law="产物面不动：未使用新名的源在两态下 .pyx 逐字相同（codegen 未动）",
                files_compared=len(rows),
                all_textual_identical=sum(1 for r in rows if r["pyx_identical"]),
                differing=[r["file"] for r in rows if not r["pyx_identical"]],
                differing_unjustified=differ_unjustified,
                volatile_prefixes=list(LIB.VOLATILE_PREFIX),
                rows=rows,
                self_checks=[c for c in CHECKS
                             if "产物面" in c["label"] or "换码" in c["label"]],
                refuse=sorted(set(REFUSE)))
    OUT6.write_text(json.dumps(doc6, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8", newline="\n")
    OUT5.write_text(json.dumps(doc5, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8", newline="\n")
    print(json.dumps({"corpus_refuse": doc6["refuse"], "codegen_refuse": doc5["refuse"],
                      "scanned": len(rows), "identical": doc5["all_textual_identical"],
                      "differing": doc5["differing"], "witness": [
                          [w["witness"], w["before_rc"], w["after_rc"], w["pyx_identical"]]
                          for w in wit]}, ensure_ascii=False, indent=1))
    return 1 if doc6["refuse"] or doc5["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
