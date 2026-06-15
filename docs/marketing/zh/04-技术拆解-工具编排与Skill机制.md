# 技术拆解：AutoCVE 如何做工具编排和 Skill 机制

> 适合平台：掘金、知乎、公众号、开源中国  
> 建议标题：安全 Agent 不能只会聊天：AutoCVE 的工具编排和 Skill 机制设计  
> 建议配图：ToolRegistry / ToolOrchestrator 流程图、Skill 管理页面、工具调用 trace

## 开头

做代码安全审计 Agent 时，一个绕不开的问题是：模型到底应该怎么使用工具？

如果工具太少，Agent 只能靠猜。  
如果工具太多，模型容易乱选。  
如果工具没有权限边界，风险不可控。  
如果工具调用没有记录，结果不可复核。  
如果所有知识都塞进 prompt，上下文很快爆掉。

AutoCVE 在这方面做了两层设计：

1. 工具编排：让 Agent 可以安全、可追踪地调用 Read、Grep、Glob、Shell、FinalizeFinding 等工具。
2. Skill 机制：让 Agent 按需加载专项审计知识，而不是一次性把所有内容塞进上下文。

这篇文章拆一下这两部分。

项目地址：`<GitHub 仓库链接>`

## 工具为什么需要编排

在一个真实的漏洞挖掘任务中，Agent 可能会连续执行很多动作：

- 列出项目文件
- 搜索路由入口
- 读取 controller
- 查找 service 调用
- 追踪权限判断
- 搜索危险函数
- 读取配置文件
- 验证依赖版本
- 生成最终 finding

这些动作背后对应不同工具。

如果只是把工具函数暴露给模型，会有几个问题：

- 工具名可能不一致
- 输入可能不合法
- 有些工具能并发，有些必须串行
- 写入和 shell 工具有副作用
- 工具执行失败后如何处理不清楚
- 前端无法展示真实调用轨迹
- 后续报告无法追溯证据来源

所以 AutoCVE 把工具调用统一接到 runtime 工具层。

## ToolRegistry：当前回合能看到哪些工具

ToolRegistry 负责注册和描述工具。

它会处理：

- 工具名称
- aliases
- 是否启用
- 是否 deferred
- 是否 always load
- 输入 schema
- 是否只读
- 是否有破坏性
- 是否需要用户交互

一个重要点是：模型每轮看到的不是系统所有能力，而是当前 Agent、当前状态下可用的工具集合。

例如 Finding Agent 常用工具包括：

- `Read`
- `Glob`
- `Grep`
- `Skill`
- `FinalizeFinding`
- `TodoWrite`
- `Bash`
- `PowerShell`
- `ToolSearch`

其中一些工具可以 deferred。也就是说，默认不放进模型工具列表，只有需要时再通过 ToolSearch 发现。

这样可以减少模型选择负担，也能避免不相关工具污染上下文。

## ToolOrchestrator：工具调用的执行入口

ToolOrchestrator 是工具执行入口。

它做的事情包括：

1. 接收模型产生的 tool call。
2. 解析工具名和 alias。
3. 校验输入 schema。
4. 计算工具是否并发安全。
5. 评估权限策略。
6. 创建工具调用记录。
7. 触发 PreToolUse checkpoint。
8. 执行工具。
9. 触发 PostToolUse 或 PostToolUseFailure。
10. 把结果写回 transcript。

这让工具调用不再是一个不可见的函数调用，而是一条完整的审计轨迹。

对安全审计来说，这非常重要。因为最后的漏洞报告不能只说“模型认为这里有漏洞”，而应该能追溯到它读过哪些文件、搜过哪些关键字、工具返回了什么结果。

## StreamingToolExecutor：并发和串行的边界

模型有时会在一轮里提出多个工具调用。

比如它可能同时想读取几个相关文件。对于只读且并发安全的工具，这样做是合理的。

但并不是所有工具都能并发。

AutoCVE 的 StreamingToolExecutor 会根据工具属性进行分组：

- 只读且并发安全的工具可以并行
- 有相同 concurrency key 的工具不能互相干扰
- 写入、shell、沙箱等有副作用的工具通常串行
- 如果某个有副作用工具失败，可以中止同批次相关调用，避免错误扩散

这对 Agent 体验和安全性都有帮助。

它允许模型一次提出多个读操作，提高效率；同时又能控制写入和执行类工具的风险。

## 工具权限和 guardrails

AutoCVE 的 runtime 工具不是裸执行。

尤其是 `Write`、`Bash`、`PowerShell` 这类工具，需要更谨慎。

系统会检查：

- 工具是否启用
- 输入是否合法
- 当前 runtime 是否允许该操作
- 是否越过项目目录
- 是否需要用户批准
- 是否触发 hook 或 guardrail

目标不是完全禁止 Agent 行动，而是让它在安全边界内行动。

代码安全审计有时确实需要运行命令、查看依赖、做验证。但这些能力必须可控、可追踪、可中止。

## Skill 机制：不要把所有知识都塞进 prompt

除了工具，AutoCVE 还引入了 Skill 机制。

为什么需要 Skill？

因为安全审计知识非常细：

- Java 反序列化
- Fastjson 利用链
- SSRF 绕过
- 文件上传
- SQL 注入
- 权限绕过
- 模板注入
- CVE 报告撰写
- huntr 提交流程
- 企业内部规范

如果把这些全部塞进系统 prompt，成本高、上下文长、命中率低，模型也不一定真的会按要求读。

AutoCVE 的 Skill 更像是一套本地能力包。

一个 Skill 可以包含：

- `SKILL.md`
- references
- checklists
- examples
- scripts
- metadata
- agent bindings

不同 Agent 可以绑定不同 Skill。

例如 Finding Agent 绑定漏洞挖掘类 Skill，Verification Agent 绑定 PoC 验证类 Skill，用户会话绑定报告撰写或解释类 Skill。

## 渐进式披露

AutoCVE 的 Skill 加载采用渐进式披露。

启动阶段不会把所有 Skill 正文都塞进上下文，而是先加载：

- available skills
- matched skills
- route plan
- startup reads
- deferred skills

当任务语义命中某个 Skill，或用户显式输入 `$code-audit-finding` 之类的引用时，模型必须先调用：

```text
Skill(action="body")
```

读取完整 `SKILL.md`。

如果 Skill 里要求继续读取 references、checklists 或 scripts，模型再调用：

```text
Skill(action="read_resource", resource_name="...")
```

每次 Skill 调用都会写入 Audit Session，记录 skill_ref、action、resource_name、调用来源和加载阶段。

这样 Skill 加载本身也是 trace 的一部分。

## Skill 机制解决了什么问题

### 1. 控制上下文长度

不是所有任务都需要所有知识。

Skill 让系统只在命中场景时加载相关内容，降低上下文噪音。

### 2. 让审计方法可复用

一个好的 SSRF 审计流程、Java 反序列化 checklist、CVE 报告模板，不应该散落在 prompt 里。

它们应该变成可管理、可导入、可绑定、可迭代的 Skill。

### 3. 让用户扩展 Agent 能力

用户可以从 GitHub 导入 Skill，也可以上传 Skill ZIP，或者直接把 Skill 文件夹放到 `skill_library/` 下同步。

这让 AutoCVE 不只是内置一套审计经验，而是允许用户把自己的方法论接进 Agent。

### 4. 让调用过程可审计

每次 Skill 调用都会被记录。

这意味着你可以回看：

- Agent 当时用了哪个 Skill
- 加载了哪些资源
- 是否读了 mandatory references
- 后续分析是否基于这些内容

这对安全审计复盘很有价值。

## 工具和 Skill 如何配合

工具解决“行动能力”，Skill 解决“专业方法”。

例如一个 SSRF 审计任务：

1. Skill route plan 命中 SSRF 审计 Skill。
2. Agent 调用 Skill 读取审计流程。
3. 根据 Skill 提醒，使用 Grep 搜索 URL fetch、HTTP client、webhook、image proxy 等入口。
4. 使用 Read 阅读关键文件。
5. 追踪 source/sink。
6. 如有条件，调用 shell 或沙箱验证。
7. 最终通过 FinalizeFinding 提交结构化漏洞。

这比单纯“让模型想办法审计 SSRF”更稳定。

## 总结

AutoCVE 的工具编排和 Skill 机制，本质上是在给安全 Agent 提供两样东西：

- 可控行动能力
- 可复用专业流程

工具层保证 Agent 的动作真实执行、可记录、可权限控制。  
Skill 层保证 Agent 能按需加载专业知识，而不是把所有知识塞进 prompt。

我认为这是 Agent 从 demo 走向真实工程场景时必须补上的部分。

尤其在代码安全审计这种高风险任务里，模型的每个动作都应该能被追踪，每个结论都应该能回到证据，每个扩展能力都应该能被管理。

项目地址：`<GitHub 仓库链接>`

