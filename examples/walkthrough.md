# 虚构项目演练

本文用一个虚构的小项目走一遍标准级流程，说明各条记录在什么时候产生、彼此怎样引用。项目、条款、机构、数字和证据全部为人为编写，只演示方法步骤，不证明任何翻译质量。文中编号与本目录的虚构记录一致。阶段定义见 [生命周期](../docs/02_项目生命周期.md)，三级流程见 [项目定位](../docs/01_项目定位与边界.md)。

## 案例

虚构的北园议事会有一份《共用果园规则》，英文，约 360 词，共 12 条，见 [源文单元](units/source.json)。需求方要求译成中文，供内部完整阅读。用途属于 B 级审校交付，选用标准级流程，适用 25 条规则。每一条作为一个稳定单元，编号为 `UNIT-DEMO-001` 至 `UNIT-DEMO-012`。

## 1. 接收与定级

把 [接收表](../templates/project-intake.blank.json) 复制到私有项目后填写：来源与版本、内部使用范围、保密级别、读者和交付格式，以及需求方书面同意把全文发送给一个已核准的模型服务；其他平台未获授权。

`process_tier` 填 `standard`，`tier_reason` 写明理由：完整阅读交付，条款涉及义务与违约后果；篇幅短、单批完成，不比较模型，不需要完整级的基准对照。同时在 `directory_convention` 中约定目录、命名和版本规则，`cost_record` 从这时开始记录工时与费用。

对应规则：`RIGHTS-001`、`PRIV-001`、`CONTEXT-001`、`FILES-001`、`COST-001`。

## 2. 继承规则

```powershell
python -B tools/sync_registry.py registry/public.registry.json --snapshot generated/orchard-intake.json --project-id DEMO-ORCHARD --phase intake --tier standard
```

快照包含标准级全部 25 条规则，适用性与验收均为 `pending`。继承不等于验收。试译放行、批量翻译启动、格式处理启动和最终交付前各刷新一次。`generated/` 只用于演示，发布检查会把其中文件视为未知文件；实际快照存放在私有项目中。

对应规则：`GOV-001`、`GOV-002`。

## 3. 源层基线

原件只读保存并记录字节哈希，12 条与 12 个稳定单元一一对应。材料没有固定页面，原文定位使用条款编号，不虚构页码。扫描确认全文为英语电子文本，没有非拉丁文字、抽取缺损或表格。`MULTI-001` 照常适用，这份扫描记录就是它的检查证据。

扫描结果和项目用途确定后，由裁决 `DEC-DEMO-002` 把四条条件规则判为不适用：`MULTI-002` 和 `MULTI-003` 因为没有非拉丁文字或平行文本，`QA-003` 因为没有表格，`BENCH-002` 因为本项目不作质量或优劣结论。四条仍留在快照中，各自写明理由、裁决和证据。示例目录每类只收一份记录，`DEC-DEMO-002` 只在本文说明。

对应规则：`SOURCE-001`、`MULTI-001`；不适用：`MULTI-002`、`MULTI-003`、`QA-003`、`BENCH-002`。

## 4. 试译与风格说明

试译选第 1、5、9 条，覆盖定义、义务句和违约后果；第 9 条是本项目唯一的高风险内容。试译同时确认 [风格说明](../templates/style-guide.blank.json) v1：正式书面语域；保留条款编号；“shall”统一译为“应”；机构名首次出现时附源文名称。责任人确认后才扩大到全部 12 条。之后改动风格，须先评估返工范围。

对应规则：`PILOT-001`、`STYLE-001`。

## 5. 术语与实体

- `TERM-DEMO-001`：“shared orchard rule”是作者特定用法，作用域限于本项目。登记候选“共用果园规则”与异译“共享果园规则”。
- `ENT-DEMO-001`：作者称“North Orchard Council”，官方名称为“North Orchard Coordination Council”，核验证据为 `EVID-DEMO-002`。两者按双轨字段分别记录，译文依作者用语。缩写 NOC 登记为变体；碰撞测试确认 12 条中出现的 NOC 都指这一机构，不作无依据的全局替换。

需求方沿用的旧术语表要求全文使用官方名称，与“译文先忠实反映作者用语”冲突。冲突登记后交责任人裁决，不自行选择。裁决前，未定译名保留原文并标记待核。

对应规则：`TERM-001`、`TERM-002`、`TERM-003`、`GOV-004`。

## 6. 底稿与分层审校

主译逐条生成 `demo-draft-1`，只提供与当前条款相关的上下文。主译、忠实度、术语专名、受保护要素和目标语编辑五层分轮记录；审校各层在未继承翻译上下文的新会话中进行。每轮结果先写入文件，更新恢复清单后再轮换会话；新会话只凭恢复清单和规范源续接。

术语审校前，对照检查器按当时仍为候选的 `TERM-DEMO-001` 在第 1 条报出 `term-pending`，只提示待定，不作强制核对。术语专名审校随后发现，第 1 条写入了登记的异译“共享果园规则”，而该术语仍是候选。示范程序把候选状态误当作锁定，登记为 `ISS-DEMO-001`，严重度 `major`。

忠实度审校在第 9 条提出 `possible-modality-shift`：源文对罚款用 shall、对暂停用 may。责任人确认译文已区分“应缴纳”与“可被暂停”，不修改，也不登记问题。

对应规则：`CONTEXT-001`、`REVIEW-001`、`REVIEW-002`、`SESSION-001`。

## 7. 裁决与回归

责任人以 `DEC-DEMO-001` 同时裁决两件事：`TERM-DEMO-001` 锁定为“共用果园规则”；机构名称冲突按作者用语处理，官方名称留在实体记录，首次出现按风格说明附源文名称，不加译注。`ENT-DEMO-001` 的官方名称状态据此记为 `verified`。修复后生成 `demo-draft-2`。

同样的根因可能出现在其他条款，回归 `REG-DEMO-001` 因此覆盖全部 12 条，检查锁定术语、候选译名残留和机构名称。其中的字面核对用对照检查器完成，源文与两版底稿见 [源文单元](units/source.json)、[底稿 1](units/draft-1.json) 和 [底稿 2](units/draft-2.json)：

```powershell
python -B tools/check_translation.py --source examples/units/source.json --target examples/units/draft-1.json --glossary examples/term.synthetic.json --glossary examples/entity.synthetic.json
python -B tools/check_translation.py --source examples/units/source.json --target examples/units/draft-2.json --glossary examples/term.synthetic.json --glossary examples/entity.synthetic.json
```

`demo-draft-1` 报出 2 条候选问题，都在 `UNIT-DEMO-001`，都指向 `TERM-DEMO-001`：`term-missing` 表示锁定译名没有出现，`term-alternate` 表示登记的异译混入，退出码为 1。`demo-draft-2` 没有发现，退出码为 0。没有发现只说明这些机械检查未报错；机构名首次出现是否附源文名称、译文是否忠实，仍由分层审校判断。两方面结果合起来，确认只有第 1 条受影响且已修复。责任人确认后，`ISS-DEMO-001` 关闭。

术语锁定后，`demo-draft-1` 上的 `term-pending` 由这两条发现取代。两条程序发现与第 9 条的模型发现合并为 [发现清单](findings.synthetic.json)，状态都是 `candidate`；`demo-draft-2` 的检查结果是 `REG-DEMO-001` 的证据之一。

对应规则：`GOV-004`、`TERM-001`、`ERROR-001`。

## 8. 质量检查

`QA-DEMO-001` 针对 `demo-draft-2` 给出 `passed`：未关闭的 `critical`、`major` 和未解决高风险均为 0；高风险 1/1、受保护要素 2/2 已核；六类检查各有证据。本例把受保护要素简化为第 5 条的天数和第 9 条的金额，`LAYOUT` 只核条款编号、标题层级和约定格式。`passed` 只表示达到放行门槛，不是准确率结论，也不是传播许可。

对应规则：`TRANS-001`、`QA-001`。

## 9. 交付

交付前再刷新一次快照，结果见 [交付快照](application.synthetic.json)：阶段为 `delivery`，25 条中 21 条适用并通过，4 条依 `DEC-DEMO-002` 不适用。这 4 条的 `acceptance` 也是 `passed`，表示不适用判断本身已经验收。[交付清单](../templates/delivery-list.blank.json) 列出正式文件的版本、责任人、用途、检查状态与字节哈希。

```powershell
python -B tools/validate_assets.py --kind application --file examples/application.synthetic.json
```

这条命令只核对快照与注册表的哈希、版本和规则集合，不核对译文。

对应规则：`GOV-001`、`GOV-002`。

## 10. 过程记录与复盘

- 成本按阶段记入 [成本表](../templates/cost-sheet.blank.json)，汇总工时与模型服务费用；模型费用无法按阶段拆分时，按调用量分摊并注明方法。
- 12 条作为一个批次记入 [批次清单](../templates/batch-list.blank.json)；第 1 条修复并通过回归后，该批次才冻结。
- 每阶段结束盘点新增文件，标为正式、候选、可重生成或待归档，并与恢复清单核对。
- `ISS-DEMO-001` 的修复规则是“成稿译名只能来自锁定条目”。`TERM-001` 已要求区分候选与锁定状态，因此只增加项目级检查，不新增公共规则候选。

对应规则：`COST-001`、`FILES-001`、`ERROR-001`。

## 换成轻量级或完整级

同一材料如果只用于理解参考，或是短小、低风险的一次性任务，可选轻量级，只保留 10 条规则：`GOV-004`、`RIGHTS-001`、`SOURCE-001`、`CONTEXT-001`、`TRANS-001`、`REVIEW-001`、`MULTI-001`、`QA-001`、`BENCH-002`、`PRIV-001`。轻量级可以不做正式试译和风格说明，关键术语直接记在任务记录中；忠实完整、独立忠实度审校、受保护要素全查和外发授权照常执行。范围或风险扩大时升级为标准级，并补齐新增规则的记录。

长篇书籍、多批次长周期项目、C 级发布候选、研究辅助层、内部出版或模型与流程比较，选完整级，共 32 条规则。比标准级多出的 7 条中，1 条为强制，6 条为条件规则，不适用时同样记录理由。
