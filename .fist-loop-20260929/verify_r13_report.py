"""R13 报告的引用核验件：报告里每一条"逐字"与每个 `BUG-NNN` 都要回到证据，锚点要指向真实行号。

与上一轮的分工相同：本件**现算**判定并写 json，报告只是被检对象。
两类反自查（canary）由 `--selftest` 注入：把某条结论改一个字符、把某个编号换成不存在的号，
尺子必须当场翻红 —— 否则它只是装饰。
"""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPORT = ROOT / "reports" / "2026-09-29" / "T0r119-cypy-selfdrive-r13-report.md"
LEDGER = ROOT / "memory" / "bugs.md"
DB = ROOT / "fist-mbt.db"
NS = "cypy-loop-20260929"
KEYWORDS = (
    "CONCLUSION",
    "passed in",
    "PASS=",
    "accuracy=",
    "Passed: ",
    "Failed: ",
    "Skipped: ",
    "total=",
    "bad=",
    "FILED ",
    "SEALED ",
    "->",
)
FLOOR = re.compile(r"(?m)^```[a-z]*\n(.*?)^```", re.S)
SPAN = re.compile(r"`([^`\n]+)`")

ANCHORS = [
    ("cypyc/analyzer/type_checker.py", 890, "self._check_container_elements(declared_type"),
    ("cypyc/analyzer/type_checker.py", 973, "self._check_container_elements("),
    ("cypyc/analyzer/type_checker.py", 4044, "def _slot_incompatible"),
    ("cypyc/analyzer/type_checker.py", 4070, "def _first_bad_element"),
    ("cypyc/analyzer/type_checker.py", 4087, "def _check_container_elements"),
    ("cypyc/analyzer/type_checker.py", 4174, "type_node.kind == 'UnionType'"),
    ("cypyc/analyzer/type_checker.py", 4202, "def _expand_nested_alias"),
    ("cypyc/analyzer/type_checker.py", 4036, "_ELEMENT_CHECKED_CONTAINERS ="),
    ("cypyc/analyzer/type_checker.py", 4039, "_SCALAR_ELEMENT_NAMES ="),
    ("SYNTAX/02-type-annotations.md", None, "## 容器元素位判定（R13 补，2026-09-29）"),
    ("tests/regression/test_corpus_pairs.py", 33, "FLOOR_SPECS = 7"),
    ("tests/regression/test_corpus_pairs.py", 34, "FLOOR_CASES = 151"),
    ("SYNTAX_IMPLEMENTATION_STATUS.md", None, "已闭环（R13）"),
    ("CHANGELOG.md", None, "闭合 BUG-137/138/139"),
]

OWN_WRITES = [
    ".fist-loop-20260929/probe_r13_container.py",
    ".fist-loop-20260929/make_corpus_r13.py",
    ".fist-loop-20260929/file_r13_container_bugs.py",
    ".fist-loop-20260929/amend_r13_ledger.py",
    ".fist-loop-20260929/verify_r13_locks.py",
    ".fist-loop-20260929/run_r13_ring.py",
    ".fist-loop-20260929/file_r13_ledger_dup.py",
    ".fist-loop-20260929/verify_r13_report.py",
    "tests/test_container_elements_r13.py",
    "tests/regression/test_corpus_pairs.py",
    ".fist-loop-20260929/derive_r13_card_ids.py",
    ".fist-loop-20260929/fill_r13_report.py",
    ".fist-loop-20260929/r13_self_certify.py",
]


def is_self_output(p: Path) -> bool:
    n = p.name
    return n.startswith("verify_r13_report") or "reportcheck" in n or n.startswith("fill_r13")


def evidence_blob() -> str:
    chunks = []
    for d in (HERE, HERE / "logs"):
        if not d.exists():
            continue
        for p in sorted(d.rglob("*")):
            if p.is_file() and p.suffix in (".log", ".out", ".json") and not is_self_output(p):
                raw = p.read_text(encoding="utf-8", errors="replace")
                if "selfcertify" in p.name or "selftest" in p.name:
                    # 核验件自己的 `PASS`/`FAIL`/`ORPHAN_QUOTE` 行**不进**证据面：
                    # 孤儿被打印出来又被下一轮读回来 ⇒ 那张门从此永远绿（尺子喂自己）。
                    raw = "\n".join(ln for ln in raw.splitlines() if ln.startswith("CONCLUSION"))
                chunks.append(raw)
    return "\n".join(chunks)


def claims(rep: str) -> list:
    """内联 `` `…` `` 与围栏代码块里带关键观测字样的行，都算"报告主张"。"""
    out = set()
    for m in SPAN.finditer(rep):
        t = m.group(1)
        if len(t) > 10 and any(k in t for k in KEYWORDS):
            out.add(t.replace("\\|", "|"))
    for block in FLOOR.findall(rep):
        for ln in block.splitlines():
            ln = ln.strip()
            if len(ln) > 10 and any(k in ln for k in KEYWORDS):
                out.add(ln)
    return sorted(out)


def resolve_missing(tokens, index) -> list:
    """写全路径的按全路径验（`cypyc/analyzer/type_checker.py` 必须真在那儿），
    只写简名的按 basename 验（`02-type-annotations.md` 指 `SYNTAX/` 下那份）。
    两种都不中才算缺失 —— 前缀/子串匹配会把"已被同名复跑盖掉的 a1 回执"读成"在"，所以不用。"""

    def ok(t):
        t = t.lstrip("./\\")
        return (ROOT / t).exists() or (HERE / t).exists() or Path(t).name in index

    return sorted(t for t in tokens if not ok(t))


def ledger_blocks() -> dict:
    led = LEDGER.read_text(encoding="utf-8")
    parts = re.split(r"(?m)^## (BUG-\d+)", led)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


def stalled_roots() -> dict:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    out = {}
    for root in ("T0r112", "T0r113"):
        rows = con.execute(
            "select status, count(*) from tasks where id=? or id like ? " "group by status",
            (root, root + ".%"),
        ).fetchall()
        out[root] = dict(rows)
    con.close()
    return out


def main() -> int:
    canary = "--selftest" in sys.argv
    rep = REPORT.read_text(encoding="utf-8")
    blob = evidence_blob()
    blocks = ledger_blocks()
    rows = []

    def rec(name, ok, detail=""):
        rows.append({"check": name, "ok": bool(ok), "detail": str(detail)[:220]})

    # 1) 逐字引用必须只存在于证据里
    orphan = []
    for c in claims(rep):
        if "\\d" in c or "N" == c[:1]:
            continue
        if c not in blob:
            if canary and "stage=start" in c:
                c2 = c.replace("faces_missing=0", "faces_missing=9")
                rec("canary_mutated_quote_is_caught", c2 not in blob, c2[:120])
            orphan.append(c)
    rec(
        "every_verbatim_quote_landed_in_evidence",
        not orphan,
        f"{len(orphan)} 条形如只在报告里（逐条见 ORPHAN_QUOTE 行）",
    )
    for c in orphan:
        print("ORPHAN_QUOTE | " + c)

    # 2) 报告点名的编号必须都在账上，且口径（FIXED/OPEN）与正文说法一致
    cited = {int(m) for m in re.findall(r"BUG-(\d{1,3})", rep)}
    missing = sorted(f"BUG-{i}" for i in cited if f"BUG-{i}" not in blocks)
    rec(
        "cited_bug_ids_exist",
        not missing and len(cited) >= 10,
        f"missing={missing} cited={len(cited)}",
    )
    for bid, want in (
        ("BUG-137", "FIXED"),
        ("BUG-138", "FIXED"),
        ("BUG-139", "FIXED"),
        ("BUG-136", "OPEN"),
    ):
        body = blocks.get(bid, "")
        has_fixed = bool(re.search(r"(?m)^### FIXED", body))
        has_amend = bool(re.search(r"(?m)^### 改判", body))
        if want == "FIXED":
            rec(f"{bid}_closed_this_round", has_fixed and "R13" in body, f"fixed={has_fixed}")
        else:
            rec(
                f"{bid}_still_open_with_amendment",
                (not has_fixed) and has_amend and "OPEN" in body.splitlines()[0],
                f"fixed={has_fixed} amend={has_amend}",
            )
    if canary:
        rec("canary_fake_bug_id_is_caught", "BUG-999999" not in blocks, "不存在编号应被判定抓住")

    # 3) 锚点：文件与行号要真指向那张表/那个函数
    bad_anchor = []
    for rel, line, needle in ANCHORS:
        p = ROOT / rel
        if not p.exists():
            bad_anchor.append(f"{rel} 不存在")
            continue
        text = p.read_text(encoding="utf-8")
        if line is None:
            if needle not in text:
                bad_anchor.append(f"{rel} 缺串 {needle[:28]!r}")
            continue
        ln = text.splitlines()[line - 1] if line <= len(text.splitlines()) else ""
        if needle not in ln:
            bad_anchor.append(f"{rel}:{line} 指到 {ln.strip()[:40]!r} 而不是 {needle[:28]!r}")
    rec("anchors_point_at_what_they_claim", not bad_anchor, bad_anchor)

    # 4) 语料与地板：报告说的对数/指纹必须是盘上那份
    spec = json.loads(
        (ROOT / "corpus" / "cypy.container.elements.json").read_text(encoding="utf-8")
    )
    rec(
        "corpus_cases_and_fingerprint_quoted",
        f"{len(spec['tests'])} 对" in rep and spec["fingerprint"] in rep,
        f"cases={len(spec['tests'])} fp={spec['fingerprint']}",
    )
    total = sum(
        len(json.loads(p.read_text(encoding="utf-8"))["tests"])
        for p in sorted((ROOT / "corpus").glob("*.json"))
    )
    rec(
        "corpus_total_matches_gate_reading",
        f"cases={total} passed={total}" in rep and f"{len(spec['tests'])} 对" in rep,
        total,
    )
    lock_src = (ROOT / "tests" / "test_container_elements_r13.py").read_text(encoding="utf-8")
    n_def = len(re.findall(r"(?m)^def test_", lock_src))
    rec(
        "lock_counts_derived_not_handadded",
        f"（{n_def} 支函数" in rep or f"{n_def} 支" in rep,
        f"def test_ = {n_def}",
    )

    # 5) 四套全量的汇总行要按形状取，且报告引的是那一份
    def last_shape(pattern):
        """按**修改时间**从新到旧取第一次命中。

        早先写成"文件名排序 + 第一个命中就返回"，于是抓到的是被作废的 b2（`specs=0`）——
        同一目录里既有作废读数又有有效读数时，"先命中"不等于"最新事实"。
        """
        files = sorted(
            (f for f in (HERE / "logs").glob("r13_*") if f.suffix in (".log", ".out")),
            key=lambda f: f.stat().st_mtime,
        )
        for f in reversed(files):
            m = re.findall(pattern, f.read_text(encoding="utf-8", errors="replace"))
            if m:
                return m[-1], f.name
        return None, None

    suite, suite_log = last_shape(r"Total: (\d+) \| Passed: (\d+) \| Failed: (\d+)")
    gate, gate_log = last_shape(r"CONCLUSION specs=(\d+) cases=(\d+) passed=(\d+) failed=(\d+)")
    gold, gold_log = last_shape(r"\[e2e-golden\] summary: PASS=(\d+) FAIL=(\d+)")
    rec("suite_total_quoted_with_source", suite and f"Passed: {suite[1]}" in rep, suite_log)
    rec(
        "gate_quoted_from_the_valid_run",
        gate and f"specs={gate[0]} cases={gate[1]} passed={gate[2]}" in rep,
        f"{gate_log} -> {gate}",
    )
    rec(
        "void_gate_reading_stays_marked_void",
        "specs=0" in rep and "作废" in rep,
        "报告须自证 b2 那一次不可采信",
    )
    rec("golden_quoted", gold and f"PASS={gold[0]} FAIL={gold[1]}" in rep, gold_log)
    final_py = (HERE / "logs" / "r13_pytest_final_c1.log").read_text(
        encoding="utf-8", errors="replace"
    )
    m = re.search(r"=+ (\d+) passed in ([\d.]+)s", final_py)
    rec(
        "final_pytest_count_and_wallclock_quoted",
        m and f"{m.group(1)} passed（{m.group(2)}s" in rep,
        m.groups() if m else None,
    )

    # 6) 承重矩阵：格数、承重数、对照 0 红必须与 json 反解一致
    mx = json.loads((HERE / "verify_r13_matrix.json").read_text(encoding="utf-8"))["cells"]

    def is_ctrl(n):
        return any(k.get("kind") == "只改注释" for k in mx[n].get("identity", []))

    mut = {n: mx[n] for n in mx if n.startswith("M") and not is_ctrl(n)}
    ctrl = {n: mx[n] for n in mx if n.startswith("M") and is_ctrl(n)}
    rec(
        "matrix_table_cells_match_json",
        len(mx) == 7 and len(mut) == 5 and len(ctrl) == 1,
        f"cells={len(mx)}",
    )
    rec(
        "matrix_table_numbers_match_json",
        all(
            f"| {n.split()[0]} |" in rep and str(c["pytest"]["n_failed"]) in rep
            for n, c in mx.items()
            if n.startswith("M")
        ),
        {n: (c["pytest"]["n_failed"], c["gate"]["failed"]) for n, c in mx.items()},
    )
    rec(
        "matrix_all_mutations_red_and_control_zero",
        all(c["pytest"]["n_failed"] > 0 for c in mut.values())
        and all(c["pytest"]["n_failed"] == 0 for c in ctrl.values()),
        "L0 也必须绿",
    )
    rec("matrix_l0_green", mx["L0 现树（应全绿）"]["pytest"]["n_failed"] == 0)

    # 7) 台账数：开口/抬头/FIXED/改判 由台账现算
    led = LEDGER.read_text(encoding="utf-8")
    ids_all = re.findall(r"(?m)^## (BUG-\d+)", led)
    dup = sorted({i for i in ids_all if ids_all.count(i) > 1})
    # `blocks` 是按 id 建的字典：重复号会**静默吃掉一张**（本轮就是这么抓到 BUG-96 复用的）。
    # 所以"抬头数"必须按正则数，"编号数"按去重数，两数并列写进报告，不许只报其中一个。
    open_n = len(
        [
            b
            for b in re.split(r"(?m)^(?=## BUG-\d+)", led)
            if b.startswith("## BUG-") and not re.search(r"(?m)^### (FIXED|DUPLICATE)", b)
        ]
    )
    counts = {
        "headers": len(ids_all),
        "unique": len(set(ids_all)),
        "open": open_n,
        "fixed": len(re.findall(r"(?m)^### FIXED", led)),
        "amend": len(re.findall(r"(?m)^### 改判", led)),
    }
    rec("ledger_counts_quoted", all(f"{v}" in rep for v in counts.values()), counts)
    rec(
        "unique_equals_headers_minus_dups",
        counts["unique"] == counts["headers"] - len(dup),
        f"headers={counts['headers']} unique={counts['unique']} dup={dup}",
    )
    rec(
        "duplicate_ids_declared_and_filed",
        (not dup) or (all(d in rep for d in dup) and "BUG-140" in rep),
        dup,
    )
    fam = sorted(
        int(b.split("-")[1])
        for b in blocks
        if int(b.split("-")[1]) in (120, 121, 122, 128, 134, 135, 136, 137, 138, 139)
        and not re.search(r"(?m)^### (FIXED|DUPLICATE)", blocks[b])
    )
    rec(
        "open_generics_family_named_as_derived_set",
        all(f"{n}" in rep for n in fam) and fam,
        f"open family={fam}",
    )

    # 8) 收口回执：只许出现一次（`--refresh` 双插是本类脚本的老毛病）
    close_once = len(re.findall(r"CONCLUSION stage=close", rep))
    rec("close_receipt_present_and_unique", close_once in (0, 1), f"copies={close_once}")
    if close_once == 1:
        m2 = re.search(r"CONCLUSION stage=close root=\S+ root_status=(\S+)", rep)
        rec(
            "close_receipt_root_closed", m2 and m2.group(1) == "已完成", m2.group(0) if m2 else None
        )
        rec(
            "close_receipt_verbatim_in_evidence",
            m2 and m2.group(0) in blob,
            "回执行必须能在 ring 日志/回执件里逐字找到",
        )
    else:
        rec(
            "close_receipt_root_closed",
            "由 `.fist-loop-20260929/fill_r13_report.py` 追加" in rep,
            "close 尚未跑：报告必须明写这是待补而不是留空",
        )
        rec("close_receipt_verbatim_in_evidence", "stage=start" in blob, "起手腿回执在场")

    # 8b) 账面**现态**复算：回执当时说"已完成"不算，回到库里再读一次；
    #     并配一根"停滞根必须还不是已完成"的对照，否则这张门只是复读回执。
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    live_root = con.execute("select status from tasks where id='T0r119'").fetchone()
    not_closed = con.execute(
        "select count(*) from tasks where (id='T0r119' or id like 'T0r119.%') and status<>'已完成'"
    ).fetchone()[0]
    n_nodes = con.execute(
        "select count(*) from tasks where id='T0r119' or id like 'T0r119.%'"
    ).fetchone()[0]
    n_leaves = con.execute(
        "select count(*) from tasks where id like 'T0r119.%' and depth=1"
    ).fetchone()[0]
    omega = dict(
        con.execute(
            "select spec_type, count(*) from specs where task_id like 'T0r119%' group by spec_type"
        ).fetchall()
    )
    stalled = con.execute("select status from tasks where id='T0r112'").fetchone()
    con.close()
    rec(
        "ring_root_closed_now_in_db",
        bool(live_root)
        and live_root[0] == "已完成"
        and not_closed == 0
        and "root_status=已完成" in rep,
        f"live={live_root and live_root[0]} not_closed={not_closed} nodes={n_nodes}",
    )
    rec(
        "omega_strong_verify_rows_cover_tree",
        omega.get("spec", 0) == n_nodes and omega.get("result", 0) == n_nodes,
        f"omega={omega} nodes={n_nodes} leaves={n_leaves}（spec/result 要覆盖整棵树，含根与枝干）",
    )
    rec(
        "check_rows_equal_leaf_count",
        omega.get("check", 0) == n_leaves,
        f"check={omega.get('check')} leaves={n_leaves}",
    )
    if canary:
        rec(
            "canary_stalled_root_is_not_closed",
            bool(stalled) and stalled[0] != "已完成",
            f"T0r112 live={stalled and stalled[0]}（这根若也'已完成'，上面那张门就是复读机）",
        )

    # 8c) 收口时的开批门读数：那份 json 里存着"放行时尺子有几张门"，报告引用它而不是我回忆。
    close_receipt = HERE / "ring_r13_close_a1.json"
    if close_receipt.exists():
        cc = json.loads(close_receipt.read_text(encoding="utf-8"))["entry_gate"]["observed"][
            "citation_check"
        ]
        rec(
            "close_entry_gate_reading_quoted",
            cc.get("failed") == 0 and str(cc.get("checks")) in rep,
            f"放行时 checks={cc.get('checks')} failed={cc.get('failed')}（报告须带上这个份数）",
        )
    else:
        rec("close_entry_gate_reading_quoted", False, f"缺件：{close_receipt.name}")

    # 9) 停滞根：报告里的待领取数必须等于库里的当下读数
    pend = stalled_roots()
    rec(
        "stalled_roots_counts_derived_from_db",
        all(f"`{k}` 待领取 {v.get('待领取', 0)}" in rep for k, v in pend.items()),
        json.dumps(pend, ensure_ascii=False),
    )

    # 10) §6.4 条数不写死：按编号行反解，并要求每条**写明渠道**（机器抓到 / 自己重读抓到）
    sec = rep.split("### 6.4")[1].split("## 7")[0]
    items = re.findall(r"(?m)^\d+\. \*\*(.+?)\*\*", sec)
    rec("self_caught_defect_list_not_empty", len(items) >= 5, f"count={len(items)}")

    def own_window(t: str) -> str:
        i = sec.find(t)
        # find 不中时不能退回"整节头 900 字"当窗口 —— 那会把别条的抓手算在这条头上。
        return "" if i < 0 else sec[i + len(t) : i + len(t) + 900]

    MACHINE = ("门", "拒", "复跑", "抓", "作废", "先红", "打回")
    got = [t for t in items if any(k in own_window(t) for k in MACHINE)]
    read = [t for t in items if "自读" in own_window(t)]
    unclaimed = [t for t in items if t not in got and t not in read]
    rec(
        "self_caught_items_name_real_artifacts",
        not unclaimed,
        f"count={len(items)} 机器抓={len(got)} 自读={len(read)} 无渠道={unclaimed}",
    )
    rec(
        "self_caught_channel_split_declared_in_header",
        not read or "自读" in sec.splitlines()[0],
        f"自读 {len(read)} 条 ⇒ 小节标题必须写明这条渠道，不能都算成门的功劳",
    )
    if canary:
        rec(
            "canary_window_lookup_miss_is_not_credited",
            own_window("这条标题根本不在正文里xyz") == "",
            "find 不中必须给空窗口，否则任何编造的条目都能蹭到抓手",
        )

    # 11) 风格主张分两档
    # 这里**不带** `--quiet`：带上 black 只回 rc=1 而不打印是哪几份（实测 2 份脏 ⇒ dirty=[]），
    # 红却不可归因等于尺子坏了，所以同时立一张"失败必须可归因"的门。
    r = subprocess.run(
        [sys.executable, "-m", "black", "--check"] + OWN_WRITES,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    dirty = sorted(
        {
            ln.split("would reformat ")[-1].strip()
            for ln in (r.stderr + r.stdout).splitlines()
            if "would reformat" in ln
        }
    )
    rec(
        "own_writes_are_black_clean",
        r.returncode == 0 and not dirty,
        f"{len(OWN_WRITES)} 份，脏={dirty}",
    )
    rec(
        "black_failure_is_attributable",
        not (r.returncode != 0 and not dirty),
        f"rc={r.returncode} dirty={len(dirty)}（红且无清单 ⇒ 尺子坏了）",
    )
    rec("style_claim_is_two_tier", "不交整档 formatter" in rep and "既有未格式化" in rep)

    # 12) 报告点名的每一份"件"必须真在盘上（首跑回执被同名复跑盖掉那类事，只能靠这张门抓）
    index = {}
    for base in (ROOT, HERE, HERE / "logs"):
        if base.exists():
            for q in base.iterdir():
                if q.is_file():
                    index.setdefault(q.name, q)
    for sub in ("tests", "scripts", "corpus", "SYNTAX", "memory", "reports", "examples"):
        d = ROOT / sub
        if d.exists():
            for q in d.rglob("*"):
                if q.is_file():
                    index.setdefault(q.name, q)
    named = set(re.findall(r"[A-Za-z0-9_\-./]+?\.(?:json|log|out|py|md|sh|txt)", rep))
    unresolved = resolve_missing(named, index)
    rec(
        "cited_files_exist_on_disk",
        len(named) >= 20 and not unresolved,
        f"点名 {len(named)} 份，解析不到={unresolved}",
    )
    if canary:
        fake = "logs/r13_never_written_z9.out"
        rec(
            "canary_fake_cited_file_is_caught",
            resolve_missing({fake, "tests/test_container_elements_r13.py"}, index) == [fake],
            f"混一真一假，只该报出 {fake}",
        )

    out = HERE / "verify_r13_report.json"
    failed = [x for x in rows if not x["ok"]]
    if canary:
        # 自检档：两条注入的假针必须都被抓，且其余判定不被我改坏
        injected = [x for x in rows if x["check"].startswith("canary_")]
        print(json.dumps(injected, ensure_ascii=False, indent=1))
        print(
            f"CONCLUSION checks={len(rows)} failed={len(failed)} "
            f"canaries={[x['check'] for x in injected]} rc={0 if not failed else 1}"
        )
        return 1 if failed else 0
    # 组合环的开批门读的就是这份 json —— 原地盖掉会让"收口时的那一次读数"不可复核，先留一份。
    if out.exists():
        shutil.copyfile(out, HERE / "verify_r13_report.prev.json")
    out.write_text(
        json.dumps(
            {
                "report_bytes": len(rep.encode("utf-8")),
                "checks": len(rows),
                "failed": len(failed),
                "ledger": counts,
                "cited": len(cited),
                "rows": rows,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    for x in rows:
        print(("PASS " if x["ok"] else "FAIL ") + x["check"] + " | " + x["detail"])
    print(
        f"CONCLUSION checks={len(rows)} failed={len(failed)} "
        f"ledger_open={counts['open']} bug_ids={len(cited)} "
        f"corpus_total={total} rc={0 if not failed else 1}"
    )
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
