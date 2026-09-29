"""Ω-gate 跑批：执行 `corpus/` 下每份 Ω-spec JSON 的测试对，产出项目准确率（PROJECT-SPEC/05）。

用法：
    python scripts/omega_gate.py                # 校验指纹 + 跑批，准确率 <100% 即 rc=1
    python scripts/omega_gate.py --seal         # 把 fingerprint 写成 fnv1a64（仅用于首次入册）
    python scripts/omega_gate.py --op <name>    # 只跑一个 op

纪律（都是既往轮次的教训，逐条落在代码里）：
- 断言键是闭集，未知键直接 refuse —— 不做「未知键降级成存在性检查」那种静默放行；
- 每条用例都要给原因：通过也要落「观测到了什么」，失败要落「期望什么 / 实际什么」；
- 结论行打在最后（外层驱动只保留 stdout 尾部时，结论不会被截掉）；
- 结果同时落 `reports/YYYY-MM-DD/omega-<UTC>.json`。
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CORPUS = ROOT / "corpus"
REPORTS = ROOT / "reports"

from cypyc.analyzer.type_checker import TypeChecker  # noqa: E402
from cypyc.codegen.cython_generator import CythonGenerator  # noqa: E402
from cypyc.parser.lexer import Lexer  # noqa: E402
from cypyc.parser.parser import Parser  # noqa: E402

EXPECTED_KEYS = {"errors", "contains", "not_contains", "matches", "min_count",
                 "no_diagnostic_contains", "slot_types", "class_fields", "fields_exclude",
                 "no_arity_diagnostic", "stage"}


def fnv1a64(data: bytes) -> str:
    h = 0xCBF29CE484222325
    for b in data:
        h = ((h ^ b) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return f"fnv1a64:{h:016x}"


def seal_payload(spec: dict) -> bytes:
    body = {k: v for k, v in spec.items() if k != "fingerprint"}
    return json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")


def compile_src(src: str) -> tuple:
    return Parser(list(Lexer(src).tokenize())).parse()


def execute(inp: dict) -> dict:
    """跑真实管线，返回可断言的观测量（不做任何「看起来通过」的近似）。"""
    op, src = inp["op"], inp["src"]
    out: dict = {"op": op, "stage": "ok", "errors": [], "code": "", "slot_types": [],
                 "class_fields": {}}
    try:
        ast = compile_src(src)
    except ValueError as exc:
        out.update(stage="parse", errors=[str(exc)])
        return out
    checker = TypeChecker()
    try:
        checker.check(ast)
    except Exception as exc:  # noqa: BLE001
        out.update(stage="analyze-crash", errors=[f"INTERNAL {type(exc).__name__}: {exc}"])
        return out
    out["errors"] = [e for e in checker.errors if e.strip()]
    if inp.get("type_name"):
        slots = checker._pattern_slot_types(inp["type_name"]) or []
        out["slot_types"] = [s.name for s in slots]
    if op in ("codegen", "codegen_unchecked"):
        if op == "codegen" and out["errors"]:
            out["stage"] = "typecheck"
            return out
        gen = CythonGenerator()
        try:
            out["code"] = gen.generate(ast)
        except Exception as exc:  # noqa: BLE001
            out.update(stage="codegen-crash", errors=out["errors"] + [f"INTERNAL {type(exc).__name__}: {exc}"])
            return out
        out["class_fields"] = {k: list(v) for k, v in (gen._class_fields or {}).items()}
    return out


def judge(assertion: dict, obs: dict) -> tuple:
    """返回 (是否通过, 原因)。未知键 ⇒ refuse（不作判定，也不算通过）。"""
    unknown = sorted(set(assertion) - EXPECTED_KEYS)
    if unknown:
        return None, f"未知断言键 {unknown}（闭集：{sorted(EXPECTED_KEYS)}）"
    text = obs["code"] if (obs["op"].startswith("codegen") and obs["stage"] == "ok") \
        else "\n".join(obs["errors"])
    if "stage" in assertion and assertion["stage"] != obs["stage"]:
        return False, f"stage 期望 {assertion['stage']}，实际 {obs['stage']}"
    if assertion.get("stage") == "parse":
        if not obs["errors"]:
            return False, "期望 parse 阶段报错，实际没有任何诊断"
    if "errors" in assertion and len(obs["errors"]) != assertion["errors"]:
        return False, f"errors 期望 {assertion['errors']}，实际 {len(obs['errors'])}：{obs['errors'][:2]}"
    for needle in assertion.get("contains", []):
        if needle not in text:
            return False, f"缺片段 {needle!r}；观测={text[:160]!r}"
    for needle in assertion.get("not_contains", []):
        if needle in text:
            return False, f"不该出现 {needle!r}；观测={text[:160]!r}"
    if "min_count" in assertion:
        one = assertion.get("contains", [""])[0]
        n = sum(1 for e in obs["errors"] if one in e)
        if n < assertion["min_count"]:
            return False, f"{one!r} 命中 {n} 条 < min_count {assertion['min_count']}"
    if "matches" in assertion and not re.search(assertion["matches"], text):
        return False, f"正则 /{assertion['matches']}/ 不匹配；观测={text[:160]!r}"
    for needle in assertion.get("no_diagnostic_contains", []):
        hit = [e for e in obs["errors"] if needle in e]
        if hit:
            return False, f"不该出现含 {needle!r} 的诊断，实际={hit[0][:110]}"
    if "slot_types" in assertion and assertion["slot_types"] != obs["slot_types"]:
        return False, f"slot_types 期望 {assertion['slot_types']}，实际 {obs['slot_types']}"
    for type_name, fields in (assertion.get("class_fields") or {}).items():
        actual = obs["class_fields"].get(type_name)
        if actual != fields:
            return False, f"_class_fields[{type_name}] 期望 {fields}，实际 {actual}"
    for type_name, banned in (assertion.get("fields_exclude") or {}).items():
        actual = obs["class_fields"].get(type_name, [])
        hit = [b for b in banned if b in actual]
        if hit:
            return False, f"_class_fields[{type_name}] 不该含 {hit}，实际={actual}"
    if assertion.get("no_arity_diagnostic") and any("Positional pattern" in e for e in obs["errors"]):
        return False, f"类型不可见时不应报元数错：{obs['errors']}"
    return True, f"观测={text[:80]!r} slot_types={obs['slot_types']} errors={len(obs['errors'])}"


def run_spec(spec: dict, verify_fp: bool) -> dict:
    fp = spec.get("fingerprint", "")
    if verify_fp:
        want = fnv1a64(seal_payload(spec))
        if fp != want:
            return {"op": spec["op"], "refuse": f"指纹不符：账上 {fp} 复算 {want}", "cases": []}
    if verify_fp and fp.endswith("PENDING"):
        return {"op": spec["op"], "refuse": "指纹未封（PENDING）⇒ 先 --seal", "cases": []}
    cases = []
    for i, pair in enumerate(spec["tests"]):
        obs = execute(pair["input"])
        side = "error" if "error" in pair else "expected"
        ok, why = judge(pair[side], obs)
        cases.append({"idx": i, "side": side, "op": pair["input"]["op"], "ok": ok, "reason": why,
                      "src_head": pair["input"]["src"].splitlines()[0][:48]})
    passed = sum(1 for c in cases if c["ok"] is True)
    refused = [c for c in cases if c["ok"] is None]
    return {"op": spec["op"], "cases": cases, "n": len(cases), "passed": passed,
            "failed": [c for c in cases if c["ok"] is False], "refused": refused,
            "accuracy": (passed / len(cases)) if cases else 0.0}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seal", action="store_true")
    ap.add_argument("--op", default="")
    args = ap.parse_args()

    files = sorted(CORPUS.glob("*.json"))
    if not files:
        print(f"CONCLUSION specs=0 refuse=corpus/ 为空 ⇒ 没有客观准确率来源")
        return 1
    non_json = [p.name for p in CORPUS.iterdir() if p.suffix != ".json"]
    if non_json and not args.seal:
        print(f"REFUSE corpus/ 只准放 JSON，发现非 JSON：{non_json}")
        return 1

    results, specs = [], []
    for p in files:
        spec = json.loads(p.read_text(encoding="utf-8"))
        if args.op and spec["op"] != args.op:
            continue
        specs.append((p, spec))
        if args.seal:
            spec["fingerprint"] = fnv1a64(seal_payload(spec))
            p.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8", newline="\n")
            print(f"SEALED {p.name} {spec['fingerprint']}")
            continue
        results.append(run_spec(spec, verify_fp=True))
    if args.seal:
        return 0

    total = sum(r.get("n", 0) for r in results)
    passed = sum(r.get("passed", 0) for r in results)
    failed = [f"{r['op']}#{c['idx']}: {c['reason']}" for r in results for c in r.get("failed", [])]
    refused = [f"{r['op']}: {r.get('refuse')}" for r in results if r.get("refuse")] + \
              [f"{r['op']}#{c['idx']}: {c['reason']}" for r in results for c in r.get("refused", [])]
    acc = (passed / total * 100.0) if total else 0.0
    stamp = datetime.datetime.now(datetime.timezone.utc)
    day = REPORTS / stamp.strftime("%Y-%m-%d")
    day.mkdir(parents=True, exist_ok=True)
    payload = {"utc": stamp.isoformat(timespec="seconds"), "specs": len(results),
               "cases_total": total, "cases_passed": passed, "accuracy_pct": round(acc, 2),
               "per_spec": [{k: v for k, v in r.items() if k != "cases"} for r in results],
               "failed": failed, "refused": refused}
    (day / f"omega-{stamp.strftime('%Y%m%dT%H%M%SZ')}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    for r in results:
        tail = f" REFUSE={r['refuse']}" if r.get("refuse") else ""
        print(f"SPEC {r['op']} cases={r.get('n', '-')} passed={r.get('passed', '-')}{tail}")
        for c in r.get("failed", []):
            print(f"  FAIL #{c['idx']} {c['op']} {c['src_head']!r} → {c['reason']}")
        for c in r.get("refused", []):
            print(f"  REFUSED #{c['idx']} {c['reason']}")
    print(f"CONCLUSION specs={len(results)} cases={total} passed={passed} failed={len(failed)} "
          f"refused={len(refused)} accuracy={acc:.2f}% rc={0 if (acc == 100.0 and not refused) else 1}")
    return 0 if (acc == 100.0 and not refused) else 1


if __name__ == "__main__":
    sys.exit(main())
