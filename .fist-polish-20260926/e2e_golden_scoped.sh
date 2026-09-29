#!/usr/bin/env bash
# ============================================================================
# scripts/e2e_golden.sh —— Cypy 端到端 golden 外部判据（非 LLM 锚点）
#
# 与 Pentad/Tnr 同构：真跑 cypyc run examples/*.cypy，剥离 CLI 横幅行后
# 与 golden 逐字 diff。语义：PASS/FAIL/RUNFAIL/UNREG/WARN 同 Tnr 版。
# 用法：bash scripts/e2e_golden.sh [--update]
# 退出码：0 = 无 FAIL 且无 RUNFAIL 且无 WARN；1 = 有任一不通过项。
#
# ---------------------------------------------------------------------------
# T0r258.4.2 加固（只变严，不变松；四条结构缺陷的封堵）：
#   LINK-1  cypyc/__main__.py 现在传播 cli.main() 的返回码，因此 `CY run` 的
#           非 0 退出码成为可信信号，RUNFAIL 分支不再只对「进程自己死了」有反应。
#   LINK-2  CLI 的失败横幅 `[FAIL] ...`（含 `[FAIL] Execution failed:`）及其后续
#           诊断行不得再被当成「程序 stdout」：
#             · strip_debug 先把 ANSI 色码归一化，再从第一条行首 `[FAIL] ` 起
#               **截断到 EOF**（run/compile/transpile 的失败分支都是终端输出，
#               横幅之后不可能再有程序 stdout），
#             · 并且只要原始输出里出现该横幅，这条样本直接判 FAIL —— 不做内容比对、
#               --update 也不写盘，杜绝「一次 --update 把 traceback 冻结成 7 份基准」。
#           误伤防护：横幅必须**顶到行首**（允许前置 ANSI 色码）才算命中，判据依据是
#           cypyc/cli.py 里失败横幅全部由 print()/print_error() 以第 0 列输出
#           （`print(f"[FAIL] Execution failed:")`、`print(colored(f"[FAIL] {message}…`），
#           而程序自身 print 的内容若要恰好以 `[FAIL] ` 开头才会被误判；真实输出里
#           带相似文本（缩进/引号内）不受影响。examples/ 实测零命中（见交付）。
#   LINK-3  空 golden / 纯空白 golden 不再算绿：比对通过但内容为空 -> FAIL；
#           --update 时程序输出为空 -> 直接拒绝注册（FAIL），不再产生 1 字节换行基准。
#   LINK-4  末行门控同时看 fail/warn/runfail，UNREG/RUNFAIL 不再是「记录但不失败」。
#   附加强度（全部只减绿集合）：golden 内嵌本机绝对路径（`X:\…` / `/home/…`）判 FAIL，
#           因为这类基准换机器必然失配（此前 7 份 traceback 基准正是如此）。
# ============================================================================
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

UPDATE=0
[ "${1:-}" = "--update" ] && UPDATE=1

# cypyc 经 python -m 调用（源码仓库形态，无独立可执行）
CY() { python -m cypyc "$@"; }

ESC="$(printf '\033')"
# 行首（可有 ANSI 色码前导）的 CLI 失败横幅 —— 用于「判失败」
BANNER_RE="^(${ESC}\[[0-9;]*m)*\[FAIL\][ ]"
# 机器绝对路径：换机器/换目录必然失配，不能作为基准内容。
# 只认 Windows 反斜杠盘符与 POSIX 家目录，**不**认正斜杠 —— 否则会误伤
# 真实程序输出里的 URL（examples/concurrency.cypy 就打印 https://api.example.com/…，
# `[A-Za-z]:[\\/]` 会在 "s:/" 处假报警，实测过）。
ABS_PATH_RE='[A-Za-z]:[\\]|^/home/[^ ]+/|^/Users/[^ ]+/'
# 基准内容本身就是 CLI 失败诊断（第一条非空白行以 `[FAIL] ` 开头）
GOLDEN_BANNER_RE='^[[]FAIL[]] '

# 剥离 cypyc run 自身的横幅/状态行，只留程序真实 stdout。
# 顺序：先去 ANSI 色码（横幅判定要按纯文本匹配）→ 再从第一条行首 [FAIL] 截断
# → 最后逐行剔掉 CLI 状态行。空行剔除规则与旧版 `grep -v '^$'` 一致，不得改。
strip_debug() {
  sed -e "s/${ESC}\[[0-9;]*m//g" | awk '
    /^[[]FAIL] /             { exit }
    /^Running /              { next }
    /^Output directory: /    { next }
    /^\[OK\] Execution successful/ { next }
    /^  Output: /            { next }
    /^============/          { next }
    /^  Cypy Transpiler/     { next }
    /^\[[0-9]+\/3\]/         { next }
    /^\[INFO\]/              { next }
    /^\[OK\] Transpiled successfully/ { next }
    /^\[OK\] Compiled successfully/   { next }
    /^$/                     { next }
    { print }
  '
}

is_deadbeef() {
  local f="$1" sz
  sz=$(wc -c < "$f" 2>/dev/null | tr -d ' ')
  [ "$sz" = "4" ] && [ "$(od -An -tx1 -v "$f" | tr -d ' \n')" = "deadbeef" ]
}

# 纯空白（含空串）判定：只含空格/制表/换行/回车即视为无约束力
is_blank_text() {
  local t
  t="$(printf '%s' "$1" | tr -d '[:space:]')"
  [ -z "$t" ]
}

pass=0; fail=0; runfail=0; warn=0
report=""

for src in examples/subtype_units.cypy; do
  [ -f "$src" ] || continue
  case "$(basename "$src")" in _*) continue ;; esac
  golden="${src%.cypy}.out"
  name="${src#examples/}"

  raw="$(CY run "$src" 2>&1)"
  code=$?
  if [ $code -ne 0 ]; then
    runfail=$((runfail+1))
    err_line=$(printf '%s\n' "$raw" | grep -m1 -i -e 'error' -e 'panic' -e 'Traceback' || echo "(无错误摘要)")
    report="${report}RUNFAIL ${name}  [run exit=${code}] ${err_line}\n"
    continue
  fi

  # LINK-2：退出码 0 但输出里有 CLI 失败横幅 —— 这条样本是坏的，既不比对也不注册
  if printf '%s\n' "$raw" | grep -q -E -e "$BANNER_RE"; then
    fail=$((fail+1))
    diag=$(printf '%s\n' "$raw" | grep -E -m1 -A1 -e "$BANNER_RE" | tail -2 | tr '\n' ' ')
    report="${report}FAIL  ${name}  [CLI 失败诊断混入程序输出，拒绝比对/注册] ${diag}\n"
    continue
  fi

  actual="$(printf '%s\n' "$raw" | strip_debug)"

  if [ "$UPDATE" -eq 1 ]; then
    # LINK-3：空输出不得注册成基准（否则得到一个永远咬不住任何东西的金丝雀）
    if is_blank_text "$actual"; then
      fail=$((fail+1))
      report="${report}FAIL  ${name}  [--update 拒绝：程序输出为空，注册了也没有约束力]\n"
      continue
    fi
    printf '%s\n' "$actual" > "$golden"
    pass=$((pass+1))
    report="${report}GEN   ${name}  -> ${golden}\n"
    continue
  fi

  if [ ! -f "$golden" ]; then
    runfail=$((runfail+1))
    report="${report}UNREG ${name}  [未注册 golden：可运行但无基准，人工审定后 --update 落库]\n"
    continue
  fi
  if is_deadbeef "$golden"; then
    fail=$((fail+1))
    report="${report}FAIL  ${name}  [防伪死码哨兵: ${golden} 是占位文件，不是基准]\n"
    continue
  fi
  # LINK-2 的基准侧：过去被冻结进 golden 的 CLI 失败诊断（第一条非空白行就是 `[FAIL] `）
  if grep -q -m1 -e "$GOLDEN_BANNER_RE" "$golden"; then
    fail=$((fail+1))
    report="${report}FAIL  ${name}  [golden 内容是 CLI 失败诊断而不是程序输出: $(head -1 "$golden")]\n"
    continue
  fi
  # 附加：基准里内嵌本机绝对路径 -> 换机器必然失配，不配当基准
  if grep -q -E -e "$ABS_PATH_RE" "$golden"; then
    leak=$(grep -m1 -E -o -e "$ABS_PATH_RE" "$golden" || true)
    fail=$((fail+1))
    report="${report}FAIL  ${name}  [golden 内嵌机器绝对路径，基准不可移植: ${leak}]\n"
    continue
  fi

  expected="$(cat "$golden")"
  if [ "$actual" = "$expected" ]; then
    # LINK-3：空 / 纯空白 golden 即使「比对通过」也不算绿
    if is_blank_text "$actual"; then
      fail=$((fail+1))
      report="${report}FAIL  ${name}  [golden 为空/纯空白，基准无约束力（run 成功但零输出）]\n"
    else
      pass=$((pass+1))
      report="${report}PASS  ${name}\n"
    fi
  else
    fail=$((fail+1))
    first_diff=$(diff <(printf '%s\n' "$expected") <(printf '%s\n' "$actual") | grep -m1 -e '^< ' -e '^> ' || echo "")
    report="${report}FAIL  ${name}  [输出与 golden 不一致] ${first_diff}\n"
  fi
done

if [ $pass -eq 0 ] && [ $fail -eq 0 ] && [ $runfail -eq 0 ] && [ $warn -eq 0 ]; then
  echo "[e2e-golden] 未发现任何 examples/*.cypy，判据空转——FAIL"
  exit 1
fi

printf '%b' "$report"
echo "[e2e-golden] summary: PASS=${pass} FAIL=${fail} UNREG/RUNFAIL=${runfail} WARN=${warn}"
# LINK-3/LINK-4：不通过项一律拉红（warn 与 runfail 过去只记录不影响退出码）
[ "$fail" -eq 0 ] || exit 1
[ "$runfail" -eq 0 ] || exit 1
[ "$warn" -eq 0 ] || exit 1
exit 0
