# Bounty Sieve

[![CI](https://github.com/junbuilds96/bounty-sieve/actions/workflows/ci.yml/badge.svg)](https://github.com/junbuilds96/bounty-sieve/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

[English README](README.md)

Bounty Sieve 是一个小型 Python 命令行工具，用来对类似开源悬赏的机会做只读、离线的初步筛选。当前版本是一个离线演示版：它读取项目内置的样例数据，使用确定性的规则打分，并在本地生成 JSON 和 Markdown 文件，方便人工复核。

这个项目的定位不是“自动接单工具”，而是一个透明、可审计的基线：在你打开浏览器、投入时间或开始沟通之前，先把机会质量、收益可信度、竞争风险和安全信号摆到台面上。

## 安全边界

当前版本刻意保持只读和离线。它不会：

- 克隆仓库或检查本地项目代码
- 创建 Pull Request、Issue、评论，或执行其他远程写入操作
- 连接钱包、使用凭据、处理密钥，或接触私人数据
- 给仓库点星，或参与以互动数据为门槛的任务
- 联系维护者或悬赏发布者
- 尝试提取提示词、策略文本、凭据或私有指令

即使悬赏金额很高，只要机会带有不安全、操纵性或越界的要求，Bounty Sieve 都会把它判为拒绝项。

## 安装

需要 Python 3.11 或更新版本。

本地开发安装：

```bash
python -m pip install -e ".[test]"
```

从仓库 checkout 直接运行：

```bash
python -m bounty_sieve --help
```

安装后也可以使用控制台脚本：

```bash
bounty-sieve --help
```

## 快速演示

运行离线演示，生成本地复核文件：

```bash
python -m bounty_sieve demo --out out/demo
```

示例输出：

```text
Wrote offline demo to out/demo
- discovered: out/demo/discovered.json
- scored: out/demo/scored.json
- report: out/demo/report.md
Recommendations: pursue=2, watch=2, reject=3
```

打开 `out/demo/report.md` 可以查看排序后的机会和安全原因。演示只使用项目内置 fixture，不访问网络。

## 使用方式

发现内置样例机会：

```bash
python -m bounty_sieve discover --source fixture --out out/discovered.json
```

对发现结果打分：

```bash
python -m bounty_sieve score out/discovered.json --out out/scored.json
```

生成 Markdown 报告：

```bash
python -m bounty_sieve report out/scored.json --out out/report.md
```

运行完整离线演示：

```bash
python -m bounty_sieve demo --out out/demo
```

安装后的脚本提供同样的命令：

```bash
bounty-sieve demo --out out/demo
```

## 输出文件

`demo` 会在指定目录下写入三个文件：

- `discovered.json`：原始的内置样例机会
- `scored.json`：带推荐结论的确定性打分结果
- `report.md`：供人工阅读和复核的 Markdown 报告

演示生成的输出文件会被 Git 忽略，避免把本地运行结果提交到仓库。

## 打分模型

打分逻辑是确定性的，目标是让读者能够直接审计规则，而不是依赖外部服务或隐藏状态。每个被打分的机会都会包含：

- `reward_estimate_usd`
- `payment_confidence`
- `issue_clarity`
- `repo_activity`
- `competition_risk`
- `complexity_estimate`
- `tech_match`
- `scope_risk`
- `roi_score`
- `recommendation`
- `reasons`

推荐结果只有三类：`pursue`、`watch` 和 `reject`。

- `pursue` 表示样例信号整体较好，值得人工继续核验。
- `watch` 表示机会未必不安全，但存在竞争、复杂度、范围或清晰度方面的明显风险。
- `reject` 表示触及安全边界或操纵性要求，例如密钥、钱包、未知资产、提示词外泄或点星门槛。

`roi_score` 会综合支付可信度、问题清晰度、仓库活跃度、技术匹配、竞争风险、复杂度和范围风险。它只是分诊辅助，不是行动指令。真正开始工作前，仍然需要人工确认付款条款、Issue 状态、维护者活跃度，以及是否已经有人认领或提交了相同工作。

## 样例覆盖

内置 fixture 覆盖了 `pursue`、`watch` 和 `reject` 三类情况：

- 安全的文档 quickstart 改进
- 安全的回归测试任务
- 要求提取提示词或私有指令的任务
- 以给仓库点星为门槛的悬赏
- 涉及未知 token 或钱包交互的任务
- 重复 PR 竞争风险很高的任务
- 范围模糊、复杂度很高的后端任务

## 开发与测试

安装测试依赖：

```bash
python -m pip install -e ".[test]"
```

运行测试：

```bash
pytest
```

查看 CLI 帮助：

```bash
python -m bounty_sieve --help
bounty-sieve --help
```

提交变更前，请不要提交 `out/`、缓存、虚拟环境、日志、本地环境文件、编辑器元数据或 `.omx/` 等生成文件和本地状态。

## 路线图

- 保持离线演示稳定、可审计。
- 增加更多边界情况和安全失败场景的 fixture。
- 增加可选的只读导入格式，用于用户自带 JSON 数据。
- 在引入任何网络访问之前，先明确并文档化连接器边界。
- 改进报告摘要，同时保持输出确定性。

## 非目标

- 自动认领、提交或完成悬赏。
- 钱包、token 或付款自动化。
- 仓库点星、互动数据刷量或批量生成重复 PR。
- 提取提示词、私有数据或处理凭据。
- 在当前离线演示版本中进行网络发现。
- 取代人工判断机会是否仍然有效、是否值得做、是否符合伦理边界。

## 贡献

欢迎围绕文档、fixture、测试覆盖和透明打分规则做改进。贡献时请保持当前项目边界：

- 发现流程默认只读，除非项目先加入经过审查的连接器边界。
- 不要加入会克隆仓库、打开 PR、联系维护者、连接钱包、使用凭据、给仓库点星，或尝试提取提示词/私有数据的代码。
- 保持 fixture 演示离线、确定性、容易审计。
- 修改打分、报告或 CLI 行为时，请同步添加或更新测试。
- 新增文件应适合公开的 MIT 开源仓库。

更多细节见 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [SECURITY.md](SECURITY.md)。

## 许可证

Bounty Sieve 使用 MIT License 发布。详情见 [LICENSE](LICENSE)。
