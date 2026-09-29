#!/bin/sh
# R5-修复 链子第二段：等第一段（锁/归属/回退）跑完，再串行跑影响面→账面→对账→needle→门禁表→自证→lint。
# 任一步非零就停（后面每一步都读它的件，带病往下跑只会产出一堆假绿）。
cd /e/IDEProjects/AI/Cypy || exit 1
D=.fist-loop-20260927
LOG=$D/fix_r5_chain_phase2.log
: > "$LOG"
echo "phase2 start $(date -u +%FT%TZ)" >> "$LOG"

i=0
while [ "$i" -lt 360 ]; do
  if grep -q "CHAIN_DONE\|CHAIN_FAILED" "$D/fix_r5_chain_rerun.log" 2>/dev/null; then break; fi
  sleep 20
  i=$((i + 1))
done
if [ "$i" -ge 360 ]; then
  echo "REFUSE 等第一段超时 120 分钟" >> "$LOG"
  echo "PHASE2_FAILED" >> "$LOG"
  exit 1
fi
grep -q CHAIN_DONE "$D/fix_r5_chain_rerun.log" || {
  echo "第一段以 CHAIN_FAILED 结束，第二段不起跑" >> "$LOG"
  echo "PHASE2_FAILED" >> "$LOG"
  exit 1
}
echo "phase1 done $(date -u +%FT%TZ)" >> "$LOG"
tail -40 "$D/fix_r5_chain_rerun.log" >> "$LOG"

# 第一段每一步都可能有 refuse（驱动非零退出不代表判据红，判据红写在件里）：
# 这里正面读三件的 refuse，任何一条不为空就不往账面/门禁那一步走。
python -X utf8 - "$D" <<'PY' >> "$LOG" 2>&1
import json, sys
from pathlib import Path
d = Path(sys.argv[1])
bad = []
for name in ("fix_r5_locks.json", "fix_r5_rc.json", "fix_r5_revert.json"):
    p = d / name
    if not p.exists():
        bad.append(f"{name} 不在盘上")
        continue
    doc = json.loads(p.read_text(encoding="utf-8"))
    ref = doc.get("refuse") or []
    if ref:
        bad.append(f"{name} refuse {len(ref)} 条：{ref[:2]}")
    if doc.get("started") == "未跑完":
        bad.append(f"{name} 还是起跑桩")
print("PHASE1_REFUSE " + ("|".join(bad) if bad else "无"))
sys.exit(1 if bad else 0)
PY
guard=$?
if [ "$guard" -ne 0 ]; then
  echo "PHASE2_STOPPED phase1 判据有红，不带病跑账面" >> "$LOG"
  exit 1
fi

step() {
  name=$1
  tmo=$2
  echo "== $name start $(date -u +%FT%TZ)" >> "$LOG"
  timeout "$tmo" python -X utf8 "$D/$name" > "$D/phase2_$name.out" 2>&1
  code=$?
  echo "== $name exit=$code $(date -u +%FT%TZ)" >> "$LOG"
  tail -30 "$D/phase2_$name.out" >> "$LOG"
  if [ "$code" -ne 0 ]; then
    echo "PHASE2_STOPPED_AT $name (exit=$code)" >> "$LOG"
    exit "$code"
  fi
  return 0
}

step fix_r5_impact.py 1800
step fix_r5_ledger.py 3600
step fix_r5_calllog_tally.py 1800
step fix_r5_needles.py 1800
step fix_r5_close_spec.py 1800
step fix_r5_report_spec.py 1800
step fix_r5_self_audit.py 2400
step fix_r5_drivers_lint.py 1800
echo "PHASE2_DONE $(date -u +%FT%TZ)" >> "$LOG"
