"""R12 报告引用核验：正文里每条 BUG 号、每个路径、每条反引号"逐字"结论、每个 file:line 锚都要反解到证据。

反解优先于手写针（与既往轮同法，另加三条本轮教训）：
 · 台账数字按**两种口径**各自反解再对表（口径 A：只看 FIXED/DUPLICATE；环口径：再剔 OUT/WONT）——
   上一版把 38 与 37 当成矛盾，其实是两个口径各自为政，写明才算数；
 · 承重矩阵的数字从 `verify_r12_matrix.json` 现算，不抄我打印过的结论行；
 · 报告正文自己也要过"未插值占位"这一类脏检 —— 台账犯过的错不许在报告里再来一遍。

canary（证明门承重，不是装饰）：
 · 锚点区间整体平移一个区间宽度 ⇒ 必须打不到；
 · 注入一条不存在的 BUG 号 ⇒ 抽取器必须点名；
 · 从报告里删掉一条真实"逐字"结论的最后一个字符再比对 ⇒ 必须报缺（证明 `in` 比对真的在生效）。
"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPORT = ROOT / "reports" / "2026-09-29" / "T0r118-cypy-selfdrive-r12-report.md"
OUT = HERE / "verify_r12_report.json"
LEDGER = ROOT / "memory" / "bugs.md"
MATRIX = HERE / "verify_r12_matrix.json"

ANCHORS = [
    ("cypyc/analyzer/type_checker.py", "def _check_declared_bounds(self, decl", 1311, 1311),
    (
        "cypyc/analyzer/type_checker.py",
        "self._check_declared_bounds(decl, binding, node)",
        1361,
        1361,
    ),
    (
        "cypyc/analyzer/type_checker.py",
        "self._check_declared_bounds(struct_def, inferred_types, node)",
        2456,
        2456,
    ),
    ("cypyc/analyzer/type_checker.py", "self._check_declared_bounds(", 3995, 3995),
    ("SYNTAX/11-generics.md", "## 声明界在使用侧的判定", 107, 140),
    ("tests/regression/test_corpus_pairs.py", "FLOOR_SPECS = 6", 34, 34),
    ("tests/regression/test_corpus_pairs.py", "FLOOR_CASES = 123", 35, 35),
    ("SYNTAX_IMPLEMENTATION_STATUS.md", "| `11-generics.md` |", 339, 339),
    ("SYNTAX_IMPLEMENTATION_STATUS.md", "| `02-type-annotations.md` | ⚠ 部分", 330, 330),
    (
        "tests/test_generic_bounds_r12.py",
        "def test_struct_literal_path_reuses_the_shared_checker",
        1,
        10**6,
    ),
    ("corpus/cypy.generic.bounds.json", "fnv1a64:65b49102e98d2fa0", 1, 10**6),
]

PATH_RE = re.compile(
    r"`((?:\./)?(?:\.fist-loop-20260929|corpus|tests|scripts|cypyc|cypy_bridge|SYNTAX|"
    r"examples|reports|logs)/[^`\s]+?\.(?:py|json|md|log|out|cypy|sh))`"
)
SUMMARY_RE = re.compile(
    r"`([^`\n]*(?:CONCLUSION|passed in|PASS=|accuracy=|Passed: |Failed: |Skipped: |"
    r"_rc=|bad=\[|SHAPE |FILED |SEALED )[^`\n]*)`"
)
BUG_RE = re.compile(r"BUG-(\d{1,3})")
EVIDENCE_DIRS = [ROOT / ".fist-loop-20260929", ROOT / ".fist-loop-20260929" / "logs"]


def ledger_state():
    text = LEDGER.read_text(encoding="utf-8")
    blocks = [b for b in re.split(r"(?m)^(?=## BUG-)", text) if b.startswith("## BUG-")]
    ids = {re.match(r"## BUG-(\d+)", b).group(1) for b in blocks}
    narrow = [b for b in blocks if not re.search(r"(?m)^### (FIXED|DUPLICATE)", b)]
    ring = [b for b in blocks if not re.search(r"(?m)^### (FIXED|DUPLICATE|OUT|WONT)", b)]
    sev = {}
    for b in narrow:
        m = re.match(r"## BUG-\d+ \[[^\]]+\] \[(\w+)\]", b)
        if m:
            sev[m.group(1)] = sev.get(m.group(1), 0) + 1
    return {
        "ids": ids,
        "headers": len(blocks),
        "open_narrow": len(narrow),
        "open_ring": len(ring),
        "fixed_sections": len(re.findall(r"(?m)^### FIXED", text)),
        "severity_per_open": sev,
        "text": text,
    }


def stamp_readings(text):
    tok = re.compile(r"\d{4}-\d\d-\d\dT[\d:]*Z*")
    canon = re.compile(r"20\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ")
    odd = [
        t
        for l in text.splitlines()
        if l.startswith("### ")
        for t in tok.findall(l)
        if not canon.fullmatch(t)
    ]
    return {
        "clock_no_Z": len([t for t in odd if not t.endswith("Z")]),
        "minute_precision": len([t for t in odd if re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\dZ", t)]),
        "hard_bad": len(
            [t for t in odd if t.endswith("ZZ") or re.search(r"\d{4}-\d\d-\d\dT\d{4}", t)]
        ),
    }


def self_output(p: Path) -> bool:
    """核验件与"打印核验结论"的日志不算证据 —— 否则自家输出会把上一轮的探针串喂回成"有出处"
    （本轮真的踩到了：canary 里那条被我改了一个字符的结论，因为上一版 `verify_r12_report.json`
    把它写进了 `detail`，而那个文件在证据目录里，于是探针 `in blob` 变真、canary 假绿）。
    """
    return (
        p.match("verify_*_report.json")
        or p.match("verify_*_report.*.json")
        or "reportcheck" in p.name
        or "fill_post" in p.name
    )


def evidence_blob():
    chunks = []
    for d in EVIDENCE_DIRS:
        if not d.exists():
            continue
        for p in sorted(d.rglob("*")):
            if p.is_file() and p.suffix in (".log", ".out", ".json") and not self_output(p):
                try:
                    chunks.append(p.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    pass
    return "\n".join(chunks)


def json_subobjects(node, acc=None):
    """把回执件里每个 dict/list 子节点收集出来（按值比，不比序列化字节 —— 分隔符/键序都是我这边选的）。
    补记段引用的是**派生读数**（rollup/gates/matrix 这些从回执再 dump 的形状），它们在日志里没有整行原文，
    但必须能对着回执逐字段相等 —— 只放"字节子串"这把尺会把合法引用打成红，
    只放"能解析成 JSON 就行"又会放过假数 ⇒ 做深度相等。"""
    acc = [] if acc is None else acc
    acc.append(node)
    if isinstance(node, dict):
        for v in node.values():
            json_subobjects(v, acc)
    elif isinstance(node, list):
        for v in node:
            json_subobjects(v, acc)
    return acc


def main() -> int:
    rep = REPORT.read_text(encoding="utf-8")
    led = ledger_state()
    blob = evidence_blob()
    checks, fails = [], []

    def rec(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)[:260]})
        if not ok:
            fails.append(name)

    cited = sorted({int(m) for m in BUG_RE.findall(rep)})
    missing = [i for i in cited if str(i) not in led["ids"]]
    rec("bug_ids_all_exist", not missing, f"cited={len(cited)} missing={missing}")
    rec("bug_ids_nonvacuous", len(cited) >= 10, f"cited={len(cited)}")

    paths = sorted({m.group(1) for m in PATH_RE.finditer(rep)})
    bad_paths = [r for r in paths if not (ROOT / r.removeprefix("./")).exists()]
    rec("paths_all_exist", not bad_paths, f"paths={len(paths)} missing={bad_paths}")
    rec("paths_nonvacuous", len(paths) >= 15, f"paths={len(paths)}")

    claims = sorted(
        {m.group(1).replace("\\|", "|") for m in SUMMARY_RE.finditer(rep) if len(m.group(1)) > 10}
    )
    receipts = []
    for f in sorted(HERE.glob("ring_r12_*.json")):
        try:
            receipts.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
    subvals = [v for r in receipts for v in json_subobjects(r)]
    unbacked, derived, regexish = [], [], []
    for c in claims:
        # §6.4 会举"针长什么样"的例子（反引号里的正则字面串）—— 那是**模式**不是日志原文，
        # 只放行含 `\d` 这种明显正则标记的串，并把它们单列进 `regex_like_claims` 供人看，
        # 不悄悄放宽整条尺（悄悄放宽 = 下一版什么都能混过去）。
        if "\\d" in c:
            regexish.append(c)
            continue
        if c in blob:
            continue
        try:
            obj = json.loads(c)
        except ValueError:
            unbacked.append(c)
            continue
        (derived if any(obj == sv for sv in subvals) else unbacked).append(c)
    rec("verbatim_claims_backed", not unbacked, f"claims={len(claims)} unbacked={unbacked[:4]}")
    rec("derived_quotes_round_trip", all(len(c) > 10 for c in derived), f"derived={len(derived)}")
    rec("verbatim_nonvacuous", len(claims) >= 10, f"claims={len(claims)}")
    rec("regex_like_exemption_stays_small", len(regexish) <= 3, f"regexish={regexish}")
    # canary：把一条真结论的中间一个字符换掉，必须"找不到"——证明上面是逐字 `in` 比对而非永真。
    # （截尾不行：截断串仍是原串的前缀，`in` 照样命中 ⇒ 那格会假绿。）
    if claims:
        c0 = claims[0]
        k = len(c0) // 2
        probe = c0[:k] + "≠" + c0[k + 1 :]
        rec("canary_mutated_claim_red", probe != c0 and probe not in blob, f"probe={probe[:60]}")

    anchor_rows = []
    for rel, needle, lo, hi in ANCHORS:
        p = ROOT / rel
        if not p.exists():
            anchor_rows.append({"rel": rel, "ok": False, "why": "文件不存在"})
            continue
        lines = p.read_text(encoding="utf-8").splitlines()
        hit = [i + 1 for i, ln in enumerate(lines) if needle in ln]
        anchor_rows.append(
            {
                "rel": rel,
                "needle": needle[:36],
                "hits": hit[:5],
                "claimed": f"{lo}-{hi}",
                "ok": any(lo <= h <= hi for h in hit),
                "file_lines": len(lines),
            }
        )
    bad_anchors = [a for a in anchor_rows if not a["ok"]]
    rec("code_anchors_in_range", not bad_anchors, bad_anchors)

    drift = []
    for rel, needle, lo, hi in [a for a in ANCHORS if a[2] < 10**5][:6]:
        lines = (ROOT / rel).read_text(encoding="utf-8").splitlines()
        hit = [i + 1 for i, ln in enumerate(lines) if needle in ln]
        w = hi - lo + 1
        drift.append(
            {
                "rel": rel,
                "needle": needle[:24],
                "still_hits_if_shifted": any(lo + w <= h <= hi + w for h in hit),
            }
        )
    rec("canary_shifted_range_red", not any(d["still_hits_if_shifted"] for d in drift), drift)

    fake = max(int(i) for i in led["ids"]) + 7
    probe_missing = [
        i
        for i in {int(m) for m in BUG_RE.findall(rep + f"\nBUG-{fake}\n")}
        if str(i) not in led["ids"]
    ]
    rec("canary_fake_bug_id_red", probe_missing == [fake], f"fake={fake} got={probe_missing}")

    nums = {
        "headers": (r"抬头 (\d+) 块", str(led["headers"])),
        "open_narrow": (r"开口 (\d+) 块", str(led["open_narrow"])),
        "fixed_total": (r"`### FIXED` 段 (\d+) 个", str(led["fixed_sections"])),
        "open_ring_in_report": (r"环口径[^0-9]*(\d+)", str(led["open_ring"])),
    }

    def grab(pat):
        m = re.search(pat, rep)
        return m.group(1) if m else None

    mism = {k: {"claim": grab(p), "actual": a} for k, (p, a) in nums.items()}
    rec("ledger_numbers_match", all(m["claim"] == m["actual"] for m in mism.values()), mism)
    # 同一个开口数在正文多处必须一致（§头 与 §6.1 各写一次，两处都要反解）
    both = re.findall(r"(?:(\d+) 块开口|开口 (\d+) 块)", rep)
    flat = [a or b for a, b in both]
    rec(
        "open_claim_consistent_all_places",
        bool(flat) and all(c == str(led["open_narrow"]) for c in flat),
        f"claims={flat} actual={led['open_narrow']}",
    )

    sev_bad = [
        b
        for b in ("134", "135", "136")
        if not re.search(rf"`BUG-{b}`（(high|medium|low)", rep)
        or re.search(rf"`BUG-{b}`（(high|medium|low)", rep).group(1)
        != re.search(rf"(?ms)^## BUG-{b} \[[^\]]+\] \[(\w+)\]", led["text"]).group(1)
    ]
    rec("new_card_severity_matches_ledger", not sev_bad, sev_bad)

    rd = stamp_readings(led["text"])
    rec(
        "legacy_stamp_readings_quoted",
        f"{rd['clock_no_Z']} 处时钟戳缺" in rep and f"{rd['minute_precision']} 处只到分钟" in rep,
        rd,
    )
    rec(
        "ledger_hard_sweep_zero",
        rd["hard_bad"] == 0 and not re.findall(r"(?m)^.*(\d{4}-\d\d-\d\dT)\1.*ZZ.*$", led["text"]),
        rd,
    )

    # 未插值占位这一类脏检：只看**代码段之外**的正文 —— §6.4 讲这个缺陷时必须把 `{CASES}` 这样的字面串
    # 打进反引号里举例，连代码段一起扫会把"解释"当成"残留"（自家说明喂坏门的又一形）。
    prose = re.sub(r"`[^`]*`", "", rep)
    residue = re.findall(r"\{[A-Za-z_][A-Za-z_]*\}", prose)
    rec("report_has_no_uninterpolated_placeholder", not residue, residue[:6])
    rec(
        "code_span_placeholder_claim_backed_by_ledger_gate",
        "{CASES}" in rep and "amend_r12_ledger.py" in rep,
        "§6.4 讲占位的那段要在，且要点名写坏的件",
    )

    spec = json.loads((ROOT / "corpus" / "cypy.generic.bounds.json").read_text(encoding="utf-8"))
    total = sum(
        len(json.loads(p.read_text(encoding="utf-8"))["tests"])
        for p in sorted((ROOT / "corpus").glob("*.json"))
    )
    locks = len(
        re.findall(
            r"(?m)^def test_",
            (ROOT / "tests" / "test_generic_bounds_r12.py").read_text(encoding="utf-8"),
        )
    )
    rec(
        "spec_cases_and_fp",
        f"{len(spec['tests'])} 对，指纹 `{spec['fingerprint']}`" in rep,
        spec["fingerprint"],
    )
    rec(
        "corpus_total_and_gate_agree",
        total == 123 and f"cases={total}" in rep and f"FLOOR_CASES = {total}" in rep,
        f"total={total}",
    )
    rec("lock_count_matches", f"{locks} 支" in rep, f"locks={locks}")

    cells = json.loads(MATRIX.read_text(encoding="utf-8"))["cells"]
    is_ctrl = lambda n: any(
        k.get("kind") == "只改注释" for k in cells[n].get("identity", [])
    )  # noqa: E731
    mut = [c for n, c in cells.items() if n.startswith("M") and not is_ctrl(n)]
    ctrl = [c for n, c in cells.items() if n.startswith("M") and is_ctrl(n)]
    rec(
        "matrix_claims_match_json",
        f"cells={len(cells)}" in rep
        and f"load_bearing_cells={len([c for c in mut if c['pytest']['n_failed'] > 0])}" in rep
        and all(c["pytest"]["n_failed"] > 0 for c in mut)
        and all(c["pytest"]["n_failed"] == 0 for c in ctrl),
        {"cells": len(cells), "mut": len(mut), "ctrl": len(ctrl)},
    )

    rec(
        "close_receipt_appears_once",
        rep.count("**R12 收口腿逐字回执") == 1,
        f"copies={rep.count('**R12 收口腿逐字回执')}",
    )
    rec(
        "close_conclusion_line_quoted",
        any(
            l.startswith("CONCLUSION stage=close") and f"`{l}`" in rep
            for l in (HERE / "logs" / "r12_ring_close_a1.out")
            .read_text(encoding="utf-8", errors="replace")
            .splitlines()
        ),
        "",
    )

    sev_open = {}
    for b in [
        x
        for x in re.split(r"(?m)^(?=## BUG-)", led["text"])
        if x.startswith("## BUG-")
        if not re.search(r"(?m)^### (FIXED|DUPLICATE)", x)
    ]:
        m = re.match(r"## BUG-\d+ \[[^\]]+\] \[(\w+)\]", b)
        if m:
            sev_open[m.group(1)] = sev_open.get(m.group(1), 0) + 1
    rec(
        "severity_split_matches_ledger",
        all(f"{n} {k}" in rep for k, n in sev_open.items())
        and sum(sev_open.values()) == led["open_narrow"],
        f"sev={sev_open} open={led['open_narrow']}",
    )
    # 泛型/类型约束族开口：按**正文内容**反解（summary 里出现这些词就算），不按轮次编号猜——
    # 编号集合是"上一轮的事实"，下一轮开工就会报假分叉。
    fam = sorted(
        {
            re.match(r"## BUG-(\d+)", b).group(1)
            for b in [
                x for x in re.split(r"(?m)^(?=## BUG-)", led["text"]) if x.startswith("## BUG-")
            ]
            if not re.search(r"(?m)^### (FIXED|DUPLICATE)", b)
            and re.search(
                r"generics|泛型|类型实参|声明界|类型约束|constraint",
                (re.search(r"^- summary: (.*)", b, re.M) or ["", ""])[1],
                re.I,
            )
        },
        key=int,
    )
    claim = re.search(r"泛型/类型约束族开口 (\d+) 条（([0-9+]+)）", rep)
    rec(
        "generics_family_named_as_derived_set",
        bool(claim) and claim.group(1) == str(len(fam)) and claim.group(2).split("+") == fam,
        f"derived={fam} claim={claim.group(0) if claim else None}",
    )

    # 风格两口径：亲笔清单必须 black clean（这才允许说"过 black"），产品文件按"存量债"记账 ——
    # 报告里那个 1688 行数要能被现算复现（HEAD 换人/换码后它就漂，漂了就该红）。
    my_writes = [
        "tests/test_generic_bounds_r12.py",
        ".fist-loop-20260929/run_r12_ring.py",
        ".fist-loop-20260929/verify_r12_report.py",
        ".fist-loop-20260929/fill_r12_report.py",
        ".fist-loop-20260929/amend_r12_ledger.py",
        ".fist-loop-20260929/make_corpus_r12.py",
        ".fist-loop-20260929/verify_r12_locks.py",
        ".fist-loop-20260929/probe_r13_type_alias.py",
        ".fist-loop-20260929/file_r13_alias_bug.py",
    ]
    b = subprocess.run(
        [sys.executable, "-m", "black", "--check", *my_writes],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    head_copy = HERE / "_head_copy_for_black.py"
    shown = subprocess.run(
        ["git", "show", "HEAD:cypyc/analyzer/type_checker.py"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    head_diff_lines = None
    if shown.returncode == 0:
        head_copy.write_text(shown.stdout, encoding="utf-8", newline="\n")
        d = subprocess.run(
            [sys.executable, "-m", "black", "--diff", str(head_copy)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        head_diff_lines = len(
            [
                ln
                for ln in (d.stdout or "").splitlines()
                if ln[:1] in "+-" and not ln.startswith(("+++", "---"))
            ]
        )
        head_copy.unlink(missing_ok=True)
    rec(
        "style_claim_two_tiers",
        b.returncode == 0
        and len(my_writes) == 9
        and head_diff_lines is not None
        and f"{head_diff_lines} 行" in rep,
        f"own_clean={b.returncode == 0} head_black_diff={head_diff_lines}",
    )

    # "复跑同数"与"墙钟差"都是报告里的主张 ⇒ 从两侧日志现算，不采信我口算的 15.86。
    def one(pat, path):
        t = (HERE / "logs" / path).read_text(encoding="utf-8", errors="replace")
        m = re.search(pat, t)
        return m.group(1) if m else None

    p3, p4 = one(r"(\d+) passed in", "r12_pytest_a3.log"), one(
        r"(\d+) passed in", "r12_pytest_a4.log"
    )
    t3 = re.search(
        r"(\d+) passed in ([\d.]+)s",
        (HERE / "logs" / "r12_pytest_a3.log").read_text(encoding="utf-8"),
    )
    t4 = re.search(
        r"(\d+) passed in ([\d.]+)s",
        (HERE / "logs" / "r12_pytest_a4.log").read_text(encoding="utf-8"),
    )
    delta = round(float(t4.group(2)) - float(t3.group(2)), 2) if t3 and t4 else None
    # 取数要按**形状**而不是"文件里第一个匹配"：套件日志每族都打 `Passed: n`（第一个是 18），
    # Ω-gate 每 spec 都打 `cases=n`（第一个是 24）—— 上一版就这么把"两个数相等"过成了空门。
    s1, s2 = one(r"Total: \d+ \| Passed: (\d+)", "r12_suite_a1.log"), one(
        r"Total: \d+ \| Passed: (\d+)", "r12_suite_a2.log"
    )
    g1, g2 = one(r"CONCLUSION specs=\d+ cases=(\d+)", "r12_gate_all_a1.log"), one(
        r"CONCLUSION specs=\d+ cases=(\d+)", "r12_gate_all_a2.log"
    )
    m2, m3 = one(r"load_bearing_cells=(\d+)", "r12_matrix_a2.out"), one(
        r"load_bearing_cells=(\d+)", "r12_matrix_a3.out"
    )
    rec(
        "post_format_reruns_agree",
        p3 == p4
        and s1 == s2
        and g1 == g2
        and m2 == m3
        and all(x is not None for x in (p3, s2, g2, m3)),
        f"pytest={p3}/{p4} suite={s1}/{s2} gate={g1}/{g2} matrix={m2}/{m3}",
    )
    rec(
        "wallclock_delta_quoted_as_derived",
        delta is not None and f"{delta}s" in rep and float(t3.group(2)) != float(t4.group(2)),
        f"delta={delta}s claimed_in_report={f'{delta}s' in rep}",
    )

    # §9 第 6 条把"待领取叶"写成现算数 ⇒ 对着隔离库重算一遍，漂了就红（结转数字不许抄）。
    con = sqlite3.connect(f"file:{ROOT / 'fist-mbt.db'}?mode=ro", uri=True)
    pend = {}
    for root in ("T0r112", "T0r113"):
        rows = dict(
            con.execute(
                "select status, count(*) from tasks where id=? or id like ? group by status",
                (root, f"{root}.%"),
            ).fetchall()
        )
        pend[root] = {
            "待领取": rows.get("待领取", 0),
            "拆分中": rows.get("拆分中", 0),
            "已完成": rows.get("已完成", 0),
        }
    con.close()
    rec(
        "stalled_roots_counts_derived_from_db",
        all(f"`{k}` 待领取 {v['待领取']}" in rep for k, v in pend.items())
        and f"合计 {sum(v['待领取'] for v in pend.values())} 支" in rep,
        json.dumps(pend, ensure_ascii=False),
    )
    rec(
        "r13_probe_section_present",
        "### 3.4" in rep and "r13_probe_alias_a2.out" in rep and "BUG-136" in rep,
        "§3.4 要点名探针日志与新单号",
    )

    out = {
        "report": REPORT.name,
        "report_bytes": len(rep.encode("utf-8")),
        "ledger": {k: v for k, v in led.items() if k not in ("text", "ids")},
        "legacy_stamp_readings": rd,
        "cited_bug_ids": cited,
        "cited_paths": len(paths),
        "verbatim_claims": len(claims),
        "anchors": anchor_rows,
        "checks": checks,
        "failed": fails,
        "close_section_appended": rep.count("**R12 收口腿逐字回执") == 1,
        "close_mark_copies": rep.count("**R12 收口腿逐字回执"),
        "script_identity": "verify_r12_report.py",
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for ch in checks:
        print(("PASS " if ch["ok"] else "FAIL "), ch["name"], "|", ch["detail"])
    print(
        f"CONCLUSION checks={len(checks)} failed={len(fails)} ledger_open_narrow={led['open_narrow']} "
        f"ledger_open_ring={led['open_ring']} bug_ids={len(cited)} claims={len(claims)} paths={len(paths)} "
        f"close_appended={out['close_section_appended']} rc={0 if not fails else 1}"
    )
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
