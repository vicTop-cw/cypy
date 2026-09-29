#!/usr/bin/env bash
# R4-打磨 收口链的固定顺序（与 R4-验证 同构）。
# 自证件与收口 spec 互为输入（收口正文引用自证格数，自证有门禁读收口 spec）
# ⇒ 跑「自证 → 收口 spec → 自证 → 收口 spec → 自证」把引用推到不动点。
# 用法：bash polish_r4_chain.sh [close|final]
#   close = lint / audit×3(夹 close_spec×2) / render / render_order
#   final = 终账 tally_final + progress（叶/根收口跑完之后）
set -u
cd /e/IDEProjects/AI/Cypy || exit 9
D=.fist-loop-20260927
PY="python -X utf8"
step() { echo "== $*"; $PY "$@" 2>&1 | tail -25; rc=${PIPESTATUS[0]}; echo "-- rc=$rc"; return $rc; }
soft() { echo "== $* (容忍红)"; $PY "$@" 2>&1 | tail -12; echo "-- rc=${PIPESTATUS[0]}"; }

if [ "${1:-close}" = "close" ]; then
  step "$D/polish_r4_drivers_lint.py" || exit 1
  soft "$D/polish_r4_self_audit.py"
  step "$D/polish_r4_close_spec.py" || exit 2
  soft "$D/polish_r4_self_audit.py"
  step "$D/polish_r4_close_spec.py" || exit 3
  step "$D/polish_r4_self_audit.py" || exit 4
  step "$D/report_kit.py" "$D/report_spec_r4_polish.json" || exit 5
  step "$D/polish_r4_render_order.py" || exit 6
  echo "CHAIN-CLOSE-OK"
else
  step "$D/polish_r4_calllog_tally.py" "polish_r4_calllog_tally_final.json" || exit 7
  step "$D/polish_r4_progress.py" || exit 8
  echo "CHAIN-FINAL-OK"
fi
