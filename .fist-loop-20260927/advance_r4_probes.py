"""生成 R4-推进 的复现夹具（全部落在 .fist-loop-20260927/advance_r4_probe/，不碰语料与产品）。"""

from pathlib import Path

HERE = Path(__file__).resolve().parent / "advance_r4_probe"

# 逐字取自 SYNTAX/02-type-annotations.md:125-133 的工作例
DOC_NEVER = '''def fatal_error(message: str) -> Never:
    raise RuntimeError(message)

def safe_divide(a: float, b: float) -> float:
    if b == 0:
        fatal_error("Division by zero")
    return a / b
'''
NEVER_MIN = '''def fatal(message: str) -> Never:
    raise ValueError(message)

def main() -> int:
    print("start")
    return 0
'''
NEG_BOGUS = '''def f() -> NeverX:
    return 1
'''
NEG_BOGUS_FN = '''def main() -> int:
    print(repx(1))
    return 0
'''
REPR_OK = '''def main() -> int:
    print(repr(1))
    return 0
'''
OPEN_OK = '''def main() -> int:
    f = open("data.txt", "r")
    return 0
'''
ITER_OK = '''def main() -> int:
    xs = [1, 2]
    it = iter(xs)
    return 0
'''
CHR_NOT_ADDED = '''def main() -> int:
    print(chr(65))
    return 0
'''
HEX_NOT_ADDED = '''def main() -> int:
    print(hex(255))
    return 0
'''
POW_NOT_ADDED = '''def main() -> int:
    print(pow(2, 10))
    return 0
'''
ROUND_NOT_ADDED = '''def main() -> int:
    print(round(3.6))
    return 0
'''
DIVMOD_NOT_ADDED = '''def main() -> int:
    print(divmod(7, 2))
    return 0
'''
BYTES_NOT_ADDED = '''def main() -> int:
    print(bytes(4))
    return 0
'''
PTR_CHAR = '''def allocate_buffer(size: int) -> *char:
    let buffer: *char = malloc(size)
    return buffer
'''
XOR_INFIX = '''def main() -> int:
    let a: int = 0b1010
    let b: int = 0b1100
    print(a ^ b)
    return 0
'''
XOR_AUG = '''def main() -> int:
    let x: int = 1
    x ^= 3
    print(x)
    return 0
'''
LET_REASSIGN = '''let pi: float = 3.14159

def main() -> int:
    pi = 3.14
    print(pi)
    return 0
'''
NEVER_PARAM = '''def needs_never(x: Never) -> int:
    return 1
'''

FILES = {
    "a4_doc_never.cypy": DOC_NEVER, "a4_never_min.cypy": NEVER_MIN,
    "a4_neg_bogus_type.cypy": NEG_BOGUS, "a4_neg_bogus_fn.cypy": NEG_BOGUS_FN,
    "a4_repr_ok.cypy": REPR_OK, "a4_open_ok.cypy": OPEN_OK, "a4_iter_ok.cypy": ITER_OK,
    "a4_chr.cypy": CHR_NOT_ADDED, "a4_hex.cypy": HEX_NOT_ADDED, "a4_pow.cypy": POW_NOT_ADDED,
    "a4_round.cypy": ROUND_NOT_ADDED, "a4_divmod.cypy": DIVMOD_NOT_ADDED,
    "a4_bytes.cypy": BYTES_NOT_ADDED, "a4_ptr_char.cypy": PTR_CHAR,
    "a4_xor.cypy": XOR_INFIX, "a4_xor_aug.cypy": XOR_AUG,
    "a4_let_reassign.cypy": LET_REASSIGN, "a4_never_param.cypy": NEVER_PARAM,
}


def main() -> int:
    for name, body in FILES.items():
        (HERE / name).write_text(body, encoding="utf-8", newline="\n")
    print(len(FILES))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
