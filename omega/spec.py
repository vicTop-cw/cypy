# -*- coding: utf-8 -*-
"""Ω-spec JSON 解析、schema 校验与 fingerprint 计算。

spec JSON 格式（参考 tnr corpus/*.spec.json）：
{
  "op": "task_report",
  "version": "1.0",
  "definition": {"signature": "...", "note": "..."},
  "preconditions": ["..."],
  "laws": ["L1"],
  "tests": [{"input": {...}, "expected": {...}}, {"input": {...}, "error": "..."}],
  "fingerprint": "fnv1a64:xxxxxxxx"
}
"""

import json
import os

REQUIRED_FIELDS = ["op", "version", "definition", "preconditions", "laws", "tests", "fingerprint"]


def fnv1a64(data: bytes) -> str:
    """FNV-1a 64 位哈希（与 tnr 一致）。"""
    h = 0xcbf29ce484222325
    for b in data:
        h ^= b
        h = (h * 0x100000001b3) & 0xFFFFFFFFFFFFFFFF
    return f"{h:016x}"


def load_spec(path):
    """加载 spec JSON 文件。"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def validate_schema(spec):
    """校验 spec 必填字段与结构，返回错误列表（空 = 通过）。"""
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in spec:
            errors.append(f"缺少必填字段: {field}")
    if "tests" in spec:
        if not isinstance(spec["tests"], list):
            errors.append("tests 必须是列表")
        else:
            for i, t in enumerate(spec["tests"]):
                if not isinstance(t, dict):
                    errors.append(f"tests[{i}] 必须是对象")
                    continue
                if "input" not in t:
                    errors.append(f"tests[{i}] 缺少 input")
                if "expected" not in t and "error" not in t:
                    errors.append(f"tests[{i}] 缺少 expected 或 error")
    return errors


def compute_fingerprint(spec):
    """对除 fingerprint 外的内容计算 fnv1a64 指纹。"""
    payload = {k: v for k, v in spec.items() if k != "fingerprint"}
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return f"fnv1a64:{fnv1a64(data)}"


def verify_fingerprint(spec):
    """校验 fingerprint 是否与内容匹配，返回 (ok, message)。"""
    if "fingerprint" not in spec:
        return False, "缺少 fingerprint"
    expected = compute_fingerprint(spec)
    if spec["fingerprint"] != expected:
        return False, f"fingerprint 不匹配: 期望 {expected}, 实际 {spec['fingerprint']}"
    return True, "ok"


def validate_spec_file(path):
    """校验单个 spec 文件，返回 (ok, message)。"""
    try:
        spec = load_spec(path)
    except Exception as e:
        return False, f"JSON 解析失败: {e}"
    errors = validate_schema(spec)
    if errors:
        return False, "; ".join(errors)
    ok, msg = verify_fingerprint(spec)
    if not ok:
        return False, msg
    return True, f"spec 有效: {spec.get('op')} v{spec.get('version')}"
