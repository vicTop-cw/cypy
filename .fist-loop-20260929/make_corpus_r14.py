"""R14 判据语料：新建 `cypy.dict.elements`，并把 R13 语料里那条"dict 豁免"半边**收紧**。

两件事一起做的理由：这两格说的是同一个事实（`dict<str,int>` 收 `{"a":"b"}` 判不判），
只改一处就会出现"两份 spec 互相矛盾"——那是判据坏了，不是产品坏了。

期望值不是手抄的：逐条现跑 `omega_gate.execute()`，再按探针自己声明的栏位对表
（`MUST_RED` 必须红、`MUST_GREEN` 必须绿），**任一条对不上就拒绝落盘**；
落盘后重读文件复算指纹，并证明除这两份点名文件外没有任何 spec 被顺带重写
（`omega_gate.py --seal` 会把 `corpus/` 全重写一遍，本件不走那条命令）。
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(HERE))
import omega_gate as g  # noqa: E402
import probe_r14_dict as pr  # noqa: E402

CORPUS = ROOT / "corpus"
NEW_SPEC = CORPUS / "cypy.dict.elements.json"
OLD_SPEC = CORPUS / "cypy.container.elements.json"
# 锚点用**内容**而不是 id：R13 那份语料的案例里没有 id 字段（当时的形状就是 {input, expected|error}），
# 猜一个键名会解出空集，然后把"收紧一条"变成"一条都没动却宣称已收紧"。
DICT_SRC_NEEDLES = ('let x: dict<str, int> = {"a": "b"}',)


def digest(d: Path) -> str:
    return hashlib.sha256(d.read_bytes()).hexdigest()[:16]


def snapshot(exclude) -> dict:
    return {p.name: digest(p) for p in sorted(CORPUS.glob("*.json")) if p.name not in exclude}


def main() -> int:
    bad = []
    # —— 现跑取实得，并与探针声明的栏位对表 ——
    got = {}
    for key, src in pr.SRC.items():
        o = g.execute({"op": "typecheck", "src": src})
        errs = [e for e in o.get("errors", []) if e.strip()]
        got[key] = {"stage": o.get("stage"), "n": len(errs), "errs": errs}
        want_red = key in pr.MUST_RED or key in pr.CTRL_RED
        want_green = key in pr.MUST_GREEN
        if want_red and not errs:
            bad.append(f"{key} 声明该红却静默")
        if want_green and errs:
            bad.append(f"{key} 声明该绿却红：{errs[0][:60]}")
    if bad:
        print(json.dumps(bad, ensure_ascii=False, indent=1))
        raise SystemExit("栏位与实得不一致 ⇒ 不落盘（这一版语料会把坏尺钉成判据）")

    tests = []
    for key in pr.SRC:
        src = pr.SRC[key]
        n, errs = got[key]["n"], got[key]["errs"]
        case = {"input": {"op": "typecheck", "src": src}}
        if n:
            case["error"] = {"errors": n, "contains": [e.strip() for e in errs]}
        else:
            case["expected"] = {"errors": 0}
        tests.append(case)

    before_others = snapshot(exclude={NEW_SPEC.name, OLD_SPEC.name})
    old = json.loads(OLD_SPEC.read_text(encoding="utf-8"))
    old_fp = old["fingerprint"]
    hit = [c for c in old["tests"] if all(n in c["input"]["src"] for n in DICT_SRC_NEEDLES)]
    TIGHT = {"errors": 1, "contains": ["Dict value type mismatch: expected int, got str"]}
    if len(hit) != 1:
        raise SystemExit(f"要收紧的那条案例命中 {len(hit)} 次（期望 1）⇒ 停手，不猜是哪一条")
    target = hit[0]
    if target.get("error") == TIGHT:
        tightened = "skipped（上一版已收紧，本次只重算指纹）"
    elif target.get("expected") == {"errors": 0}:
        target.pop("expected")
        target["error"] = TIGHT
        tightened = "yes"
    else:
        raise SystemExit(f"既不是零诊断也不是目标形状 ⇒ 拒绝改写：{json.dumps(target)[:150]}")
    old["fingerprint"] = g.fnv1a64(g.seal_payload(old))
    OLD_SPEC.write_text(json.dumps(old, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    spec = {
        "op": "cypy.dict.elements",
        "version": 1,
        "preconditions": ["cypyc 可导入", "TypeChecker.check 在 parse 之后运行"],
        "laws": [
            "SYNTAX/02-type-annotations.md「字典字面量的键值位判定（R14 补）」规则 1-6",
            "SYNTAX/02-type-annotations.md「容器元素位判定（R13 补）」规则 3-5（加宽、占位、保守集）",
        ],
        "tests": tests,
    }
    spec["fingerprint"] = g.fnv1a64(g.seal_payload(spec))
    NEW_SPEC.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # —— 落盘后回读复算：两份指纹必须自洽，其余 spec 一字节没动 ——
    after_others = snapshot(exclude={NEW_SPEC.name, OLD_SPEC.name})
    reread_new = json.loads(NEW_SPEC.read_text(encoding="utf-8"))
    reread_old = json.loads(OLD_SPEC.read_text(encoding="utf-8"))
    checks = {
        # 复算必须用**仓库自己的判据公式**（`g.fnv1a64` 自带 `fnv1a64:` 前缀）。
        # 上一版这里也写成了 `"fnv1a64:" + g.fnv1a64(...)` ⇒ 自证与写盘共用同一个错公式，
        # 双前缀指纹一路"合格"落盘，最后是 tests/regression/test_corpus_pairs.py 把它抓出来的。
        "new_fp_selfconsistent": reread_new["fingerprint"] == g.fnv1a64(g.seal_payload(reread_new)),
        "old_fp_selfconsistent": reread_old["fingerprint"] == g.fnv1a64(g.seal_payload(reread_old)),
        # 只有真的收紧了那一条才要求指纹变化；幂等复跑（tightened=skipped）时内容没动，
        # 指纹当然不变 —— 上一版把这条当成无条件门，于是第二次跑自己把自己拦下。
        "old_fp_changed": reread_old["fingerprint"] != old_fp or tightened != "yes",
        # 形状门：双前缀（`fnv1a64:fnv1a64:`）上一版就是靠它才该红 —— 自证与写盘同公式时看不出来。
        "fp_shape_ok": all(
            v["fingerprint"].startswith("fnv1a64:") and v["fingerprint"].count(":") == 1
            for v in (reread_new, reread_old)
        ),
        "old_case_count_kept": len(reread_old["tests"]) == len(old["tests"]),
        "others_untouched": before_others == after_others,
        "drift": [k for k in before_others if before_others[k] != after_others.get(k)],
    }
    if not all(v for k, v in checks.items() if k != "drift"):
        raise SystemExit(f"落盘自证不过：{json.dumps(checks, ensure_ascii=False)}")
    total = sum(
        len(json.loads(p.read_text(encoding="utf-8"))["tests"]) for p in CORPUS.glob("*.json")
    )
    print(
        f"SEALED tightened={tightened} dict cases={len(reread_new['tests'])} "
        f"fp={reread_new['fingerprint']} "
        f"tightened {OLD_SPEC.name} fp {old_fp}->{reread_old['fingerprint']} "
        f"specs={len(list(CORPUS.glob('*.json')))} total_cases={total} "
        f"others_untouched={checks['others_untouched']} drift={checks['drift']} "
        f"bucket_agreement={len(pr.SRC)}/{len(pr.SRC)}"
    )
    print(
        f"CONCLUSION make_corpus_r14 tightened={tightened!r} "
        f"dict_cases={len(reread_new['tests'])} "
        f"dict_fp={reread_new['fingerprint']} container_fp={reread_old['fingerprint']} "
        f"specs_before=7 specs_after={len(list(CORPUS.glob('*.json')))} total_cases={total} "
        f"others_untouched={checks['others_untouched']} drift={len(checks['drift'])}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
