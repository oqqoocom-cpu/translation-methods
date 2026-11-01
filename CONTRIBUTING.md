# 贡献说明

## 内容边界

- 只提交通用方法和虚构示例。不提交任何实际项目的原文、译文、术语库、翻译记忆、页面图、模型日志、专家意见、本地路径或密钥，改名、截短或遮盖后也不行。
- 新示例从零编写，记录中写 `"synthetic": true`，编号用 `TERM-DEMO-001` 这类带 `DEMO` 的格式。
- 文档中引用的规则编号必须在 [规则注册表](registry/public.registry.json) 中存在。

## 修改步骤

1. 按 [快速上手](QUICKSTART.md) 在仓库外建立虚拟环境并安装依赖。
2. 在 [发布清单](release_manifest.json) 中登记每个新增或改动文件的 `path`、`sha256` 和 `size_bytes`，删除文件时同步移除其条目，否则持续集成会失败。下面的命令依次打印哈希、字节数和路径，把 `README.md` 换成实际改动的文件：

   ```powershell
   python -c "import hashlib, pathlib, sys; [print(hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_size, p.as_posix()) for p in map(pathlib.Path, sys.argv[1:])]" README.md
   ```

3. 在 [更新记录](CHANGELOG.md) 中写明用户可见的变化。
4. 移出或删除 `generated/` 和 `__pycache__/`，然后运行：

   ```powershell
   python -B -m unittest discover -s tests -v
   python -B tools/validate_assets.py
   python -B tools/check_release.py
   ```

5. 提交拉取请求并说明修改理由和范围。持续集成会在 Ubuntu 和 Windows、Python 3.11、3.14 与 3.15 上重跑这些检查；失败时先修复再合并。

清单哈希只证明文件与清单一致，不证明内容合适；合并前仍须人工审核内容。

## 文件格式

- UTF-8 无 BOM，LF 换行，文件末尾保留换行。
- 允许的类型：`.md`、`.json`、`.py`、`.txt`、`.yml`，以及 `.gitignore` 和 `.gitattributes`。不提交二进制、压缩包、字体或图片。

## 许可

代码采用 MIT，文档、模板、Schema、规则注册表和示例采用 CC BY 4.0，范围见 [许可证说明](LICENSE.md)。
