# XEngineer AI PR Review TUI

用于审查 GitHub Pull Request 的终端界面工具。它会抓取 PR 元数据和 diff，结合确定性规则与 AI 分析生成审查报告，并支持导出 Markdown。公开 PR 可匿名审查；私有仓库 PR 需要本机已配置有权限的 GitHub token。

## 快速开始

### 评委零配置演示

评委优先运行内置稳定 demo。这个模式不需要 `OPENAI_API_KEY`、`GITHUB_TOKEN`，
也不依赖实时 GitHub PR：

```bash
# 需要 Node.js 18+ 和 Python 3.12+。
npx xengineer-pr-review --judge-demo
```

TUI 会自动填入演示 PR 地址并开始分析，可直接检查产品主链路、报告结构、风险识别、
审查建议和 Markdown 导出。
如果是在 npm 包发布前从本仓库 checkout 里运行，用 `npx . --judge-demo`。
演示视频：[Bilibili](https://www.bilibili.com/video/BV1eTVQ6iEEN/)。

### 普通本地运行

```bash
cp .env.example .env
# 编辑 .env，填写 DEEPSEEK_API_KEY 或 OPENAI_API_KEY。
npx xengineer-pr-review
```

npm wrapper 会在用户缓存目录里自动创建并复用内部 Python virtualenv（虚拟环境），
然后运行现有 Python CLI。如果没有自动找到 Python 3.12+，可以设置
`XENGINEER_PYTHON=/path/to/python`。

如果是贡献者开发，仍然可以使用 Python console script（命令行入口）：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
xpr-review
```

如果你的 shell 使用 SOCKS 代理，开发模式下拉取更新后请重新运行
`pip install -e ".[dev]"`，确保 `socksio` 依赖已安装。

## 当前范围

- 支持公开 GitHub PR，以及已配置 token 且有权限访问的私有 GitHub PR。
- TUI 作为主要入口。
- npm/npx wrapper 隐藏手动 virtualenv 配置，普通用户可一条命令启动。
- 基于规则识别稳定风险信号。
- 使用 LLM 生成摘要和审查建议。
- 会把 PR Conversation 评论、review 正文、行内 review comment、timeline 事件和 commit message
  纳入审查上下文。
- 审查项支持结构化 evidence（证据）：代码文件行号范围和可用的 web 引用 URL。
- 支持 Markdown 报告导出。
- 支持人工确认后发布 PR 顶层 Conversation 评论，也可选择发布为 PR review 正文。
- 支持作为 GitHub Action 集成到其他仓库，在 PR 创建、重新打开、标记 ready for review，
  或有人在 PR 页面评论 `/xengineer review` 后发布一条 PR 评论。
- 默认中文界面，可切换英文。

## 使用方式

配置真实模型 key 后，如果希望完全在命令行里分析 PR，不打开 TUI，可以传入 PR URL 和输出目标。
`--output -` 会把 Markdown 报告打印到 stdout（标准输出，终端文本流），传入文件路径
则会写入报告文件：

```bash
npx xengineer-pr-review --pr-url "https://github.com/owner/repo/pull/1" --output -
npx xengineer-pr-review --pr-url "https://github.com/owner/repo/pull/1" --output review-report.md
```

评委零配置 demo 也支持同样的无界面命令行路径：

```bash
npx xengineer-pr-review --judge-demo --output -
```

使用真实模型输出：

```bash
cp .env.example .env
# 编辑 .env，填写 OPENAI_API_KEY。
npx xengineer-pr-review
```

如需改用 DeepSeek：

```bash
# 编辑 .env，填写 DEEPSEEK_API_KEY。
# 可选；DEEPSEEK_MODEL 默认是 deepseek-v4-flash。
npx xengineer-pr-review
```

真实模型模式会使用 LangGraph（用于编排 agent 循环的库）驱动审查 agent。在 LLM 审查
阶段，模型可以主动调用只读工具，读取 PR head commit 上的文件，或 grep（按文本/正则搜索）
仓库代码；当模型不再请求工具并返回最终结构化报告时，审查正常结束。若因为工具轮数上限、
工具失败等硬性因素收束，报告会在 warnings 中说明。
最终报告可以保留结构化 evidence，让代码行号和 web 引用跟随风险/建议进入 TUI 和 Markdown，
而不是只停留在模型临时上下文里。

如需启用可选 web search（联网搜索），配置 Tavily：

```bash
# 编辑 .env，填写 TAVILY_API_KEY。
npx xengineer-pr-review
```

如果 GitHub 匿名 API 请求被限流，或需要审查私有仓库 PR，可以提供 GitHub token：

```bash
# 编辑 .env，填写 GITHUB_TOKEN；或者继续使用 gh auth login。
npx xengineer-pr-review
```

也可以使用 `GH_TOKEN`，或先运行 `gh auth login`，让应用通过 `gh auth token` 读取本机登录态。
细粒度 token 至少需要目标仓库的 `Pull requests: read` 或 `Contents: read` 权限。
TUI 不会输入、显示或保存 token。

如需把生成的报告发布为 PR 顶层 Conversation 评论，请先配置 GitHub token，然后在分析
完成后点击 TUI 的 `发布评论` 按钮。TUI 里也可以把发布目标切到 `PR Review`，并用
`行内评论：开` 把带行号证据的 AI 发现挂到代码行上。第一次点击只进入确认状态，第二次点击
才会真正发布。Conversation 评论需要 `Issues: write`，PR review 需要
`Pull requests: write`。

同一个写入路径也可以从命令行触发；因为命令行没有 TUI 预览步骤，所以必须显式传入确认参数：

```bash
npx xengineer-pr-review --pr-url "https://github.com/owner/repo/pull/1" --publish-comment --confirm-publish
```

如果要把同一份 Markdown 报告发布成 PR review 正文，使用 review 模式：

```bash
npx xengineer-pr-review --pr-url "https://github.com/owner/repo/pull/1" --publish-comment --comment-mode review --confirm-publish
```

如果还要把带代码行号证据的 AI 风险或建议发布成行内评论，在 review 模式追加
`--inline-comments`。自动行内评论会挂到 GitHub diff 的 RIGHT 侧，也就是新增、修改或上下文行；
暂不自动推断删除行的 LEFT 侧映射。

```bash
xpr-review --pr-url "https://github.com/owner/repo/pull/1" --publish-comment --comment-mode review --inline-comments --confirm-publish
```

review 模式默认提交不阻塞合并的 `COMMENT` review。如果确认要提交批准或阻塞式修改请求，
再显式追加 `--review-action approve` 或 `--review-action request-changes`。这两个动作可能影响
启用了 review 门禁的仓库是否可合并，所以默认保持 comment。review 模式需要 `Pull requests: write`
权限；Conversation 评论模式需要 `Issues: write`。严格 token 配置下，如果 review 模式也要把
PR Conversation 历史纳入分析上下文，还需要 `Issues: read`。

在 CI 等非交互式自动化环境里，可以用 `--auto-publish` 代替 `--confirm-publish`，
让“自动发布”的意图更清楚。

### GitHub Actions 集成

如果希望其他 GitHub 仓库在 PR 后自动调用 XEngineer，在目标仓库新增
`.github/workflows/xengineer-pr-review.yml`：

```yaml
name: XEngineer PR Review

on:
  pull_request:
    types: [opened, reopened, ready_for_review]
  issue_comment:
    types: [created]

permissions:
  contents: read
  issues: write
  pull-requests: write

jobs:
  review:
    runs-on: ubuntu-latest
    if: >-
      ${{
        (github.event_name == 'pull_request' && !github.event.pull_request.draft) ||
        (
          github.event_name == 'issue_comment' &&
          github.event.issue.pull_request != null &&
          (
            github.event.comment.author_association == 'OWNER' ||
            github.event.comment.author_association == 'MEMBER' ||
            github.event.comment.author_association == 'COLLABORATOR'
          ) &&
          contains(github.event.comment.body, '/xengineer review')
        )
      }}
    steps:
      - name: Run XEngineer PR review
        uses: colnii/XEngineer-ai-pr-review-tui@v1
        with:
          pr-url: ${{ github.event.pull_request.html_url || format('https://github.com/{0}/pull/{1}', github.repository, github.event.issue.number) }}
          github-token: ${{ github.token }}
          comment-mode: conversation
          review-action: comment
          inline-comments: false
          language: zh
          deepseek-api-key: ${{ secrets.DEEPSEEK_API_KEY }}
          openai-api-key: ${{ secrets.OPENAI_API_KEY }}
          tavily-api-key: ${{ secrets.TAVILY_API_KEY }}
```

默认 workflow 会在 PR 创建、重新打开、从 draft 变成 ready for review，或有人在 PR 页面评论
`/xengineer review` 且该评论者是 owner、member 或 collaborator 时发一条新的 PR Conversation 评论；如需发布为 PR review 正文，设置
`comment-mode: review`。`review-action` 默认是 `comment`，也可以显式设为 `approve` 或
`request-changes`，用于需要进入合并门禁的 workflow。如果同时设置
`inline-comments: true` 和 `comment-mode: review`，会把带行号证据的 AI 发现发布到代码行。
Conversation 评论模式需要保留 `issues: write` 权限；使用 review 模式时保留
`issues: read` 读取 PR Conversation 历史，并保留 `pull-requests: write` 发布 review 正文。
它不会编辑旧评论，也不会在每次 push 新 commit 时重复触发，除非有人再次
发送这个命令评论。
如需真实模型输出，请在目标仓库配置 `DEEPSEEK_API_KEY` 或 `OPENAI_API_KEY` secret；
没有模型 key 时，Action 会失败且不会发布审查结果。

也可以不用手写 YAML，直接用 npx 生成同样的 workflow：

```bash
npx xengineer-pr-review init-action --repo-path /path/to/target/repo
```

如果命令就在目标仓库里执行，可以省略 `--repo-path`。如果要生成发布 PR review 正文的
workflow，使用 `--comment-mode review`；如果要选择 review 状态，使用
`--review-action comment|approve|request-changes`；如果要启用行内 AI review 评论，使用
`--inline-comments`。如果要指向 fork、分支或发布版本，用 `--action-uses owner/repo@ref`；
只有确认要替换已有文件时才加 `--overwrite`。

启动后粘贴 PR 地址，例如：

```text
https://github.com/Textualize/textual/pull/1
```

## 语言切换

默认语言是中文。TUI 顶部有 `English` 按钮，点击后切换到英文；英文模式下按钮会变成 `中文`。

也可以从命令行指定语言：

```bash
npx xengineer-pr-review --language zh
npx xengineer-pr-review --language en
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
- npm wrapper 运行时：Node.js 18+，没有 npm runtime dependency（运行时依赖包）。

外部服务包括 GitHub REST API、可选 OpenAI/DeepSeek 模型 API、可选 Tavily web search。
这些服务均通过本项目代码接入，不包含复制进仓库的第三方功能代码。

本项目原创实现包括 PR URL 解析、unified diff 解析、确定性规则分析、上下文裁剪、报告聚合与导出、
中英文 TUI 展示、人工确认后发布 PR 评论、LangGraph review client 集成、有边界的
`read_file`/`grep_code`/`web_search` 工具行为、GitHub 文件/目录树 adapter、安全限制、fallback warning
、npm wrapper 以及 fake client 测试体系。第三方库提供基础设施；PR Review 产品流程和工具策略由本仓库实现。

## 模型选择

当存在 `DEEPSEEK_API_KEY` 时，应用优先使用 DeepSeek；否则在存在 `OPENAI_API_KEY`
时使用 OpenAI。DeepSeek 走 OpenAI-compatible Chat Completions API（兼容 OpenAI
聊天补全格式的接口），默认 `base_url` 是 `https://api.deepseek.com`；只有接入兼容网关时
才需要覆盖 `DEEPSEEK_BASE_URL`。`DEEPSEEK_MODEL` 默认是 `deepseek-v4-flash`。
CLI 会在构建 review pipeline 前加载最近的项目 `.env`；`.env` 里的值会覆盖本次命令里的
临时 shell export。把 `.env.example` 复制为 `.env` 后填写本机密钥即可；`.env` 已被
git 忽略，不应提交。

评委复现优先使用 `--judge-demo`，这个路径不需要模型或 GitHub 密钥。普通 PR 审查需要配置
DeepSeek 或 OpenAI key；没有模型 key 时不会生成审查结果。

## 上下文策略

应用会把 PR 元数据、规则风险信号和 diff 片段发送给模型，也会纳入 PR Conversation 评论、
review 正文、行内 review comment、timeline 事件和 commit message 等历史/当前 PR 活动。
适合审查的文件不再按数量裁剪。prompt 会跳过明显低信号文件，例如 lockfile、生成 bundle、
二进制资源和压缩包；过长 hunk 和过长 PR 活动正文仍会裁剪。被跳过的文件会在最终报告中列出。

diff hunk 会被索引为变更后的行号范围。变更文件也会获得短 ID（例如 `F1`），模型可以调用
`read_file(file_id="F1")`，不需要复制很长的仓库路径。`read_file` 和 `grep_code` 会返回带行号的
代码上下文；`read_pr_activity` 可按类型重新读取已抓取的 PR 讨论/历史；`web_search` 会返回稳定
ID（例如 `[W1]`）、URL 和 snippet（摘要片段）。模型提示词要求把这些引用写进风险或建议的
`evidence` 对象；TUI 和 Markdown 导出会在对应审查项下展示这些证据。

配置真实模型后，LangGraph agent 可以按需请求更多上下文：

- `read_file`：读取 PR head commit 上的仓库相对路径文件。
- `grep_code`：在 PR head commit 的审查相关文件中搜索代码。
- `read_pr_activity`：读取已抓取的 PR 评论、review、行内评论、timeline 事件和 commit，
  可按类型过滤。
- `web_search`：仅在配置 `TAVILY_API_KEY` 后搜索公开网页上下文。

## 限制

- 私有仓库 PR 需要本机 token 具备目标仓库读取权限；权限不足时 GitHub 可能返回 404。
- GitHub Action 默认发布顶层 PR Conversation 评论。默认生成的 workflow 每次触发都会发一条新评论，
  不会编辑旧的 XEngineer 评论。
- 已支持 `--comment-mode review` 发布 PR review 正文；也支持显式使用
  `--review-action approve` 或 `--review-action request-changes` 进入 review 门禁流程。
  行内 review comment 是可选能力，只会为带代码行号证据的 RIGHT 侧审查项生成。
- 发布到 GitHub 的评论正文会在发送前做长度上限截断，避免超长报告触发 GitHub API 校验失败。
- 没有仓库级语义索引。
- 工具调用有轮数和输出限制；如果模型触达限制或工具失败，报告会显示 warning。

## 后续方向

- 基于相同 Review Core 的 Web UI。
- 可配置的组织级审查规则。
