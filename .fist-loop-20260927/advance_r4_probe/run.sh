#!/bin/bash
# usage: run.sh file.cypy  [check]
f="$1"; mode="${2:-transpile}"
base=$(basename "$f" .cypy)
out=".fist-loop-20260927/advance_r4_probe/out_$base"
rm -rf "$out"
if [ "$mode" = "check" ]; then
  python -m cypyc transpile "$f" --check-only -o "$out" 2>&1
else
  python -m cypyc transpile "$f" -o "$out" 2>&1
fi
echo "EXIT=$?"
if [ -d "$out" ]; then
  for g in "$out"/*.pyx "$out"/*.pxd; do
    [ -f "$g" ] && { echo "--- $g ---"; cat -n "$g"; }
  done
fi
