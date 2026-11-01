# 通用翻译方法与工具

版本：0.7.0，规则注册表仍为 0.4.0。仓库名称：`translation-methods`。许可证：代码采用 MIT，文档、模板和虚构示例采用 CC BY 4.0，详见 [许可证说明](LICENSE.md)。

本库整理可复用的翻译工作流、术语管理、质量控制、译审提示词、记录模板与检查工具，面向一般文档、技术资料、商务文本、文学与学术材料等翻译任务，不限于学术翻译。

短文本、批量文档和长篇书籍按体量、风险与用途选择流程；书籍研究辅助层和印刷交付是特定场景，不是所有项目的必选项。提示词可填写源语与目标语，部分文档以中文译入和书籍处理为例。这些适用场景不代表本库已经对所有语种、文体或文件格式完成效果验证。

规则分轻量、标准、完整三级，逐级累加，分别包含 10、25 和 32 条。流程等级在接收时按用途、体量和风险选定并记录理由；条件规则不适用时标为不适用，并写明理由和裁决，不从快照中删除。

它不是自动翻译产品，不含任何实际项目的原文、译文、页图、翻译记忆、专家意见或模型调用日志。示例全部为人为编写的虚构记录，不用于证明翻译质量。

## 方法入口

首次阅读从 [快速上手](QUICKSTART.md) 开始，再看 [虚构项目演练](examples/walkthrough.md) 中的完整小例，然后按当前阶段查阅下列文档。

- [定位与边界](docs/01_项目定位与边界.md)
- [生命周期与阶段放行](docs/02_项目生命周期.md)
- [术语与实体治理](docs/03_术语与实体治理.md)
- [质量控制与回归](docs/04_质量控制与回归.md)
- [多模型协作](docs/05_多模型协作.md)
- [数据结构与目录](docs/06_数据模型与目录.md)
- [排版与交付](docs/07_排版与交付.md)
- [受控修改与续接](docs/08_受控修改与续接.md)
- [权利、隐私与发布](docs/09_权利隐私与发布.md)
- [技术复盘与失败模式](docs/10_技术复盘与失败模式.md)
- [项目目录整理](docs/11_项目目录整理.md)
- [通用译审提示词](templates/translation-prompts.md)
- 记录模板：[接收表](templates/project-intake.blank.json)、[风格说明](templates/style-guide.blank.json)、[术语](templates/term.blank.json)、[批次清单](templates/batch-list.blank.json)、[成本表](templates/cost-sheet.blank.json)、[交付清单](templates/delivery-list.blank.json)、[续接清单](templates/recovery.blank.json)
- [规则注册表](registry/public.registry.json)
- [第三方参考](REFERENCES.md)

## 工具范围

要求 Python 3.11 或更高版本，结构验证依赖 `jsonschema`。建议先按 [快速上手](QUICKSTART.md) 在仓库外建立虚拟环境；未使用虚拟环境时，macOS 和 Linux 用 `python3` 代替 `python`。`validate_assets.py` 验证记录结构和部分状态约束；`make_units.py` 把 UTF-8 纯文本或 Markdown 切分为单元文件；`check_translation.py` 按稳定单元对照源文与译文，机械检查结构、数字、单位符号、标记和已裁决的术语；`export_bilingual.py` 把源文与译文导出为 Markdown 或 CSV 对照表。工具不能核实权威来源、专家能力或语义正确性，也不能自动授予翻译、传播或调用外部服务的权限。

```powershell
python -m pip install -r requirements.txt
python -B -m unittest discover -s tests -v
python -B tools/validate_assets.py
python -B tools/check_release.py
python -B tools/make_units.py --input examples/units/source.txt --output generated/source.units.json --language en --version demo-source-v1 --prefix UNIT-DEMO --synthetic
python -B tools/check_translation.py --source examples/units/source.json --target examples/units/draft-2.json --glossary examples/term.synthetic.json --glossary examples/entity.synthetic.json
python -B tools/export_bilingual.py --source examples/units/source.json --target examples/units/draft-2.json --output generated/bilingual.md
python -B tools/sync_registry.py registry/public.registry.json --markdown generated/registry.md --snapshot generated/application.json --project-id DEMO-NEW --phase intake --tier standard
```

输出必须是尚不存在的新文件。快照只包含所选流程等级的规则，其中的 `pending` 是“待验收”，不是已通过。对照检查的每条发现都是待人判断的候选问题；没有发现只说明这些机械检查未报错，不表示译文合格。对照表只是阅读副本，修改仍在单元文件中进行。工具不会调用云端翻译服务，也不提供 API 密钥配置。

## 发布边界

发布以逐文件白名单为准，不从私有工作区直接建立公开仓库。发布清单记录本目录的全部交付文件和校验值；清单不包含自身哈希，以免循环计算。审计记录留在私有整理区。

目录只包含通用方法内容，可在本地初始化全新的独立 Git；不得导入任何私有项目的 Git 历史。暂存内容可用 `python -B tools/check_release.py --staged` 核验；该检查不审查完整提交历史，不能用于把旧私有仓库转为公开。

发布和日常更新的步骤见 [发布与更新](PUBLICATION.md)，版本变化见 [更新记录](CHANGELOG.md)，参与修改见 [贡献说明](CONTRIBUTING.md)。推送到 `main` 和每个拉取请求都由 GitHub Actions 在 Ubuntu 和 Windows、Python 3.11、3.14 与 3.15 上重跑测试和检查。本库不声称已建成专家基准集、已实现原书全自动翻译或已优于某个翻译平台。详见 [许可证说明](LICENSE.md)、[许可证状态](LICENSE-STATUS.md) 与 [发布检查表](RELEASE-CHECKLIST.md)。
