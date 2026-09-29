#!/usr/bin/env python3
"""R2-修复：往 memory/bugs.md 的 6 个条目下追加 FIXED 段（账本无 close API ⇒ 只能追加）。

三条纪律：
1. **正文数字全部从证据件反解**，不手写（回退红的用例名、基线三套的实测数、锁的条数都取自 JSON）；
2. 锚点唯一：段头 `## BUG-N [` 必须在文件里恰好出现一次，插入点是该条目末尾（下一个 `## BUG-` 之前）；
3. 幂等：同一条目里已有本轮标记（`R2-修复(循环轮)`）就跳过，不重复追加。

BUG-35 是**部分修**：只修分桶，深嵌套 RecursionError 的守卫与行列另账转结 —— 段头如实写
`FIXED(verify=已完成, 范围=分桶)`，不留"整单已修"的误读空间。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(r"E:\IDEProjects\AI\Cypy")
LEDGER = ROOT / "memory" / "bugs.md"
STAGE = "2026-09-27 R2-修复(循环轮)"
REPORT = sys.argv[1] if len(sys.argv) > 1 else "memory/reviews/PENDING.md"

base = json.loads((HERE / "fix_r2_baselines.json").read_text(encoding="utf-8"))
locks = json.loads((HERE / "fix_r2_lint.json").read_text(encoding="utf-8"))

BASELINE_LINE = (
    f"pytest `{base['pytest']['passed']} passed`（下限 {base['pytest']['floor']}，"
    f"末行 `{base['pytest']['line'].strip()}`）；"
    f"自研套件 `{base['suite']['line'].strip()}`；"
    f"e2e `{base['e2e']['line'].strip()}`"
)


def revert_line(bug: str) -> str:
    d = json.loads((HERE / f"fix_r2_lockproof_revert_{bug}.json").read_text(encoding="utf-8"))
    res = d["tree_result"]
    red = "、".join(f"`{x}`" for x in d["red_locks"])
    return (
        f"在**只回退本单**的临时树上证红 {len(d['red_locks'])} 条：{red}；"
        f"同树上其余 {res['collected'] - len(d['red_locks'])} 条（本单对照 + 另 5 单的用例）保持绿"
        f"（混因={len(d['mixed_cause'])} 条、对照被带回={len(d['own_controls_red'])} 条）"
    )


SECTIONS = {
    44: (
        "FIXED(verify=已完成)",
        f"""- 修复面：`cypyc/codegen/cython_generator.py` 新增 `_decorator_names`/`_is_selfless_method`，
  `_visit_FuncDef` 的 self 注入改为「已声明 self **或** 是 @staticmethod/@classmethod 都不再注入」；
  struct 方法循环里 `@cython.binding(False)` 只挂在绑定方法上（此前 3 个方法挂 3 条）。
- 锁死回归：{revert_line('bug44')}。
- 调用面证据：`cypyc transpile` 产物由 `def origin(self):` 变成 `def origin():`
  （锁：`tests/test_loop_20260927_fix_r2.py::test_bug44_at_cli_product_is_transpiled_without_self`）。
- 修复边界：SYNTAX/06d 的绑定方法写法是**显式 `self`**；隐式 self 在类型检查面仍报
  `Undefined name 'self'`（本轮实测，属既有面、不在本单半径），已在环节报告里单列一条观察。""",
    ),
    45: (
        "FIXED(verify=已完成)",
        f"""- 修复面：`cython_generator._param_default_str` 把 `= __implicit_default__` 脱糖成
  `{{参数类型}}.__implicit_default__()`（产物形状：`cfg=Config.__implicit_default__()`）；
  `cypyc/parser/parser.py::_parse_params` 对**无类型注解**的该默认值给带行列诊断（此时无从确定调谁）。
- 锁死回归：{revert_line('bug45')}。
- 成对对照：普通默认值 `t: int = 5` 产物仍是 `t=5`（脱糖逻辑不误伤），对照用例 `test_bug45_control_ordinary_default_untouched`。
- 修复边界：只做「默认值形状」的脱糖，不改 `__implicit_default__` 的**调用时机语义**
  （文档"参数未提供时自动使用"= Python 默认参数求值语义，本轮不引入新的隐式填充路径）。""",
    ),
    39: (
        "FIXED(verify=已完成)",
        f"""- 修复面：`parser.py::_parse_return_stmt` 补上早就存在的 `_require_function_scope`
  （`defer` 一直在用，`return` 漏用）⇒ 顶层 return 由「rc=0 + 产物含顶格 `return 0`」变成
  `return must be used inside a function, found at 4:1` 且 rc≠0。
- 锁死回归：{revert_line('bug39')}。
- 波及面实测（首版不足，已勘误）：只跑 `examples/` 27 份 .cypy 全绿不足以断言「不打掉既有形状」——
  全量 pytest 当场红 2 条（宏体与宏展开片段里的 `return` 被同一道守卫吃掉），
  修回方式见 `BUG-51`：`Parser(body_scope=...)` 只对宏体/展开片段放宽，`_scope_stack` 不动。
  永久锁 3 条：`test_bug39_macro_body_return_stays_legal`、
  `test_bug39_expanded_fragment_return_stays_legal` 与对照
  `test_bug39_control_fragment_without_body_scope_still_rejected`。
- 修复边界：只诊断，不给「顶层 return 提升到 main」之类的语义扩展（那属推进半径的未实现面）。""",
    ),
    35: (
        "FIXED(verify=已完成, 范围=分桶)",
        f"""- 本轮修的是**归桶**：`cypy_hook/hook.py::transpile_file` 把读文件单独 try/except OSError，
  只有 I/O 失败才写「读取文件错误」；外层兜底改名「编译错误」⇒ 解析/生成期诊断不再冒充读文件失败，
  且其自带的行列信息保住（`编译错误: defer must be used inside a function, found at 4:7`）。
- 锁死回归：{revert_line('bug35')}。
- **本单未修的另一半（如实留账）**：200 层括号那类 `RecursionError` 仍无深度守卫、诊断无行列，
  只是桶名不再撒谎 ⇒ 深嵌套守卫转结后续轮；本条目在 `bug_list` 里仍应视为**部分完成**。
- 判据口径：夹具用顶层 `defer`（该越域诊断本轮之前就有）而不是顶层 `return`（BUG-39 新增），
  否则回退 BUG-39 会把本单的锁一起带红 ⇒ 归因混在一起。""",
    ),
    46: (
        "FIXED(verify=已完成)",
        f"""- 取**口径修法（本单 a/b 二选一里的 b）**，不动用户环境：`cypyc/cli.py` 的
  `hook install/uninstall/status` 三条输出全部限定「当前进程」，install 不再打
  `installed successfully`，status 不再打 `[FAIL] ... is not installed`（两命令此前互相否定）；
  `docs/USAGE.md` 2.6 段同步删掉「写入用户 sitecustomize / 注册」这句未实现的承诺，
  改为给出跨进程的正确写法（在自己进程里 `cypy_hook.install_hook()`）。
- 为什么不选 a（真做持久化）：写用户 site-packages/.pth 属改动本机 Python 环境，
  在本轮红线里是不可逆动作 ⇒ 只挂账待裁决，不在自动轮里替用户装东西。
- 锁死回归：{revert_line('bug46')}。
- 成对对照：`test_bug46_fresh_process_reports_not_active` 钉住"新进程仍报未激活"是真的
  （修复前它也绿 ⇒ 说明旧缺陷不在这条面上，而在两条横幅互相否定）。""",
    ),
    47: (
        "FIXED(verify=已完成)",
        f"""- 修复面：`cypy_hook/__init__.py` 再导出 `install_hook`/`uninstall_hook`/`is_hook_installed`
  并把 `__all__` 补齐 ⇒ 手册 3.x 承诺的包级 API 路径可用（此前只有 `CypyHook`）。
- 锁死回归：{revert_line('bug47')}。
- 判据自身对照：探测里额外问 `hasattr(cypy_hook, 'is_hook_installed_v2')` 必须为 False
  ⇒ 证明 `hasattr` 探测本身不是恒真。
- 修复边界：只补再导出，不动 `cypy_hook.hook` 里的实现位置（`from cypy_hook.hook import ...` 仍可用）。""",
    ),
    51: (
        "FIXED(verify=已完成)",
        """- 修复面：`Parser.__init__(tokens, body_scope=False)` + `_require_function_scope` 改成
  `if not (self._in_function or self._body_scope)`；`_parse_macro_def` 解析宏体时置位、之后恢复；
  `cypyc/parser/macro_expander.py::_parse_code` 用 `Parser(tokens, body_scope=True)`。
  **刻意不动 `_scope_stack`** —— 它是 `_is_module_level()` 的依据，宏体里照旧可以生成 struct/impl。
- 证据形状（与另 5 单不同，如实写明）：本单**不参与逐单回退矩阵**（它锁的是"别把守卫做过头"，
  回退 BUG-39 的守卫不会让它红）。承重证据是首版那次全量 pytest 的 2 条红
  （`.fist-loop-20260927/r2fix/pytest_gate.txt`：`2 failed, 1881 passed`，
  `test_parser_macro.py::test_macro_definition_parsing` 与
  `test_macro_features.py::test_macro_interpolation_expression`）+ 修回后 18 条全收集全绿。
- 锁：`test_bug39_macro_body_return_stays_legal`、`test_bug39_expanded_fragment_return_stays_legal`
  （`macro_exemption` 组），以及归在 BUG-39 名下的
  `test_bug39_control_fragment_without_body_scope_still_rejected`（断言守卫本身在拦）。
- 未扩测的部分如实转结：`defer`、`@meta` 之类同样受作用域判定约束的构造，在宏体里的形状本轮没测。""",
    ),
}


BUG_BRANCH = {44: "1", 45: "2", 39: "3", 51: "3", 35: "4", 46: "5", 47: "6"}
NOW = sys.argv[2] if len(sys.argv) > 2 else "2026-09-27T09:20:00Z"


def build(bug: int, heading: str, body: str) -> str:
    branch = BUG_BRANCH[bug]
    return (
        f"\n### {heading} — {NOW} 追加留档（{STAGE}，"
        f"本条目正文与标题行 `OPEN` 一字未改）\n"
        f"- 修复单：根 `T0r56`（ns `cypy-loop-20260927`）下 `T0r56.{branch}.1` 与 `T0r56.{branch}.2`，"
        f"全链带 `[omega:required]`，逐叶 `output_validate` pass 后才 verify；报告：`{REPORT}`\n"
        f"{body}\n"
        f"- 双套基线：{BASELINE_LINE}\n"
        f"- 本轮判据件：`.fist-loop-20260927/fix_r2_lint.json`"
        f"（亲笔行 {locks['authored_lines_checked']} 条，black/flake8 零违例 + 必然违例自检通过）"
        f" 与 `.fist-loop-20260927/fix_r2_lockproof.json`（6 单回退矩阵 refuse=[]）\n"
    )


def main() -> int:
    text = LEDGER.read_text(encoding="utf-8")
    added, skipped = [], []
    for bug, (heading, body) in sorted(SECTIONS.items()):
        head = f"## BUG-{bug} ["
        if text.count(head) != 1:
            print(f"REFUSE — 锚点不唯一：{head} count={text.count(head)}")
            return 1
        start = text.index(head)
        nxt = text.find("\n## BUG-", start + len(head))
        end = len(text) if nxt < 0 else nxt + 1
        section = build(bug, heading, body)
        if STAGE in text[start:end]:
            skipped.append(bug)
            continue
        text = text[:end] + section + text[end:]
        added.append(bug)
    LEDGER.write_text(text, encoding="utf-8", newline="\n")
    total = len(re.findall(r"^## BUG-", text, flags=re.M))
    mine = len(re.findall(re.escape(STAGE), text))
    print(
        json.dumps(
            {
                "added": added,
                "skipped_already": skipped,
                "bug_entries": total,
                "sections_with_this_stage": mine,
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
