"""R4-推进 法②的后果件：`open` 放行激活了一条休眠测试，实测它到底在主张什么。

三件事必须一起量，缺一条就只能靠嘴说：
① 两棵树激活证明——同一份源（逐字取 `tests/test_codegen_verification.py:131-136`）在改前
   `success=False`（诊断 `Undefined name 'open' at 2:9`）⇒ 测试里的 `if result.success`
   守卫为假 ⇒ 断言整块被跳过；改后 `success=True` ⇒ 断言真跑。没有这条，「本环让红变多」
   与「本环让潜伏的失效现形」两种叙事分不开。
② 声明面测量——`defer` 在冻结文档里只承诺「函数退出时自动执行 / 多 defer 逆序」
   （`SYNTAX/14-syntax-sugar.md:167-190`、`SYNTAX/04-pointer-types.md:59-63`），
   **没有任何一处承诺 try/finally**。产物里到底有没有 try/finally、deferred 调用被搬去
   哪儿、`return` 之前那条会不会变成死代码，全部实测而不是引用谁的断言。
③ 新断言的成对 canary——真产物必须被放行，形状错（deferred 调用留在原地）必须被抓；
   少了后者，「改完的测试仍然承重」这句话就是恒绿的。
"""

from __future__ import annotations

import datetime
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import advance_r4_lib as LIB  # noqa: E402
from loop_kit import record  # noqa: E402

OUT = HERE / "advance_r4_dormant.json"
TESTS = ROOT / "tests"
TARGET = "tests/test_codegen_verification.py"
SNIPPET = (
    "import json,sys;from cypy_hook import CypyHook;h=CypyHook();"
    "x=h.transpile(open(sys.argv[1],encoding='utf-8').read());cc=x.cython_code or '';"
    "print(json.dumps({'success':bool(x.success),'errors':[str(e) for e in list(x.errors)][:3],"
    "'code':cc}))")

# 逐字取自既有测试的源（改这里必须同步改测试，否则「同一段源」这句话又漂了）
ACT_SOURCE = ('def safe_file():\n    f = open("test.txt", "w")\n    defer:\n        f.close()\n'
              '    f.write("hello")\n')
SAY = 'def say(msg):\n    print(msg)\n\n'
SINGLE = SAY + 'def one():\n    say("bodyA")\n    defer:\n        say("Z1")\n    say("bodyB")\n'
LIFO = (SAY + 'def two():\n    say("bodyA")\n    defer:\n        say("Z1")\n'
        '    defer:\n        say("Z2")\n    say("bodyB")\n')
BEFORE_RET = ('def make():\n    print("make")\n    return 1\n\n'
              'def three():\n    f = make()\n    defer:\n        print("DONE")\n    return 7\n')
TWO_RET = ('def pick(flag):\n    f = open("t.txt", "w")\n    defer:\n        f.close()\n'
           '    if flag:\n        return 1\n    return 2\n')
# (形状名, 源, 期望搬到体末的 deferred 调用（产物里的引号形态）, 体末最后一个语句, 判定档, 被测函数)
# 注：产物把字符串字面量归一成单引号，所以钉的是发射后的形态（这条本身就是实测出来的）
SHAPES = [("single_defer", SINGLE, ["say('Z1')"], "say('bodyB')", "moved", "one"),
          ("two_defers_lifo", LIFO, ["say('Z2')", "say('Z1')"], "say('bodyB')", "lifo", "two"),
          ("defer_before_return", BEFORE_RET, ["print('DONE')"], "return 7",
           "before_return", "three"),
          ("defer_two_exits", TWO_RET, ["f.close()"], "return 2", "record_only", "pick")]
DOC_BASIS = [("SYNTAX/14-syntax-sugar.md", 167, 190), ("SYNTAX/04-pointer-types.md", 59, 63)]
GUARD = "if result.success"
CHECKS: list = []
REFUSE: list = []


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def run_hook(tree: Path, src: str, tag: str) -> dict:
    """在那棵树里转译一份源，返回 success/诊断/产物（产物只留必要字段，别把整仓灌进件里）。"""
    probe = tree / f"dormant_{tag}.cypy"
    probe.write_text(src, encoding="utf-8", newline="\n")
    r = subprocess.run([sys.executable, "-X", "utf8", "-c", SNIPPET, str(probe)],
                       cwd=str(tree), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300)
    lines = [ln for ln in (r.stdout or "").splitlines() if ln.strip().startswith("{")]
    if not lines:
        REFUSE.append(f"{tag}：探针没拿到 JSON 回执（rc={r.returncode}）："
                      f"{(r.stderr or '').strip()[-200:]}")
        return {}
    return json.loads(lines[-1])


def moved_to_end(code: str, deferred: str, body_last: str) -> bool:
    """声明面口径：deferred 调用出现在函数体最后一个语句之后（即「函数退出时执行」）。"""
    return code.rfind(deferred) > code.rfind(body_last) >= 0


def reverse_order(code: str, first_declared: str, second_declared: str) -> bool:
    """多 defer 逆序：后声明的调用先出现在产物里。"""
    i, j = code.find(second_declared), code.find(first_declared)
    return i >= 0 and j >= 0 and i < j


def func_slice(code: str, func: str) -> str:
    """只取被测函数那一段：整份产物里别的函数的 return 不能算进它的出口数。"""
    head = f"def {func}("
    i = code.find(head)
    if i < 0:
        return ""
    nxt = code.find("\ndef ", i + 1)
    return code[i:nxt if nxt > 0 else len(code)]


def main() -> int:
    started = now_iso()
    before = LIB.build_tree(LIB.BEFORE_TREE, revert=True)
    after = LIB.build_tree(LIB.AFTER_TREE, revert=False)
    idb, ida = LIB.identity_probe(LIB.BEFORE_TREE), LIB.identity_probe(LIB.AFTER_TREE)
    if not (idb["inside"] and ida["inside"]):
        REFUSE.append(f"身份探针失败：before={idb.get('scope')} after={ida.get('scope')}")

    rb = run_hook(LIB.BEFORE_TREE, ACT_SOURCE, "before")
    ra = run_hook(LIB.AFTER_TREE, ACT_SOURCE, "after")
    rec_b = next((e for e in rb.get("errors", []) if "Undefined name 'open'" in e), "")
    record(CHECKS, REFUSE, "激活证明：改前这份源转译失败（守卫为假 ⇒ 旧测试整块空过）",
           [rb.get("success"), rb.get("code", "") == ""], [False, True],
           f"改前诊断 {rec_b or rb.get('errors')}")
    record(CHECKS, REFUSE, "激活证明：改后同一份源转译成功（断言这才开始真跑）",
           ra.get("success"), True, f"改后诊断 {ra.get('errors')}")
    code_a = ra.get("code", "")
    record(CHECKS, REFUSE, "既有测试主张的 try/finally 在产物里不存在（这就是那条红的成因）",
           ["try:" in code_a, "finally:" in code_a], [False, False],
           f"产物尾 {code_a[-160:]!r}")

    doc_rows = []
    for rel, lo, hi in DOC_BASIS:
        text = (ROOT / rel).read_text(encoding="utf-8", errors="replace").splitlines()
        quote = "\n".join(text[lo - 1:hi])
        doc_rows.append({"file": rel, "lines": [lo, hi], "quote": quote,
                         "try_or_finally_declared": ("try" in quote.lower()
                                                     or "finally" in quote.lower()
                                                     or "异常" in quote),
                         "exit_word_declared": ("退出" in quote or "逆序" in quote)})
    record(CHECKS, REFUSE, "声明面：两处文档引文里都没写 try/finally/异常路径（测试主张超出声明）",
           [r["try_or_finally_declared"] for r in doc_rows], [False, False],
           f"引文行数 {[len(r['quote'].splitlines()) for r in doc_rows]}")
    record(CHECKS, REFUSE, "声明面：两处引文都写了「函数退出时执行 / 逆序」——新断言就钉这个",
           [r["exit_word_declared"] for r in doc_rows], [True, True],
           f"{[r['file'] for r in doc_rows]}")

    shapes = []
    for name, src, deferred, body_last, mode, func in SHAPES:
        s = run_hook(LIB.AFTER_TREE, src, f"shape_{name}")
        cc = s.get("code", "")
        seg = func_slice(cc, func)
        row = {"shape": name, "mode": mode, "source": src, "deferred_calls": deferred,
               "body_last": body_last, "tested_function": func, "success": s.get("success"),
               "errors": s.get("errors"), "code": cc, "function_slice": seg,
               "try": "try:" in cc, "finally": "finally:" in cc,
               "moved_to_end": all(moved_to_end(cc, d, body_last) for d in deferred),
               "cleanup_count": sum(seg.count(d) for d in deferred),
               "exit_paths": seg.count("return ")}
        if len(deferred) == 2:
            row["reverse_order"] = reverse_order(cc, deferred[1], deferred[0])
        if mode == "before_return":
            row["deferred_before_return"] = 0 <= cc.rfind(deferred[0]) < cc.rfind(body_last)
            row["whole_file_returns"] = cc.count("return ")
        shapes.append(row)
        record(CHECKS, REFUSE, f"形状 {name}：转译成功（新断言钉的是能跑的产物不是失败态）",
               s.get("success"), True, f"诊断 {s.get('errors')}")
        record(CHECKS, REFUSE,
               f"形状 {name}：被测函数那一段数得出清理调用（尺子没量空、也没量到隔壁函数）",
               [row["cleanup_count"] >= 1, bool(seg)], [True, True],
               f"函数段 {seg!r}")

    single = next(r for r in shapes if r["shape"] == "single_defer")
    lifo = next(r for r in shapes if r["shape"] == "two_defers_lifo")
    ret = next(r for r in shapes if r["shape"] == "defer_before_return")
    exits = next(r for r in shapes if r["shape"] == "defer_two_exits")
    record(CHECKS, REFUSE, "声明面「函数退出时执行」在单 defer 上成立（deferred 调用被搬到体末）",
           single["moved_to_end"], True, f"产物 {single['code'][-140:]!r}")
    record(CHECKS, REFUSE,
           "声明面「多 defer 逆序」成立（后声明的先出现，且都在体末之后）",
           [lifo["reverse_order"], lifo["moved_to_end"]], [True, True],
           f"产物 {lifo['code'][-170:]!r}")
    record(CHECKS, REFUSE,
           "defer 在 return 之前声明：产物把清理搬到 return **之前**（这条路可达），不是搬到函数末尾",
           ret["deferred_before_return"], True, f"产物 {ret['code'][-170:]!r}")
    record(CHECKS, REFUSE,
           "钉住的缺陷（BUG-76 的一半）：嵌套在 if 里的 return 不算顶层出口 ⇒ 2 个出口只发 1 次清理；"
           "修好后这一格必须红，和关账一起走",
           [exits["exit_paths"], exits["cleanup_count"]], [2, 1],
           f"出口 {exits['exit_paths']} 个 / 清理 {exits['cleanup_count']} 次；函数段 "
           f"{exits['function_slice']!r}")

    guards = []
    for p in sorted(TESTS.glob("*.py")):
        for i, ln in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if ln.strip().startswith(GUARD):
                guards.append({"file": p.relative_to(ROOT).as_posix(), "line": i,
                               "text": ln.strip()})
    guard_files = sorted({g["file"] for g in guards})
    tgt_text = (ROOT / TARGET).read_text(encoding="utf-8", errors="replace")
    i0 = tgt_text.index("    def test_defer_statement(")
    i1 = tgt_text.index("\n    def ", i0 + 1)
    patched_body = tgt_text[i0:i1]
    still_guarded = any(ln.strip().startswith(GUARD) for ln in patched_body.splitlines())
    record(CHECKS, REFUSE,
           "被激活的那条守卫已去掉：test_defer_statement 体内没有守卫语句行的 if result.success，"
           "且断言是无条件的",
           [still_guarded, "assert result.success" in patched_body],
           [False, True], f"函数体 {patched_body[:120]!r}…")
    record(CHECKS, REFUSE,
           "其余同款守卫逐条点名入账（BUG-77；本环不动它们，交 R5 一次量完再改）",
           [len(guards), guard_files], [7, ["tests/test_codegen_verification.py",
                                            "tests/test_unit_test_modes.py"]],
           f"{len(guards)} 处 / {len(guard_files)} 个文件："
           f"{[g['file'] + ':' + str(g['line']) for g in guards]}")

    canary = {"activation_direction_differs": (rb.get("success") is False
                                               and ra.get("success") is True),
              "declared_shape_holds": bool(single["moved_to_end"] and lifo["reverse_order"]),
              "test_asserts_more_than_declared": "try:" not in code_a,
              "predicate_rejects_wrong_shape": not moved_to_end(
                  "def one():\n    say('Z1')\n    say('bodyB')\n", "say('Z1')", "say('bodyB')"),
              "predicate_accepts_real_shape": moved_to_end(
                  single["code"], "say('Z1')", "say('bodyB')"),
              "slicer_narrows_to_target_function": (
                  ret["whole_file_returns"] > ret["exit_paths"]),
              "guard_scanner_still_finds_other_sites": (
                  any(g["file"] == "tests/test_unit_test_modes.py" for g in guards)),
              "guard_scanner_not_fooled_by_comment_mention": (
                  any(GUARD in ln for ln in patched_body.splitlines()) and not still_guarded)}
    record(CHECKS, REFUSE,
           "canary 八格必须同时成立（形状错的被拒、切片变窄、守卫扫描器既看得见也不上注释的当）",
           [len(canary), sorted(canary.values())], [8, [True] * 8],
           json.dumps(canary, ensure_ascii=False))
    LIB.cleanup()

    doc = {"started": started,
           "law": "法②后果：放行 open 激活休眠测试 test_defer_statement，声明面实测 try/finally 未被承诺",
           "decision": "指挥官裁决 2026-09-28：改测试期望为声明面语义（defer 调用搬到体末 + 多 defer 逆序），"
                       "产品码本环不动；其余 7 处同款守卫与 defer-before-return 不可达一起入账",
           "target_test": {"file": TARGET, "class": "TestCodegenVerification",
                           "method": "test_defer_statement", "source_verbatim": ACT_SOURCE},
           "activation": {"before": {"success": rb.get("success"), "errors": rb.get("errors"),
                                     "code_empty": rb.get("code", "") == "",
                                     "undefined_open": rec_b},
                          "after": {"success": ra.get("success"), "errors": ra.get("errors"),
                                    "has_try": "try:" in code_a,
                                    "has_finally": "finally:" in code_a,
                                    "code_tail": code_a[-300:]}},
           "trees": {"before": before, "after": after, "identity_before": idb,
                     "identity_after": ida},
           "doc_basis": doc_rows, "shapes": shapes,
           "test_patch": {"file": TARGET, "body_after": patched_body.strip()},
           "card_expected_id": "BUG-76",
           "pinned_defect": {"shape": "defer_two_exits", "exit_paths": exits["exit_paths"],
                             "cleanup_count": exits["cleanup_count"],
                             "mechanism": "cypyc/codegen/cython_generator.py:979-1000 只在函数体顶层"
                                          "遍历 normal_stmts，`if`/`for` 里的 return 不是顶层 ReturnStmt"
                                          " ⇒ 那条出口不注入清理；而任一顶层 return 注入过就把 "
                                          "emitted_at_return 置真、函数末尾不再补 ⇒ 嵌套出口泄漏",
                             "product_slice": exits["function_slice"]},
           "vacuous_guards": {"pattern": GUARD, "sites": guards, "count": len(guards),
                              "files": guard_files},
           "canary": canary, "self_checks": CHECKS, "refuse": sorted(set(REFUSE)),
           "at_utc": now_iso()}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": doc["refuse"], "guards": len(guards),
                      "activation": doc["activation"]["before"],
                      "moved_to_end": [r.get("moved_to_end") for r in shapes],
                      "deferred_before_return": ret["deferred_before_return"],
                      "exits": [exits["exit_paths"], exits["cleanup_count"]],
                      "canary": canary}, ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
