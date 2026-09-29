"""R10 报告引用核验：报告里每条 BUG 号、每个路径、每个"逐字"结论、每个 file:line 锚都要反解到证据。

反解优先于手写针：
- 「逐字结论」从报告正文里按形状自动抽取（含 CONCLUSION / passed / PASS= / Total: 的反引号串），
  再回到 `logs/` 与 `*.log|*.out|*.json` 里找 —— 凭记忆写的针不算针；
- file:line 锚先定位真实行号，再断言落进报告声明的区间（漂移即红）；
- 账本类数字（open / headers / FIXED / severity 分布）从盘上重算，与报告逐格比；
- 两条 canary：漂一格的锚必须红、不存在的 BUG 号必须被点名 ⇒ 证明这套门不是装饰。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "reports" / "2026-09-29" / "T0r116-cypy-selfdrive-r10-report.md"
OUT = HERE_OUT = Path(__file__).with_name("verify_r10_report.json")
LEDGER = ROOT / "memory" / "bugs.md"

# 报告里声明"实测"的锚（needle 是本轮我亲笔的代码文本，脚本按 needle 定位真实行号）
ANCHORS = [
    ("cypyc/parser/parser.py", "self.type_args = type_args or []", 650, 659),
    ("cypyc/parser/parser.py", "candidate: Optional[List[Any]] = None", 3855, 3885),
    ("cypyc/parser/parser.py", "type_args_for_call = []", 3943, 3951),
    ("cypyc/codegen/cython_generator.py", "类型实参在产物里必须**擦除**", 3814, 3818),
    ("cypyc/analyzer/type_checker.py", "def _bind_explicit_type_args", 1272, 1301),
    ("cypyc/analyzer/type_checker.py", "explicit_binding = self._bind_explicit_type_args", 1330, 1347),
    ("cypy_bridge/compiler.py", "调用点的 `<…>` 是类型实参", 284, 289),
    ("SYNTAX/33-type-constraints-subtypes-dispatch.md", "P-1.8 v1 明确不支持", 518, 518),
    ("corpus/cypy.generic.callsite.json", "fnv1a64:65bd56a87c83d42a", 1, 10 ** 6),
]

PATH_RE = re.compile(r"`((?:\./)?(?:\.fist-loop-20260929|corpus|tests|scripts|cypyc|cypy_bridge|SYNTAX|examples|reports)/[^`\s]+?\.(?:py|json|md|log|out|cypy|sh))`")
SUMMARY_RE = re.compile(r"`([^`\n]*(?:CONCLUSION|passed in|PASS=|Total:|accuracy=|SHAPE |WROTE |FILED |SEALED )[^`\n]*)`")
BUG_RE = re.compile(r"BUG-(\d{1,3})")
EVIDENCE_DIRS = [ROOT / ".fist-loop-20260929", ROOT / ".fist-loop-20260929" / "logs"]


def ledger_state():
    text = LEDGER.read_text(encoding="utf-8")
    blocks = [b for b in re.split(r"(?m)^(?=## BUG-)", text) if b.startswith("## BUG-")]
    ids = {re.match(r"## BUG-(\d+)", b).group(1) for b in blocks}
    open_blocks = [b for b in blocks if not re.search(r"(?m)^### (FIXED|DUPLICATE)", b)]
    sev = {}
    for b in open_blocks:
        m = re.match(r"## BUG-\d+ \[[^\]]+\] \[(\w+)\]", b)
        if m:
            sev[m.group(1)] = sev.get(m.group(1), 0) + 1
    judge = [re.match(r"## BUG-(\d+)", b).group(1) for b in open_blocks
             if re.search(r"^- summary: \[(?:判据面|Ω-gate|文档面)", b, re.M)
             or "判据" in (re.search(r"^- summary: (.*)", b, re.M).group(1)[:12]
                           if re.search(r"^- summary: (.*)", b, re.M) else "")]
    return {"ids": ids, "headers": len(blocks), "open": len(open_blocks), "open_ids": sorted(open_ids := [
        re.match(r"## BUG-(\d+)", b).group(1) for b in open_blocks], key=int),
        "severity": sev, "judge_face": sorted(judge, key=int), "product_face": len(open_blocks) - len(judge),
        "fixed_sections": len(re.findall(r"(?m)^### FIXED", text)),
        "amendment_sections": len(re.findall(r"(?m)^### AMENDMENT", text)),
        "text": text}


def evidence_blob():
    chunks = []
    for d in EVIDENCE_DIRS:
        if not d.exists():
            continue
        for p in sorted(d.rglob("*")):
            if p.is_file() and p.suffix in (".log", ".out", ".json"):
                try:
                    chunks.append(p.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    pass
    return "\n".join(chunks)


def main() -> int:
    rep = REPORT.read_text(encoding="utf-8")
    led = ledger_state()
    blob = evidence_blob()
    checks, fails = [], []

    def rec(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)[:220]})
        if not ok:
            fails.append(name)

    # 1) 每个被引用的 BUG 号必须在账本里
    cited = sorted({int(m) for m in BUG_RE.findall(rep)})
    missing = [i for i in cited if str(i) not in led["ids"]]
    rec("bug_ids_all_exist", not missing, f"cited={len(cited)} missing={missing}")
    rec("bug_ids_nonvacuous", len(cited) >= 10, f"cited={len(cited)}（少于 10 说明抽取坏了）")

    # 2) 每个被引用的路径必须存在（本核验件自己的输出除外：它在这次运行结束后才存在）
    paths = sorted({m.group(1) for m in PATH_RE.finditer(rep)})
    bad_paths = []
    for rel in paths:
        p = (ROOT / rel.removeprefix("./"))
        if p.resolve() == OUT.resolve():
            continue
        if not p.exists():
            bad_paths.append(rel)
    rec("paths_all_exist", not bad_paths, f"paths={len(paths)} missing={bad_paths}")
    rec("paths_nonvacuous", len(paths) >= 12, f"paths={len(paths)}（实测 17，地板 12）")

    # 3) 每条"逐字"结论必须能在证据件里找到（报告 → 证据 的反向核对）
    #    表格里为 Markdown 转义的 `\|` 要还原成 `|` 才能对上日志字节
    claims = sorted({m.group(1).replace("\\|", "|") for m in SUMMARY_RE.finditer(rep)
                     if len(m.group(1)) > 12})
    unbacked = [c for c in claims if c not in blob]
    rec("verbatim_claims_backed", not unbacked, f"claims={len(claims)} unbacked={unbacked[:4]}")
    rec("verbatim_nonvacuous", len(claims) >= 8, f"claims={len(claims)}")

    # 4) file:line 锚：定位真实行号并断言落在报告声明的区间
    anchor_rows = []
    for rel, needle, lo, hi in ANCHORS:
        p = ROOT / rel
        if not p.exists():
            anchor_rows.append({"rel": rel, "ok": False, "why": "文件不存在"})
            continue
        lines = p.read_text(encoding="utf-8").splitlines()
        hit = [i + 1 for i, ln in enumerate(lines) if needle in ln]
        inside = [h for h in hit if lo <= h <= hi]
        anchor_rows.append({"rel": rel, "needle": needle[:34], "hits": hit[:4],
                            "claimed": f"{lo}-{hi}", "ok": bool(inside),
                            "file_lines": len(lines)})
    bad_anchors = [a for a in anchor_rows if not a["ok"]]
    rec("code_anchors_in_range", not bad_anchors, bad_anchors)

    # 5) 账本数字逐格比（报告里写的 open / headers / FIXED / 严重度 / 判据面清单）
    nums = {
        "open_blocks": (r"open 块 \*\*(\d+)\*\*", led["open"]),
        "headers": (r"实测 `headers=(\d+)`", led["headers"]),
        "fixed_total": (r"`### FIXED` 段总数 \d+→(\d+)", led["fixed_sections"]),
        "high": (r"(\d+) high /", led["severity"].get("high", 0)),
        "medium": (r"\d+ high / (\d+) medium /", led["severity"].get("medium", 0)),
        "low": (r"(\d+) low", led["severity"].get("low", 0)),
        "judge_face_ids": (r"判据/文档面 (\d+)", len(led["judge_face"])),
        "product_face": (r"其余 (\d+)", led["product_face"]),
    }
    mism = {}
    for key, (pattern, actual) in nums.items():
        m = re.search(pattern, rep)
        mism[key] = {"claim": m.group(1) if m else None, "actual": str(actual)}
        if not m or m.group(1) != str(actual):
            fails.append(f"ledger_number:{key}")
    rec("ledger_numbers_match", all(v["claim"] == v["actual"] for v in mism.values()), mism)
    rec("judge_face_ids_named", all(f"BUG-{i}" in rep for i in led["judge_face"]), led["judge_face"])

    # 6) 判据层数字：Ω-spec 的对数与指纹必须与盘上一致
    spec = json.loads((ROOT / "corpus" / "cypy.generic.callsite.json").read_text(encoding="utf-8"))
    rec("spec_cases_20", f"20 对，指纹 `{spec['fingerprint']}`" in rep, spec["fingerprint"])
    rec("spec_fp_in_report", spec["fingerprint"] in rep, "")
    total = sum(len(json.loads(p.read_text(encoding="utf-8"))["tests"])
                for p in sorted((ROOT / "corpus").glob("*.json")))
    rec("floor_71_matches_corpus", total == 71 and "cases=71" in rep, f"corpus_total={total}")

    # 7) canary：把整段区间平移"区间宽度"这么多行，必须打不到 ⇒ 证明锚点是承重的而非大窗口
    drift = []
    for rel, needle, lo, hi in ANCHORS[:4]:
        lines = (ROOT / rel).read_text(encoding="utf-8").splitlines()
        hit = [i + 1 for i, ln in enumerate(lines) if needle in ln]
        width = hi - lo + 1
        drift.append({"rel": rel, "still_hits_if_shifted": bool(
            [h for h in hit if lo + width <= h <= hi + width])})
    any_shift_hit = any(d["still_hits_if_shifted"] for d in drift)
    rec("canary_shifted_range_red", not any_shift_hit, drift)
    fake = [i for i in (9999, 130) if str(i) not in led["ids"]]
    rec("canary_fake_bug_id_red", len(fake) == 2 and 130 not in led["ids"], f"fake={fake}")

    out = {"report": REPORT.name, "report_bytes": len(rep.encode("utf-8")),
           "ledger": {k: v for k, v in led.items() if k not in ("text", "ids")},
           "cited_bug_ids": cited, "cited_paths": len(paths), "verbatim_claims": len(claims),
           "anchors": anchor_rows, "checks": checks, "failed": fails,
           "placeholder_section_6": "<!--FIST-SECTION-->" in rep}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for ch in checks:
        print(("PASS " if ch["ok"] else "FAIL "), ch["name"], "|", ch["detail"])
    print(f"CONCLUSION checks={len(checks)} failed={len(fails)} ledger_open={led['open']} "
          f"bug_ids={len(cited)} claims={len(claims)} paths={len(paths)} "
          f"section6_deferred={out['placeholder_section_6']} rc={0 if not fails else 1}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
