"""R4-推进 法④：从两份量件套**反解**生成永久回归锁（不手打形状、不手打中文）。

生成的文件是 `tests/test_loop_20260927_advance_r4.py`：每条探针的源码、期望退出码、
诊断子串、理由全部取自 `advance_r4_never.json` / `advance_r4_builtins.json` 的实测条目，
所以「测试钉的是量件套量过的同一批形状」这句话是可查的，不是叙述。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
NEVER = json.loads((HERE / "advance_r4_never.json").read_text(encoding="utf-8"))
BUILT = json.loads((HERE / "advance_r4_builtins.json").read_text(encoding="utf-8"))
FILED = json.loads((HERE / "advance_r4_filed.json").read_text(encoding="utf-8"))
DORM = json.loads((HERE / "advance_r4_dormant.json").read_text(encoding="utf-8"))
OUT = ROOT / "tests" / "test_loop_20260927_advance_r4.py"
PLAN = HERE / "advance_r4_lock_plan.json"
PROBE_DIR = HERE / "advance_r4_probe"
BUG_IDS = sorted({f["ledger_number"] for f in FILED["filed"] if f.get("ledger_number")})


def src_of(fixture: str) -> str:
    return (PROBE_DIR / fixture).read_text(encoding="utf-8")


def probes() -> list:
    """(id, law, role, src, want, needles, why) —— want∈{clean,error}，role 说明这条在证什么。"""
    out = []
    for r in NEVER["cases"]:
        fixture = Path(r["probe"]).name
        if r["expect"].startswith("expect_green"):
            want, needles = "clean", []
        else:
            want = "error"
            needles = sorted({n.split("'")[1] for n in r["before"]["undefined_names"]})
        out.append((f"A4-{r['case']}", "法①Never", r["expect"], src_of(fixture), want,
                    needles, f"改前 rc={r['before']['rc']} 改后 rc={r['after']['rc']}；"
                             f"红因 {r['before']['undefined_names'] or '（无）'}"))
    for row in BUILT["cases"]:
        want = "clean" if row["after_rc"] == 0 else "error"
        needles = (sorted({n.split("'")[1] for n in row["after_undefined"]})
                   if want == "error" else [])
        role = "已放行" if want == "clean" else "半径外仍拒"
        out.append((f"A4B-{row['name']}", "法②内建名", role, src_of(Path(row["probe"]).name),
                    want, needles, f"改前 rc={row['before_rc']} 改后 rc={row['after_rc']}；"
                                   f"{row['after_undefined'] or '（诊断干净）'}"))
    return out


def render() -> str:
    rows = probes()
    doc_evi = BUILT["doc_evidence"]
    defer_rows = defer_rows_of()
    table = "\n".join(
        f"| {r[0]} | {r[2]} | {r[4]} | {r[6].replace(chr(10), ' ')} | |" for r in rows)
    body = ['"""R4-推进 的永久回归锁：把名称面（`Never` 与三个文档内建名）的实测形状钉进仓库。',
            '',
            f'来源三份：`{NEVER["law"]}`、`{BUILT["law"]}` 与 `{DORM["law"]}`；',
            '本文件由 `.fist-loop-20260927/advance_r4_gen_locks.py` 从',
            '`.fist-loop-20260927/advance_r4_never.json` / `advance_r4_builtins.json` 反解生成，',
            '探针源码逐字取自 `.fist-loop-20260927/advance_r4_probe/`。',
            '',
            '| 锁 | 角色 | 期望 | 实测依据 | 若被回退 |',
            '|---|---|---|---|---|',
            table + "\n| 产物签名 | codegen 未动 | `-> NoReturn` | "
            "见 test_doc_worked_example_maps_to_noreturn | 回退即该行消失 |",
            '| 账实一致 | 挂账 | 在档 | ' + " / ".join(BUG_IDS) + ' 有卡 | 卡被删 ⇒ 红 |',
            '| defer 形状 | 声明面语义 | 在档 | 4 档实测（含钉住的 BUG-76 形状） | '
            '搬迁规则或出口注入被改 ⇒ 红 |',
            '| 文档声明面 | 引用行 | 在档 | 三处 `name(` 引用行仍含该调用 | 文档改写 ⇒ 红，逼人重量 |',
            '',
            '"""',
            '',
            'from __future__ import annotations',
            '',
            'import re',
            'import subprocess',
            'import sys',
            'from pathlib import Path',
            '',
            'import pytest',
            '',
            'ROOT = Path(__file__).resolve().parent.parent',
            'ANSI = re.compile(r"\\x1b\\[[0-9;]*m")',
            'BUGS = ROOT / "memory" / "bugs.md"',
            'LEAKS = ("Traceback", "NoneType object", "cypyc.analyzer", "object at 0x")',
            '',
            '# (id, law, role, src, want, [诊断子串…], 出题理由)',
            'PROBES = ' + json.dumps(rows, ensure_ascii=True, indent=4),
            '',
            '',
            'def _run_cli(tmp_path: Path, src: str, extra: list) -> subprocess.CompletedProcess:',
            '    f = tmp_path / "probe.cypy"',
            '    f.write_text(src, encoding="utf-8", newline="\\n")',
            '    return subprocess.run(',
            '        [sys.executable, "-X", "utf8", "-m", "cypyc", "transpile", str(f),',
            '         "-o", str(tmp_path)] + extra,',
            '        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",',
            '        errors="replace", timeout=300)',
            '',
            '',
            'def _plain(p: subprocess.CompletedProcess) -> str:',
            '    return ANSI.sub("", (p.stdout or "") + (p.stderr or ""))',
            '',
            '',
            '@pytest.mark.parametrize("probe", PROBES, ids=[p[0] for p in PROBES])',
            'def test_name_face_at_cli_entry(tmp_path, probe):',
            '    """每条探针钉三件事：退出码、诊断里的名字、不把内部实现吐给用户。"""',
            '    pid, law, role, src, want, needles, _why = probe',
            '    p = _run_cli(tmp_path, src, [])',
            '    text = _plain(p)',
            '    expected_rc = 1 if want == "error" else 0',
            '    assert p.returncode == expected_rc, f"{pid}/{law}/{role} rc={p.returncode}"',
            '    if want == "error":',
            '        low = text.lower()',
            '        assert [n for n in needles if n.lower() in low or n in text], \\',
            '            f"{pid}: 诊断里找不到预期名字 {needles}"',
            '    for leak in LEAKS:',
            '        assert leak not in text, f"{pid}: 内部实现外泄 {leak}"',
            '',
            '',
            'def test_doc_worked_example_maps_to_noreturn(tmp_path):',
            '    """文档工作例真编译到产物：`Never` 走既有 codegen 的 NoReturn 映射（本环未动 codegen）。"""',
            '    src = next(r[3] for r in PROBES if r[0] == "A4-doc_worked_example")',
            '    p = _run_cli(tmp_path, src, [])',
            '    assert p.returncode == 0, _plain(p)[-300:]',
            '    pyx = sorted(tmp_path.rglob("*.pyx"))',
            '    assert pyx, "没产出 .pyx"',
            '    text = pyx[0].read_text(encoding="utf-8")',
            '    assert "-> NoReturn:" in text, "产物里没有 NoReturn 签名 ⇒ 名称面或映射被回退"',
            '',
            '',
            '@pytest.mark.parametrize("bug", ' + json.dumps(BUG_IDS) + ')',
            'def test_pinned_defects_still_have_a_card(bug):',
            '    """账实一致锁：本环挂账的两条（复合异或静默产错码 / 位运算符词位不可达）必须可查。"""',
            '    assert bug in BUGS.read_text(encoding="utf-8"), f"{bug} 卡片不在账本里"',
            '',
            '',
            'DOC_CITATIONS = ' + json.dumps(
                [[e["name"], e["cited"], e["cited_text"]] for e in doc_evi], ensure_ascii=True),
            '',
            '',
            '@pytest.mark.parametrize("name,wanted,text", DOC_CITATIONS,',
            '                         ids=[c[0] for c in DOC_CITATIONS])',
            'def test_declared_builtins_still_cited_in_syntax_docs(name, wanted, text):',
            '    """放行三个内建名的依据是文档自己在用；文档改写就要重量，不能靠这行绿着。"""',
            '    path, _, line = wanted.partition(":")',
            '    doc = (ROOT / path).read_text(encoding="utf-8", errors="replace").splitlines()',
            '    got = doc[int(line) - 1].strip()',
            '    assert name + "(" in got, f"{wanted} 这一行已不含 {name}( ⇒ 声明面变了"',
            '    assert got == text, f"{wanted} 原文漂了：{got!r} != {text!r}"',
            '',
            '',
            '# (形状, 源, [deferred 调用…], 体末最后语句, 判定档, 被测函数, 出口数, 清理次数)',
            'DEFER_SHAPES = ' + json.dumps(defer_rows, ensure_ascii=True, indent=4),
            '',
            '',
            'def _func_slice(code: str, func: str) -> str:',
            '    """只取被测函数那一段：隔壁函数的 return 不能算进它的出口数。"""',
            '    head = f"def {func}("',
            '    i = code.find(head)',
            '    assert i >= 0, f"产物里没有 {head}：{code[-200:]!r}"',
            '    nxt = code.find("\\ndef ", i + 1)',
            '    return code[i:nxt if nxt > 0 else len(code)]',
            '',
            '',
            '@pytest.mark.parametrize("shape,src,deferred,body_last,mode,func,exits,cleanups",',
            '                         DEFER_SHAPES, ids=[r[0] for r in DEFER_SHAPES])',
            'def test_defer_declared_shape(tmp_path, shape, src, deferred, body_last, mode, func,',
            '                             exits, cleanups):',
            '    """钉声明面语义（2026-09-28 裁决：`defer` = 函数退出时执行 + 多 defer 逆序，'
            '不含 try/finally）。"""',
            '    p = _run_cli(tmp_path, src, [])',
            '    assert p.returncode == 0, _plain(p)[-300:]',
            '    pyx = sorted(tmp_path.rglob("*.pyx"))',
            '    assert pyx, "没产出 .pyx"',
            '    seg = _func_slice(pyx[0].read_text(encoding="utf-8"), func)',
            '    if mode == "pinned_defect":',
            '        # BUG-76 今天的行为：只遍历顶层出口，嵌套 return 那条不注入清理。',
            '        # 修好后这两格会红 ⇒ 与关账同批走，不许悄悄把钉住的形状改掉。',
            '        emitted = sum(seg.count(c) for c in deferred)',
            '        assert [seg.count("return "), emitted] == [exits, cleanups], seg',
            '        return',
            '    for call in deferred:',
            '        assert call in seg, f"{shape}: 产物函数段里没有 {call}：{seg!r}"',
            '        if mode in ("moved", "lifo"):',
            '            assert seg.rfind(call) > seg.rfind(body_last) >= 0, f"{shape}: 没搬到体末"',
            '        if mode == "before_return":',
            '            assert seg.rfind(call) < seg.rfind(body_last), f"{shape}: 清理在 return 之后"',
            '    if mode == "lifo":',
            '        assert seg.find(deferred[0]) < seg.find(deferred[1]), f"{shape}: 不按逆序"',
            '']
    return "\n".join(body) + "\n"


def defer_rows_of() -> list:
    """defer 的四档形状行：判定档里 `pinned_defect` 那档钉的是今天的行为（BUG-76）。"""
    pin = DORM["pinned_defect"]["shape"]
    return [[r["shape"], r["source"], r["deferred_calls"], r["body_last"],
             "pinned_defect" if r["shape"] == pin else r["mode"],
             r["tested_function"], r["exit_paths"], r["cleanup_count"]]
            for r in DORM["shapes"]]


def all_ids(rows: list, defer_rows: list) -> list:
    """按 pytest 的打印形态列出本文件应有的全部用例 id（收集数与红点名单都靠它对齐）。"""
    ids = [f"test_name_face_at_cli_entry[{r[0]}]" for r in rows]
    ids.append("test_doc_worked_example_maps_to_noreturn")
    ids += [f"test_pinned_defects_still_have_a_card[{b}]" for b in BUG_IDS]
    ids += [f"test_declared_builtins_still_cited_in_syntax_docs[{e['name']}]"
            for e in BUILT["doc_evidence"]]
    ids += [f"test_defer_declared_shape[{r[0]}]" for r in defer_rows]
    return ids


def main() -> int:
    rows = probes()
    if len(rows) != len(NEVER["cases"]) + len(BUILT["cases"]):
        print(json.dumps({"refuse": ["反解条数与两份量件套之和不符"]}, ensure_ascii=False))
        return 1
    missing = [r[0] for r in rows if r[4] == "error" and not r[5]]
    if missing:
        print(json.dumps({"refuse": [f"这些 error 探针没有诊断名字可钉：{missing}"]},
                         ensure_ascii=False))
        return 1
    text = render()
    compile(text, str(OUT), "exec")          # 先语法自检，再落盘
    OUT.write_text(text, encoding="utf-8", newline="\n")
    breakdown = {"name_face_probes": len(rows), "doc_worked_example": 1,
                 "pinned_card_locks": len(BUG_IDS),
                 "doc_citation_locks": len(BUILT["doc_evidence"]),
                 "defer_shape_locks": len(DORM["shapes"])}
    expected = sum(breakdown.values())
    defer_rows = defer_rows_of()
    if len(all_ids(rows, defer_rows)) != expected:
        print(json.dumps({"refuse": [f"id 清单 {len(all_ids(rows, defer_rows))} 条与 "
                                     f"expected_tests {expected} 不符 ⇒ 生成器自己数不对"]},
                         ensure_ascii=False))
        return 1
    # 改前码那棵树里**应当**红的名单：依赖本轮放行名字的探针。名单由同一批反解数据算出，
    # `advance_r4_locks.py` 拿 pytest 实际红点来比——两份来源不一致就红（不手打字面量）。
    added = [n for n in BUILT["added"]]
    prefix_red = [f"test_name_face_at_cli_entry[{r[0]}]" for r in rows if r[4] == "clean"]
    prefix_red.append("test_doc_worked_example_maps_to_noreturn")
    for sh in DORM["shapes"]:
        if any(re.search(rf"\b{re.escape(n)}\s*\(", sh["source"]) for n in added):
            prefix_red.append(f"test_defer_declared_shape[{sh['shape']}]")
    PLAN.write_text(json.dumps(
        {"file": OUT.relative_to(ROOT).as_posix(), "expected_tests": expected,
         "breakdown": breakdown, "card_ids": BUG_IDS,
         "prefix_red_ids": sorted(prefix_red),
         "prefix_green_ids": sorted(set(all_ids(rows, defer_rows)) - set(prefix_red)),
         "generator": Path(__file__).name,
         "sources": ["advance_r4_never.json", "advance_r4_builtins.json",
                     "advance_r4_filed.json", "advance_r4_dormant.json"],
         "note": "条数由本生成器按反解到的条目数算出；`advance_r4_locks.py` 与 "
                 "`advance_r4_baselines.py` 各自拿实测收集数来比这格——两份来源不一致就红"},
        ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"file": OUT.relative_to(ROOT).as_posix(), "probes": len(rows),
                      "expected_tests": expected, "breakdown": breakdown,
                      "plan": PLAN.name, "bytes": OUT.stat().st_size,
                      "green": sum(1 for r in rows if r[4] == "clean"),
                      "red": sum(1 for r in rows if r[4] == "error")},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
