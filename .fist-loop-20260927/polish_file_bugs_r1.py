"""R1-打磨：把两条调用面已证实的失踪/死代码入账（report_bug），并回读对账。

文案里的引号一律用「」，不用 ASCII 双引号——上一版就因为在双引号字符串里嵌了 ASCII 引号而SyntaxError。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lfist_lib  # noqa: E402

D41 = """调用面实测（证据件 `.fist-loop-20260927/polish_probe_r1.json` 的 P1，可复跑）：

  import tests.test_boundary_comprehensive 之后，模块属性 TestPointerBoundary 指向源码第 420 行那份，
  而第 200 行那份自己定义了 3 个 test_ 方法 ⇒ 这 3 条用例从不被执行；
  同文件 TestPipelineBoundary 同形状（282 行 3 条被 910 行的 7 条覆盖）⇒ 合计 6 条用例静默失踪。

证据怎么数出来的（两条独立口径互相咬合）：
 - AST 逐个 ClassDef 数体内的 test_ 方法：{200: 3, 420: 5}、{282: 3, 910: 7}；
 - inspect.getsourcelines(生效类)[1] 给出生效定义行 420 / 910，
   len([m for m in dir(类) if m.startswith('test_')]) 给出 5 / 7 ⇒ 被遮的 3+3 条确实不在类对象上。

影响：这种失踪没有任何失败信号。`pytest tests/` 报的 1862 passed 从来只含后定义那组；
而上一轮把 1862 当「覆盖率只升不降」的基数，基数本身就少算了 6 条。
flake8 侧以 F811 报了这两处（tests/test_boundary_comprehensive.py:420 与 :910），
但 F811 只说「重复定义」，不说被遮的是测试类 ⇒ 极易被当噪声划掉。

修法（交修复轮；打磨环节的红线是不动既有测试）：
 a) 给前一组改名（如 TestPointerBoundaryLegacy）让 6 条都跑起来，再逐条处理新暴露的失败；
 b) 若确认前一组是废弃副本，删除它并在提交说明里写明判断依据（哪一份更新、谁引用了谁）。"""

D42 = """调用面实测（证据件 `.fist-loop-20260927/polish_probe_r1.json` 的 P2）：

 - CythonGenerator._visit_ExprStmt 在 cypyc/codegen/cython_generator.py 定义两次：
   1399 行那份 7 行体，2065 行那份 15 行体；
   `CythonGenerator.__dict__['_visit_ExprStmt'].__code__.co_firstlineno == 2065`
   ⇒ 1399 行那份从不被调用（死代码）。
 - ScopeAnalyzer._visit_MetaBlock 同样两处（cypyc/analyzer/scope_analyzer.py 484 行 11 行体、
   926 行 6 行体），生效的是 926 行 ⇒ 484 行那份是死代码，
   而且它比生效版本**长 5 行**：如果两次改动各写了一半逻辑，被覆盖的那一半就是丢的功能。
   本单不断言「哪一份才是意图」，只交可复算的事实（生效行号 + 两份体长）。

影响：同一文件里两份同名实现，意味着任何「改那份代码」的动作都可能改在死地址上，
测试与 review 都看不出——这正是 FIST 账本里「守卫覆盖面窄于主张」在产品码侧的镜像。
flake8 的 F811 报了这两处但只说 redefinition of unused '...' from line N，不指明被遮分支的规模。

修法（修复轮）：先用 `git log -L <起>,<止>:<文件>` 比对两份来历（哪份是后加的、为何加），
保留一份、把另一份的用例补进测试；本环节不动产品码。"""

ITEMS = [
    ("tests/test_boundary_comprehensive.py 两组测试类被同名重复定义遮住，6 条用例静默不执行", D41),
    ("产品码里 _visit_ExprStmt / _visit_MetaBlock 各定义两次，前一份成为死代码", D42),
]


def main() -> int:
    c = lfist_lib.Client(timeout=240)
    c._send(
        "initialize",
        {
            "protocolVersion": lfist_lib.PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": lfist_lib.CLIENT_INFO,
        },
    )
    out = []
    for summ, det in ITEMS:
        r = c.call(
            "report_bug",
            {
                "project_dir": ".",
                "summary": summ,
                "detail": det,
                "severity": "medium",
                "publish_task": True,
                "now": lfist_lib.utc_now(),
            },
        )
        if isinstance(r, dict) and "__error__" in r:
            print("REFUSE — 入账被拒：", json.dumps(r["__error__"], ensure_ascii=False)[:260])
            c.close()
            return 1
        out.append({"bug_id": r.get("bug_id"), "task_id": r.get("task_id"), "path": r.get("path")})
        print("filed:", json.dumps(out[-1], ensure_ascii=False))
    bl = c.call("bug_list", {"project_dir": "."})
    items = bl.get("bugs") or []
    ids = [it.get("id") for it in items]
    print("bug_list count:", len(items), "| tail:", ids[-4:])
    missing = [o["bug_id"] for o in out if o["bug_id"] not in ids]
    c.close()
    if missing:
        print("REFUSE — 报了号但列表里查不到：", missing)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
