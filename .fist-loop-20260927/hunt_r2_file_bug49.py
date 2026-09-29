#!/usr/bin/env python3
"""R2-寻虫 第二条入账：文档声明与实测矛盾（只报我实测过的那半句，不扩大射程）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lfist_lib  # noqa: E402

SUMMARY = "SYNTAX/33 的实现状态栏说 constraint 未实现，但同一文件与实测都表明它四层已落地（过期声明会诱使后续轮重复实现）"

DETAIL = """声明处（逐字）：
  SYNTAX/33-type-constraints-subtypes-dispatch.md:6
    > **实现状态**：三件套 **全部未实现（0/4 层）**。`constraint` 与 `dispatch` 目前会被**静默吞成普通标识符/函数调用**，
  同文件 :40 的 B2 行还断言：`constraint Numeric = int | float` + `def f<T: Numeric>(x: T)` 用 `f(1)`
  会报 `type 'int' does not satisfy constraint 'Numeric'`。

调用面实测（本次，可复跑）：把 :40 那个 B2 程序原样写成 .cypy 交给 CLI：
  constraint Numeric = int | float

  def f<T: Numeric>(x: T) -> T:
      return x

  print(f(1))
  → `python -X utf8 -m cypyc transpile <该文件> -o <临时目录>` **rc=0**，
    打印 `[OK] Transpiled successfully`，产物 .pyx 非空。
  （对照：把 `def f<T: Numeric>` 误写成 `def f[T: Numeric]` 会在 3:10 报 `Expected LPAREN, got LBRACKET`
   ——说明 rc=0 不是因为解析器根本没看见这段，形状判据是活的。）

实现面旁证：`grep -c constraint cypyc/parser/lexer.py` = 3、`cypyc/codegen/cython_generator.py` = 6，
且仓库里有永久回归 `tests/test_named_constraints.py`（文件头自述：与 `Find_BUG/audit_2026q3/feat_constraint_*.py`
同源，覆盖 C-1.2/C-2.3/C-2.5 与 §5 的 codegen 行为）。

我只声称我实测过的部分：**`constraint` 的"未实现/静默吞"这半句与实测矛盾**；
`subtype` / `dispatch` 本轮没打探针，不在本单射程内（:6 里它们那半句可能是对的）。

影响（不是文案洁癖）：这条状态栏是给后续自动化轮次读的"路由表"。R1 已经因为 appendix-A:88
的过期描述把 `constraint` 当成候选核过一遍（当时结论：四层已落地、那行过期）；
本轮又同一形状复现。留着它就会每轮重新怀疑/重做同一件已完成的事。

修法（交文档/推进轮，红线要求我不改 SYNTAX/ 与 PROJECT-SPEC/）：
 把 :6 的状态行改成按件套分层的实测事实（constraint 四层可用 + 指回 tests/test_named_constraints.py；
 subtype/dispatch 维持未实现），或在文件头写明"状态以 §表格逐行实测为准，本行仅是快照"。
判据：改后仍要能用上面那条 .cypy 探针跑出 rc=0，否则是改错了而不是改好了。"""


def main() -> int:
    c = lfist_lib.Client(timeout=180)
    c._send(
        "initialize",
        {
            "protocolVersion": lfist_lib.PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": lfist_lib.CLIENT_INFO,
        },
    )
    c._recv(1, 60)
    r = c.call(
        "report_bug",
        {
            "summary": SUMMARY,
            "detail": DETAIL,
            "severity": "medium",
            "project_dir": ".",
            "reported_by": "cypy-hunter",
            "now": lfist_lib.utc_now(),
        },
    )
    bl = c.call("bug_list", {"project_dir": ".", "limit": 80, "now": lfist_lib.utc_now()})
    rows = bl.get("bugs") or bl.get("items") or []
    got = [b.get("id") for b in rows if str(b.get("id")) == str(r.get("bug_id"))]
    doc = {
        "filed": {"resp": r, "readback_ids": got},
        "summary": SUMMARY[:60],
        "bug_list_count": len(rows),
    }
    (HERE / "hunt_r2_file_bug49.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    print(json.dumps(doc, ensure_ascii=False)[:400])
    return 0 if got else 1


if __name__ == "__main__":
    sys.exit(main())
