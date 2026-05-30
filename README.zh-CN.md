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
- 审查项支持结构化 evidence（证据）：代码文件行号范围和可用的 web 引用 URL。
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

真实模型模式会使用 LangGraph（用于编排 agent 循环的库）驱动审查 agent。在 LLM 审查
阶段，模型可以主动调用只读工具，读取 PR head commit 上的文件，或 grep（按文本/正则搜索）
仓库代码；当模型不再请求工具并返回最终结构化报告时，审查正常结束。若因为工具轮数上限、
工具失败等硬性因素收束，报告会在 warnings 中说明。
最终报告可以保留结构化 evidence，让代码行号和 web 引用跟随风险/建议进入 TUI 和 Markdown，
而不是只停留在模型临时上下文里。

如需启用可选 web search（联网搜索），配置 Tavily：

```bash
export TAVILY_API_KEY="..."
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
- Adapters：GitHub HTTP 客户端、LangGraph LLM agent、Markdown 导出器。

## 第三方依赖与原创功能说明

顶层第三方依赖已在 [pyproject.toml](pyproject.toml) 中声明：

- `textual`：终端 UI 框架。
- `httpx[socks]`：用于 GitHub、模型兼容接口和 Tavily 的 HTTP 请求，并支持可选 SOCKS 代理。
- `openai`：用于 OpenAI 和 DeepSeek Chat Completions 的 OpenAI-compatible 客户端。
- `langgraph`：用于编排 model -> tool -> model 的 agent 审查循环。
- `pydantic`：结构化模型的数据校验支持。
- 开发依赖：`pytest` 用于测试，`ruff` 用于 lint。

外部服务包括 GitHub REST API、可选 OpenAI/DeepSeek 模型 API、可选 Tavily web search。
这些服务均通过本项目代码接入，不包含复制进仓库的第三方功能代码。

本项目原创实现包括 PR URL 解析、unified diff 解析、确定性规则分析、上下文裁剪、报告聚合与导出、
中英文 TUI 展示、人工确认后发布 PR 评论、LangGraph review client 集成、有边界的
`read_file`/`grep_code`/`web_search` 工具行为、GitHub 文件/目录树 adapter、安全限制、fallback warning
以及 fake client 测试体系。第三方库提供基础设施；PR Review 产品流程和工具策略由本仓库实现。

## 模型选择

当存在 `DEEPSEEK_API_KEY` 时，应用优先使用 DeepSeek；否则在存在 `OPENAI_API_KEY`
时使用 OpenAI。DeepSeek 走 OpenAI-compatible Chat Completions API（兼容 OpenAI
聊天补全格式的接口），默认 `base_url` 是 `https://api.deepseek.com`；只有接入兼容网关时
才需要覆盖 `DEEPSEEK_BASE_URL`。`DEEPSEEK_MODEL` 默认是 `deepseek-v4-flash`。

也可以使用 `--mock-llm` 获得确定性的本地审查输出。评委复现优先使用 `--judge-demo`，
这个路径不需要模型或 GitHub 密钥。

## 上下文策略

应用会把 PR 元数据、规则风险信号和 diff 片段发送给模型。适合审查的文件不再按数量裁剪。
prompt 会跳过明显低信号文件，例如 lockfile、生成 bundle、二进制资源和压缩包；过长 hunk 仍会裁剪。
被跳过的文件会在最终报告中列出。

diff hunk 会被索引为变更后的行号范围。`read_file` 和 `grep_code` 会返回带行号的代码上下文；
`web_search` 会返回稳定 ID（例如 `[W1]`）、URL 和 snippet（摘要片段）。模型提示词要求把这些
引用写进风险或建议的 `evidence` 对象；TUI 和 Markdown 导出会在对应审查项下展示这些证据。

配置真实模型后，LangGraph agent 可以按需请求更多上下文：

- `read_file`：读取 PR head commit 上的仓库相对路径文件。
- `grep_code`：在 PR head commit 的审查相关文件中搜索代码。
- `web_search`：仅在配置 `TAVILY_API_KEY` 后搜索公开网页上下文。

## 限制

- 私有仓库 PR 需要本机 token 具备目标仓库读取权限；权限不足时 GitHub 可能返回 404。
- PR 评论只支持手动发布：TUI 会要求人工确认后，才发布顶层 Conversation 评论。
- 暂不支持行内 review comment，也不支持 approve/request-changes review 状态。
- 没有仓库级语义索引。
- 工具调用有轮数和输出限制；如果模型触达限制或工具失败，报告会显示 warning。

## 后续方向

- 发布轻量 npm wrapper，评委可用
  `npx xengineer-pr-review --judge-demo` 启动打包后的 Python 应用。
- GitHub Action 集成。
- 基于相同 Review Core 的 Web UI。
- 支持 PR review 模式，在完成 GitHub 行内评论 position 映射后发布可选行内评论。
- 可配置的组织级审查规则。
