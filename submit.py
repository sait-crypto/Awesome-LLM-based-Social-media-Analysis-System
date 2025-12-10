# submit.py
"""
主提交脚本
项目入口3：供外部协作者使用
"""

import os
import sys
import subprocess
import webbrowser
from tkinter import messagebox

def check_dependencies():
    """检查依赖"""
    try:
        import tkinter
        return True
    except ImportError:
        print("错误: 需要tkinter支持")
        print("在Windows/Linux上，tkinter通常已预装")
        print("在macOS上，可能需要安装: brew install python-tk")
        return False

def main():
    """主函数"""
    print("=" * 60)
    print("论文提交系统")
    print("=" * 60)
    print()
    print("功能:")
    print("1. 启动图形界面提交论文")
    print("2. 保存论文到更新文件")
    print("3. 自动提交Pull Request")
    print()
    
    if not check_dependencies():
        sys.exit(1)
    
    # 检查是否在正确的目录
    if not os.path.exists("config"):
        print("错误: 请在项目根目录运行此脚本")
        input("按Enter键退出...")
        sys.exit(1)
    
    # 启动图形界面
    try:
        from scripts.submit_gui import main as gui_main
        gui_main()
    except ImportError as e:
        print(f"错误: 无法导入图形界面模块: {e}")
        print("请确保所有文件都在正确的位置")
        input("按Enter键退出...")
        sys.exit(1)

if __name__ == "__main__":
    main()