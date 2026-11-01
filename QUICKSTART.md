# 快速上手

这是通用翻译的方法、记录结构和检查工具，不限于学术或长篇书籍，也不是接收文件后自动生成合格译稿的翻译服务。实际原始材料、译稿与审校数据始终存放在仓库外。

## 从一份新材料开始

| 顺序 | 需要确定的事 | 使用入口 |
|---|---|---|
| 1 | 来源、用途、读者、源语与目标语、外发许可、目标质量与流程等级 | [项目定位](docs/01_项目定位与边界.md)、[接收表](templates/project-intake.blank.json)、[成本表](templates/cost-sheet.blank.json) |
| 2 | 源文件哈希、结构与原文定位、稳定单元编号 | [生命周期](docs/02_项目生命周期.md)、[数据结构](docs/06_数据模型与目录.md) |
| 3 | 代表性试译、专名风险及独立译审角色 | [译审协作](docs/05_多模型协作.md)、[提示词](templates/translation-prompts.md)、[风格说明](templates/style-guide.blank.json) |
| 4 | 术语、实体、疑难及裁决的作用域 | [术语治理](docs/03_术语与实体治理.md)、[术语模板](templates/term.blank.json) |
| 5 | 按单元或批次生成忠实底稿、独立审校、裁决与目标语编辑 | [质量回归](docs/04_质量控制与回归.md)、[批次清单](templates/batch-list.blank.json) |
| 6 | 全项目检查、适用的格式验收、交付及未决问题 | [排版交付](docs/07_排版与交付.md)、[交付清单](templates/delivery-list.blank.json)、[续接模板](templates/recovery.blank.json) |

空白模板是待填写的记录，不是可通过验收的成品。放行条件逐项核实，不把“运行工具成功”当作“译文已正确”。

流程等级在第 1 步选定。轻量级 10 条规则，用于理解参考或短小、低风险的一次性任务；标准级 25 条，用于审校交付、批量文档或高风险材料；完整级 32 条，用于长篇书籍、多批次长周期项目、C 级发布候选、研究辅助层、内部出版或模型与流程比较。范围或风险扩大时升级。

短文本可在同一任务中完成这些步骤；批量文档按文件和稳定单元定位；长篇书籍另建章节、页码与跨章上下文。无页面的材料使用段落编号或其他稳定定位，不虚构页码。研究辅助、影印保留和印刷规则仅在相应条件满足时适用，不适用项仍须记录理由。

## 先运行虚构示例

要求 Python 3.11 或更高版本。虚拟环境建在仓库外，否则发布检查会把其中文件视为未知文件。在方法库目录运行以下命令，在上一级目录建立并激活虚拟环境。Windows PowerShell：

```powershell
python -m venv ..\tm-venv
..\tm-venv\Scripts\Activate.ps1
```

macOS 或 Linux：

```bash
python3 -m venv ../tm-venv
source ../tm-venv/bin/activate
```

激活后各平台都用 `python`。PowerShell 不允许运行激活脚本时，可不激活，直接用 `..\tm-venv\Scripts\python.exe` 代替下文的 `python`。

```powershell
python -m pip install -r requirements.txt
python -B -m unittest discover -s tests -v
python -B tools/validate_assets.py
python -B tools/check_release.py
```

缺少依赖时，`validate_assets.py`、`make_units.py`、`check_translation.py`、`export_bilingual.py` 和 `sync_registry.py` 只打印一行安装提示，不生成输出文件：`missing_dependency=jsonschema; run: python -m pip install -r requirements.txt`。

`validate_assets.py` 验证注册表和虚构示例的结构与部分状态依赖。`check_release.py` 检查仓库发布白名单、哈希、链接和已知风险模式；出现未知文件即退回检查，不自动删除。

[虚构项目演练](examples/walkthrough.md) 用这些示例记录串起一个标准级小项目的全部步骤。

## 继承规则，不冒充通过

```powershell
python -B tools/sync_registry.py registry/public.registry.json --markdown generated/registry.md --snapshot generated/application.json --project-id DEMO-NEW --phase intake --tier standard
```

输出路径必须尚不存在。快照只包含所选等级的规则，每条规则初始为待核状态，适用性、例外、证据和阶段验收须在私有项目记录。演示输出留在忽略目录，发布检查会把它视为未知文件；演示完成后自行保管到私有项目，不把生成物加入公开清单。

## 切分源文

源文先存为 UTF-8 纯文本或 Markdown，再用切分工具生成单元文件：

```powershell
python -B tools/make_units.py --input examples/units/source.txt --output generated/source.units.json --language en --version demo-source-v1 --prefix UNIT-DEMO --synthetic
```

默认按空行分段，每段一个单元；`--split line` 让每个非空行各成一个单元。后缀为 `.md` 或 `.markdown` 的文件按 Markdown 读取，标题行和围栏代码块各成一个单元，代码块内部不再切分；`--format text` 或 `--format markdown` 可改变读法。编号按出现顺序从“前缀-001”开始，`--prefix` 默认为 `UNIT`；`locator` 记录单元起始行。屏幕只显示单元数、读法、切分方式、最长单元行数和写入状态，不回显文本。示例切出 12 个单元，编号和文本与 [源文单元](examples/units/source.json) 一致，定位则是行号，不是条款编号。

`--language` 和 `--version` 必填；`--role` 默认为 `source`，中转语文本标为 `pivot`。源文以逗号作小数点时加 `--decimal-mark ","`。`--synthetic` 只用于虚构示例。

切分结果存为基线后，编号即固定。之后发现源文错误，另建源层版本并登记差异，不重新切分：多出或少了一处段落分隔，其后的编号就会整体错位，已有译文和记录都对不上。长篇材料按章分别切分，每章用不同前缀，例如 `CH01`。

PDF、Word 等文件先导出为 UTF-8 纯文本，核对缺漏、乱码和断行后再切分。工具只按 UTF-8 读取，有无 BOM 均可，不猜测编码；GBK、UTF-16 等文件通常无法解码。解码失败或输出文件已存在时，屏幕显示 `make_units_failed=` 和错误类别，退出码为 1，不写出文件；参数错误时退出码为 2。段落之间没有空行时，整篇会成为一个单元，`max_unit_lines` 明显偏大；这时补空行，或改用 `--split line`。

译文也可用 `--role target` 切分，但只有段落与源文一一对应时编号才能对齐；否则按源文编号逐条写入译文。

## 对照源文与译文

源文和译文各存一份单元文件，结构见 [units Schema](schemas/units.schema.json)。两份文件使用相同的稳定单元编号，检查器按编号对齐，不靠行号或段落顺序猜测对应关系。

```powershell
python -B tools/check_translation.py --source examples/units/source.json --target examples/units/draft-1.json --glossary examples/term.synthetic.json --glossary examples/entity.synthetic.json --report generated/findings.json
```

屏幕只显示检查项、计数、单元编号、问题代码和相关编号，不回显原文或译文；完整结果写入报告文件，报告与快照一样留在忽略目录。退出码 0 表示已运行的检查未发现问题，1 表示有候选问题，2 表示输入无效、缺少依赖、报告文件已存在或没有任何检查得以运行。不加 `--glossary` 时跳过术语检查，屏幕显示 `skipped=terms:no-glossary`。

示例中 `draft-1` 的退出码为 1，报出 2 条术语发现，都在 `UNIT-DEMO-001`；换成 `draft-2` 时退出码为 0。原命令再次运行会因报告已存在返回 2，须换一个新文件名。运行发布检查前，先把 `generated/` 移出仓库或删除。

检查只作机械比对。“km”译作“公里”、阿拉伯数字“14”写成“十四”，都会报为缺失，是否属于合理改写由人判断；“35,000”写成“3.5万”按同一数值比较，不报缺失。源文和译文都标为 en、zh 或 ja 时，“3.5 million”与“350万”也按同一数值比较。确认的问题另行登记，不把候选发现直接计入问题统计。源文或译文以逗号作小数点时，在单元文件中设置 `decimal_mark`。检查范围与未覆盖的内容见 [质量控制与回归](docs/04_质量控制与回归.md)。

## 导出对照表

审校时可把源文与译文导出为对照表：

```powershell
python -B tools/export_bilingual.py --source examples/units/source.json --target examples/units/draft-2.json --output generated/bilingual.md
```

对照表按单元编号把源文和译文排在同一行，列为编号、定位、源文和译文；行序跟随源文，只在译文中出现的单元排在最后，缺失的一侧留空。输出后缀为 `.md` 或 `.markdown` 时生成 Markdown，为 `.csv` 时生成 CSV，其他后缀须用 `--format` 指定。屏幕只显示行数、对齐数、译文缺失数、译文多出数、格式和写入状态，不回显文本；示例导出 12 行，全部对齐。

Markdown 表格中，`<`、`>`、`&`、`|` 和反斜杠转为字符实体，换行转为 `<br>`，文本不会破坏表格结构。CSV 采用 UTF-8 加 BOM 和 CRLF 换行，每个单元格都加引号；以 `=`、`+`、`-`、`@` 或其全角形式、制表符、回车、换行开头的单元格前加撇号，防止电子表格软件把内容当作公式执行，做法参照 [OWASP 的 CSV 注入说明](https://owasp.org/www-community/attacks/CSV_Injection)。

源文与译文角色颠倒、同一文件内编号重复、输入无效或输出文件已存在时，屏幕显示 `export_failed=` 和错误类别，退出码为 1，不写出文件；参数错误时退出码为 2。

对照表只是阅读副本。审校意见写回单元文件后重新导出，不从对照表反向导入。

限制：在 Excel 等电子表格软件中保存 CSV 后，引号和撇号可能被去掉，再次打开时公式防护已经失效；不要用保存后的文件覆盖导出文件，需要时从单元文件重新导出。Markdown 对照表中，行内代码里的字符实体按原样显示，例如 `&lt;` 不还原为 `<`。

## 哪些事情仍需人完成

来源核实、领域判断、原文忠实度、未决问题裁决、语种专家复核、逐页版式和传播许可均不由这些工具自动完成。模型共识、回译、Schema 验证和字节哈希各有用途，但都不能单独证明翻译质量。
