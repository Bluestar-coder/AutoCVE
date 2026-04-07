# Finding Runtime Compatibility Review

## 1. 评审目标

本评审用于回答一个具体问题：

当前 AuditAI backend 中已经迁入的 Python finding runtime，与 `restored-from-cli-map-v3` 的实际 agent 设计、运行流程、tool 调度、skill、memory、session、handoff 等机制相比，哪些已经兼容，哪些只是部分迁移，哪些仍未实现。

本评审结论只基于当前分支代码现实，不按目标愿景打分。

## 2. 总结结论

当前迁移状态可以归纳为：
- 已完成一个“可运行、可持久化、可追问、可交接 verification”的 finding runtime 垂直切片
- 已对齐 `query loop -> tool call -> tool result -> continue -> final payload -> verification handoff -> same-session follow-up` 这条主路径
- 但还没有把 `restored-from-cli-map-v3` 的全部 agent 生态完整迁入
- 当前更准确的描述是：已完成“finding runtime 内核 + finding 所需关键适配层”的 Python 化，而不是“整个 restored runtime 全功能镜像”

结论分级：
- 主运行闭环：高兼容
- finding 所需工具调度：中高兼容
- 会话与 transcript：中高兼容
- verification handoff：高兼容
- skill 机制：中兼容
- memory 机制：中兼容
- 沙箱机制：低兼容，主要仍在 verification 路径
- subagent / team / MCP / workflow / remote：未迁移

## 3. 已基本对齐的部分

### 3.1 Query Loop 主闭环

已迁入：
- `query loop`
- transcript messages
- tool call 请求解析
- tool 结果回写
- 多轮继续执行
- final assistant payload 提取

这部分与 restored runtime 的核心闭环基本一致：
- LLM 收到 transcript + tool schema
- 返回 content 和 tool calls
- runtime 执行工具
- 将 tool_use/tool_result 回填到消息流
- 继续下一轮直到 stop

当前实现位置：
- `backend/app/services/finding_runtime/query_loop.py`
- `backend/app/services/finding_runtime/runner.py`
- `backend/app/services/finding_runtime/bridge.py`

### 3.2 Finding -> Verification 交接

已迁入：
- finding runtime 输出 final payload
- 基于 finding 结果构建 handoff
- handoff 显式持久化
- verification 继续沿用既有 contract 接收 handoff
- handoff 同时在 session transcript 中可见

这是当前迁移里最完整的一部分，兼容性较高。

### 3.3 会话与追问闭环

已迁入：
- `audit_sessions`
- messages/tool_calls/skills/memories/handoffs 持久化
- 独立审计会话页
- finding 完成后继续在同一 session 追问
- follow-up 可继续触发 runtime 续跑

这已经满足了“每个审计是一个会话，人工可围绕审计细节继续追问”的核心目标。

### 3.4 默认切换与双栈兼容

已迁入：
- 全局默认 finding runtime stack
- 单任务显式 override
- 任务列表/详情可观测最终 stack
- 旧 verification contract 不变
- 旧 finding stack 仍可回滚

这使当前分支具备灰度切换条件。

## 4. 部分迁移、但尚未完全对齐的部分

### 4.1 Tool Framework

已实现：
- 统一 runtime tool 抽象
- schema 校验
- permission hook
- 读型工具并发、写型工具串行的 batch 执行模型
- tool call 持久化

与 restored 的差异：
- 当前 runtime tool 集主要包裹 AuditAI 现有 finding tools，而不是完整复制 restored 的全工具宇宙
- 主要服务 finding 阶段，不是通用 agent runtime tool platform
- 没有完整迁入 restored 中的大量外围工具能力

当前结论：
- 对 finding 审计主路径够用
- 对“完全复刻 restored tool ecosystem”还不够

### 4.2 Skill System

已实现：
- 会话启动时预加载 skill catalog
- skill route message 注入 transcript
- `invoke_skill` runtime tool
- skill invocation 持久化
- `code-audit-finding` 相关能力接入

与 restored 的差异：
- 当前依赖 AuditAI 现有 `SkillService` 和 finding skill router
- 不是 restored 那套 markdown/frontmatter loader、动态目录扫描、条件激活、`.claude/skills` 发现机制的完整 Python 翻译
- 没有完整迁入 nested skills、legacy commands、MCP skill builders 这类机制

当前结论：
- finding 所需的技能路由已经可用
- 但严格来说不是 restored 原生 skill system 的完整复刻

### 4.3 Memory System

已实现：
- 指令记忆注入
- 基于规则集的 instruction memory
- 基于 `code-audit-finding` references 的 recall memory
- memory attachment transcript
- memory 持久化与页面展示

与 restored 的差异：
- 当前没有完整实现 `CLAUDE.md / .claude/rules / AutoMem / TeamMem / memdir` 那套多层发现与召回链路
- 记忆来源更偏 AuditAI 现有 rule sets 和 skill references
- 没有 side-query 选择最相关记忆的独立 memory engine

当前结论：
- 已有“可工作的 finding memory 机制”
- 但不是 restored memory subsystem 的完整迁移

### 4.4 文件系统与工程上下文装配

已实现：
- 通过现有 AuditAI finding tools 访问项目文件
- follow-up 续跑时可重建项目根目录、工具集和 LLM context

与 restored 的差异：
- 没有把 restored 那套独立 FS 抽象、安全路径解析、读写约束层完整翻成新的 runtime-native filesystem module
- 当前更像“复用 AuditAI 原工具层”，而不是“完整迁移 restored FS subsystem”

当前结论：
- 对 finding 审计流程可用
- 对 restored 的底层 FS 机制只是功能近似，不是结构一致

## 5. 尚未实现或明显未对齐的部分

### 5.1 Subagent / Team / Swarm

当前未实现：
- runtime 内递归 subagent
- agent lineage
- worker/coordinator team 结构
- background agent / async agent
- subagent worktree 隔离

这部分与 restored 的 `AgentTool` 路径差异非常大，目前基本未迁。

### 5.2 MCP / Resource / Plugin 生态

当前未实现：
- MCP resources
- MCP prompts / skills builders
- plugin 式 runtime 扩展
- remote agent / remote trigger

如果目标是“与 restored 完全一致”，这是明确的缺口。

### 5.3 通用 Workflow / Task 系统

当前未实现：
- restored 中更通用的 workflow / monitor / sleep / cron / trigger 类机制
- plan mode / todo / brief 等运行时交互能力
- 非 finding 领域的广义 agent orchestration

当前迁移仍然聚焦于 finding 子系统，而不是把 restored 整个 CLI 运行时搬进来。

### 5.4 Sandboxing 运行机制

当前状态：
- verification 仍大量依赖 AuditAI 原有 sandbox/tooling
- finding runtime 本身没有形成 restored 风格的独立沙箱策略层
- finding 阶段主要仍以代码阅读和分析工具为主

结论：
- “finding runtime 已完整迁移 sandboxes” 这个说法当前不成立
- 更准确的说法是：verification sandbox 仍沿用 AuditAI 既有实现

### 5.5 Streaming / Compaction / Checkpoint Recovery

当前状态：
- 有 session、turn、checkpoint 基础表
- 但没有形成 restored 那种完整的 compact/recover/session compression 机制
- 没有用户可直接使用的 checkpoint restore workflow
- 没有完整 streaming tool executor 等价实现

结论：
- 数据骨架有了
- 高级运行机制未完全对齐

## 6. 运行逻辑不一致的关键点

当前与 restored 不一致的核心点有：

1. 技能加载来源不同
- 当前：AuditAI `SkillService`
- restored：markdown/frontmatter + 动态目录扫描 + 条件 skills

2. 记忆来源不同
- 当前：rule sets + code-audit references
- restored：CLAUDE.md / rules / memdir / AutoMem / TeamMem

3. 文件系统层级不同
- 当前：复用现有 finding tools
- restored：独立 FS abstraction + 路径安全层

4. 沙箱责任位置不同
- 当前：主要在 verification 和原工具层
- restored：更统一地作为 runtime/tool 生态一部分

5. 子代理机制缺失
- 当前：没有 restored `AgentTool -> query() recursion` 的完整路径

## 7. 兼容性结论

如果问题是：
“当前 finding agent 能不能按 restored 的思路跑真实审计任务，并把结果正常交给 verification，还能保留会话追问？”

答案是：
- 可以，主链路已经成立

如果问题是：
“当前是否已经把 restored-from-cli-map-v3 的 agent 架构和所有机制完整、无差异地迁移进 AuditAI backend？”

答案是：
- 还没有

更准确的表述是：
- 已完成 finding runtime 核心闭环迁移
- 已完成会话、handoff、追问、默认切换等关键适配
- 但 restored 的广义 agent runtime 生态仍有明显未迁移区域

## 8. 当前最重要的未完事项

若目标是继续向“完全一致”推进，优先级最高的补齐项是：
1. Python 化的 markdown/frontmatter skill loader 与动态发现机制
2. Python 化的 CLAUDE/memdir 风格多层 memory system
3. runtime-native filesystem/security layer，而不是继续完全依赖旧 tools
4. subagent / lineage / recursive runtime
5. 对 sandboxes、checkpoints、streaming 的统一 runtime 化

## 9. 对当前分支的最终判断

当前分支适合做的事：
- 真实 finding 审计灰度
- 会话与追问验证
- verification handoff 验证
- runtime 默认切换试运行

当前分支不适合宣称的事：
- 已 100% 完整复刻 restored agent 全部功能
- 已完成所有 tools/skills/memory/sandbox/subagent 的等价迁移

因此，当前最合理的决策是：
- 将它视为“finding runtime 主链已成、可进入真实审计验证”的版本
- 不把它视为“restored runtime 全生态迁移完成版”