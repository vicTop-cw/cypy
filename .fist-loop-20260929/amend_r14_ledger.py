"""给 BUG-141 / BUG-142 各追加一段 `### FIXED(R14 …)`：抬头行与本单正文一字不改。

纪律沿用 R12/R13：编号从台账的 `reported_key` 反解（不手写 `## BUG-NN`）；
段落里的每个数都在写盘瞬间现算（缺证据件即拒写，不许凭记忆）；
脏检分双口径 —— 门只钉本件亲笔那段，整档脏检只印读数；
`--refresh` 只回收自己那两段（换自己写的东西，不是新关一单）；
落盘走 temp + `os.replace`，先把旧档留备份。
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LOGS = HERE / "logs"
LEDGER = ROOT / "memory" / "bugs.md"
MARK = "FIXED(R14"
IDS = {"R14-DICT-LITERAL-NO-INFER": None, "R14-MANUAL-DANGLING-TEST-PATH": None}

SPEC_NEW = ROOT / "corpus" / "cypy.dict.elements.json"
SPEC_OLD = ROOT / "corpus" / "cypy.container.elements.json"
LOCK_R14 = ROOT / "tests" / "test_dict_elements_r14.py"
PROBE_BEFORE = LOGS / "r14_dict_probe_a2.json"
PROBE_AFTER = LOGS / "r14_dict_probe_c2.json"
PYTEST_RADIUS = LOGS / "r14_pytest_radius_a1.log"
PYTEST_FINAL = LOGS / "r14_pytest_final_c3.log"
# 关单之后判据又长过一次（矩阵 M3 抓到"数值阶梯取最宽"那支在 Ω-gate 半边没语料）：
# 补形前的那份 spec 与它的指纹都要在段落里点名，否则读者拿卡片正文里的 23 对去核对现在的 25 对会以为账坏了。
CORPUS_RECEIPT = LOGS / "r14_corpus_b1.out"
SUITE = LOGS / "r14_suite_c1.log"
GATE = LOGS / "r14_gate_c1.log"
GOLDEN = LOGS / "r14_golden_c1.log"


def need(*paths):
    for p in paths:
        if not p.exists():
            raise SystemExit(f"证据件缺失：{p.name} ⇒ 不写台账（数没有来源就不许落笔）")


def passed_in(path):
    txt = path.read_text(encoding="utf-8", errors="replace")
    m = re.findall(r"(\d+) passed in ([\d.]+)s", txt)
    if not m:
        raise SystemExit(f"{path.name} 里解不出 `N passed in Xs` ⇒ 拒绝手填")
    return int(m[-1][0]), float(m[-1][1])


def derived() -> dict:
    need(
        PROBE_BEFORE,
        PROBE_AFTER,
        SPEC_NEW,
        SPEC_OLD,
        LOCK_R14,
        PYTEST_RADIUS,
        PYTEST_FINAL,
        SUITE,
        GATE,
        GOLDEN,
    )
    before = json.loads(PROBE_BEFORE.read_text(encoding="utf-8"))
    after = json.loads(PROBE_AFTER.read_text(encoding="utf-8"))
    new_spec = json.loads(SPEC_NEW.read_text(encoding="utf-8"))
    old_spec = json.loads(SPEC_OLD.read_text(encoding="utf-8"))
    import probe_r14_dict as pr

    # 「改动前静默」只能在**改动前那份快照里有的形**上数：D08/G15 是关单后补的，
    # 那时产品已修 ⇒ 它们没有改动前读数，把它们混进"静默清单"就是编历史。
    silent = sorted(k for k in pr.MUST_RED if k in before and before[k]["n"] == 0)
    late = sorted(k for k in pr.MUST_RED if k not in before)
    if len(silent) + len(late) != len(pr.MUST_RED):
        raise SystemExit("MUST_RED 既不在快照也不在补形清单 ⇒ 分栏漏了")
    now_red = sorted(k for k in silent if after[k]["n"] > 0)
    kept_green = sorted(k for k in pr.MUST_GREEN if after[k]["n"] == 0)
    r_total, r_secs = passed_in(PYTEST_RADIUS)
    f_total, f_secs = passed_in(PYTEST_FINAL)
    suite = re.findall(r"Total: (\d+) \| Passed: (\d+) \| Failed: (\d+)", SUITE.read_text("utf-8"))
    gate = re.findall(r"specs=(\d+) cases=(\d+) passed=(\d+) failed=(\d+)", GATE.read_text("utf-8"))
    gold = re.search(r"PASS=(\d+) FAIL=(\d+)", GOLDEN.read_text(encoding="utf-8"))
    n_locks = len(re.findall(r"(?m)^def test_", LOCK_R14.read_text(encoding="utf-8")))
    if not CORPUS_RECEIPT.exists():
        raise SystemExit(f"缺 {CORPUS_RECEIPT.name} ⇒ 拿不到「补形前那份指纹」，不写台账")
    prev = re.findall(
        r"dict_fp=(fnv1a64:[0-9a-f]+)", CORPUS_RECEIPT.read_text(encoding="utf-8", errors="replace")
    )
    if not prev:
        raise SystemExit(f"{CORPUS_RECEIPT.name} 里解不出 dict_fp ⇒ 拒写")
    d = {
        "stamp": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cases_probe": len(after),
        "silent": silent,
        "late": late,
        "now_red": now_red,
        "kept_green": kept_green,
        "must_green": len(pr.MUST_GREEN),
        "dict_cases": len(new_spec["tests"]),
        "dict_fp": new_spec["fingerprint"],
        "container_cases": len(old_spec["tests"]),
        "container_fp": old_spec["fingerprint"],
        "locks": n_locks,
        "prev_fp": prev[-1],
        "radius_total": r_total,
        "final_total": f_total,
        "delta": f_total - r_total,
        "delta_parts": n_locks + len(new_spec["tests"]),
        "suite": suite[-1] if suite else None,
        "gate": gate[-1] if gate else None,
        "golden": (gold.group(1), gold.group(2)) if gold else None,
    }
    # 明细与累加必须各说同一件事：新增用例只可能是「新锁 + 新语料对」两项
    if d["delta"] != d["delta_parts"]:
        raise SystemExit(
            f"终版-半径={d['delta']} 与明细 {d['locks']}+{len(new_spec['tests'])}={d['delta_parts']} "
            "不等 ⇒ 有一项没被数进来（或旧测试被删了），不写台账"
        )
    if not d["suite"] or d["suite"][2] != "0" or not d["gate"] or d["gate"][3] != "0":
        raise SystemExit(f"套件读数不合格：suite={d['suite']} gate={d['gate']}")
    if d["golden"] != ("25", "0"):
        raise SystemExit(f"golden 读数不是 25/0：{d['golden']}")
    if len(d["now_red"]) != len(silent) or len(d["kept_green"]) != d["must_green"]:
        raise SystemExit(f"探针栏位与实得不一致：{d['now_red']} {d['kept_green']}")
    import subprocess

    r = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "pytest", str(LOCK_R14), "-k", "manual", "-rf"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    # 汇总行在"跑子集"时长这样：`1 passed, 28 deselected in 0.17s` ——
    # 拿 `N passed in Xs` 当针会解不出，于是把一次**真绿**读成红（先怀疑尺子，再怀疑被测）。
    tail = r.stdout + r.stderr
    m = re.search(r"(\d+) passed", tail)
    w = re.search(r"in ([\d.]+)s", tail)
    if m and w and not re.search(r"\d+ (?:failed|error)", tail):
        d["manual_lock"] = f"{m.group(1)} passed（{w.group(1)}s，子集 -k manual）"
    if r.returncode != 0 or not (m and w):
        raise SystemExit(
            f"手册对表锁没跑绿（rc={r.returncode}）⇒ 文档单不能宣称已修：\n{(r.stdout or r.stderr)[-400:]}"
        )
    return d


D = derived()

SECTION = f"""### {{kind}}({{title}} {{STAMP}}）— 追加留档（本单正文与标题行一字未添改）

- 现算读数（写盘瞬间，非回忆）：成对探针 `{{CASES}}` 形 ⇒ 改动前该红却静默 {{SILENT_N}} 形
  （`{{SILENT}}`），改动后逐条转红；声明该绿的 {{MUSTG}} 形改动后仍全绿（`{{KEPT}}`）。
  另有 {{LATE_N}} 形（`{{LATE}}`）是关单后补的（见下方"判据又长了一次"那条）——
  补它的时候产品已经修好，所以**没有**改动前读数，不混进上面那份静默清单里充数。
- 判据：Ω-spec `corpus/cypy.dict.elements.json`（{{DICT_CASES}} 对，指纹 `{{DICT_FP}}`）；
  同轮把 R13 那份 `cypy.container.elements`（{{CONTAINER_CASES}} 对）里"dict 豁免"的那一条
  由 `errors=0` 收紧成 `errors=1`，该份指纹因此重封为 `{{CONTAINER_FP}}` ——
  旧指纹 `fnv1a64:7349f8d14b3fc9fc` 是 R13 台账里那次读数的身份，不改写它。
- 回归锁：`tests/test_dict_elements_r14.py`（{{LOCKS}} 支 `def test_`），
  同轮把 R13 的两条豁免锁改成反向断言（`test_dict_value_slot_is_required_since_r14`、
  `test_dict_is_now_in_the_checked_container_list`）—— 收紧而不是删除，旧名与新断言的来由写进 docstring。
- 关单之后判据又长了一次（这一条不是补装饰，是承重矩阵抓出来的洞）：
  `verify_r14_locks.py` 的 M3 格（撤掉"数值阶梯取最宽"）在 Ω-gate 那半边 **0 失** ⇒
  说明 spec 里没有形状喂这一支。于是补 `D08_mixed_numeric_narrow`（`dict<str, int>` 收
  `{{'a': 1, 'b': 2.5}}` 要红）与成对半边 `G15_mixed_numeric_widening_ok`（同一字面量收进
  `dict<str, float>` 要绿），探针由 23 形长到 {{CASES}} 形，spec 由 23 对长到 {{DICT_CASES}} 对，
  指纹由 `{{PREV_FP}}` 变成 `{{DICT_FP}}`。本单卡片正文里那句"23 对 / `{{PREV_FP}}`"是**取号那一刻**
  的读数，append-only 不改写它，差异只在这一段里交代。
- 四套全量：pytest 半径 {{RADIUS}} → 终版 {{FINAL}}（差 {{DELTA}} = 新锁 {{LOCKS}} + 新语料 {{DICT_CASES}}，
  由本件现算对表）；自研套件 `Total|Passed|Failed = {{SUITE}}`；
  Ω-gate 全 spec `{{GATE}}`；e2e golden `PASS={{GOLDEN_P}} FAIL={{GOLDEN_F}}`。
"""


SECTION_DOC = f"""### {{kind}}({{title}} {{STAMP}}）— 追加留档（本单正文与标题行一字未添改）

- 修法：`SYNTAX/02-type-annotations.md` 的锁死用例那句改指实际文件
  （`tests/test_container_elements_r13.py`，R13 那份锁一直在 `tests/` 下而不在 `tests/regression/`），
  并在同句点名 R14 的锁 `tests/test_dict_elements_r14.py`。
- 判据（把"手册引用的路径存在"变成会红的事）：
  `tests/test_dict_elements_r14.py::test_manual_revokes_the_r13_dict_exemption`
  断言手册引用的就是**这份文件本身**（拿 `Path(__file__).name` 对表，不是抄一个字符串）；
  现跑读数：`{{MANUAL_LOCK}}`。
- 范围声明（不装作已闭合）：本单只钉了这一条路径。
  "全量扫描 SYNTAX/ + CHANGELOG + STATUS 里所有仓内引用是否存在"仍是一件**没做**的事，
  它属于 R15 的文档完整性腿，不是本单的完成项。
- 本单不动产品码：字典判定那一面在 BUG-141，两段各说各的，不互相借证据。
"""


def section(key: str) -> str:
    tmpl = SECTION_DOC if key == "R14-MANUAL-DANGLING-TEST-PATH" else SECTION
    body = (
        tmpl.replace("{STAMP}", D["stamp"])
        .replace("{MANUAL_LOCK}", D["manual_lock"])
        .replace("{PREV_FP}", D["prev_fp"])
    )
    rep = {
        "{CASES}": D["cases_probe"],
        "{SILENT_N}": len(D["silent"]),
        "{SILENT}": ", ".join(D["silent"]),
        "{LATE_N}": len(D["late"]),
        "{LATE}": ", ".join(D["late"]) or "（无）",
        "{MUSTG}": D["must_green"],
        "{KEPT}": ", ".join(D["kept_green"]),
        "{DICT_CASES}": D["dict_cases"],
        "{DICT_FP}": D["dict_fp"],
        "{CONTAINER_CASES}": D["container_cases"],
        "{CONTAINER_FP}": D["container_fp"],
        "{LOCKS}": D["locks"],
        "{RADIUS}": f"{D['radius_total']} passed",
        "{FINAL}": f"{D['final_total']} passed",
        "{DELTA}": D["delta"],
        "{SUITE}": " | ".join(D["suite"]),
        "{GATE}": "specs={0} cases={1} passed={2} failed={3}".format(*D["gate"]),
        "{GOLDEN_P}": D["golden"][0],
        "{GOLDEN_F}": D["golden"][1],
    }
    for k, v in rep.items():
        body = body.replace(k, str(v))
    return body.replace("{kind}", "FIXED").replace("{title}", titles[key])


titles = {
    "R14-DICT-LITERAL-NO-INFER": "R14 字典字面量推断件与键值位判定",
    "R14-MANUAL-DANGLING-TEST-PATH": "R14 手册锁死用例路径悬空已改指实际文件",
}


def counts(text: str) -> dict:
    blocks = re.split(r"(?m)^(?=## BUG-\d+)", text)
    return {
        "headers": len(re.findall(r"(?m)^## BUG-\d+", text)),
        "unique": len(set(re.findall(r"(?m)^## (BUG-\d+)", text))),
        "open": len(
            [
                b
                for b in blocks
                if b.startswith("## BUG-") and not re.search(r"(?m)^### (FIXED|DUPLICATE)", b)
            ]
        ),
        "fixed": len(re.findall(r"(?m)^### FIXED", text)),
        "amend": len(re.findall(r"(?m)^### 改判", text)),
    }


def main() -> int:
    refresh = "--refresh" in sys.argv
    src = LEDGER.read_text(encoding="utf-8")
    before = counts(src)
    parts = re.split(r"(?m)^(?=## BUG-\d+)", src)
    id_of = {}
    for b in parts:
        m = re.match(r"## (BUG-\d+)", b)
        if not m:
            continue
        for key in IDS:
            if f"reported_key: {key}" in b:
                id_of[key] = m.group(1)
    if set(id_of) != set(IDS):
        raise SystemExit(f"两张键在账上没配齐编号：{id_of} ⇒ 先取号再写台账，拒绝凭空插段")

    key_of_bid = {v: k for k, v in id_of.items()}
    out, touched = src, []
    for key, bid in id_of.items():
        seg = section(key)
        head = re.search(r"(?ms)^## " + re.escape(bid) + r" .*?(?=\n## BUG-|\Z)", out)
        if not head:
            raise SystemExit(f"账上查无 {bid} ⇒ 停手")
        block = head.group(0)
        pat = re.compile(r"(?ms)(?<=\n)### " + re.escape(MARK) + r".*?(?=\n## BUG-|\Z)")
        already = pat.search(block)
        if already and not refresh:
            print(f"SKIP {bid}：本件那段已在账上（覆盖用 --refresh）")
            continue
        if already:
            new_block = block[: already.start()] + seg.rstrip("\n") + "\n" + block[already.end() :]
        else:
            new_block = block.rstrip("\n") + "\n" + seg.rstrip("\n") + "\n"
        out = out.replace(block, new_block, 1)
        touched.append(bid)
    if not touched:
        print("CONCLUSION touched=0（已在账，幂等）")
        return 0

    LEDGER.with_name("bugs.md.pre_r14_ledger").write_text(src, encoding="utf-8", newline="\n")
    tmp = LEDGER.with_suffix(".md.tmp")
    tmp.write_text(out, encoding="utf-8", newline="\n")
    after_text = tmp.read_text(encoding="utf-8")
    after = counts(after_text)
    n = len(touched)
    own_segs = [section(key_of_bid[bid]) for bid in touched]
    preserved = True
    for bid in touched:
        old_block = re.search(r"(?ms)^## " + re.escape(bid) + r" .*?(?=\n## BUG-|\Z)", src).group(0)
        lines = [
            ln
            for ln in old_block.splitlines()
            if ln.startswith("## BUG-") or ln.startswith("- summary:")
        ]
        preserved = preserved and all(ln in after_text for ln in lines)
    landed = sum(1 for seg in own_segs if seg.rstrip("\n") in after_text)
    own_stamps = re.findall(
        r"(?m)^### " + re.escape(MARK) + r" .+? (20\d\d-\d\d-\d\dT\d\d:\d\d:\d\d)Z）", after_text
    )
    dirty = {
        # 未插值占位只可能长成 `{标识符}`；正文里合法的源码花括号（`{"a": "b"}`）不在该形状内。
        "own_residue": len(
            [m for seg in own_segs for m in re.findall(r"\{[A-Za-z_][A-Za-z0-9_]*\}", seg)]
        ),
        "own_stamp_count": len(own_stamps),
        "own_badstamp": len([s for s in own_stamps if s != D["stamp"].rstrip("Z")]),
    }
    delta = (
        {"open": -n, "fixed": n, "headers": 0}
        if not refresh
        else {"open": 0, "fixed": 0, "headers": 0}
    )
    ok = (
        landed == n
        and after["headers"] == before["headers"] + delta["headers"]
        and after["open"] == before["open"] + delta["open"]
        and after["fixed"] == before["fixed"] + delta["fixed"]
        and preserved
        and dirty["own_residue"] == 0
        and dirty["own_badstamp"] == 0
        and dirty["own_stamp_count"] == n
        and re.fullmatch(r"20\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ", D["stamp"]) is not None
    )
    sweep = {
        "whole_residue_lines": len(re.findall(r"(?m)^.*\{[A-Z][A-Z_]*\}.*$", after_text)),
        "whole_dblstamp_lines": len(
            re.findall(r"(?m)^.*20\d\d-\d\d-\d\dT20\d\d-\d\d-\d\dT.*$", after_text)
        ),
    }
    print("LANDED", landed, "OF", n, "DIRTY_OWN", dirty, "SWEEP", sweep)
    print("BEFORE", before, "AFTER", after, "TOUCHED", touched, "SUMMARY_KEPT", preserved)
    if not ok:
        raise SystemExit("自证不符 ⇒ 不落盘，tmp 与备份留在 .fist-loop-20260929/ 待查")
    os.replace(tmp, LEDGER)
    print(
        f"CONCLUSION r14_ledger touched={n} ids={touched} headers={after['headers']} "
        f"open={after['open']} fixed={after['fixed']} refresh={refresh} stamp={D['stamp']} "
        f"dict_cases={D['dict_cases']} dict_fp={D['dict_fp']} locks={D['locks']} "
        f"pytest={D['radius_total']}->{D['final_total']} delta={D['delta']}"
    )
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    sys.exit(main())
