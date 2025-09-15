import os

# 按顺序执行多个 Python 脚本
scripts = ["./scripts/manage_members.py", "./scripts/update_description.py"]

for script in scripts:
    print(f"正在执行: {script}")
    # 使用 os.system 执行脚本
    exit_code = os.system(f"python {script}")
    
    # 检查执行结果
    if exit_code != 0:
        print(f"警告: {script} 执行可能失败 (退出码: {exit_code})")
    
    print(f"{script} 执行完成\n")