# 技术拆解：Continue、Terminal 和 Nudge 如何避免 Agent “假完成”

> 适合平台：掘金、知乎、公众号、V2EX  
> 建议标题：AI Agent 最大的问题不是不会做，而是“假装做完了”  
> 建议配图：Continue/Terminal 状态图、terminal action nudge 日志、FinalizeFinding payload

## 开头

在做 AutoCVE 的 Finding Agent 时，我遇到过一个很典型的 Agent 问题：

模型经常会自然语言说“我已经完成分析”，但从系统角度看，它并没有真的完成。

比如：

- 它没有调用任何终止工具
- 它没有提交结构化漏洞结果
- 它只分析了一个文件就宣布完成
- 它说“我会继续检查”，但没有实际调用工具
- 它输出了看似完整的漏洞报告，但 source、sink、PoC、影响范围并不完整

这类问题我称为 Agent 的“假完成”。

在普通聊天场景里，这可能只是回答质量问题。但在代码安全审计和 CVE 挖掘场景里，这是流程可靠性问题。

AutoCVE 为了解决这个问题，引入了 Continue / Terminal 状态转换和 Nudge 机制。

项目地址：`<GitHub 仓库链接>`

## 为什么“模型说完成”不等于完成

一个 Agent 系统至少有两层状态：

1. 模型文本里的状态
2. Runtime 里的状态

模型可能会说：

```text
我已经完成审计，并发现了一个 SSRF 漏洞。
```

但 runtime 需要关心的是：

- 有没有调用工具确认代码路径
- 有没有读取 source 和 sink 所在文件
- 有没有形成利用链
- 有没有记录文件路径和行号
- 有没有提交合法 payload
- 有没有执行终止动作
- 有没有把 finding 写入结果库

如果只相信自然语言，就会出现很多不可复核结果。

所以 AutoCVE 的设计原则是：**自然语言不能直接代表状态完成，完成必须由 runtime 状态和终止动作共同确认。**

## Continue / Terminal 的基本设计

Finding Agent 的 ReAct loop 每一轮结束后，都会进入状态判断。

大体上只有两类结果：

- Continue：继续下一轮
- Terminal：结束当前 runtime

看起来简单，但关键在于“为什么继续”和“为什么结束”必须可记录。

AutoCVE 不只是返回一个 boolean，而是记录具体原因。

### 常见 Continue 原因

`next_turn`：本轮执行了工具调用。  
例如模型调用了 Grep 搜索危险函数，工具结果回来后，需要进入下一轮让模型继续分析。

`terminal_action_nudge`：当前阶段要求终止动作，但模型没有调用。  
例如模型说“审计完成”，但没有调用 `FinalizeFinding`。

`legacy_tool_syntax_nudge`：模型输出了伪工具语法。  
例如它写了 `Action: Read`，但没有产生 provider 原生 tool call。

`token_budget_continuation`：当前还有上下文预算，并且证据不足。  
此时 runtime 可以提醒模型继续查证，而不是草率收尾。

`stop_hook_blocking`：stop hook 判断不能结束。  
例如缺少关键字段，或者仍有必须处理的约束。

### 常见 Terminal 原因

`completed`：正常完成。  
理想状态下，completion mode 是 finalize tool，terminal action 是 `finalize_finding`。

`max_turns`：达到最大轮次。  
这是防止 Agent 无限循环的保护。

`model_error`：模型调用失败且无法恢复。

`aborted_tools`：工具执行被中止。

`natural_end_without_terminal_action`：模型自然结束，但没有调用终止工具。  
这通常不是理想完成，而是需要被标记为不完整或谨慎处理。

## Terminal Action：把结束变成动作

AutoCVE 里最重要的终止动作是 `FinalizeFinding`。

它不是普通工具，而是 Finding 阶段的终点工具。

调用成功意味着：

1. 当前 Finding 阶段可以结束。
2. 最终结构化结果可以被读取。
3. 后续漏洞管理和报告生成可以承接。

这和让模型输出 Markdown 完全不同。

Markdown 只是一段文本，而 `FinalizeFinding` 是一个带 schema 的结构化提交动作。

它可以校验字段是否完整，也可以在 payload 不合格时拒绝终止。

## Nudge：运行时纠偏

Nudge 可以理解成 runtime 给模型的“流程提醒”。

它不是让模型变聪明，而是让模型回到正确轨道上。

### 1. Native Tool Calling Reminder

很多模型在 ReAct 任务中习惯输出文本版工具调用：

```text
Action: Grep
Action Input: {"pattern": "exec("}
```

但如果系统使用的是原生 tool calling，这段文本不会被后端执行。

于是 AutoCVE 会提醒模型：不要输出伪工具语法，必须使用原生工具调用。

这可以避免前端看起来像有动作，后端实际上什么都没执行。

### 2. Legacy Tool Syntax Nudge

如果模型已经输出了伪工具语法，但没有真正 tool call，runtime 会触发 `legacy_tool_syntax_nudge`。

提醒内容大意是：

- 刚才的文本工具调用不会执行
- 如果需要继续审计，请重新发起原生工具调用
- 如果确实完成，请调用 FinalizeFinding

这个机制对兼容不同模型很重要。因为不同模型对工具调用格式的稳定性差异很大。

### 3. Terminal Action Nudge

这是 Finding Agent 里最关键的 nudge。

如果当前阶段要求终止工具，而模型没有调用，runtime 会提醒：

- 如果还没查完，就继续调用工具
- 如果已经查完，必须调用 `FinalizeFinding`
- 不要只用自然语言宣布完成

AutoCVE 还限制了 nudge 次数。超过上限后，如果模型仍然没有提交终止动作，runtime 会倾向标记为 `natural_end_without_terminal_action`，而不是强行把自然语言包装成成功结果。

这个取舍很重要：宁可把一次审计标记为不完整，也不要把不可复核结果当成漏洞入库。

### 4. Continue Intent Nudge

还有一种常见情况：模型说它要继续。

比如：

```text
我需要继续检查这个参数是否能流入危险函数。
```

但它没有调用 Read、Grep、Glob 等工具。

在 AutoCVE 里，这种“继续意图但没有行动”也会被识别。runtime 会要求模型实际调用工具，而不是只描述计划。

这可以减少 Agent 在原地自言自语。

## 为什么这比简单 while loop 更可靠

很多 Agent demo 的 loop 逻辑类似：

```text
while not done:
    call_model()
    if tool_calls:
        run_tools()
    else:
        break
```

这个设计的问题是：没有工具调用并不代表任务完成。

在漏洞挖掘中，“没有工具调用”可能意味着：

- 模型真的完成了
- 模型卡住了
- 模型忘了调用工具
- 模型输出了伪工具语法
- 模型想继续但没有行动
- 模型提前总结

这些情况不能用一个 `else: break` 处理。

AutoCVE 的 QueryLoop 会把这些分支拆开，用具体 transition 记录原因，再决定继续、纠偏还是终止。

## 对 CVE 挖掘的意义

CVE 挖掘最重要的是证据质量。

一个漏洞报告至少要能回答：

- 漏洞在哪里
- 输入从哪里来
- 经过哪些处理
- 最终流向哪个危险点
- 攻击者需要什么条件
- 影响是什么
- 哪些版本受影响
- 是否有复现或验证证据
- 为什么具备 CVE 价值

如果 Agent 过早结束，这些字段很可能不完整。

Continue / Terminal / Nudge 的作用，就是防止系统被一段漂亮但不完整的自然语言骗过去。

## 经验总结

做安全 Agent 时，我认为有几个原则很重要：

1. 终止必须是动作，不应该只是文本。
2. 状态转换必须可记录，不能只有 done=true。
3. 工具调用必须走后端执行链路，不能依赖伪工具文本。
4. 发现一个漏洞不等于任务完成。
5. 结果不完整时宁可 incomplete，也不要强行成功。
6. Nudge 要有限次，否则会变成无限循环。

这些设计看起来偏工程，但它们直接决定了 Agent 结果能不能进入真实工作流。

## 结尾

AutoCVE 里的 Continue / Terminal / Nudge 机制，本质上是在给 Agent 加“流程骨架”。

模型负责推理和决策，但 runtime 负责约束状态、执行工具、记录证据和判断终止。

如果你也在做 Agent 工程化，尤其是安全、代码审计、运维、数据分析这类高风险任务，我建议尽早把“完成条件”从自然语言里拿出来，变成结构化动作和可审计状态。

项目地址：`<GitHub 仓库链接>`

