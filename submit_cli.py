"""
项目入口3：提交系统主入口
"""
import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import json
import pandas as pd
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), './'))

from scripts.core.config_loader import config_loader
from scripts.utils import read_json_file, read_excel_file, write_json_file, write_excel_file


def check_dependencies():
    """检查依赖是否安装"""
    try:
        import pandas
        import openpyxl
        import requests
        return True
    except ImportError as e:
        print(f"缺少依赖: {e}")
        return False


def install_dependencies():
    """安装依赖"""
    print("正在安装依赖...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", 
                              "pandas", "openpyxl", "requests"])
        print("依赖安装成功")
        return True
    except subprocess.CalledProcessError as e:
        print(f"安装依赖失败: {e}")
        return False


def run_gui():
    """运行图形界面"""
    try:
        from submit_gui import main as gui_main
        gui_main()
    except ImportError as e:
        print(f"导入GUI模块失败: {e}")
        return False
    return True


def check_update_files():
    """检查更新文件是否存在且非空"""
    config = config_loader
    settings = config.settings
    
    update_json_path = settings['paths']['update_json']
    update_excel_path = settings['paths']['update_excel']
    
    json_exists = os.path.exists(update_json_path) and os.path.getsize(update_json_path) > 0
    excel_exists = os.path.exists(update_excel_path) and os.path.getsize(update_excel_path) > 0
    
    return json_exists or excel_exists


def create_pr():
    """创建Pull Request"""
    try:
        # 检查当前分支
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=True
        )
        current_branch = result.stdout.strip()
        
        # 如果当前是main分支，创建新分支
        if current_branch == "main":
            branch_name = f"paper-submission-{pd.Timestamp.now().strftime('%Y%m%d%H%M%S')}"
            subprocess.run(["git", "checkout", "-b", branch_name], check=True)
            print(f"已创建并切换到新分支: {branch_name}")
        else:
            branch_name = current_branch
        
        # 添加更新文件
        config = config_loader
        settings = config.settings
        
        update_files = []
        if os.path.exists(settings['paths']['update_json']):
            update_files.append(settings['paths']['update_json'])
        if os.path.exists(settings['paths']['update_excel']):
            update_files.append(settings['paths']['update_excel'])
        
        if not update_files:
            print("没有找到更新文件")
            return False
        
        for file in update_files:
            subprocess.run(["git", "add", file], check=True)
        
        # 提交更改
        commit_message = "Add paper submission"
        subprocess.run(["git", "commit", "-m", commit_message], check=True)
        
        # 推送到远程
        subprocess.run(["git", "push", "origin", branch_name], check=True)
        
        # 创建PR（需要GitHub CLI）
        try:
            pr_title = "Paper Submission"
            pr_body = "Automated paper submission via submission system"
            
            subprocess.run([
                "gh", "pr", "create",
                "--title", pr_title,
                "--body", pr_body,
                "--base", "main"
            ], check=True)
            
            print("✅ Pull Request已创建")
            return True
            
        except (subprocess.CalledProcessError, FileNotFoundError):
            # 如果没有GitHub CLI，提供手动创建PR的说明
            print("\n" + "="*60)
            print("✅ 更改已提交并推送到远程仓库")
            print("\n请手动创建Pull Request：")
            print(f"1. 访问GitHub仓库")
            print(f"2. 切换到分支: {branch_name}")
            print(f"3. 点击 'Compare & pull request'")
            print(f"4. 填写PR信息并提交")
            print("="*60)
            return True
            
    except subprocess.CalledProcessError as e:
        print(f"Git操作失败: {e}")
        return False
    except Exception as e:
        print(f"创建PR时出错: {e}")
        return False


def main():
    """主函数"""
    print("="*60)
    print("Efficient Reasoning Models 论文提交系统")
    print("="*60)
    
    # 检查依赖
    if not check_dependencies():
        print("\n缺少必要的Python包。")
        response = input("是否自动安装依赖？ (y/n): ")
        if response.lower() == 'y':
            if not install_dependencies():
                print("依赖安装失败，请手动安装：")
                print("pip install pandas openpyxl requests")
                return
        else:
            print("请手动安装依赖：")
            print("pip install pandas openpyxl requests")
            return
    
    # 检查是否是Git仓库
    if not os.path.exists(".git"):
        print("\n⚠️  警告: 当前目录不是Git仓库")
        print("请确保在项目根目录运行此脚本")
        response = input("是否继续？ (y/n): ")
        if response.lower() != 'y':
            return
    
    # 显示菜单
    while True:
        print("\n请选择操作:")
        print("1. 🖥️  打开图形界面提交论文")
        print("2. 📤  直接提交现有更新文件")
        print("3. 📋  查看更新文件状态")
        print("4. 🆘  帮助")
        print("5. 🚪  退出")
        
        choice = input("\n请输入选项 (1-5): ").strip()
        
        if choice == "1":
            # 运行图形界面
            print("\n正在启动图形界面...")
            success = run_gui()
            if not success:
                print("启动图形界面失败")
        
        elif choice == "2":
            # 直接提交更新文件
            if check_update_files():
                print("\n找到更新文件，准备提交...")
                if create_pr():
                    print("\n提交成功！")
                else:
                    print("\n提交失败")
            else:
                print("\n没有找到更新文件")
                print("请先使用图形界面或手动创建更新文件")
        
        elif choice == "3":
            # 查看更新文件状态
            config = config_loader
            settings = config.settings
            
            update_json_path = settings['paths']['update_json']
            update_excel_path = settings['paths']['update_excel']
            
            print("\n更新文件状态:")
            print("-" * 40)
            
            json_exists = os.path.exists(update_json_path)
            excel_exists = os.path.exists(update_excel_path)
            
            if json_exists:
                size = os.path.getsize(update_json_path)
                if size > 0:
                    try:
                        data = read_json_file(update_json_path)
                        paper_count = len(data.get('papers', []))
                        print(f"✅ JSON文件: {update_json_path}")
                        print(f"   大小: {size} 字节")
                        print(f"   包含论文: {paper_count} 篇")
                    except:
                        print(f"⚠️  JSON文件: {update_json_path} (读取失败)")
                else:
                    print(f"📭 JSON文件: {update_json_path} (空文件)")
            else:
                print(f"❌ JSON文件: {update_json_path} (不存在)")
            
            if excel_exists:
                size = os.path.getsize(update_excel_path)
                if size > 0:
                    try:
                        df = read_excel_file(update_excel_path)
                        if df is not None and not df.empty:
                            print(f"✅ Excel文件: {update_excel_path}")
                            print(f"   大小: {size} 字节")
                            print(f"   包含论文: {len(df)} 篇")
                        else:
                            print(f"📭 Excel文件: {update_excel_path} (空文件)")
                    except:
                        print(f"⚠️  Excel文件: {update_excel_path} (读取失败)")
                else:
                    print(f"📭 Excel文件: {update_excel_path} (空文件)")
            else:
                print(f"❌ Excel文件: {update_excel_path} (不存在)")
            
            print("-" * 40)
        
        elif choice == "4":
            # 帮助
            print("\n" + "="*60)
            print("帮助信息")
            print("="*60)
            print("\n提交论文的几种方式:")
            print("1. 使用图形界面 (推荐)")
            print("   - 运行本脚本选择选项1")
            print("   - 在界面中填写论文信息")
            print("   - 保存并提交PR")
            print("\n2. 手动创建更新文件")
            print("   - 编辑 submit_template.json 或 submit_template.xlsx")
            print("   - 运行本脚本选择选项2直接提交")
            print("\n3. 通过GitHub直接提交PR")
            print("   - Fork本仓库")
            print("   - 编辑更新文件")
            print("   - 创建Pull Request")
            print("\n注意事项:")
            print("- 确保填写必填字段 (DOI, 标题, 作者, 分类, 论文链接)")
            print("- DOI和URL格式会自动验证")
            print("- 提交前请仔细检查信息")
            print("="*60)
        
        elif choice == "5":
            print("\n感谢使用，再见！")
            break
        
        else:
            print("\n无效选项，请重新选择")


if __name__ == "__main__":
    main()