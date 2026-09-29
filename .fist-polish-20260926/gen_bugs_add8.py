#!/usr/bin/env python3
"""Append the 8th triaged defect (found while re-reading the parser lane) to bugs_batch.json.

Idempotent: re-running never duplicates the payload.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "bugs_batch.json")

SUMMARY = ("[silent-fail] cypyc/parser/macro_expander.py:380 宏展开后的代码块解析失败时静默"
           "返回原块，整条宏语句从输出中消失且无任何告警")

PAYLOAD = {
    "tool": "report_bug",
    "args": {
        "project_dir": ".",
        "severity": "medium",
        "summary": SUMMARY,
        "detail": (
            "现象: `_reparse_code()` 末尾 `try: Lexer/Parser ... except Exception as e:` 直接把"
            "未解析的原文包成 `BacktickBlock(code, '', line, col)` 返回，异常对象 `e` 被丢弃、"
            "无任何 stderr 输出。模块自己的实现约束注释（同文件 :20-23）就写着「这条降级路径会让"
            "整条宏调用语句从输出里消失」，即已知其危害，但用户/CI 看不到任何线索。\n"
            "复现（确定性，零依赖）: `MacroExpander.__new__(MacroExpander)._reparse_code('def (', 7, 3)`"
            " → 返回 BacktickBlock 且 capsys 捕获的 stderr 为空串。见 "
            "`tests/test_polish_20260926.py::test_bug8_macro_reparse_degradation_is_reported`"
            "（修复前该条 1 failed / err == ''）。\n"
            "影响: 宏实参渲染或插值产出的文本一旦不可解析，展开结果被原样透传给 codegen，"
            "该语句在生成的 .pyx 里消失——编译「成功」但少了一条语句，属静默数据丢失；"
            "与本轮 BUG-3/BUG-4/BUG-5/BUG-6/BUG-7 同族。\n"
            "建议: 不改降级语义（仍返回 BacktickBlock，避免打破 23 条既有 macro 用例），"
            "只在 except 分支打一条点名 行/列/原始代码/底层异常的 stderr 告警；"
            "彻底修复（把失败上报到 diagnostics 并非零退出）属语义面变更，需单独立项。"
        ),
        "publish_task": True,
        "reported_by": "cypy-polisher",
    },
}


def main():
    batch = json.load(open(PATH, encoding="utf-8"))
    if any(p["args"]["summary"] == SUMMARY for p in batch):
        print(f"already present, payloads={len(batch)}")
        return 0
    batch.append(PAYLOAD)
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(batch, f, ensure_ascii=False, indent=2)
    print(f"appended, payloads={len(batch)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
