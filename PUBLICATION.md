# 发布与更新

本方法库在独立目录维护，远端仓库为 GitHub 上的 `oqqoocom-cpu/translation-methods`。暂存、提交、推送和持续集成分别核验，不把其中一步冒称全部完成。

## 更新步骤

1. 修改或新增文件，确认内容只涉及通用方法和虚构示例。
2. 在 [发布清单](release_manifest.json) 中登记每个新增或改动文件的 `path`、`sha256`、`size_bytes`，计算方法见 [贡献说明](CONTRIBUTING.md)。发布新版本时，同步清单的 `version`、README 版本行、`tools/check_translation.py` 的 `VERSION` 和 [更新记录](CHANGELOG.md)。
3. 移出或删除仓库内的 `generated/` 和 `__pycache__/`，然后运行：

   ```powershell
   python -B -m unittest discover -s tests -v
   python -B tools/validate_assets.py
   python -B tools/check_release.py
   git add -A
   python -B tools/check_release.py --staged
   git status --short
   ```

4. 对照 [发布检查表](RELEASE-CHECKLIST.md) 复核后提交并推送。
5. 确认 GitHub Actions 在 Ubuntu 和 Windows、Python 3.11、3.14 与 3.15 上全部通过。

## 发布范围

允许范围以发布清单为准：通用方法文档、Schema、空白模板、纯虚构示例、通用工具及其测试，以及持续集成配置。清单刻意不记录自身哈希。

真实书籍、译稿、来源映射、审计报告、运行缓存、恢复包、字体、密钥和个人路径均不在这个仓库中。不要添加私有 Git 远端、对象库引用或旧提交历史。

许可证范围以 [许可证说明](LICENSE.md) 为准；代码与文档采用不同许可证，发布新文件时必须同步判断其内容类型和适用许可证。不要把“可以看到代码”称为“所有内容都可自由使用”。

## 限制

- 更新哈希不等于审核通过，新增文件需要内容审核。
- 工具不签发发布批准，也不清理未知文件；私有检查记录留在仓库外。
- `check_release.py` 不检查完整 Git 历史，`--staged` 只检查本次暂存快照。这个流程用于全新的独立库，不用于清除旧仓库中的私有历史。后续提交同样需要审查变更与全部历史的发布边界。
