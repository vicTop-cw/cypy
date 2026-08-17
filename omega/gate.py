# -*- coding: utf-8 -*-
"""Ω-gate 跑批验证：对 spec 的测试对批量执行（input → expected，含错误路径）。

evaluator 约定：evaluator(input_dict) -> (ok: bool, value)
- ok=True 表示执行成功，value 为结果；
- ok=False 表示执行失败，value 为错误信息（字符串）。
"""


def run_tests(spec, evaluator):
    """对 spec 的每个测试对跑批，返回结果列表。

    每个结果: {"index", "type": "normal"/"error", "passed": bool, "detail": str}
    """
    results = []
    for i, t in enumerate(spec.get("tests", [])):
        try:
            ok, value = evaluator(t.get("input", {}))
        except Exception as e:  # 执行器自身异常视为失败
            ok, value = False, f"执行器异常: {e}"
        if "error" in t:
            # 期望错误路径：执行必须失败，且错误信息包含期望错误类型
            passed = (not ok) and (t["error"] in str(value))
            results.append({
                "index": i, "type": "error", "passed": passed,
                "detail": f"期望错误 {t['error']}，实际: {value}",
            })
        else:
            passed = ok and value == t.get("expected")
            results.append({
                "index": i, "type": "normal", "passed": passed,
                "detail": f"期望 {t.get('expected')}，实际: {value}",
            })
    return results


def summarize(results):
    """汇总跑批结果，返回 (total, passed, accuracy)。"""
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    accuracy = (passed / total * 100.0) if total else 0.0
    return total, passed, accuracy
