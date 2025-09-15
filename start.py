import subprocess
import sys

# 要执行的脚本列表
scripts = [
    "./habitica-party-auto-management/scripts/manage_members.py",
    "./habitica-party-auto-management/scripts/update_description.py", 
]

python_path = "C:\\Users\\36273\\AppData\\Local\\Programs\\Python\\Python313\\python.exe"  # 替换为你的 Python 可执行文件路径

for script in scripts:
    print(f"正在执行: {script}")
    
    try:
        # 使用 subprocess.run 执行脚本
        result = subprocess.run(
            [python_path, script],  # 使用当前 Python 解释器
            capture_output=True,       # 捕获输出
            text=True,                 # 以文本形式返回输出
            check=True                 # 如果脚本返回非零退出码则抛出异常
        )
        
        # 打印脚本输出
        if result.stdout:
            print("输出:", result.stdout)
            
    except subprocess.CalledProcessError as e:
        print(f"错误: {script} 执行失败")
        print(f"错误信息: {e.stderr}")
        # 可以选择继续执行下一个脚本或中断
        # break  # 取消注释此行以在出错时停止执行
        
    print(f"{script} 执行完成\n")

print("所有脚本执行完毕")