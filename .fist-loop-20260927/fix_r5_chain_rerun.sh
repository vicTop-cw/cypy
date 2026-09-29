#!/bin/sh
# R5-修复 的重跑链：串行跑，绝不并发两套全量（上一环的教训写在报告 §八 第 10 条）。
# 顺序：等基线跑完 → 锁先行（法②）→ 归属复算（法③）→ 回退矩阵（法④）。
cd /e/IDEProjects/AI/Cypy || exit 1
D=.fist-loop-20260927
LOG=$D/fix_r5_chain_rerun.log
: > "$LOG"
echo "chain start $(date -u +%FT%TZ)" >> "$LOG"

i=0
while [ "$i" -lt 240 ]; do
  if grep -q BASELINES_EXIT "$D/fix_r5_baselines.rerun.out" 2>/dev/null; then
    break
  fi
  sleep 20
  i=$((i + 1))
done
if [ "$i" -ge 240 ]; then
  echo "REFUSE: 等基线超时 80 分钟，链子不接着跑（宁可停下也不并发全量）" >> "$LOG"
  echo "CHAIN_FAILED" >> "$LOG"
  exit 1
fi
echo "baselines finished $(date -u +%FT%TZ)" >> "$LOG"
tail -20 "$D/fix_r5_baselines.rerun.out" >> "$LOG"

run_step() {
  step=$1
  tmo=$2
  echo "== $step start $(date -u +%FT%TZ)" >> "$LOG"
  timeout "$tmo" python -X utf8 "$D/$step" > "$D/chain_$step.out" 2>&1
  code=$?
  echo "== $step exit=$code $(date -u +%FT%TZ)" >> "$LOG"
  tail -24 "$D/chain_$step.out" >> "$LOG"
  return 0
}

run_step fix_r5_locks.py 3600
run_step fix_r5_rc.py 1200
run_step fix_r5_revert.py 5400
echo "CHAIN_DONE $(date -u +%FT%TZ)" >> "$LOG"
