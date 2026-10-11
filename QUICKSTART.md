# 快速上手

这是通用翻译的方法、记录结构和检查工具，不限于学术或长篇书籍，也不是接收文件后自动生成合格译稿的翻译服务。实际原始材料、译稿与审校数据始终存放在仓库外。

## 从一份新材料开始

| 顺序 | 需要确定的事 | 使用入口 |
|---|---|---|
| 1 | 来源、用途、读者、源语与目标语、外发许可与目标质量 | [项目定位](docs/01_项目定位与边界.md)、[接收表](templates/project-intake.blank.json) |
| 2 | 源文件哈希、结构与原文定位、稳定单元编号 | [生命周期](docs/02_项目生命周期.md)、[数据结构](docs/06_数据模型与目录.md) |
| 3 | 代表性试译、专名风险及独立译审角色 | [译审协作](docs/05_多模型协作.md)、[提示词](templates/translation-prompts.md) |
| 4 | 术语、实体、疑难及裁决的作用域 | [术语治理](docs/03_术语与实体治理.md)、[术语模板](templates/term.blank.json) |
| 5 | 按单元或批次生成忠实底稿、独立审校、裁决与目标语编辑 | [质量回归](docs/04_质量控制与回归.md) |
| 6 | 全项目检查、适用的格式验收、交付及未决问题 | [排版交付](docs/07_排版与交付.md)、[续接模板](templates/recovery.blank.json) |

空白模板是待填写的记录，不是可通过验收的成品。放行条件逐项核实，不把“运行工具成功”当作“译文已正确”。

短文本可在同一任务中完成这些步骤；批量文档按文件和稳定单元定位；长篇书籍另建章节、页码与跨章上下文。无页面的材料使用段落编号或其他稳定定位，不虚构页码。研究辅助、影印保留和印刷规则仅在相应条件满足时适用，不适用项仍须记录理由。

## 先运行虚构示例

要求 Python 3.10 或更高版本；安装依赖后，在方法库目录运行：

```powershell
python -m pip install -r requirements.txt
python -B -m unittest discover -s tests -v
python -B tools/validate_assets.py
python -B tools/check_release.py
```

`validate_assets.py` 验证注册表和虚构示例的结构与部分状态依赖。`check_release.py` 检查仓库发布白名单、哈希、链接和已知风险模式；出现未知文件即退回检查，不自动删除。

## 继承规则，不冒充通过

```powershell
python -B tools/sync_registry.py registry/public.registry.json --markdown generated/registry.md --snapshot generated/application.json --project-id DEMO-NEW --phase intake
```

输出路径必须尚不存在。每条规则初始为待核状态，适用性、例外、证据和阶段验收须在私有项目记录。演示输出留在忽略目录，发布检查会把它视为未知文件；演示完成后自行保管到私有项目，不把生成物加入公开清单。

## 哪些事情仍需人完成

来源核实、领域判断、原文忠实度、未决问题裁决、语种专家复核、逐页版式和传播许可均不由这些工具自动完成。模型共识、回译、Schema 验证和字节哈希各有用途，但都不能单独证明翻译质量。
