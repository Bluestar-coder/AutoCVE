# 技术拆解：AutoCVE 的 Finding Agent ReAct Loop 如何设计

> 适合平台：掘金、知乎、公众号、开源中国  
> 建议标题：不只是套壳 LLM：我在 AutoCVE 里实现了一个面向漏洞挖掘的 ReAct Runtime  
> 建议配图：Finding Runtime 架构图、QueryLoop 流程图、Agent 审计日志截图

## 开头

很多 AI 安全扫描项目最容易陷入一个问题：把代码塞给模型，让模型输出一段分析，然后把这段分析叫做“审计结果”。

这在 demo 阶段很容易做，但在真实漏洞挖掘场景里远远不够。

代码审计需要多轮搜索、阅读、验证、回看上下文、补证据、去误报。模型不能只“回答”，它必须能不断行动：读文件、搜调用链、检查配置、定位 source/sink、调用工具、整理证据，最后以结构化结果提交。

AutoCVE 的 Finding Agent 就是围绕这个目标设计的。

它的核心不是单次 prompt，而是一个可追踪、可恢复、可约束的 ReAct loop。

项目地址：`<GitHub 仓库链接>`

## 为什么 Finding Agent 要单独设计 Runtime

AutoCVE 里有多个 Agent：Orchestrator、Recon、Scan、Triage、Finding、Verification。

其中 Finding Agent 的职责最特殊。

Scan 更偏工具调用，Triage 更偏候选复核，Verification 更偏动态验证。而 Finding Agent 面向的是“直接阅读源码并深挖高价值漏洞”。这件事有几个特点：

1. 需要多轮探索，不可能一次读完项目。
2. 需要工具调用，不只是自然语言推理。
3. 需要状态管理，否则很容易丢失上下文。
4. 需要终止约束，否则模型可能提前宣布完成。
5. 需要结构化结果，否则后续报告、漏洞管理和 CVE 流程无法承接。

所以 AutoCVE 没有把 Finding Agent 写成一个简单的 `call_llm(prompt)`，而是拆成了一套 runtime。

关键组件包括：

- `FindingRuntimeBridge`：连接外层 Agent 和 runtime 内核
- `FindingRuntimeRunner`：驱动多轮 QueryLoop
- `QueryLoop`：核心 ReAct 循环
- `ToolRegistry`：注册当前可用工具
- `ToolOrchestrator`：执行和记录工具调用
- `AuditSessionStore`：保存消息、工具调用、checkpoint 和 runtime state
- `RuntimeSkillCatalog`：预加载和路由 Skill
- `FinalizeFindingTool`：提交最终结构化漏洞结果

## 单轮 QueryLoop 在做什么

可以把 Finding Runtime 的一轮执行概括为：

```text
加载会话快照
-> 合并 runtime 上下文
-> 整理 transcript
-> 构造模型消息
-> 调用 LLM
-> 解析 native tool calls
-> 执行工具
-> 写入工具结果
-> 判断 Continue 或 Terminal
```

这看起来像普通 ReAct，但关键差异在于：AutoCVE 把每个环节都显式状态化了。

### 1. 加载 Session Snapshot

每轮开始时，runtime 会从 session store 加载当前审计会话。

这里不只是聊天记录，还包括：

- 用户消息
- 模型回复
- 工具调用记录
- runtime state
- Skill 加载状态
- memory
- handoff
- checkpoint

这让审计过程可以被前端展示，也能在后续继续对话时恢复上下文。

### 2. 合并运行时上下文

Finding Agent 不是孤立运行的。

它需要知道：

- 当前项目是什么
- Recon 阶段发现了什么
- 上游 Agent 传来了哪些 handoff
- 当前有哪些可用工具
- 哪些 Skills 已经匹配
- 之前是否已经找到候选漏洞
- 是否接近 token budget 或 max turns

这些都会在进入模型前被整理进上下文。

### 3. 模型必须使用原生工具调用

AutoCVE 不鼓励模型输出类似这样的伪工具文本：

```text
Action: Grep
Action Input: {"pattern": "eval("}
```

这种文本看起来像工具调用，但后端不会真的执行，前端也无法形成可靠 trace。

因此 Finding Runtime 要求模型使用 provider 原生 tool calling。工具调用会进入 ToolOrchestrator，由后端统一处理输入校验、权限检查、checkpoint、执行记录和结果回写。

这样做的好处是：

- 工具调用是真实执行，不是文本表演
- 每次调用都有审计记录
- 高风险工具可以走权限策略
- 前端可以展示完整工具轨迹
- 后续报告可以追溯证据来源

## 工具体系如何配合 ReAct

Finding Agent 常用工具包括：

- `Read`：读取文件内容
- `Glob`：按模式列出文件
- `Grep`：搜索代码关键字或正则
- `Bash` / `PowerShell`：在允许时执行命令
- `Skill`：加载匹配的审计 Skill
- `TodoWrite`：维护运行时待办
- `FinalizeFinding`：提交最终漏洞结果
- `ToolSearch`：当工具被延迟加载时搜索可用工具

这套工具不是全部无脑暴露给模型。

ToolRegistry 会根据当前 Agent、当前场景和工具配置返回可用工具。部分工具可以 deferred，只有在需要时通过 ToolSearch 暴露。

这可以减少模型工具选择噪音，也能避免过早暴露不相关能力。

## Continue / Terminal 状态转换

ReAct loop 里最关键的问题是：什么时候继续，什么时候结束。

AutoCVE 把这个设计成显式状态转换。

常见 Continue 原因包括：

- `next_turn`：本轮执行了工具调用，需要把工具结果交还给模型
- `terminal_action_nudge`：模型没有调用终止工具，但当前阶段要求终止动作
- `legacy_tool_syntax_nudge`：模型输出了伪工具语法，需要纠偏
- `token_budget_continuation`：预算允许且证据不足，提醒继续查证
- `stop_hook_blocking`：stop hook 判断当前还不能结束
- `reactive_compact_retry`：上下文过长或异常，需要压缩后继续

常见 Terminal 原因包括：

- 正常完成
- 达到最大轮次
- 模型错误
- 工具执行中止
- stop hook 允许停止
- 阻塞次数达到上限

这比“模型说结束就结束”更稳。

因为漏洞挖掘不是写作文，不能只看自然语言结尾。真正重要的是 runtime 状态、终止动作和结构化 payload。

## FinalizeFinding：不是普通输出，而是终止工具

Finding Agent 最终必须调用 `FinalizeFinding`。

这个工具的意义是：当前 Finding 阶段已经完成，提交最终结构化结果，可以终止 runtime。

它要求 payload 包含比较完整的漏洞字段，例如：

- `vulnerability_type`
- `severity`
- `title`
- `description`
- `file_path`
- `line_start`
- `line_end`
- `code_snippet`
- `source`
- `sink`
- `exploit_chain`
- `poc`
- `impact`
- `cve_justification`
- `verification_notes`

如果字段不合法，工具不会把结果当作成功终止，而是返回 rejected 信息，让模型继续补充证据。

这个设计解决了一个实际问题：模型很容易在还没有完整证据时写出“看起来很完整”的结论。终止工具的存在，让系统可以把“完成”变成可校验动作。

## Nudge：让 Agent 从偏航中回来

真实模型不会总是按预期行动。

它可能：

- 输出伪工具语法
- 说“我将继续检查”，但没有调用工具
- 只发现一个漏洞就想结束
- 说“已经完成”，但没有提交结构化结果
- 在证据不足时生成漂亮报告

所以 Finding Runtime 引入了 nudge 机制。

例如模型自然语言表示“我需要继续检查”，但没有发起 Read、Grep、Glob 等工具调用，runtime 会提醒它：继续就必须实际调用工具。

如果模型准备结束但没有调用 FinalizeFinding，runtime 会触发 terminal action nudge，要求它要么继续查证，要么提交结构化终止工具。

这个机制不是为了“控制模型”，而是为了把安全审计流程从聊天式输出拉回可验证工作流。

## 为什么这对安全审计重要

安全审计最怕两类结果：

1. 看起来很厉害，但不可复核。
2. 过程里有发现，但最后没有结构化沉淀。

AutoCVE 的 Finding Runtime 想解决的正是这两个问题。

它把模型推理、工具调用、状态转换、终止动作、Skill 调用和最终漏洞结果都纳入同一条 trace 中。

这样前端可以展示过程，后端可以保存状态，用户可以继续追问，报告可以引用证据，漏洞管理可以跟踪 CVE 状态。

## 总结

AutoCVE 的 Finding Agent 不是一个 prompt，而是一套面向漏洞挖掘场景的 Agent Runtime。

它的核心设计包括：

- 多轮 ReAct loop
- 原生工具调用
- ToolRegistry / ToolOrchestrator
- Continue / Terminal 状态机
- Nudge 纠偏机制
- FinalizeFinding 终止工具
- Skill 渐进加载
- 审计会话持久化

如果你对 AI Agent 工程化、代码审计自动化或 CVE 挖掘流程感兴趣，欢迎看看这个项目，也欢迎一起讨论如何把 Agent 从 demo 推向真实工作流。

项目地址：`<GitHub 仓库链接>`

