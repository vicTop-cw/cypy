import json, sys
sys.path.insert(0, sys.argv[1])
from cypyc.analyzer.type_checker import TypeChecker
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
srcs = json.load(open(sys.argv[2], encoding="utf-8"))
out = {}
for label, src in srcs.items():
    try:
        ast = Parser(list(Lexer(src).tokenize())).parse()
    except ValueError as e:
        # 解析期硬拒是"诊断"而不是"崩"：历轮夹具里九成是这种，混进 crashes 会把尺子读成坏了
        out[label] = {"errors": [], "crash": "", "parse_refused": "ValueError: " + str(e)[:140]}
        continue
    except Exception as e:
        out[label] = {"errors": [], "crash": type(e).__name__ + ": " + str(e)[:140], "parse_refused": ""}
        continue
    tc = TypeChecker()
    try:
        tc.check(ast)
        out[label] = {"errors": list(tc.errors), "crash": "", "parse_refused": ""}
    except Exception as e:
        out[label] = {"errors": [], "crash": "check " + type(e).__name__ + ": " + str(e)[:140],
                      "parse_refused": ""}
json.dump(out, open(sys.argv[3], "w", encoding="utf-8"), ensure_ascii=False)
print("RUNNER tree=" + sys.argv[1] + " sources=" + str(len(out)))
