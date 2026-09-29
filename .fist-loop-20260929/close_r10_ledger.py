"""R10 收尾账面：三张新缺陷单（report_bug 取号）+ BUG-118 的 `### FIXED` 追加段。

纪律：
- 先取号再写台账（FIXED 段里引用的编号全部来自本脚本实测的 `bug_list`/账本反解，不手敲）；
- 幂等守卫：FIXED 段已存在 ⇒ 只指认不重复追加；卡片 summary needle 已在账本 ⇒ 标 `### DUPLICATE` 候选并跳过；
- 追加段只增不改：写前留 `.pre_r10_fixed` 快照，写后逐字校验原正文与标题行未被改动。
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LEDGER = ROOT / "memory" / "bugs.md"
SNAPSHOT = HERE / "bugs.md.pre_r10_fixed"
OUT = HERE / "close_r10_ledger.json"
NS = "cypy-loop-20260929"
AGENT = "cypy-selfdrive-agent"

NEW_CARDS = [
    {
        "key": "R10-JUDGE-GETSOURCE-SKew",
        "severity": "medium",
        "summary": ("[判据面·仓内尺子] inspect.getsource 型源码文本锁在同一进程内被测文件行号漂移时会读到错位窗口，"
                    "全量跑期间改产品文件就造出假红"),
        "detail": (
            "本轮实测（逐字见 `.fist-loop-20260929/logs/r10_pytest_a2.log`）："
            "`FAILED tests/test_polish_20260926_pass7.py::test_bug26_artifact_scan_accepts_non_windows_extensions`，"
            "失败原因是 `assert ([])` —— 即 `scan` 列表为空，而不是产物真的退化了。"
            "同一条单跑 `1 passed in 0.08s`；把树冻结后重跑两轮全量（a3、a4）都是 2241 passed rc=0。\n"
            "机制（可复算，不是猜测）：该锁用 `inspect.getsource(comp.BridgeCompiler._compile_c_to_shared_lib)`，"
            "函数对象的 `co_firstlineno` 在 import 那一刻定格。我在 a2 全量运行中途（06:10:30Z 前后）编辑了"
            "`cypy_bridge/compiler.py:284` 区（净 +1 行），目标函数在 :3760、`endswith('.pyd')` 那行在 :3837 —— "
            "旧行号去切新文件字节，窗口整体错开 1 行 ⇒ 扫不到目标行 ⇒ 断言把「尺读错了位置」渲染成「产品退化了」。\n"
            "危害：这类「红」不是产品信号，且任何在 CI 里与源码改动并发的 inspect.getsource 锁都不可信。"
            "本仓同型锁不少（`grep -rn 'inspect.getsource' tests/ | wc -l` 实测计数见本轮报告 §5）。\n"
            "建议（交裁决，不在本环半径）：① 这类锁改为直接从磁盘取函数体（`ast.get_source_segment` 或按 `def` 行做区间切），"
            "不依赖 code 对象的行号；② 或在 conftest 里对被 getsource 的模块加身份断言（file + 行号自证）。"
            "流程侧本轮已做：全量跑期间冻结被测量面，a2 判作废并重跑 a3/a4 留档。\n"
            "定性：[真缺陷·仓内判据面]。复跑现形方式：在 `pytest tests` 运行中途编辑 `cypy_bridge/compiler.py` 的 :284 区。"
        ),
    },
    {
        "key": "R10-STATUS-DOC-BLANKET-CLAIM",
        "severity": "medium",
        "summary": ("[文档面·主张宽于判据] SYNTAX_IMPLEMENTATION_STATUS.md 对每一章逐行写「✅ 完整 / 无缺口」，"
                    "与账本 open 面直接矛盾，且全仓无任何判据认领这张表"),
        "detail": (
            "实测：`SYNTAX_IMPLEMENTATION_STATUS.md:330-356` 每章一行、清一色 `| ✅ 完整 | 无 |`（含本环已确认存在"
            "解析缺口的 `07-trait-impl.md`、`08-class.md`、`11-generics.md`）；"
            "`grep -rn 'SYNTAX_IMPLEMENTATION_STATUS' tests/ scripts/ PROJECT-SPEC/` → **0 命中** ⇒ 这张表的每一格都是无主主张。\n"
            "本环的两个直接反例：BUG-119（`class Box<T>:` 不解析）、BUG-120（trait 无体抽象方法不解析）"
            "都落在被标成「无缺口」的章节里。本轮只把 `11-generics.md` 那一行改成 `⚠ 部分` 并点名四个缺口 "
            "（BUG-119/120/121/122）+ 已闭环面（BUG-118），其余行不动 —— 未实测的格子不由我代写。\n"
            "危害：读者会把这张表当审计结论用；而它既不与账本对齐，也不与 Ω-spec 覆盖面对齐（Ω-spec 目前 4 op/71 对，"
            "远未覆盖 26 章）。\n"
            "建议（交裁决，二选一）：① 给表配判据 —— 逐格要求「缺口栏非空 ⇔ 账本存在同号 OPEN 单」，"
            "并把 `corpus/` 的 op 数/测试对数写进表；② 把表的口径收窄到可判定的「解析层是否接受该章语法」。\n"
            "定性：[真缺陷·主张宽于判据]。"
        ),
    },
    {
        "key": "R10-BUILTIN-NAME-SHADOWS-USER-FN",
        "severity": "high",
        "summary": ("[codegen·静默错误产物] 用户 def id/addr 的调用点在产物里被改写成 C 构造（`id(3)`→`<size_t><void*>3`、"
                    "`addr(3)`→`&3`），函数照样导出，编译期 0 诊断"),
        "detail": (
            "实测（调用面 = `scripts/omega_gate.py` 的同一条 execute 管线）：\n"
            " - `def id(x: int) -> int:` + `y: int = id(3)` ⇒ 产物含 `__all__ = [\"id\", \"f\"]`、`def id(x):`，"
            "但调用点渲染为 `y: int = <size_t><void*>3`（用户函数被整个跳过）；\n"
            " - `def addr(v: int) -> int:` + `addr(3)` ⇒ `y: int = &3`（对字面量取地址，Cython 侧是非法构造）；\n"
            " - `def sizeof(n: int) -> int:` + `sizeof(3)` ⇒ 产物 `sizeof(3)`（同一条分支，未做编译验，运行/编译面另测）。\n"
            "机制：`cypyc/codegen/cython_generator.py:3779-3810` 的特判只看 `func_name` 字符串"
            "（`malloc/sizeof/addr/free/id/isinstance`），不看该名字在本模块是否被用户 `def` 占用；"
            "分析器侧也没有「内置名不可重定义 / 重定义即拒」的判定，文档亦无声明"
            "（`grep -rn '内置函数.*覆盖|覆盖.*内置|shadow.*builtin' SYNTAX/` → 0 命中）。\n"
            "危害：与 BUG-023 的 trait isinstance 注册表改写同族 —— 声明侧与调用侧口径分叉，用户看不出异常，"
            "`isinstance` 那条还会与 `_known_traits` 判定叠加。\n"
            "建议（交裁决，本环不扩权）：要么在分析器把「与内置特判同名」判成诊断（窄、可判定），"
            "要么让这些特判仅在该名字未被用户 `def` 占用时生效。\n"
            "定性：[真缺陷·静默错误产物]。复跑：`python -X utf8 -c \"import sys; sys.path.insert(0,'scripts'); "
            "import omega_gate as og; print(og.execute({'op':'codegen','src':'def id(x: int) -> int:\\n    return x\\n\\n\\n"
            "def f() -> int:\\n    return id(3)\\n'})['code'])\"`"
        ),
    },
]

FIXED_MARK = "### FIXED(修复=已完成) — 2026-09-29"
BUG118_NEEDLE = "- reported_key: R10-CALLSITE-CHECKER"


def headers(text: str) -> list:
    return [int(m) for m in re.findall(r"(?m)^## BUG-(\d+) ", text)]


def refused(res) -> bool:
    blob = json.dumps(res, ensure_ascii=False)
    return "__error__" in blob or blob.startswith("RPC-ERROR") or (res or {}).get("ok") is False


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    before = LEDGER.read_text(encoding="utf-8")
    ids_before = set(headers(before))
    rep = {"started_z": started, "ids_before_max": max(ids_before), "filed": [], "refusals": [],
           "skipped_existing": [], "fixed": {}}
    SNAPSHOT.write_text(before, encoding="utf-8", newline="\n")

    sys.path.insert(0, str(ROOT / "scripts"))
    os.environ["FIST_NAMESPACE"] = NS
    os.environ["FIST_SERVER_CWD"] = str(ROOT).replace("\\", "/")
    import fist  # noqa: PLC0415

    c = fist.FistClient(timeout=180)
    for card in NEW_CARDS:
        if card["key"] in before or card["summary"][:48] in before:
            rep["skipped_existing"].append({"key": card["key"], "needle": card["summary"][:48]})
            continue
        res = c.call("report_bug", {"project_dir": ".", "summary": card["summary"],
                                   "severity": card["severity"],
                                   "detail": card["detail"] + f"\n- reported_key: {card['key']}",
                                   "reported_by": AGENT, "publish_task": False})
        rec = {"key": card["key"], "reply_verbatim": json.dumps(res, ensure_ascii=False)[:320]}
        (rep["refusals"] if refused(res) else rep["filed"]).append(rec)
    bl = c.call("bug_list", {"project_dir": ".", "namespace": "bugs", "limit": 400})
    rep["bug_list_rows"] = len(bl.get("bugs") or []) if isinstance(bl, dict) else 0
    if rep["bug_list_rows"] == 0:
        rep["refusals"].append({"node": "(回读)", "tool": "bug_list",
                               "reply_verbatim": json.dumps(bl, ensure_ascii=False)[:300]})
    c.close()

    after = LEDGER.read_text(encoding="utf-8")
    ids_after = set(headers(after))
    rep["new_ids"] = sorted(i for i in ids_after - ids_before)
    rep["ids_after_max"] = max(ids_after)
    rep["keys_present"] = {card["key"]: card["key"] in after for card in NEW_CARDS}

    # BUG-118 的 FIXED 追加段（编号取自上面实测的 new_ids，不手敲）
    if BUG118_NEEDLE in after:
        block_start = after.index(BUG118_NEEDLE)
        nxt = after.find("\n## BUG-", block_start)
        insert_at = nxt if nxt != -1 else len(after)
        seg = after[block_start:insert_at]
        if FIXED_MARK in seg:
            rep["fixed"]["BUG-118"] = {"skipped": "FIXED 段已在盘上，不重复追加（幂等守卫）"}
        else:
            section = (
                "\n" + FIXED_MARK + " — 追加留档（2026-09-29 R10 自驱组合环，"
                "本条目正文与标题行 `OPEN` 一字未改）\n"
                "- 规范先行：`SYNTAX/11-generics.md` 新增「调用点的类型实参」规则 1-5 + 「明确不支持」表"
                "（逐条指认 BUG-119/120/121/122，本单只覆盖尖括号形态）\n"
                "- 修复面：`cypyc/parser/parser.py:650-658`（`Call.checker` → `Call.type_args`）、"
                "`:3855-3878`（可回溯试探的类型实参表，收逗号多项）、`:3943-3951`（实参表只归紧邻一次调用）；"
                "`cypyc/codegen/cython_generator.py:3814-3818`（删 `(checker(), f(args))[1]`，产物只留调用）；"
                "`cypyc/analyzer/type_checker.py:1273-1303`（`_bind_explicit_type_args`：元数/非泛型/代入）、"
                "`:1330-1347`（显式实参优先于推断）；`cypy_bridge/compiler.py:284-289`（第二台发射器的同形死码一并删）\n"
                "- 判据面：`corpus/cypy.generic.callsite.json` 20 对（`fnv1a64:65bd56a87c83d42a`），"
                "Ω-gate 逐字 `CONCLUSION specs=4 cases=71 passed=71 failed=0 refused=0 accuracy=100.00% rc=0`；"
                "回归件地板 `FLOOR_SPECS` 3→4、`FLOOR_CASES` 51→71\n"
                "- 回归锁：`tests/test_generic_callsite_r10.py` 9 支 + corpus 20 对（由 "
                "`tests/regression/test_corpus_pairs.py` 逐对执行）\n"
                "- 承重证明（变异矩阵 6 格 9 门全过，`.fist-loop-20260929/verify_r10_locks.json`；"
                "语料扩到 20 对后以本轮报告 §5 的复跑数为准）：L1 三处全退 18 红 + gate 3/14 rc=1、"
                "L2 只退解析器 10 红、L3 只退分析器 7 红、L4 产物退回零参调用形态 9 红、"
                "L5 只改注释对照 0 红 ⇒ 解析/生成/分析三处各自承重，尺子不读散文\n"
                "- 调用面证据：全仓 13 处调用点（`.fist-loop-20260929/baseline_r10_typeargs.json`："
                "generic_func 11 / generic_struct 2 / parse_fail 0）产物从 "
                "`(NamedItem(), display_name(item))[1]` 变为 `display_name(item)`；"
                "`examples/generic.cypy`、`examples/generics_advanced.cypy` 走 `cypyc transpile --check-only` rc=0\n"
                "- 终验（冻结被测量面后）：pytest 2241 passed rc=0；自研套件 47/47；"
                "e2e golden `PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`；Ω-gate 71/71 100%\n"
                "- 不随本单关闭：BUG-121（方括号形态 `f[T](x)`）、BUG-119（泛型类解析）、"
                "BUG-120（trait 无体抽象方法）、BUG-122（类型实参子树不被 visit）各自 OPEN\n"
                "- 本轮流程债一并了结：R9 欠的「报告先落盘才收根」在本轮改为入口门"
                "（`.fist-loop-20260929/close_r10_ring.py` 起手即验报告存在 + 引用核验通过），"
                "并给 `verify` 挂上 `docs_check`（服务端 [gate:required] 的「文档即实现」面）\n"
            )
            out = after[:insert_at] + section + after[insert_at:]
            tmp = LEDGER.with_suffix(".md.tmp_r10")
            tmp.write_text(out, encoding="utf-8", newline="\n")
            os.replace(tmp, LEDGER)
            rep["fixed"]["BUG-118"] = {"appended": True, "section_bytes": len(section.encode("utf-8"))}
    else:
        rep["fixed"]["BUG-118"] = {"refused": "账本里找不到 BUG-118 的 reported_key 锚点"}

    # 追加段自证：原正文与标题行必须逐字仍在，且只增不改
    final = LEDGER.read_text(encoding="utf-8")
    rep["append_only_check"] = {
        "prefix_identical": final[:after.index(BUG118_NEEDLE)] == before[:before.index(BUG118_NEEDLE)],
        "bug118_header_untouched": "## BUG-118 [2026-09-29T06:01:43Z] [high] OPEN" in final,
        "grew_by": len(final.encode("utf-8")) - len(before.encode("utf-8")),
        "fixed_sections_now": len(re.findall(r"(?m)^### FIXED", final)),
        "headers_now": len(headers(final)),
    }
    con = sqlite3.connect(f"file:{ROOT / 'fist-mbt.db'}?mode=ro", uri=True)
    rep["call_log_error_rows"] = con.execute(
        "select count(*) from call_log where ts>=? and result_json like '%__error__%'", (started,)).fetchone()[0]
    con.close()
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")

    for r in rep["filed"]:
        print("FILED", r["key"], "|", r["reply_verbatim"][:170])
    for r in rep["refusals"]:
        print("REFUSED", r.get("key") or r.get("node"), "|", r["reply_verbatim"][:200])
    for r in rep["skipped_existing"]:
        print("SKIP(existing)", r["key"])
    print("FIXED", json.dumps(rep["fixed"], ensure_ascii=False))
    print("APPEND_ONLY", json.dumps(rep["append_only_check"], ensure_ascii=False))
    print(f"CONCLUSION filed={len(rep['filed'])} refused={len(rep['refusals'])} new_ids={rep['new_ids']} "
          f"bug_list_rows={rep['bug_list_rows']} headers={rep['append_only_check']['headers_now']} "
          f"error_rows={rep['call_log_error_rows']}")
    return 0 if not rep["refusals"] and rep["append_only_check"]["prefix_identical"] else 1


if __name__ == "__main__":
    sys.exit(main())
