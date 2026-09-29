"""R1-打磨 law2：三处 skip 类标记的**人工读定**落成数据件，并让每条结论都能被引回原文。

为什么还要一个脚本：定性是判断，判断要能被复核。这里做的不是"自动生成结论"，而是
把「我引用了哪一行」变成硬门——每条结论必须附一段**能在该 file:line 逐字找到的**引文，
找不到就整体拒绝（防"结论写在空气上"，也防文件之后被改动而结论没跟着改）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(r"E:\IDEProjects\AI\Cypy")

READS = [
    {
        "where": "tests/test_demos.py:35",
        "quote": 'pytest.skip(f"DEMO 文件不存在: {file_path}")',
        "shape": "机制型 skip：读 DEMO 前先看文件在不在",
        "verdict": "风险型（本轮未触发）：文件被删时用例静默跳过而非失败。"
        "全量运行里这条 skip **一次都没走**（R1-验证 的 pytest 汇总行是 `1862 passed`，"
        "无 skipped、日志里 SKIPPED 出现 0 次）⇒ 现在没有任何 DEMO 缺失被掩盖；"
        "但机制仍在：R1-验证 记到 examples/demos/legacy/** 有 9 项删除无人认领，"
        "将来若有测试改读这些路径，就会静默跳掉。建议由'清单必须完整'的断言承担（交人类裁决）",
        "cross_ref": ".fist-loop-20260927/verify_dirt_r1.json 的 deleted 列表",
    },
    {
        "where": "tests/test_polish_20260926.py:179",
        "quote": 'pytest.skip("平台允许写 property，回滚未失败")',
        "shape": "平台条件型 skip：只有在 setattr 不抛 AttributeError 时才跳",
        "verdict": "平台条件型（合法，且本轮未触发）：被测行为依赖 CPython 对同名 property 覆写的容忍度；"
        "全量 1862 passed / 0 skipped ⇒ 本机走的是 setattr 真的失败那条分支，断言被执行了，"
        "不是被跳过的绿。跳过条件由当场判定得出，不钉缺陷号 ⇒ 形状正确",
        "cross_ref": "同文件的 bug 号引用是我第一版扫描器的误挂（±4 行窗口把下一个函数头上的"
        " `# ---- BUG-6` 算了进来），修正为按所属函数体取号后本条不再引用任何缺陷",
    },
    {
        "where": "tests/test_project_compiler.py:361",
        "quote": 'pytest.skip("该源码在当前 parser 下仍能解析，无法验证解析失败诊断")',
        "shape": "自证型 skip：只有解析失败时才有断言可跑",
        "verdict": "分支型弱断言（本轮未触发 skip 分支）：只有解析失败时才有断言可跑；"
        "全量 0 skipped ⇒ 本机走到的是 `pc._parse_errors` 非空的那一支，"
        "所以它当前确实在断言而不是恒跳。但另一支（解析成功 ⇒ skip）意味着"
        "若解析器放宽，这条用例会静默失去意义 ⇒ 建议改成显式必坏源码的夹具（本轮不动既有测试）",
        "cross_ref": "skip 未触发的依据：.fist-loop-20260927/verify_pytest_full_r1.log 的汇总行"
        "（`1862 passed`，日志内 SKIPPED 计数 0），与 polish 轮基线复跑互证",
    },
]


def main() -> int:
    bad = []
    for r in READS:
        rel, line = r["where"].rsplit(":", 1)
        p = ROOT / rel
        if not p.exists():
            bad.append(f"{r['where']} 文件不在盘上")
            continue
        lines = p.read_bytes().decode("utf-8-sig", errors="replace").splitlines()
        n = int(line)
        if not (1 <= n <= len(lines)):
            bad.append(f"{r['where']} 行号越界（文件只有 {len(lines)} 行）")
            continue
        got = lines[n - 1].strip()
        if r["quote"].strip() != got:
            bad.append(f"{r['where']} 引文与盘上不一致：期望 {r['quote']!r} 实为 {got!r}")
    # 自证：三处结论都声称"本轮未触发"，那就必须拿真日志核一遍，不能只靠文字
    log = HERE / "verify_pytest_full_r1.log"
    summ = ""
    if log.exists():
        txt = log.read_text(encoding="utf-8", errors="replace")
        lines = [l for l in txt.splitlines() if " passed" in l]
        summ = lines[-1].strip() if lines else ""
        if "skipped" in summ or txt.count("SKIPPED") > 0:
            bad.append(f"结论声称未触发，但日志里有 skip：{summ[:120]}")
    else:
        bad.append("缺少用于自证的 verify_pytest_full_r1.log ⇒ '未触发'这条主张没有依据")
    doc = {
        "refuse": bad,
        "reads": READS,
        "count": len(READS),
        "evidence_summary_line": summ,
        "skipped_tokens_in_log": (
            log.read_text(encoding="utf-8", errors="replace").count("SKIPPED")
            if log.exists()
            else None
        ),
    }
    (HERE / "polish_law2_reads_r1.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "refuse": bad,
                "count": len(READS),
                "verdicts": [r["where"] + " → " + r["verdict"][:40] for r in READS],
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
