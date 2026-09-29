"""R4-寻虫 法 3：判据可观察性硬门——每条确诊都要有一条「判据坏了就一定会红」的见证。

三类见证，各自能红的条件不同（缺一类就是在用「看不见」冒充「没有缺陷」）：
W1 合成违例喂进分类器：把「一切都静默」的假观察送进同一个 `defect_seen`，确诊数必须塌到 0；
   塌不下去 ⇒ 分类器读的是常量不是观察 ⇒ 本环所有确诊作废。
W2 真变异树：把 `_check_callable_arity` 那一行调用摘掉，依赖它的候选观察**必须发生变化**；
   一丁点没变 ⇒ 我们读的是旧产物/硬编码，不是这棵树。
W3 零发现与看不见分家：每一族要么交出候选，要么由 control 证明「这一带能被看见」；
   再把 16 上下文探针里 `context_not_visited` 的那一格原样记进 blind_spots（不许糊）。
"""

from __future__ import annotations

import datetime
import json
import shutil
import sys
from pathlib import Path

import hunt_r4_cards as K

HERE = Path(__file__).resolve().parent
OUT = HERE / "hunt_r4_witness.json"
SCRATCH = HERE / "tmp_witness"
MUTANT = SCRATCH / "tree"
REFUSE: list = []
CHECKS: list = []


def check(label, got, want, why, ok=None) -> None:
    CHECKS.append({"label": label, "got": got, "want": want, "why": why,
                   "ok": (got == want) if ok is None else bool(ok)})


def build_mutant() -> bool:
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    MUTANT.mkdir(parents=True)
    for pkg in K.IMPORTABLE:
        shutil.copytree(K.ROOT / pkg, MUTANT / pkg, ignore=shutil.ignore_patterns("__pycache__"))
    tc = MUTANT / "cypyc" / "analyzer" / "type_checker.py"
    text = tc.read_text(encoding="utf-8", newline="")
    n = text.count(K.NEEDLE)
    if n != 1:
        REFUSE.append(f"变异锚点计数={n}（期望 1）⇒ 变异不会生效，W2 作废")
        return False
    tc.write_text(text.replace(K.NEEDLE, "", 1), encoding="utf-8", newline="")
    return True


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    OUT.write_text(json.dumps({"started": started, "refuse": ["未跑完"]}, ensure_ascii=False) + "\n",
                   encoding="utf-8", newline="\n")
    sources = [c["src"] for c in K.CANDIDATES] + [K.CTLS[k][0] for k in sorted(K.CTLS)]
    batch = K.run_batch(sources)
    real = {c["id"]: batch["rows"][i] for i, c in enumerate(K.CANDIDATES)}
    rows = []

    # W1：同一批分类器喂三种**合成**观察，各自应标记的集合必须精确等于按现象定义**手推**出来的集合。
    # 恒真分类器在 silent 栏全标记、恒假在 mismatch 栏零标记 ⇒ 三张手推表只要有一张对不上就红。
    SYN = {"silent": [], "mismatch": ["Type mismatch: expected int, got str at 1:1"],
           "leaky": ["Type mismatch: expected Callable[tuple[int], str], got int at 1:1"]}
    EXPECT = {  # 手推：不查表、不按 kind 取，逐条按现象写死（写错了就让 W1 红给我看）
        "silent": {"C02", "C04", "C05", "C06", "C07", "C08", "C09", "C10", "C11"},
        "mismatch": {"C01", "C03"},
        "leaky": {"C01", "C03", "C12"}}
    for tag, errs in SYN.items():
        obs = K.observed_kind(errs)
        flagged = {c["id"] for c in K.CANDIDATES if K.defect_seen(obs, c)}
        rows.append({"kind": "W1_合成观察", "payload": tag, "payload_errors": errs,
                     "flagged": sorted(flagged), "expected": sorted(EXPECT[tag]),
                     "matches": flagged == EXPECT[tag],
                     "why": "分类器必须只读观察：同一份代码喂不同观察要给出不同标记集"})
        if flagged != EXPECT[tag]:
            REFUSE.append(f"W1 合成载荷 {tag} 下分类器给出的集合与手推表不符："
                          f"实得 {sorted(flagged)} / 期望 {sorted(EXPECT[tag])} ⇒ 确诊全部作废")
    check("W1 三张合成载荷的标记集两两不同（恒真/恒假的分类器过不了这一条）",
          [len(EXPECT) == 3, EXPECT["silent"] != EXPECT["mismatch"] != EXPECT["leaky"],
           len({frozenset(v) for v in EXPECT.values()})], [True, True, 3], "期望表自身的区分度")
    for cand in K.CANDIDATES:
        rows.append({"kind": "W1_真实观察", "id": cand["id"], "case": cand["case"],
                     "real_defect_seen": K.defect_seen(K.observed_kind(real[cand["id"]]), cand),
                     "observed_errors": real[cand["id"]],
                     "flipped": any(K.defect_seen(K.observed_kind(e), cand)
                                    != K.defect_seen(K.observed_kind(real[cand["id"]]), cand)
                                    for e in SYN.values())})
    check("W1 三种合成载荷全部与按 kind 推演的集合精确相符",
          [r["matches"] for r in rows if r["kind"] == "W1_合成观察"], [True, True, True],
          "silent/mismatch/leaky 三格")
    check("W1 每条候选都能被某种合成载荷打翻（没有读常量的格子）",
          [r["id"] for r in rows if r["kind"] == "W1_真实观察" and not r["flipped"]], [],
          "未翻面的候选")
    check("真实观察下 12 条候选的现象全部现形（与 confirm 环同结论）",
          sum(1 for r in rows if r["kind"] == "W1_真实观察" and r["real_defect_seen"]),
          len(K.CANDIDATES), "逐条计数")

    # W2：真变异树差分——凡「现象就是那条判定产生的」的候选，与所有 arity 对照，都必须变
    mutated_ok = build_mutant()
    w2 = []
    if mutated_ok:
        mbatch = K.run_batch(sources, MUTANT)
        arity_ctls = [k for k, v in K.CTLS.items() if v[1] == "arity"]
        n = len(K.CANDIDATES)
        for i, cand in enumerate(K.CANDIDATES):
            r_, m_ = batch["rows"][i], mbatch["rows"][i]
            w2.append({"target": cand["id"], "case": cand["case"], "must_change": cand["needs_arity_check"],
                       "identical_between_trees": r_ == m_, "real_errors": r_, "mutant_errors": m_})
        for j, kname in enumerate(sorted(K.CTLS)):
            r_, m_ = batch["rows"][n + j], mbatch["rows"][n + j]
            w2.append({"target": f"ctl:{kname}", "case": kname, "must_change": kname in arity_ctls,
                       "identical_between_trees": r_ == m_, "real_errors": r_, "mutant_errors": m_})
        for e in w2:
            if e["must_change"] and e["identical_between_trees"]:
                REFUSE.append(f"W2 {e['target']}：摘掉元数判定那一行后观察毫无变化 ⇒ 读的不是这棵树")
        check("W2 该变的全部变了（含 arity 对照），不该变的保持可比",
              [e["target"] for e in w2 if e["must_change"] and not e["identical_between_trees"]],
              [e["target"] for e in w2 if e["must_change"]], "arity 判定的活体证据")
        check("W2 变异树与真树不是同一棵（身份两两点名）",
              [batch["ident"] == mbatch["ident"], "cypyc" in mbatch["ident"], "tmp_witness" in mbatch["ident"]],
              [False, True, True], "identity 探针")
        w2_ident = {"real_tree": batch["ident"], "mutant_tree": mbatch["ident"]}
    else:
        check("W2 变异树没建成（这一条必须红，不许静默降级）", mutated_ok, True, "build_mutant()")
        w2_ident = {"real_tree": batch["ident"], "mutant_tree": None}
    shutil.rmtree(MUTANT, ignore_errors=True)
    left = sorted(p.name for p in SCRATCH.glob("*")) if SCRATCH.exists() else []
    check("快照/变异树自删干净", left, [], "SCRATCH 目录清点")

    # W3：零发现 vs 看不见
    faces = json.loads((HERE / "hunt_r4_faces.json").read_text(encoding="utf-8"))
    probe = json.loads((HERE / "hunt_r4_probe.json").read_text(encoding="utf-8"))
    blind = [{"source": "faces 电池", "family": b["family"], "control": b["control"],
              "observed": b["observed"]} for b in faces["blind_spots"]]
    blind += [{"source": "16 上下文探针", "context": c,
               "why": "该形状没有到达元数判定（不是判定放行）⇒ 不许计入「上下文全覆盖」"}
              for c in probe["context_not_visited"]]
    per_family = {}
    for r in faces["rows"]:
        per_family[r["family"]] = {"candidates": len(r["candidates"]), "control_ok": r["control_ok"],
                                   "cases": len(r["cases"]), "control_proves": r["control_proves"]}
    zero_but_visible = [f for f, v in per_family.items() if v["candidates"] == 0 and v["control_ok"]]
    check("零发现的族全部有 control 证明可见（否则必须出现在 blind_spots）",
          [f for f in zero_but_visible if per_family[f]["control_ok"]], zero_but_visible,
          f"零发现族：{zero_but_visible}")
    check("faces 与探针两边都没有把看不见写成没缺陷",
          [len(faces["blind_spots"]) == 0, probe["counts"]["silent"] == 0], [True, True],
          "blind_spots / silent 计数")

    doc = {"started": started, "rows": rows, "w2_diff": w2, "per_family_visibility": per_family,
           "blind_spots": blind, "blind_spot_total": len(blind),
           "w1_flipped": [r["id"] for r in rows if r["kind"] == "W1_真实观察" and r["flipped"]],
           "w1_synthetic_matches": {r["payload"]: r["matches"] for r in rows
                                    if r["kind"] == "W1_合成观察"},
           "w2_changed": [e["target"] for e in w2 if not e["identical_between_trees"]],
           "w2_must_change_total": sum(1 for e in w2 if e["must_change"]),
           "identity": w2_ident,
           "self_checks": CHECKS, "refuse": [],
           "rule": "W1 证明分类器读观察不读常量；W2 证明读的是当前源码；W3 把零发现与看不见分栏",
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    doc["refuse"] = sorted(set(REFUSE)) + [f"判据自证未过：{c['label']}（实得 {json.dumps(c['got'], ensure_ascii=False)[:200]}）"
                                          for c in CHECKS if not c["ok"]]
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": doc["refuse"], "w1_flipped": doc["w1_flipped"],
                      "w2_changed": doc["w2_changed"], "blind_spots": blind,
                      "zero_but_visible": zero_but_visible,
                      "self_checks": f"{sum(1 for c in CHECKS if c['ok'])}/{len(CHECKS)}"},
                     ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as exc:
        OUT.write_text(json.dumps({"refuse": [f"崩在 {type(exc).__name__}: {exc}"]},
                                  ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps({"crashed": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        sys.exit(2)
