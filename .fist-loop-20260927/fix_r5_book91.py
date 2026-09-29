"""R5-修复 现场新发现的一单：BUG-91 入账（附摘除/装回双向实测的逐字红字）。

缺陷本体：BUG-90 把「调用方没给源路径就不伪造身份」落地后，本环又把源路径接上了
（`CypyHook.transpile_file` / `ProjectCompiler.compile_module` 传 `source_file`）——
产物头注里的 Windows 路径带着单反斜杠，落进模块开头的三引号串就被读成 unicode 转义，
Cython 侧就地语法错误。HEAD 时代这条路不可达（没有调用方传真路径）。

判据形状（两条锁都必须「摘了就红」）：
  1. 生成器侧：`.fist-loop-20260927/fix_r5_snap/ab_escape_lock.py` 的 A/B；
  2. 调用面侧：`tests/test_project_compiler.py::TestProjectCompiler::test_single_module_compile`
     真起 Cython 编译，红字是 `CythonCompilerErrorsCompileError`。

入账后立刻在同一环修掉，所以 detail 里写的是「立单时产品码原文」+「已修」的实测对照，
而不是「待修」。
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import lfist_lib  # noqa: E402

GEN = ROOT / "cypyc" / "codegen" / "cython_generator.py"
LEDGER = ROOT / "memory" / "bugs.md"
DB = ROOT / "fist-mbt.db"
AB = HERE / "fix_r5_snap" / "ab_escape_lock.py"
DROP = '.replace("\\\\", "\\\\\\\\")'
TARGETS = [
    "tests/codegen/test_r5_fix_codegen.py::"
    "test_bug91_windows_path_in_header_docstring_is_a_valid_literal",
    "tests/test_project_compiler.py::TestProjectCompiler::test_single_module_compile",
]
SUMMARY = (
    "[CODEGEN_header_docstring_backslash_escape] 产物头注把 Windows 源路径原文写进三引号串，"
    "反斜杠没转义 ⇒ Cython 就地语法错误"
)
REFUSE: list = []
CHECKS: list = []


def check(label: str, got, want, why: str) -> None:
    ok = got == want
    CHECKS.append({"label": label, "ok": ok, "got": got, "want": want, "why": why})
    if not ok:
        REFUSE.append(f"{label}：实得 {got} / 应得 {want}（{why}）")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:12]


def pytest_tail(text: str, limit: int = 700) -> str:
    """取 pytest 输出里最能说明问题的一段（断言行 + 失败汇总），逐字保留。"""
    lines = [ln.rstrip() for ln in (text or "").splitlines() if ln.strip()]
    keep = [ln for ln in lines if re.search(r"^(E |FAILED|Cython|Assert|.*Error)", ln)]
    return "\n".join(keep[:14])[:limit]


def measure() -> dict:
    """跑一次双向 A/B：摘除转义 ⇒ 两条锁都红；按字节装回 ⇒ 两条都绿。"""
    original = GEN.read_bytes()
    text = original.decode("utf-8")
    hits = text.count(DROP)
    check("锚点唯一：产品码里那条 replace 只有一处", hits, 1, f"命中 {hits} 处")
    if hits != 1:
        return {}
    before = {t: run_pytest(t) for t in TARGETS}
    GEN.write_bytes(text.replace(DROP, "", 1).encode("utf-8"))
    try:
        during = {t: run_pytest(t) for t in TARGETS}
    finally:
        GEN.write_bytes(original)
    after = {t: run_pytest(t) for t in TARGETS}
    check("摘除前两条锁都必须绿", [rc for rc, _ in before.values()], [0, 0], str(before))
    check("摘除后两条锁都必须红", [rc for rc, _ in during.values()], [1, 1], str(during))
    check("装回后两条锁都必须绿", [rc for rc, _ in after.values()], [0, 0], str(after))
    check("装回按字节一致（没顺手改坏别处）", sha(GEN.read_bytes()), sha(original), "sha 前 12 位")
    return {
        "before": {t: v[1] for t, v in before.items()},
        "red_while_removed": {t: v[1] for t, v in during.items()},
        "green_after_restore": {t: v[1] for t, v in after.items()},
        "generator_sha": sha(original),
    }


def run_pytest(target: str) -> tuple:
    p = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "pytest", "-q", target],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return p.returncode, pytest_tail((p.stdout or "") + (p.stderr or ""))


def ledger_numbers(text: str) -> list:
    return [int(x) for x in re.findall(r"(?m)^## BUG-(\d+) ", text)]


def brief(d: dict) -> str:
    """把每条锁的最后输出压成一行（detail 里只放摘要，全文在 measurement 件里）。"""
    return json.dumps({k: v[:90] for k, v in d.items()}, ensure_ascii=False)


def bug_rows() -> int:
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    n = con.execute("select count(*) from tasks where ns='bugs'").fetchone()[0]
    m = con.execute("select count(*) from call_log where tool='report_bug'").fetchone()[0]
    con.close()
    return n, m


def main() -> int:
    if "--check" in sys.argv:
        doc = json.loads((HERE / "fix_r5_book91.json").read_text(encoding="utf-8"))
        for c in doc["checks"]:
            if not c["ok"]:
                REFUSE.append(f"复算 {c['label']}：实得 {c['got']} / 应得 {c['want']}")
        print(json.dumps({"refuse": REFUSE, "checks": len(doc["checks"])}, ensure_ascii=False))
        return 1 if REFUSE else 0

    nums0 = ledger_numbers(LEDGER.read_text(encoding="utf-8"))
    n_bug0, log0 = bug_rows()
    want_num = nums0[-1] + 1
    meas = measure()
    if not meas:
        print(json.dumps({"refuse": REFUSE}, ensure_ascii=False))
        return 1

    before_s = brief(meas["before"])
    after_s = brief(meas["green_after_restore"])
    pre_code = (
        "  `self._write(f\"Source file: {self.source_file or '<not supplied by caller>'}\")`\n"
    )
    detail = (
        "立单依据（产品码原文，摘除转义后的形状）：\n"
        + pre_code
        + "  ——路径原文里的反斜杠紧跟 U 时，落在模块 docstring 的三引号串里就是非法 unicode 转义。\n\n"
        "可达性：BUG-90 之后调用方开始传真路径（`cypy_hook/hook.py` 的 `transpile_file` → "
        "`transpile(source, source_path=...)`、`cypyc/project/project_compiler.py` 的 "
        "`compile_module` → `CythonGenerator(self._source_files.get(module_name))`）。"
        "HEAD 时代没有任何调用方覆盖 `source_file=None`，所以这条不可达——"
        "是 BUG-90 收口时只改生成器、没管调用方留下的第二个口子（本单补的就是这一半）。\n\n"
        "现场复跑（摘除/装回双向，逐字红字见 red_while_removed）：\n"
        f"  判据件：{AB.relative_to(ROOT).as_posix()}\n"
        f"  锁 1（生成器侧）：{TARGETS[0]}\n  锁 2（调用面侧，真起 Cython 编译）：{TARGETS[1]}\n"
        f"  摘除前：{before_s}\n"
        f"  摘除后：\n{meas['red_while_removed'][TARGETS[0]]}\n---\n"
        f"{meas['red_while_removed'][TARGETS[1]]}\n"
        f"  装回后：{after_s}\n\n"
        "症状 3 条：项目模式 `.pyx` 就地编译失败（`Cython.Compiler.Errors.CompileError`）；"
        "产物头注行反斜杠数量与 `__file__` 常量不一致；同一段元数据（版本/目标/profile）照发\n\n"
        f"机制：产物头注走 f-string 直插路径原文，不过任何转义；"
        f"生成器写死 `Source file: {{path}}`，而 `{TARGETS[1].split('::')[0]}` 的临时目录是 Windows 路径\n\n"
        '修法（本环已改）：`shown_source = (self.source_file or "<not supplied by caller>").replace(...)` '
        "——反斜杠成对后再写头注；`__name__`/`__file__` 走 repr 不受影响\n\n"
        "不算证明：本单没有跨平台验证（Linux/macOS 路径无反斜杠，这条判据在那些平台上恒绿）；"
        "路径含三引号或尾随引号的情形未覆盖，只保证「反斜杠不吃字符」\n\n"
        f"去重结论：与 memory/bugs.md 现有 {len(nums0)} 单按机制签名比对无重合；"
        "近亲逐条裁决=BUG-90（同一段产物头注，那条讲「不伪造身份」，这条讲「传真路径时转义」）、"
        "BUG-81/82（comptime 结果直插产物不吃转义，同一类形状但落点是 docstring 位 vs 字面量位）。\n\n"
        f"来历：[loop:20260927-loop:R5-修复] {lfist_lib.utc_now()} 实测；"
        "severity=high（P1：接上调用方后项目模式产物直接编不过）；修属：R5-修复（同环已修）"
    )

    n_bug1, log1 = bug_rows()
    resp = {}
    try:
        c = lfist_lib.Client(timeout=180)
        resp = c.call(
            "report_bug",
            {
                "summary": SUMMARY,
                "detail": detail,
                "severity": "high",
                "project_dir": ".",
                "reported_by": "cypy-fixer",
                "publish_task": True,
                "now": lfist_lib.utc_now(),
            },
        )
        c.close()
    except Exception as exc:
        REFUSE.append(f"report_bug 抛 {type(exc).__name__}: {exc}")

    back = ledger_numbers(LEDGER.read_text(encoding="utf-8"))
    got_num = back[-1] if back else None
    n_bug2, log2 = bug_rows()
    check("账本新条目号就是预期的下一号", f"BUG-{got_num}", f"BUG-{want_num}", f"现有 {back[-6:]}")
    check(
        "新单标题进了账本正文",
        SUMMARY.split("]")[0][1:] in LEDGER.read_text(encoding="utf-8"),
        True,
        "机制签名",
    )
    check("sqlite bugs 树 +1", n_bug2 - n_bug1, 1, f"{n_bug1}→{n_bug2}")
    check("call_log report_bug +1", log2 - log1, 1, f"{log1}→{log2}")
    rpc_id = resp.get("bug_id") or resp.get("id") or resp.get("task_id")
    check(
        "RPC 回了单号（不能只靠账本）",
        bool(rpc_id),
        True,
        json.dumps(resp, ensure_ascii=False)[:200],
    )

    doc = {
        "started_at_utc": lfist_lib.utc_now(),
        "ring": "R5-修复",
        "bug_num": f"BUG-{got_num}",
        "expected_num": f"BUG-{want_num}",
        "rpc": {
            "bug_id": rpc_id,
            "raw_keys": sorted(resp.keys()) if isinstance(resp, dict) else [],
        },
        "measurement": meas,
        "targets": TARGETS,
        "ledger_before": len(nums0),
        "ledger_after": len(back),
        "sqlite_bugs": [n_bug1, n_bug2],
        "calllog_report_bug": [log1, log2],
        "checks": CHECKS,
        "refuse": REFUSE,
    }
    (HERE / "fix_r5_book91.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps({"bug": doc["bug_num"], "rpc": rpc_id, "refuse": REFUSE[:6]}, ensure_ascii=False)
    )
    return 1 if REFUSE else 0


if __name__ == "__main__":
    sys.exit(main())
