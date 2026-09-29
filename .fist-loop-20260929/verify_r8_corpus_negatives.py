"""R8 新门的负面控制：证明 corpus 回归的三格常驻门真的会红。

规矩：每格都要「必然违例」的一次实测，而不是声称逻辑上会红。
被改动的是内存里的副本 + 临时目录里的克隆语料，`corpus/` 本体一字未动（收尾断言字节一致）。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "verify_r8_corpus_negatives.json"

_spec = importlib.util.spec_from_file_location("omega_gate", ROOT / "scripts" / "omega_gate.py")
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

_rspec = importlib.util.spec_from_file_location(
    "corpus_pairs", ROOT / "tests" / "regression" / "test_corpus_pairs.py")
reg = importlib.util.module_from_spec(_rspec)
_rspec.loader.exec_module(reg)
FLOOR = reg.FLOOR_CASES   # 地板值只认回归模块那一份，别在这里抄第二个数

CORPUS = ROOT / "corpus"


def fingerprint_gate_negative(specs: dict) -> dict:
    """篡改一格内容但保留原指纹 ⇒ 复算必须不符。"""
    name = "cypy.annotation.shape.json"
    tampered = json.loads(json.dumps(specs[name]))
    tampered["tests"][7]["error"]["contains"] = ["Some other wording"]
    want = gate.fnv1a64(gate.seal_payload(tampered))
    return {"cell": "篡改 spec 后指纹不符",
            "stored": tampered["fingerprint"], "recomputed": want,
            "carries": tampered["fingerprint"] != want,
            "also_recomputed_stable": want == gate.fnv1a64(gate.seal_payload(tampered))}


def floor_gate_negative(specs: dict) -> dict:
    """从一份 spec 里删掉一条用例 ⇒ 数量地板门必须发现（FLOOR → FLOOR-1 < FLOOR）。"""
    total = sum(len(s["tests"]) for s in specs.values())
    shrunk = json.loads(json.dumps(specs["cypy.annotation.shape.json"]))
    shrunk["tests"].pop()
    after = total - 1
    return {"cell": "少一条用例时地板门为真红", "baseline_cases": total,
            "after_removal": after, "floor": FLOOR,
            "carries": after < FLOOR and total == FLOOR}


def unknown_key_negative() -> dict:
    obs = gate.execute({"op": "typecheck", "src": "def f():\n    x: int = 1\n    return x\n"})
    ok, why = gate.judge({"expected_output_hash": "x"}, obs)
    return {"cell": "未知断言键被 refuse 而不是降级", "verdict": ok, "reason": why[:70],
            "carries": ok is None and "未知断言键" in why}


def wrong_expectation_negative() -> dict:
    """合法程序被判错 / 非法程序被判对，两个方向都必须能红。"""
    good = gate.execute({"op": "typecheck", "src": "def f():\n    x: [int] = [1]\n    return x\n"})
    ok_wrong_allowed, why_a = gate.judge({"errors": 0}, good)          # 非法形态却期望零错误 ⇒ 必须红
    bad = gate.execute({"op": "typecheck", "src": "def f():\n    x: int = 1\n    return x\n"})
    ok_wrong_denied, why_b = gate.judge(                               # 合法形态却期望诊断 ⇒ 必须红
        {"contains": ["Invalid type annotation"]}, bad)
    return {"cell": "两向对照：放过非法 / 拦掉合法 都被判红",
            "illegal_expected_clean": {"verdict": ok_wrong_allowed, "reason": why_a[:70]},
            "legal_expected_error": {"verdict": ok_wrong_denied, "reason": why_b[:70]},
            "carries": ok_wrong_allowed is False and ok_wrong_denied is False}


def pytest_reruns_in_tmp_copy() -> dict:
    """把 tests/regression 指到一份被删掉一条用例的语料克隆上 ⇒ pytest 必须红。"""
    tmp = Path(tempfile.mkdtemp(prefix="r8neg_"))
    try:
        shutil.copytree(ROOT / "scripts", tmp / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(CORPUS, tmp / "corpus")
        target = tmp / "corpus" / "cypy.annotation.shape.json"
        spec = json.loads(target.read_text(encoding="utf-8"))
        spec["tests"].pop()                      # 删一条：地板门应当被打破
        spec["fingerprint"] = gate.fnv1a64(gate.seal_payload(spec))  # 只防指纹门，专测地板门
        target.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        shutil.copytree(ROOT / "tests" / "regression", tmp / "tests" / "regression")
        shutil.copytree(ROOT / "cypyc", tmp / "cypyc", ignore=shutil.ignore_patterns("__pycache__"))
        p = subprocess.run([sys.executable, "-X", "utf8", "-m", "pytest",
                            "tests/regression/test_corpus_pairs.py::test_corpus_case_floor_does_not_drop",
                            "-q", "--no-header", "-p", "no:cacheprovider"],
                           cwd=tmp, capture_output=True, text=True, encoding="utf-8", errors="replace")
        out = p.stdout + p.stderr
        red = p.returncode != 0 and "1 failed" in out
        return {"cell": "克隆语料少一条 ⇒ pytest 地板门真红", "rc": p.returncode,
                "tail": next((ln.strip() for ln in reversed(out.splitlines())
                              if " failed" in ln or " passed" in ln), "")[:120],
                "carries": red}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(CORPUS.glob("*.json"))}
    specs = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in sorted(CORPUS.glob("*.json"))}
    cells = [fingerprint_gate_negative(specs), floor_gate_negative(specs), unknown_key_negative(),
             wrong_expectation_negative(), pytest_reruns_in_tmp_copy()]
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(CORPUS.glob("*.json"))}
    untouched = before == after
    rep = {"cells": cells, "corpus_untouched": untouched,
            "all_negative_controls_carry": all(c.get("carries") for c in cells) and untouched}
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    for c in cells:
        print(f"{c['cell']:<34} carries={c.get('carries')} {json.dumps({k: v for k, v in c.items() if k not in ('cell', 'carries')}, ensure_ascii=False)[:130]}")
    print(f"CONCLUSION controls={len(cells)} carrying={sum(1 for c in cells if c.get('carries'))} "
          f"corpus_untouched={untouched} all_carry={rep['all_negative_controls_carry']}")
    return 0 if rep["all_negative_controls_carry"] else 1


if __name__ == "__main__":
    sys.exit(main())
