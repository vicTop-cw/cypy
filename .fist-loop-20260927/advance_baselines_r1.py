"""R1-推进 law6/7：基线不回落 + 文档声明句的验收（数字全部实测，不引用别处的观测值）。

判据：
 7a pytest 全量 `passed ≥ 1868`（= 打磨轮终态 1862 + 本轮新增 6 条锁）且零红零错；
 7b 自研套件末行逐字段解析（total=47、passed=total、failed=0、skipped=0）且 rc=0；
 7c 端到端基准（不带 --update）`PASS=25 FAIL=0`；
 7d 本轮新文件被收集到 6 条（防止"文件写了但一根锁没跑"）；
 6a 文档双向核对：`SYNTAX/13-build-blocks.md` 里声明 `let result =:` 的**原文代码块**逐字送进
    `cypyc transpile`，必须 rc=0 且产物结构与裸形一致（只把文档承诺的形状当判据，不自行加严）；
 6b 半径核对：本轮产品改动只落在两个既有函数体内，`git diff` 里没有新增 TokenType/新语法规则。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(r"E:\IDEProjects\AI\Cypy")
sys.path.insert(0, str(HERE))
import lane_load  # noqa: E402
from advance_lockproof_r1 import ADV1_AFTER, ADV2_AFTER  # noqa: E402

FLOOR = 1868
SUITE_CASES = 47
REFUSE = []


def sh(cmd: list, timeout: int = 3600) -> tuple:
    r = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def run_save(cmd: list, log: str, timeout: int = 3600) -> tuple:
    rc, out = sh(cmd, timeout)
    (HERE / log).write_text(out, encoding="utf-8", newline="\n")
    return rc, out


def suite_verdict(line: str) -> tuple:
    m = re.match(
        r"^Total:\s*(?P<total>\d+)\s*\|\s*Passed:\s*(?P<passed>\d+)\s*\|"
        r"\s*Failed:\s*(?P<failed>\d+)\s*\|\s*Skipped:\s*(?P<skipped>\d+)$",
        line.strip(),
    )
    if not m:
        return False, "末行不符合 `Total: N | Passed: N | Failed: N | Skipped: N`，判据无法证明绿"
    f = {k: int(v) for k, v in m.groupdict().items()}
    if f["total"] != SUITE_CASES:
        return False, f"用例总数 {f['total']} ≠ {SUITE_CASES}"
    if f["passed"] != f["total"]:
        return False, f"passed {f['passed']} < total {f['total']}"
    if f["failed"] or f["skipped"]:
        return False, f"failed={f['failed']} skipped={f['skipped']}"
    return True, ""


def doc_block(rel: str, needle: str) -> str:
    """取文档里包含 needle 的那个 ``` 代码块的原文（逐字，不做任何"顺手修正"）。"""
    text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
    blocks = re.findall(r"```[a-zA-Z]*\n(.*?)```", text, flags=re.S)
    for b in blocks:
        if needle in b:
            return b
    return ""


def main() -> int:
    load = lane_load.snapshot()
    if not load.get("measured"):
        REFUSE.append(f"负载探针测不到：{load.get('reason')}")

    rc, out = run_save(
        [sys.executable, "-X", "utf8", "-m", "pytest", "tests/", "-q", "-p", "no:cacheprovider"],
        "advance_pytest_r1.log",
        3600,
    )
    m = re.search(r"(\d+) passed", out)
    passed = int(m.group(1)) if m else None
    bad = re.findall(r"(\d+) (?:failed|error)", out)
    summary = [ln for ln in out.splitlines() if " passed" in ln or " failed" in ln]
    doc = {
        "load": load,
        "pytest": {
            "rc": rc,
            "passed": passed,
            "failed_or_error": bad,
            "failed_tests": sorted(set(re.findall(r"^FAILED (\S+)", out, flags=re.M))),
            "skipped_lines": out.count("SKIPPED"),
            "summary_line": summary[-1][:200] if summary else "",
        },
    }
    if passed is None:
        REFUSE.append(f"判据7a 解析不到 passed 计数：{doc['pytest']['summary_line'][:160]}")
    elif passed < FLOOR:
        REFUSE.append(f"判据7a 通过数 {passed} < 下限 {FLOOR} ⇒ 基线回落")
    if bad:
        REFUSE.append(f"判据7a 有红/错：{bad}")

    rc, out = run_save(
        [sys.executable, "-X", "utf8", "scripts/run_tests.py"], "advance_suite_r1.log", 1800
    )
    line = next((ln for ln in out.splitlines() if ln.startswith("Total:")), "")
    ok, why = suite_verdict(line)
    doc["suite"] = {"rc": rc, "line": line, "green": ok, "verdict": why or "绿"}
    if not ok:
        REFUSE.append(f"判据7b 自研套件不绿：{line!r}（原因：{why}）")
    if rc != 0:
        REFUSE.append(f"判据7b 自研套件退出码非零：rc={rc}")

    rc, out = run_save(["bash", "scripts/e2e_golden.sh"], "advance_e2e_r1.log", 2400)
    gline = next((ln for ln in out.splitlines() if "PASS=" in ln), "")
    doc["e2e"] = {"rc": rc, "line": gline}
    if "PASS=25 FAIL=0" not in gline:
        REFUSE.append(f"判据7c 端到端基准不是 25/25：{gline!r} rc={rc}")

    rc, out = sh(
        [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "pytest",
            "tests/test_loop_20260927_advance.py",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            "-o",
            "addopts=",
        ],
        300,
    )
    # 项目 addopts 里带 -v，`--collect-only -q` 会打成 <Function …> 树而不是 `id::name` 行 ⇒
    # 必须显式清空 addopts，两种形状也都要能数到（判据不能只认自己习惯的那一种）。
    collected = len(
        set(re.findall(r"::(test_\w+)", out)) | set(re.findall(r"<Function (test_\w+)>", out))
    )
    doc["collection"] = {
        "rc": rc,
        "count": collected,
        "file": "tests/test_loop_20260927_advance.py",
    }
    if collected != 6:
        REFUSE.append(f"判据7d 新文件收集到的锁数 {collected} ≠ 6")

    # law6a：把文档原文代码块打到 CLI 调用面
    blk = doc_block("SYNTAX/13-build-blocks.md", "let result =:")
    probe = HERE / "probes" / "doc_13_let_block.cypy"
    probe.parent.mkdir(parents=True, exist_ok=True)
    probe.write_text(blk, encoding="utf-8", newline="\n")
    rc, out = sh(
        [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "cypyc",
            "transpile",
            str(probe.relative_to(ROOT)).replace("\\", "/"),
            "-o",
            str((HERE / "probes" / "out").relative_to(ROOT)).replace("\\", "/"),
        ],
        300,
    )
    emitted = HERE / "probes" / "out" / (probe.stem + ".pyx")
    code = emitted.read_text(encoding="utf-8", errors="replace") if emitted.exists() else ""
    doc["doc_example"] = {
        "where": "SYNTAX/13-build-blocks.md（含 `let result =:` 的原文块，逐字送进 CLI）",
        "quoted": blk.strip().splitlines()[:6],
        "rc": rc,
        "cli_error": next(
            (ln.strip()[:160] for ln in out.splitlines() if "rror" in ln or "xpect" in ln), ""
        ),
        "emit_has_block_call": bool(re.search(r"(?m)^\w+\s*=\s*_bb_\d+\(\)$", code)),
    }
    if not blk:
        REFUSE.append("判据6a 从 13 号文档里取不到含 `let result =:` 的代码块 ⇒ 声明句核对无从谈起")
    elif rc != 0:
        REFUSE.append(
            f"判据6a 文档原文例子在 CLI 上没过：rc={rc} {doc['doc_example']['cli_error']}"
        )
    elif not doc["doc_example"]["emit_has_block_call"]:
        REFUSE.append("判据6a 文档原文例子的产物里没有『先定义块再赋值调用』的结构")

    # law6b：半径核对——**用 mtime 归属**（工作树里还有上一轮的未提交改动，拿 git diff 当"本轮改了啥"
    # 会把别人的改动算成本轮，那是判据坏不是代码坏）。起点取"打磨轮收口件落盘的时刻"，
    # 之后动过的产品文件必须恰好是两个。
    start_ts = (HERE / "close_r1_polish_root.out.json").stat().st_mtime
    touched = sorted(
        f.relative_to(ROOT).as_posix()
        for d in ("cypyc", "cypy_bridge", "test_suite", "scripts")
        for f in (ROOT / d).rglob("*.py")
        if f.stat().st_mtime >= start_ts
    )
    expect = {"cypyc/codegen/cython_generator.py", "cypyc/parser/parser.py"}
    _hunks = ADV1_AFTER + chr(10) + ADV2_AFTER
    mine_added = [ln.strip() for ln in _hunks.splitlines() if ln.strip()]
    new_syntax = [a for a in mine_added if re.search(r"^\s*(class \w+|\w+\s*=\s*\")", a)]
    doc["radius"] = {
        "attribution": "mtime ≥ 本轮起点（不是 git diff——工作树里还有上一轮的未提交改动）",
        "since": "polish 收口之后",
        "product_files_touched_this_stage": touched,
        "expected": sorted(expect),
        "new_token_or_class_defs_in_my_hunks": new_syntax,
    }
    if set(touched) != expect:
        REFUSE.append(
            f"判据6b 本轮动过的产品文件与预期两个不符：多了 {sorted(set(touched) - expect)}，"
            f"少了 {sorted(expect - set(touched))}"
        )
    if new_syntax:
        REFUSE.append(
            f"判据6b 我的改动里出现了新增语法单元（越出『已声明未实现』半径）：{new_syntax[:4]}"
        )

    # 本轮改动自身的 lint（只作用到自己写的行，沿用验证轮的作用域口径）
    # 作用域 = 本轮**自己写过的每一个文件**（产品 2 个 + 新测试 1 个 + lane 取证件 8 个）。
    # 之前只列两个 lane 脚本，那是"清单口径漏文件 ⇒ 自己写的违例无人认领"的复发。
    # 归属分两类口径，混用就会"把自己的代码放掉 / 把别人的存量债算到自己头上"：
    #  - 本轮**整篇新写**的文件（新测试 + lane 取证件）：所有违例都算我的；
    #  - 本轮**只改了几个区间**的既有产品文件：只有落在**亲笔行区间**内的违例才算我的。
    #    上一版把这两个产品文件也塞进"整篇新写"那一栏，于是 673 条存量 E501 全被判成本轮违例。
    AUTHORED_WHOLE = [
        "tests/test_loop_20260927_advance.py",
        ".fist-loop-20260927/lane_load.py",
        ".fist-loop-20260927/advance_baselines_r1.py",
        ".fist-loop-20260927/advance_verify_r1.py",
        ".fist-loop-20260927/advance_lockproof_r1.py",
        ".fist-loop-20260927/advance_file_bugs_r1.py",
        ".fist-loop-20260927/close_stage_generic.py",
        ".fist-loop-20260927/close_root_generic.py",
    ]
    PREEXISTING = ["cypyc/parser/parser.py", "cypyc/codegen/cython_generator.py"]
    # 唯一的豁免：报告生成器里嵌的是 markdown 表格行，折行会破坏表格 ⇒ 只放过它的 E501，
    # 其余码照抓，并在报告 §四 里点名这条豁免（不做静默过滤）。
    E501_ONLY_EXEMPT = [".fist-loop-20260927/gen_report_r1_advance.py"]
    fl = sh(
        [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "flake8",
            "--max-line-length=100",
            *AUTHORED_WHOLE,
            *PREEXISTING,
            *E501_ONLY_EXEMPT,
        ]
    )
    hits = [h for h in fl[1].splitlines() if re.search(r":\d+:\d+: [EWFC]\d+", h)]

    def hunk_lines(rel: str, hunk: str) -> set:
        """亲笔区间：把补丁全文在文件里定位（必须恰好命中 1 处，否则判据作废）后取其行号集合。"""
        raw = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        n = raw.count(hunk)
        if n != 1:
            REFUSE.append(f"判据7e 亲笔区间定位失败：{rel} 里该补丁命中 {n} 处（要求恰好 1）")
            return set()
        start = raw[: raw.index(hunk)].count(chr(10)) + 1
        return set(range(start, start + len(hunk.rstrip().splitlines())))

    MY_LINES = {}
    for rel, hunk in (
        ("cypyc/codegen/cython_generator.py", ADV1_AFTER),
        ("cypyc/parser/parser.py", ADV2_AFTER),
    ):
        if rel in PREEXISTING:
            MY_LINES[rel] = hunk_lines(rel, hunk)

    mine_hits = []
    exempted = []
    for h in hits:
        parts = h.split(":")
        rel = parts[0].replace("\\", "/")
        if rel in E501_ONLY_EXEMPT and ": E501 " in h:
            exempted.append(h[:160])
            continue
        if rel in AUTHORED_WHOLE:
            mine_hits.append(h[:200])
            continue
        if rel in MY_LINES and len(parts) > 2 and parts[1].isdigit():
            if int(parts[1]) in MY_LINES[rel]:
                mine_hits.append(h[:200])
    doc["lint"] = {
        "scanned_files": len(AUTHORED_WHOLE) + len(PREEXISTING) + len(E501_ONLY_EXEMPT),
        "authored_whole": len(AUTHORED_WHOLE),
        "preexisting_with_hunk_ranges": {k: sorted(v) for k, v in MY_LINES.items()},
        "total_in_scope_files": len(hits),
        "attributable_to_this_round": sorted(set(mine_hits))[:12],
        "e501_only_exempted_files": E501_ONLY_EXEMPT,
        "exempted_hits": len(exempted),
    }
    if sorted(set(mine_hits)):
        REFUSE.append(f"判据7e 本轮自己写的代码有 lint 违例：{sorted(set(mine_hits))[:6]}")

    # 7f：项目 pyproject 声明了 black ⇒ 本轮**整篇新写**的文件必须 black 干净。
    # 不对既有产品文件做这条断言（全仓 4 个产品文件本就要整档重排，那是转结里的裁决项，不是本轮的债）。
    bk = sh([sys.executable, "-X", "utf8", "-m", "black", "--check", *AUTHORED_WHOLE])
    bk_lines = [x for x in bk[1].splitlines() if "would reformat" in x or "left unchanged" in x]
    doc["black"] = {"rc": bk[0], "files": len(AUTHORED_WHOLE), "line": bk_lines[:8]}
    if bk[0] != 0:
        REFUSE.append(f"判据7f 本轮新写的文件不是 black 干净：{bk_lines[:6]}")

    (HERE / "advance_baselines_r1.json").write_text(
        json.dumps({"refuse": REFUSE, **doc}, ensure_ascii=False, indent=1),
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "refuse": REFUSE,
                "pytest": doc["pytest"],
                "suite": doc["suite"],
                "e2e": doc["e2e"],
                "collection": doc["collection"],
                "radius": doc["radius"],
                "lint": doc["lint"],
                "doc_rc": doc["doc_example"]["rc"],
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 1 if REFUSE else 0


if __name__ == "__main__":
    sys.exit(main())
