import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "tmp_r3" / "out"
rows = {}
for name in ("demo.pyx", "demo.c", "setup.py"):
    p = OUT / name
    if p.exists():
        rows[name] = {"bytes": p.stat().st_size,
                      "sha256_12": hashlib.sha256(p.read_bytes()).hexdigest()[:12]}
pyds = sorted(p.name for p in OUT.glob("*.pyd")) + sorted(
    str(p.relative_to(OUT)).replace("\\", "/") for p in OUT.glob("build/**/*.pyd"))
out = {
    "measured_at_local": "2026-09-28 00:08",
    "cmd": "cd .fist-loop-20260927/tmp_r3/out && python -X utf8 setup.py build_ext --inplace",
    "rc": 0,
    "artifacts": rows,
    "pyd_found": pyds,
    "note": "验证 `cypyc transpile --generate-setup` 写出的 setup.py 真能走通编译链"
            "（中间目录 build/ 落在 out/ 下，因为 cwd 在 out/）；本轮不把它做成测试"
            "（需要 MSVC 且墙钟数十秒，属 e2e 档位，交裁决是否入基准）。",
}
(HERE / "fix_r3_setup_build_evidence.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
)
print(json.dumps(out, ensure_ascii=False, indent=1))
