用 edit 工具（不要用 bash heredoc 或重定向改文件）修改三个文件，各追加一行 print：

1. examples/generic.cypy 末尾追加：print(f"generic add = {result1}")
2. examples/minimal_test.cypy 末尾追加：print("minimal ok")
3. examples/struct.cypy 末尾追加：print("struct ok")

new_syntax_features.cypy 不动。

改完后用 bash 依次运行：
python -m cypyc run examples/generic.cypy
python -m cypyc run examples/minimal_test.cypy
python -m cypyc run examples/struct.cypy
确认三个命令退出码均为 0 且有输出。

禁止 git 命令。完成后每个文件一句话汇报。
