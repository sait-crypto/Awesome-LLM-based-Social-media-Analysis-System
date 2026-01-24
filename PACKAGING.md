如何将 `submit_gui.py` 打包为可执行程序（不包含 PR 功能）

1. 环境准备
- 建议在项目的虚拟环境中操作（已存在 `.venv` 时激活它）。
- 安装 pyinstaller：

```bash
pip install pyinstaller
```

2. 打包命令（Windows）
- 在仓库根目录下运行：

```bash
pyinstaller --noconfirm --onefile --windowed --name SurveyPaperSubmitGUI src/submit_gui.py
```

说明：
- `--onefile` 将生成单文件 exe；
- `--windowed`（或 `-w`）避免弹出控制台窗口；
- 如需包括额外数据或资源，请参考 PyInstaller 文档并使用 `--add-data`。

3. 禁用 PR 功能
- 本工具在运行时会根据运行环境自动决定是否显示“自动提交PR”按钮：
  - 当检测到为打包后的可执行文件（`sys.frozen` 为 True）时，PR 按钮默认被禁用；
  - 也可以通过命令行参数 `--no-pr` 或环境变量 `NO_PR=1` 强制禁用（开发时测试用）。

现在你也可以通过配置文件来控制：在 `config/config.ini` 中新增 `[ui]` 段，设置 `enable_pr = true` 或 `enable_pr = false` 来开启/关闭 PR 功能，程序启动时会读取该值。

4. 运行可执行文件
- 打包完成后，exe 位于 `dist/SubmitGUI.exe`（Windows），直接双击即可运行。
- 启动后使用“保存到更新文件”按钮会弹出另存为对话框，默认文件名为 `submit_template.json`，便于贡献者统一输出格式。

5. 额外说明
- 如果希望在打包后仍然启用 PR（仅用于内部受信环境），可以在运行 exe 时传入 `--no-pr` 的相反逻辑尚未实现；推荐在开发环境运行 `python src/submit_gui.py` 并使用 `--no-pr` 参数测试。

如需我代为生成 `pyinstaller` 打包脚本或 CI 打包配置（GitHub Actions），我可以继续帮你补充。