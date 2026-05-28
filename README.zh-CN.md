# XEngineer AI PR Review TUI

用于审查公开 GitHub Pull Request 的终端界面工具。它会抓取 PR 元数据和 diff，结合确定性规则与 AI 分析生成审查报告，并支持导出 Markdown。

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
xpr-review
```

如果你的 shell 使用 SOCKS 代理，拉取更新后请重新运行 `pip install -e ".[dev]"`，确保 `socksio` 依赖已安装。

## 当前范围

- 仅支持公开 GitHub PR。
- TUI 作为主要入口。
- 基于规则识别稳定风险信号。
- 使用 LLM 生成摘要和审查建议。
- 支持 Markdown 报告导出。
- 默认中文界面，可切换英文。

## 使用方式

无网络或不想消耗模型额度时，使用 mock LLM：

```bash
xpr-review --mock-llm
```

使用真实模型输出：

```bash
export OPENAI_API_KEY="..."
xpr-review
```

如果 GitHub 匿名 API 请求被限流，可以提供 GitHub token：

```bash
export GITHUB_TOKEN="$(gh auth token)"
xpr-review --mock-llm
```

启动后粘贴公开 PR 地址，例如：

```text
https://github.com/Textualize/textual/pull/1
```

## 语言切换

默认语言是中文。TUI 顶部有 `English` 按钮，点击后切换到英文；英文模式下按钮会变成 `中文`。

也可以从命令行指定语言：

```bash
xpr-review --language zh
xpr-review --language en
```

导出的 `review-report.md` 会使用当前 TUI 语言。

## 架构

- TUI：终端输入、进度展示、报告渲染和导出。
- Review Core：PR URL 解析、diff 解析、规则分析、上下文裁剪、报告聚合。
- Adapters：GitHub HTTP 客户端、LLM 客户端、Markdown 导出器。

## 模型选择

当存在 `OPENAI_API_KEY` 时，应用使用 OpenAI 兼容客户端。也可以使用 `--mock-llm`，这样演示时不需要网络和模型额度。

## 上下文策略

应用会把 PR 元数据、规则风险信号和裁剪后的 diff 片段发送给模型。大 PR 会按文件数量和 hunk 长度裁剪，省略文件会在最终报告中列出。

## 限制

- 仅支持公开 GitHub PR。
- 不会自动在 PR 下发表评论。
- 没有仓库级语义索引。

## 后续方向

- GitHub Action 集成。
- 支持私有仓库 token。
- 基于相同 Review Core 的 Web UI。
- 可配置的组织级审查规则。
