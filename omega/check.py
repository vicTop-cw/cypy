# -*- coding: utf-8 -*-
"""项目结构验证：对照 PROJECT-SPEC/01 标准结构检查 project_dir。

验证维度：
1. 结构验证：必填项（README.md / CHANGELOG.md / reports/）是否存在；
2. 回传格式验证：任务回传是否符合五段式（结论/证据/分析/缺口与风险/建议入档位置）。
"""

import os

# PROJECT-SPEC/01 必填项
REQUIRED_ITEMS = ["README.md", "CHANGELOG.md", "reports"]

# FIST-SKILL 第 3 章子代理回传强制五段式
REQUIRED_REPORT_SECTIONS = ["结论", "证据", "分析", "缺口与风险", "建议入档位置"]


def check_structure(project_dir):
    """检查项目标准结构，返回结果列表。"""
    results = []
    if not os.path.isdir(project_dir):
        return [{"item": "project_dir", "passed": False, "detail": f"目录不存在: {project_dir}"}]
    for item in REQUIRED_ITEMS:
        path = os.path.join(project_dir, item)
        exists = os.path.exists(path)
        results.append({"item": f"必填项: {item}", "passed": exists, "detail": "存在" if exists else "缺失"})
    return results


def check_report_format(text):
    """检查回传文本是否符合五段式，返回结果列表。"""
    results = []
    if not text or not text.strip():
        return [{"item": "回传文本", "passed": False, "detail": "回传为空"}]
    for section in REQUIRED_REPORT_SECTIONS:
        found = section in text
        results.append({"item": f"回传段: {section}", "passed": found, "detail": "包含" if found else "缺失"})
    return results
