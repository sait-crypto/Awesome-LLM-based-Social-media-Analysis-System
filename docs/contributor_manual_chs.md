[Document Homepage](./../README.md)
# 贡献者使用手册

本手册面向需要向仓库提交论文的贡献者，介绍两种方便的论文提交方式，根据您的使用习惯**二选一**即可：

首先你需要fork本仓库到你的GitHub账号下，然后克隆到本地进行操作，最后提交PR。

**关键文件**（你只需要关注以下文件或文件夹）
- 更新文件：用于提交论文更新，支持json和excel两种格式。以下两个文件用于自动化提交，二选一填写或两个都填均可
    - `submit_template.json`：JSON 更新文件（程序/脚本与 CI 主要使用）。
    - `submit_template.xlsx`：Excel 更新文件（备选，供习惯表格操作的用户使用，请注意清空示例条目）。
- `figures/`：存放引用图片（论文截图、pipeline 图等），更新图片需在 PR 中一并提交。

更新逻辑：填写任意更新文件，引用图片放到正确位置（figures/）后，提交PR。

将有github action自动处理以上三个文件，忽略其他文件的更新，经过各种筛选后将更新文件中内容**自动增量更新到论文列表**

---

## 1 使用“规范化提交GUI”进行提交（👍推荐）
运行`submit.py`以打开GUI界面，不依赖第三方包即可运行（如需加载 Excel 需要 `pandas`）。

运行（在项目根目录、虚拟环境已激活）：

```bash
python submit.py
```
或者运行`SurveyPaperSubmitGUI.exe`文件使用打包版本（有的话）

GUI 推荐流程：
1. 启动后点击“`➕ 添加论文`”，按规范填写表单中各字段。
   - 填写时会进行实时字段验证，**红色背景**代表验证未通过，注意按照悬浮框提示规范填写
   - 字段名后标`*`的是必填字段，除分类字段外，会用**蓝色背景**标明
2. 完成所有论文后，点击“`📤 保存全部论文到文件`”。弹出“另存为”对话框，默认文件名即为自动化提交要求的 `submit_template.json`
3. 如果需要引用图片：建议把图片放到 `figures/` 目录，并在表单中填写对应图片字段（全名或相对路径）。
4. 保存为文件后（更新文件），可以
   - 点击 “`🚀 自动提交PR`”按钮，将自动创建分支（若在主分支）并提交PR（完整版功能）
   - 通过邮件或其他方式将**更新文件**和**引用图片**发给管理者[lixiajie2182712226@gmail.com](mailto:lixiajie2182712226@gmail.com),
   - 手动提交PR

>👍强烈推荐使用特意开发的`One-Click Copy Metadata`插件，从Zotero一键复制论文元数据并填充表单字段，极大简化填写过程。
><br>该插件可以从项目tool文件夹中获取（One-Click Copy Metadata.xpi），或从[GitHub仓库](https://github.com/lxj218218/Awesome-Social-media-LLM-based-Analysis/tree/main/tool)下载。

>使用GUI 的优点：界面易理解，自动规范化字段、验证并提示错误，全自动提交PR，保证不会因为格式问题导致的 PR 被自动拒绝，降低管理者工作量。

---

## 2 手动更新（适合熟悉格式的用户）
1. 在本地打开 `submit_template.xlsx`（或 `submit_template.json`）。
2. 按照项目约定填写字段：确保必填字段（如 `title`、`authors`、`category` 等，在submit_template.xlsx对应字段名单元格为深蓝色）均已正确填写；分类必须使用仓库中 `config/categories_config.py` 中启用的分类 `unique_name`（或 GUI 中选择的显示名），字段具体要求可参照`config/tag_config.py` 。
3. 如果更新或新增图片，请把图片放到 `figures/` 目录并在表格中填写图片路径（建议仅填写文件名或 `figures/<filename>`，脚本会规范化）。
4. 手动或使用规范化提交GUI提交PR，或者发送更新文件和引用图片给管理者[lixiajie2182712226@gmail.com](mailto:lixiajie2182712226@gmail.com),

>提示：若你不熟悉字段规范或担心格式错误，方法一“规范化提交GUI”更推荐。

---
## 其他指导及疑难解答
### PR提交指导

手动 PR 提交流程（命令行）：
>确保已安装`git`，然后终端命令行中复制执行即可

```bash
git checkout -b submit-branch
git add -A
git commit -m "Add N new papers via submit_template"
git push origin submit-branch
# 然后打开 GitHub，创建 Pull Request
```

如果你使用 GUI 的自动提交 PR 功能（仅在开发者允许时启用）：
- GUI 可尝试自动创建分支、提交并推送、更进一步使用 `gh` 或 GitHub API 自动创建 PR。
- 若自动创建失败，GUI 会提供手动创建 PR 的链接与指引。

PR 注意事项：
- 若包含图片，PR 必须包含 `figures/` 的对应文件。

---

### 常见问题与校验规则提示
- 分类必须是启用的 `unique_name` 或在 GUI 中通过下拉选择；错误的分类会导致保存 PR 被阻止。
- DOI 会被自动清洗（移除 URL 前缀与冲突标注）并进行基本格式校验。因此支持带网页前缀的形式
- 论文发布日期不全时，可以直接填有缺省的日期，详见对应tag（date）描述，或gui悬浮框提示
- 若你在某些字段看到“[💥冲突]”之类冲突标注，系统会在验证时忽略该标注以便手动分辨，但建议在最终提交前解决冲突并移除标注。
- 可以为一篇论文设置多个分类，具体操作为点击category字段的`+`和`-`按钮

---

