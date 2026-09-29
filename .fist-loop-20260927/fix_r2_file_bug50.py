#!/usr/bin/env python3
"""把本轮**自己造出来的**缺陷入账：操作者一次 black 调用整档重写了两个产品文件。

形状与产品缺陷不同但同样要入账：它破坏了「最小改动」与「不可逆动作只挂账」两条纪律，
且损失不可回滚。判据面全部是当场可复算的（git diff --stat 行数、无副本的三条反证）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lfist_lib  # noqa: E402

DETAIL = """现象（全部当场可复算）：

  $ git diff --stat -- cypyc/parser/parser.py cypyc/parser/macro_expander.py
   cypyc/parser/macro_expander.py |  365 ++++---
   cypyc/parser/parser.py         | 1885 +++++++++++++++++++++++++++----------
  ↑ 相对 HEAD(17d68b4) 的改动行数是 425 → 1885（parser.py）。而**本单对该文件的真实意图只有 4 处**：
    ① `_parse_params` 里给 `= __implicit_default__` 加无注解诊断（9 行）；
    ② `_parse_return_stmt` 补 `_require_function_scope`（2 行）；
    ③ `Parser.__init__` 增 `body_scope` 形参与 `self._body_scope`（3 行）；
    ④ `_require_function_scope` 条件加 `or self._body_scope` + `_parse_macro_def` 保存/恢复该标志（5 行）。

来历（一次性命令，写在 `.fist-loop-20260927/` 的执行记录里）：
  python -X utf8 -m black \\
      .fist-loop-20260927/fix_r2_lint.py .fist-loop-20260927/fix_r2_lockproof.py \\
      .fist-loop-20260927/fix_r2_baselines.py \\
      cypyc/parser/parser.py cypyc/parser/macro_expander.py \\
      tests/test_loop_20260927_fix_r2.py
本意是"格式化我本轮写的文件"，但把两档**存量未格式化**的产品文件一起传了进去：
仓库声明的是 flake8 100 列（且 BUG-40 已证 `[tool.flake8]` 根本不生效），black 从未在这两档上跑过
⇒ black 按自己的口径整档重排（引号、空行、换行位置、长表达式续行等）。

为什么这是缺陷而不是"顺手整理"：
1. 不可逆：改动前的文本没有任何副本 —— 三条反证当场可查：
   `git ls-files -s cypyc/parser/parser.py` 的索引 blob 与 `git rev-parse HEAD:...` **同一个哈希**
   （fe5a888…，164275 字节），即从未 `git add` 过；
   IDE 侧 `file-history` 目录里今天 16:00 之后没有任何 >140KB 的快照（全量 `find` 只命中本仓那份）；
   `git archive HEAD` 类快照树取的是 HEAD，不含 09-26/R1 的**未提交**工作。
   ⇒ 唯一还能确定的是「语义应保持不变」（black 只做格式化），但这是**主张不是证据**。
2. 覆盖了别人的在飞工作：这两档里压着 09-26 审计轮与 R1 轮未提交的改动，
   现在它们的作者若再按原文本做锚点替换（并发 lane 的脚本化补丁正是这么做的），会静默改不到位置。
3. 破坏了评审面：人类 reviewer 拿到的 diff 从 425 行变 1885 行，真正的 4 处改动被埋在重排噪声里。

期望：操作者对**产品文件**只做定向编辑；格式化只在"本轮亲笔整档"上跑；
任何可能整档重写工具的调用前先落快照（本轮起 `.fist-loop-20260927/snapshot_tracked.py`
把 `git ls-files` 全集复制到仓库外 `E:/IDEProjects/AI/_cypy_snapshots/<标签>/` 并自证文件数/字节数）。

不算证明的现象：三套基线（pytest/自研/e2e）全绿**不能**证明没有损失 —— 它们测的是行为，
而这条损失是文本层与评审面的；反过来基线若红，也说明不了是格式化引起的（本轮已实测一例真回归
是语义改动引起：`_require_function_scope` 吃掉了宏体 return，见 BUG-51）。

修法（交人工裁决，自动轮不再动这两档的排版）：
 a) 接受现状，在提交说明里把"4 处真实改动"与"black 整档重排"分开列（我已在本轮报告 §五′ 写清）；
 b) 由持有原始文件的人（09-26 轮 / R1 轮的作者或用户本地备份）提供原文，再由我重放 4 处改动；
 c) 长期项：给仓库加 `black --check` 的**范围化**门禁（只判本轮改动的 hunk），
    避免"格式化器一旦有人手滑就整档重排"这条路再次被走。"""

ITEMS = [
    (
        "操作者把两档存量未格式化的产品文件交给 black 整档重写，改动不可回滚且淹没真实 diff",
        DETAIL,
        "high",
    ),
    (
        "BUG-39 的顶层 return 守卫首版吃掉宏体/宏展开片段里的 return，全量 pytest 当场红 2 条",
        """现象（修复前一次真实全量跑，日志 `.fist-loop-20260927/r2fix/pytest_gate.txt`）：
  2 failed, 1881 passed in 373.79s
  FAILED tests/test_parser_macro.py::test_macro_definition_parsing - ValueError:
      return must be used inside a function, found at 2:5
  FAILED tests/test_macro_features.py::test_macro_interpolation_expression - assert 1 == 0
      [cypy][warn] 宏展开后的代码块无法解析，按原样保留（该语句可能从输出中消失）

来历：`cypyc/parser/parser.py::_parse_return_stmt` 加 `_require_function_scope` 时，
按「函数体之外」理解作用域，而**宏体本身也是 `-> Tokens` 的返回语义**：
`_parse_macro_def` 与 `cypyc/parser/macro_expander.py::_parse_code` 都用一个新建 Parser 解析宏体/
展开片段，此时 `_in_function` 为假 ⇒ 合法的 `macro m(ts: Tokens) -> Tokens = return ts` 被拒；
展开路径更糟——异常被 expander 吞成 warn，整条宏调用**从产物里消失**（静默丢代码）。

本单记录的是**修 BUG 时把半径判窄了一半**这个缺陷本身：
我当场给的"波及面实测"只跑了 `examples/` 27 份 .cypy（全绿），据此就在报告草稿里写了
"不会打掉既有可编译样例" —— 真正暴露它的是随后那次全量 pytest。⇒ 判据口径修正：
"改了 parser/lexer 的作用域判定"这类改动，波及面必须用**全量套件**（两套体系）量，
examples 语料不能代表 `tests/` 里那些为特性写的形状。

修法（本轮已落地并锁死）：`Parser.__init__(..., body_scope: bool = False)`，
`_require_function_scope` 改为 `if not (self._in_function or self._body_scope)`；
`_parse_macro_def` 解析宏体前置位、解析后恢复；expander 用 `Parser(tokens, body_scope=True)`。
刻意不动 `_scope_stack` —— 它是 `_is_module_level()` 的依据，宏体里仍可生成 struct/impl。
锁：`tests/test_loop_20260927_fix_r2.py` 的
`test_bug39_macro_body_return_stays_legal`、`test_bug39_expanded_fragment_return_stays_legal`
与对照 `test_bug39_control_fragment_without_body_scope_still_rejected`（不开标志时仍必须被拒）。

不算证明：只看这两条测试绿不足以说明宏语义没被动 —— 它们只覆盖 `return`；
`defer`/`@meta` 之类同样走 `_require_function_scope`/`_require_module_level` 的构造，
本轮未扩测，转结后续轮。""",
        "medium",
    ),
]


def main() -> int:
    c = lfist_lib.Client(timeout=120)
    c._send(
        "initialize",
        {
            "protocolVersion": lfist_lib.PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": lfist_lib.CLIENT_INFO,
        },
    )
    c._recv(1, 60)
    out = []
    for title, detail, sev in ITEMS:
        r = c.call(
            "report_bug",
            {
                "summary": title,
                "detail": detail,
                "severity": sev,
                "project_dir": ".",
                "reported_by": "cypy-fixer",
                "now": lfist_lib.utc_now(),
            },
        )
        out.append({"title": title[:50], "resp": r})
        print(json.dumps({"filed": r.get("bug_id") or r, "title": title[:60]}, ensure_ascii=False))
    bl = c.call("bug_list", {"project_dir": ".", "limit": 80, "now": lfist_lib.utc_now()})
    rows = bl.get("bugs") or bl.get("items") or bl
    ids = []
    if isinstance(rows, list):
        for b in rows:
            head = b.get("summary") or b.get("title") or ""
            ids.append(f"{b.get('id')}|{b.get('status')}|{head[:40]}")
    print(json.dumps({"tail": ids[-6:], "count": len(ids)}, ensure_ascii=False))
    (HERE / "fix_r2_file_bug50.json").write_text(
        json.dumps({"filed": out, "tail": ids}, ensure_ascii=False, indent=1),
        encoding="utf-8",
        newline="\n",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
