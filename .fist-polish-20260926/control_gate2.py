#!/usr/bin/env python3
"""违例对照：证明 verify_gate2.py 真在比对，而不是把 lockproof_head.json 复述一遍。

做法：拿真实的 lockproof_head.log / 当前报告当基准，把 JSON 副本改坏 N 种（每种对应一条
应该被抓住的谎），逐份用 GATE2_JSON 环境变量喂给 verify_gate2.py 跑：
  - 未改坏的副本必须 rc=0（否则对照本身坏了，不产出结论）；
  - 改坏的副本必须 rc!=0，且 RED 明细里出现该变体预先指定的那一句判据关键字。
「rc 非零」本身不算通过——必须命中指名的那条判据，否则就是撞上了别的东西凑数。
"""
import copy
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.stdout.reconfigure(encoding="utf-8")
AUD = os.path.join(HERE, "verify_gate2.py")
REAL = os.path.join(HERE, "lockproof_head.json")
TMP = os.path.join(HERE, "_gate2ctl")
BASE = json.load(open(REAL, encoding="utf-8"))


def run(js_path):
    env = dict(os.environ, GATE2_JSON=js_path, PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, AUD], cwd=HERE, env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    reds = [ln.strip()[4:] for ln in (p.stdout or "").splitlines() if ln.strip().startswith("RED ")]
    return p.returncode, reds, (p.stdout or "") + (p.stderr or "")


def write(name, obj):
    path = os.path.join(TMP, name)
    json.dump(obj, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    return path


def m_collected():
    d = copy.deepcopy(BASE)
    d["collected"] = 23
    return d, "日志解析出的用例数", "把 collected 从 24 改成 23（少收一例）"


def m_summary():
    d = copy.deepcopy(BASE)
    d["summary_line"] = "======================== 24 passed, 0 failed in 0.75s ========================"
    return d, "JSON 汇总行与日志一致", "汇总行谎称 24 passed"


def m_drop_control():
    d = copy.deepcopy(BASE)
    d["controls"] = {}
    return d, "BUG-12 日志重算", "删掉对照声明，拿 GREEN 的对照用例顶数"


def m_forge_unlocked():
    """最硬的一种：把 BUG-3 唯一的红用例整体改口成「对照」，并把 JSON 各行改到自相一致，
    使「JSON 与日志重算一致」那道检查失效，只有门禁②本身（每单 ≥1 条非对照红）能抓住。"""
    d = copy.deepcopy(BASE)
    row = next(r for r in d["rows"] if r["bug"] == "BUG-3")
    case = row["lock_case"]
    d["controls"][case] = "伪称：该用例是缺陷之外的行为对照"
    row["lock_cases"] = 0
    row["red_on_head"] = 0
    row["green_on_head"] = 1
    row["controls_red"] = [case]
    row["detail"] = [{"case": case, "on_head": "FAILED", "role": "control"}]
    row["locks"] = False
    d["no_lock"] = ["BUG-3"]
    return d, "BUG-3 至少 1 条非对照非混因用例在 HEAD 上变红", \
        "把 BUG-3 的红用例改口成对照并把 JSON 改到自洽（只有门禁②判据能抓）"


def m_shadow_twin():
    d = copy.deepcopy(BASE)
    d["module_paths"]["nogil"] = "E:\\IDEProjects\\AI\\Cypy\\cypy_bridge\\nogil.py"
    return d, "身份探针：nogil", "把探针路径换成工作区真身（即「跑了错的副本」那种事故）"


def m_lock_case_green():
    d = copy.deepcopy(BASE)
    row = next(r for r in d["rows"] if r["bug"] == "BUG-12")
    ctl = list(BASE["controls"])[0]
    row["lock_case"] = ctl
    return d, "BUG-12 报告点名的锁死用例", "把点名的锁死用例换成日志里为 PASSED 的那条"


def m_head_commit():
    d = copy.deepcopy(BASE)
    d["head"] = "0000000"
    return d, "正文写明对照基准 commit", "换掉基准 commit（正文里对不上）"


def m_differing_zero():
    d = copy.deepcopy(BASE)
    d["product_py_differing"] = 0
    return d, "正文锚定句的不同 .py 数", "不同的 .py 数写成 0（临时树等于工作区 = 对照空转）"


def m_subtype_claimed_present():
    d = copy.deepcopy(BASE)
    d["subtype_confound_evidence"]["head"]["cypyc/parser/parser.py"] = 23
    return d, "混因依据独立重算", "谎称 HEAD 已含 subtype 特性码（那条红就从混因变成真缺陷）"


VARIANTS = [m_collected, m_summary, m_drop_control, m_forge_unlocked, m_shadow_twin,
            m_lock_case_green, m_head_commit, m_differing_zero, m_subtype_claimed_present]


def main() -> int:
    os.makedirs(TMP, exist_ok=True)
    rows, failures = [], []

    rc, reds, raw = run(REAL)
    rows.append({"variant": "(真实 JSON)", "expect": "rc=0 全项通过", "expect_key": None,
                 "note": "基准：未改动的 JSON 必须让审计器判绿，否则后面所有「抓到了」都不成立",
                 "rc": rc, "reds": reds})
    if rc != 0 or reds:
        print(raw[-2500:])
        sys.exit("[control_gate2] 真实 JSON 都没让 verify_gate2 判绿 —— 对照本身坏了，不产出结论")
    print("[control_gate2] 基准：真实 JSON → rc=0 全项通过")

    for fn in VARIANTS:
        mutated, key, note = fn()
        name = fn.__name__[2:] + ".json"
        path = write(name, mutated)
        rc, reds, raw = run(path)
        hit = [r for r in reds if key in r]
        caught = rc != 0 and bool(hit)
        rows.append({"variant": name[:-5], "expect": f"rc!=0 且 RED 命中「{key}」",
                     "expect_key": key, "note": note, "rc": rc,
                     "reds": reds, "matched": hit, "caught": caught})
        print(f"  {'CAUGHT' if caught else 'MISSED'} {name[:-5]:18s} rc={rc} "
              f"reds={len(reds)} 命中={[h[:34] for h in hit]}")
        if not caught:
            failures.append(name[:-5])
            print("         全部 RED:", reds or "(无)")
            print("         stdout 尾部:", raw[-600:])

    out = {"baseline_rc": rows[0]["rc"], "variants": len(VARIANTS),
           "caught": sum(1 for r in rows if r.get("caught")),
           "missed": failures, "rows": rows}
    json.dump(out, open(os.path.join(HERE, "control_gate2.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    import shutil
    shutil.rmtree(TMP, ignore_errors=False)
    print(f"\n[control_gate2] {out['variants']} 种违例 {out['caught']}/{out['variants']} 被指名抓住；"
          f"未抓住：{failures or '无'}")
    print("[control_gate2] 临时副本目录 _gate2ctl 已删除，control_gate2.json 留存")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
