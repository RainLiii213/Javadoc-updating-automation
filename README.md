# JavaDoc Miner

JavaDoc Miner 是一个用于研究 JavaDoc 如何随代码变更更新的 Python 挖掘工具。

它会从 GitHub Java 仓库中遍历 commit 历史，筛选同时修改 Java 代码和 JavaDoc 的提交，并输出实体级样本。这里的“实体级”指一个 JSON 样本对应一个方法、构造器或类，而不是整个 commit。

第一版主要面向 Apache Commons Lang，也可以用于其他 Apache Java 项目。

## 能做什么

工具会自动完成：

1. 从 GitHub URL clone 仓库到 `.cache/repos/`。
2. 遍历 commit 历史，默认只扫最近一部分，也支持全量历史。
3. 只分析 `src/main/java/**/*.java`。
4. 忽略 `src/test/java/`、测试类、Markdown、XML、构建脚本等无关文件。
5. 检测同一个 commit 中是否同时存在 Java 代码变化和 JavaDoc 变化。
6. 解析 JavaDoc，并尽量绑定到对应的方法、构造器或类。
7. 输出一个样本一个 JSON 文件，并生成 `summary.csv`。

## 输出格式

默认输出目录是 `dataset/`：

```text
dataset/
  sample_0001.json
  sample_0002.json
  summary.csv
```

单个样本大致如下：

```json
{
  "repo": "apache/commons-lang",
  "commit_hash": "9abd79314b19676c54eab02d441cfb3051bb2d8c",
  "commit_url": "https://github.com/apache/commons-lang/commit/9abd79314b19676c54eab02d441cfb3051bb2d8c",
  "issue": "#1685",
  "issues": ["#1685"],
  "entity_type": "method",
  "entity_name": "isAsciiNumeric",
  "old_javadoc": "",
  "new_javadoc": "/** ... */",
  "patch": "commit ...",
  "commit_message": "Add CharUtils isHex(int), isAsciiNumeric(int), isOctal(int). (#1685)",
  "change_type": "method_addition",
  "quality": "B"
}
```

## 质量等级

- `A`：方法或类的 API 发生变化，并且 JavaDoc 同步更新。例如方法改名、参数变化、返回类型变化、异常变化。
- `B`：新增方法或新增类，并且新增实体带有 JavaDoc。
- `C`：JavaDoc 和代码都变了，但关系较弱，只能作为低置信候选。

默认只输出 `A` 和 `B`。如果想保留弱相关样本，可以使用 `--min-quality C`。

## 安装

需要：

- Python 3.10 或更高版本
- Git
- 能访问 GitHub 的网络

推荐创建虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

macOS / Linux：

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -e ".[dev]"
```

如果只运行工具，不跑测试，也可以：

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

## 使用

挖掘 Apache Commons Lang 最近一部分历史：

```powershell
.\.venv\Scripts\python.exe -m javadoc_miner mine `
  --repo-url https://github.com/apache/commons-lang `
  --max-commits 200 `
  --max-samples 10 `
  --output-dir dataset
```

安装为可执行命令后，也可以这样运行：

```powershell
javadoc-miner mine `
  --repo-url https://github.com/apache/commons-lang `
  --max-commits 200 `
  --max-samples 10 `
  --output-dir dataset
```

全量扫描：

```powershell
javadoc-miner mine `
  --repo-url https://github.com/apache/commons-lang `
  --full-history `
  --min-quality B `
  --output-dir dataset
```

## 常用参数

- `--repo-url`：目标 GitHub 仓库 URL。
- `--cache-dir`：仓库缓存目录，默认 `.cache/repos`。
- `--output-dir`：样本输出目录，默认 `dataset`。
- `--max-commits`：默认扫描 commit 数上限，默认 `1000`。
- `--max-samples`：默认输出样本数上限，默认 `100`。
- `--full-history`：扫描完整历史。
- `--min-quality A|B|C`：最小质量等级，默认 `B`。
- `--force-refresh`：删除缓存仓库并重新 clone。

## 运行测试

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

当前实现包含针对 issue 提取、路径过滤、JavaDoc 解析、实体对齐、分类、写入器和 CLI 集成流程的测试。

## 实现思路

工具分成两阶段：

1. 粗筛 commit：通过 git patch 判断是否同时存在 JavaDoc 变化和 Java 代码变化。
2. 实体抽取：读取 commit 前后版本的 Java 文件，解析 JavaDoc 块并绑定到紧邻的方法、构造器或类，再按规则分类。

这个实现没有依赖 GitHub API，也没有依赖完整 Java AST parser。原因是第一版的目标是稳定产出可审查样本，先把数据链路跑通。后续如果需要更高精度，可以把 `java_parser.py` 替换为基于 Java parser 的实现。

## 当前限制

- Java 结构识别是启发式解析，不是完整 Java 语法解析。
- 对复杂泛型、多行注解、非常规格式的签名可能漏检。
- 默认遍历 `HEAD` 的 first-parent 历史，偏向主线提交。
- 输出的 `dataset/` 默认不提交到仓库，因为真实数据集可能很大。

## 文档

- 设计文档：`docs/superpowers/specs/2026-06-04-javadoc-miner-design.md`
- 实现计划：`docs/superpowers/plans/2026-06-04-javadoc-miner.md`
