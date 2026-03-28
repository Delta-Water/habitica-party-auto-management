import subprocess
import sys

# 按顺序执行多个 Python 脚本，并始终复用当前解释器。
scripts = ["./scripts/manage_members.py", "./scripts/update_description.py"]

for script in scripts:
    print(f"正在执行: {script}")
    result = subprocess.run([sys.executable, script], check=False)

    if result.returncode != 0:
        print(f"警告: {script} 执行可能失败 (退出码: {result.returncode})")

    print(f"{script} 执行完成\n")
