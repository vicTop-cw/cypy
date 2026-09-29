"""R4-寻虫 法 2：成对对照确诊。每条候选要 pos 现象现形 + 同族 ctl 今天行为正确，两档齐全才 CONFIRMED。

为什么 ctl 必须是「同族里今天正确」而不是「随便一条正确程序」：
邻域整体坏掉时（比如分析器对这一带全静默），pos 的「没报错」证明不了是这一条检查缺失，
只能记 UNSURE 不入账。上一轮踩过「把只跑正例的对照当确诊」的坑，所以这里两档都实测、都落原文。
另外把本脚本的观察与 hunt_r4_faces.json 的独立一次跑对照：**两次分类必须一致**，不一致 ⇒ 判据坏了。
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

import hunt_r4_cards as K

HERE = Path(__file__).resolve().parent
OUT = HERE / "hunt_r4_confirm.json"
REFUSE: list = []
CHECKS: list = []


def check(label, got, want, why, ok=None) -> None:
    CHECKS.append({"label": label, "got": got, "want": want, "why": why,
                   "ok": (got == want) if ok is None else bool(ok)})


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    OUT.write_text(json.dumps({"started": started, "refuse": ["未跑完"]}, ensure_ascii=False) + "\n",
                   encoding="utf-8", newline="\n")
    sources = [c["src"] for c in K.CANDIDATES] + [K.CTLS[k][0] for k in sorted(K.CTLS)]
    batch = K.run_batch(sources)
    rows_obs = batch["rows"][:len(K.CANDIDATES)]
    ctl_names = sorted(K.CTLS)
    ctl_obs = {n: o for n, o in zip(ctl_names, batch["rows"][len(K.CANDIDATES):])}

    faces = json.loads((HERE / "hunt_r4_faces.json").read_text(encoding="utf-8"))
    # faces 用的是全名（F1_func_symbol_…），本表用短码（F1）⇒ 先归一，否则两次独立跑永远对不上
    short = lambda f: f.split("_", 1)[0]  # noqa: E731
    face_cands = {f"{short(r['family'])}/{c}": r["family"] for r in faces["rows"] for c in r["candidates"]}
    face_by_case = {f"{short(r['family'])}/{c['case']}": c for r in faces["rows"] for c in r["cases"]}

    rows = []
    for cand, errs in zip(K.CANDIDATES, rows_obs):
        obs = K.observed_kind(errs)
        pos_by_expectation = not K.satisfies(obs, cand["want"])
        pos_ok = K.defect_seen(obs, cand)
        # 两套编码互校只对「报/不报」两档成立；文案形状档的期望取反不等价于正面定义
        # （无错时也满足「not clean_message」），所以只在可比的那批上做，并把可比条数落进证据。
        comparable = cand["kind"] in ("false_positive", "false_negative")
        if comparable and pos_ok != pos_by_expectation:
            REFUSE.append(f"{cand['id']}：两套编码（正面定义 vs 期望取反）不同向 ⇒ 分类器不可信")
        ctl_spec = K.CTLS[cand["ctl"]][1]
        ctl_kind = K.observed_kind(ctl_obs[cand["ctl"]])
        ctl_ok = K.satisfies(ctl_kind, ctl_spec)
        verdict = "CONFIRMED" if pos_ok and ctl_ok else "UNSURE"
        tag = f"{cand['family']}/{cand['case']}"
        agree = (tag in face_cands) == pos_ok
        rows.append({"id": cand["id"], "rc": cand["rc"], "family": cand["family"], "case": cand["case"],
                     "kind": cand["kind"], "phenomenon": cand["phenomenon"],
                     "want": cand["want"], "observed_errors": errs,
                     "pos_phenomenon_visible": pos_ok,
                     "pos_by_expectation_negation": pos_by_expectation, "pos_encodings_comparable": comparable,
                     "ctl": cand["ctl"], "ctl_spec": ctl_spec,
                     "ctl_observed_errors": ctl_obs[cand["ctl"]], "ctl_ok": ctl_ok,
                     "verdict": verdict, "agrees_with_faces_battery": agree,
                     "faces_classification": face_by_case.get(tag, {}).get("candidate")})
        if not agree:
            REFUSE.append(f"{cand['id']} 两次独立跑的结论不一致（本脚本 pos={pos_ok} "
                          f"faces={face_by_case.get(tag, {}).get('candidate')}）⇒ 分类器不可信")
        if "RUNNER-EXC" in " ".join(errs):
            REFUSE.append(f"{cand['id']}：夹具让分析器抛异常 ⇒ 不能算观察")

    confirmed = [r["id"] for r in rows if r["verdict"] == "CONFIRMED"]
    unsure = [r["id"] for r in rows if r["verdict"] != "CONFIRMED"]
    mine = sorted(f"{r['family']}/{r['case']}" for r in rows if r["pos_phenomenon_visible"])
    check("两次独立跑（本脚本 vs faces 电池）对同一批夹具给出同一偏差集合",
          mine, sorted(face_cands), f"faces 侧 {len(face_cands)} 条")
    check("每条候选都有对照，且对照今天行为正确",
          [r["id"] for r in rows if not r["ctl_ok"]], [], "ctl_ok=False")
    check("对照库全部实测过（每键都拿到了观察，含应为空的那条）",
          sorted(ctl_obs), sorted(ctl_names), f"{len(ctl_names)} 条对照")
    check("确诊+未确认 = 候选总数", len(confirmed) + len(unsure), len(K.CANDIDATES), "两栏回加")
    check("确诊集合非空（否则是本判据看不见，不是产品干净）", bool(confirmed), True,
          f"确诊 {len(confirmed)} 条", ok=bool(confirmed))
    check("每个根因至少一条确诊", sorted({r["rc"] for r in rows if r["verdict"] == "CONFIRMED"}),
          sorted({c["rc"] for c in K.CANDIDATES}), "RC 集合两边比")
    doc = {"started": started, "rows": rows, "confirmed": confirmed, "unsure": unsure,
           "confirmed_total": len(confirmed), "unsure_total": len(unsure),
           "by_root_cause": {rc: [r["id"] for r in rows if r["rc"] == rc and r["verdict"] == "CONFIRMED"]
                             for rc in sorted({c["rc"] for c in K.CANDIDATES})},
           "identity": batch["ident"], "ctl_observations": ctl_obs,
           "self_checks": CHECKS, "refuse": [],
           "rule": "pos=现象与『文档声明的语义』不符；ctl=同族里今天行为正确的形状。两档齐全才 CONFIRMED",
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    doc["refuse"] = sorted(set(REFUSE)) + [f"判据自证未过：{c['label']}（实得 {c['got']}）"
                                          for c in CHECKS if not c["ok"]]
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": doc["refuse"], "confirmed": confirmed, "unsure": unsure,
                      "by_root_cause": doc["by_root_cause"],
                      "self_checks": f"{sum(1 for c in CHECKS if c['ok'])}/{len(CHECKS)}",
                      "identity": doc["identity"]}, ensure_ascii=False, indent=1))
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
