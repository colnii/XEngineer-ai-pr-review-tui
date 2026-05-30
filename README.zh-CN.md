# XEngineer AI PR Review TUI

用于审查 GitHub Pull Request 的终端界面工具。它会抓取 PR 元数据和 diff，结合确定性规则与 AI 分析生成审查报告，并支持导出 Markdown。公开 PR 可匿名审查；私有仓库 PR 需要本机已配置有权限的 GitHub token。

## 快速开始

### 评委零配置演示

评委优先运行内置稳定 demo。这个模式不需要 `OPENAI_API_KEY`、`GITHUB_TOKEN`，
也不依赖实时 GitHub PR：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
xpr-review --judge-demo
```

TUI 会自动填入演示 PR 地址并开始分析，可直接检查产品主链路、报告结构、风险识别、
审查建议和 Markdown 导出。

### 普通本地运行

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
xpr-review
```

如果你的 shell 使用 SOCKS 代理，拉取更新后请重新运行 `pip install -e ".[dev]"`，确保 `socksio` 依赖已安装。

## 当前范围

- 支持公开 GitHub PR，以及已配置 token 且有权限访问的私有 GitHub PR。
- TUI 作为主要入口。
- 基于规则识别稳定风险信号。
- 使用 LLM 生成摘要和审查建议。
- 支持 Markdown 报告导出。
- 支持人工确认后发布 PR 顶层 Conversation 评论。
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

如需改用 DeepSeek：

```bash
export DEEPSEEK_API_KEY="..."
# 可选；默认是 deepseek-v4-flash。
export DEEPSEEK_MODEL="deepseek-v4-pro"
xpr-review
```

如果 GitHub 匿名 API 请求被限流，或需要审查私有仓库 PR，可以提供 GitHub token：

```bash
export GITHUB_TOKEN="$(gh auth token)"
xpr-review --mock-llm
```

也可以使用 `GH_TOKEN`，或先运行 `gh auth login`，让应用通过 `gh auth token` 读取本机登录态。
细粒度 token 至少需要目标仓库的 `Pull requests: read` 或 `Contents: read` 权限。
TUI 不会输入、显示或保存 token。

如需把生成的报告发布为 PR 顶层 Conversation 评论，请先配置 GitHub token，然后在分析
完成后点击 TUI 的 `发布评论` 按钮。第一次点击只进入确认状态，第二次点击才会真正发布。
细粒度 token 需要目标仓库的 `Issues: write` 或 `Pull requests: write` 权限。

同一个写入路径也可以从命令行触发；因为命令行没有 TUI 预览步骤，所以必须显式传入确认参数：

```bash
xpr-review --pr-url "https://github.com/owner/repo/pull/1" --publish-comment --confirm-publish
```

如需本地确定性测试，可以追加 `--mock-llm`，发布 mock 报告正文。

启动后粘贴 PR 地址，例如：

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

当存在 `DEEPSEEK_API_KEY` 时，应用优先使用 DeepSeek；否则在存在 `OPENAI_API_KEY`
时使用 OpenAI。DeepSeek 走 OpenAI-compatible Chat Completions API（兼容 OpenAI
聊天补全格式的接口），默认 `base_url` 是 `https://api.deepseek.com`；只有接入兼容网关时
才需要覆盖 `DEEPSEEK_BASE_URL`。`DEEPSEEK_MODEL` 默认是 `deepseek-v4-flash`。

也可以使用 `--mock-llm` 获得确定性的本地审查输出。评委复现优先使用 `--judge-demo`，
这个路径不需要模型或 GitHub 密钥。

## 上下文策略

应用会把 PR 元数据、规则风险信号和裁剪后的 diff 片段发送给模型。大 PR 会按文件数量和 hunk 长度裁剪，省略文件会在最终报告中列出。

## 限制

- 私有仓库 PR 需要本机 token 具备目标仓库读取权限；权限不足时 GitHub 可能返回 404。
- PR 评论只支持手动发布：TUI 会要求人工确认后，才发布顶层 Conversation 评论。
- 暂不支持行内 review comment，也不支持 approve/request-changes review 状态。
- 没有仓库级语义索引。

## 后续方向

- 发布轻量 npm wrapper，评委可用
  `npx xengineer-pr-review --judge-demo` 启动打包后的 Python 应用。
- GitHub Action 集成。
- 基于相同 Review Core 的 Web UI。
- 支持 PR review 模式，在完成 diff 行号映射后发布可选行内评论。
- 可配置的组织级审查规则。
