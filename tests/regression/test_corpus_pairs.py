"""回归面（PROJECT-SPEC/03 §1 的 `tests/regression/`）：把 `corpus/` 的 Ω-spec 测试对当 pytest 用例跑。

只认一个事实源：断言逻辑从 `scripts/omega_gate.py` 导入，本文件不复制第二套判定代码
（两份判定各自演化 = 迟早一份说谎）。三格常驻门：

- `test_corpus_is_present_and_sealed`：目录里有 JSON、能解析、指纹复算相符 ⇒ 防篡改；
- `test_corpus_case_floor_does_not_drop`：用例数不得少于台账值（少了就是有用例静默消失）；
- `test_gate_refuses_unknown_assertion_key`：未知断言键必须 refuse，不许降级成存在性检查。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "corpus"

_spec = importlib.util.spec_from_file_location("omega_gate", ROOT / "scripts" / "omega_gate.py")
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

SPECS = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in sorted(CORPUS.glob("*.json"))}
PAIRS = [(fname, idx) for fname, spec in sorted(SPECS.items()) for idx in range(len(spec["tests"]))]

# 台账值：R14 当日实测 `specs=8 cases=176`（R13 的 7 spec / 151 例
# + R14 字典字面量键值位面 `cypy.dict.elements` 25 例，逐字见
# .fist-loop-20260929/logs/r14_corpus_*.out 的 CONCLUSION 与 omega_gate 的 specs/cases 读数）。
# 只许增不许减；扩面时同一批改台账值并留一份跑批回执。
FLOOR_SPECS = 8
FLOOR_CASES = 176


def test_corpus_is_present_and_sealed():
    assert len(SPECS) >= FLOOR_SPECS, f"corpus/ 只有 {len(SPECS)} 份 spec：{sorted(SPECS)}"
    for name, spec in SPECS.items():
        want = gate.fnv1a64(gate.seal_payload(spec))
        assert (
            spec["fingerprint"] == want
        ), f"{name} 指纹不符：账上 {spec['fingerprint']} 复算 {want}"
        assert spec["op"] in name and spec["laws"] and spec["preconditions"], name


def test_corpus_case_floor_does_not_drop():
    assert len(PAIRS) >= FLOOR_CASES, f"测试对掉到 {len(PAIRS)}，台账地板是 {FLOOR_CASES}"


def test_gate_refuses_unknown_assertion_key():
    obs = gate.execute({"op": "typecheck", "src": "def f():\n    x: int = 1\n    return x\n"})
    ok, why = gate.judge({"expected_output_hash": "whatever"}, obs)
    assert ok is None and "未知断言键" in why, (ok, why)


@pytest.mark.parametrize("fname,idx", PAIRS, ids=[f"{f}#{i}" for f, i in PAIRS])
def test_corpus_pair(fname: str, idx: int):
    spec = SPECS[fname]
    pair = spec["tests"][idx]
    obs = gate.execute(pair["input"])
    side = "error" if "error" in pair else "expected"
    ok, why = gate.judge(pair[side], obs)
    assert ok is True, f"{fname}#{idx} {side} 判不过：{why}"
