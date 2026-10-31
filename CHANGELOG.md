# 更新记录

版本号对应 README 的版本行、发布清单的 `version` 和 `tools/check_translation.py` 的 `VERSION`；规则注册表单独编号。

## 0.6.0

日期：2026-10-31。规则注册表仍为 0.4.0。

- 新增 GitHub Actions 持续集成：推送到 `main` 和每个拉取请求都在 Ubuntu 和 Windows、Python 3.10 与 3.12 上运行测试、结构验证和发布检查。
- 新增 [贡献说明](CONTRIBUTING.md) 和本更新记录。
- 发布检查接受清单内的 `.yml` 文件；`.yaml` 等其他后缀仍被退回。
- 缺少 `jsonschema` 时，`validate_assets.py`、`check_translation.py` 和 `sync_registry.py` 只打印一行安装提示，不再输出报错堆栈；`check_translation.py` 此时的退出码为 2。
- [快速上手](QUICKSTART.md) 补充 Windows、macOS 和 Linux 的虚拟环境命令，虚拟环境建在仓库外。
- 测试改用解析后的真实临时目录：macOS 的默认临时目录位于符号链接 `/var` 之下，而工具按设计拒绝经过链接目录的路径。
- 重排 7 份文档，做法与步骤在前，限制集中在末尾：权利隐私与发布、技术复盘、项目目录整理、发布与更新、发布检查表、许可证状态和第三方参考。
- [发布与更新](PUBLICATION.md) 由首次发布说明改为日常更新流程。[发布检查表](RELEASE-CHECKLIST.md) 改为勾选格式，新增版本一致性、暂存检查和持续集成三项；用户确认目标仓库、可见性和范围改在首次发布或范围变化时进行。
- [许可证说明](LICENSE.md) 写明 `.github/` 中的持续集成配置采用 MIT，`CHANGELOG.md` 和 `CONTRIBUTING.md` 采用 CC BY 4.0。
- 测试从 125 项增至 128 项。

## 0.5.0

日期：2026-10-30。提交：`f6d1886`、`e9b3598`。

- 新增 `tools/check_translation.py`：按稳定单元编号对齐源文与译文，机械检查结构、数字、单位符号、标记和已裁决术语；每条发现都是待人判断的候选问题。
- 新增 units 和 findings 两个 Schema、`examples/units/` 中的单元示例和 [发现清单示例](examples/findings.synthetic.json)。
- 新增风格说明、批次清单、成本表和交付清单 4 个模板。
- [译审提示词](templates/translation-prompts.md) 新增统一输出格式、术语抽取和风格试写三节，输出按 Schema 格式。
- [质量控制与回归](docs/04_质量控制与回归.md) 新增“程序检查”一节。
- 测试从 83 项增至 125 项。

## 0.4.0

日期：2026-10-30。提交：`c7555dc`。

- 规则注册表升至 0.4.0：共 32 条，其中强制 22 条、适用时强制 10 条；新增 STYLE-001、SESSION-001、REVIEW-002、FILES-001、COST-001。哈希见 [规则表](registry/public.registry.md)。
- 流程分轻量、标准、完整三级，逐级累加 10、25、32 条规则；规则快照新增 `process_tier`，`sync_registry.py` 生成快照时必须指定 `--tier`。
- 术语与实体的 `candidate_zh` 改为 `target_language` 加 `candidate_target`，不再限定中文译入。
- [接收表](templates/project-intake.blank.json) 新增 `directory_convention` 和 `cost_record`。
- 发布检查的风险模式改用 ASCII 前后断言，能识别紧接中文书写的路径和编号。
- 发布清单由 `release_manifest_v0.3.json` 改名为 `release_manifest.json`；新增 [虚构项目演练](examples/walkthrough.md)。
- 测试从 66 项增至 83 项。

## 0.3.1

日期：2026-10-11。提交：`e7fd807`。

- 采用双许可证：代码采用 MIT，文档、模板和虚构示例采用 CC BY 4.0；新增 [许可证说明](LICENSE.md) 和 `LICENSES/`。
- 测试从 65 项增至 66 项。

## 0.3.0

日期：2026-10-11。提交：`ba3a02f`。

- 首次发布：方法文档、规则注册表 0.3.0-draft 共 27 条规则、Schema、空白模板、虚构示例，以及 `validate_assets.py`、`sync_registry.py`、`check_release.py` 三个工具。
- 65 项测试。
- 发布时未附开源许可证。
