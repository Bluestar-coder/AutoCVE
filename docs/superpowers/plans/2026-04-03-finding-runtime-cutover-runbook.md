# Finding Runtime Cutover Runbook

## 1. 目标

本 runbook 用于把 AuditAI finding agent 从 legacy stack 切换到新的 Python finding runtime stack，并定义旧 finding stack 的下线门槛、回滚条件和现场验证步骤。

当前分支目标不是立刻删除 legacy，而是先完成：
- 全局默认 stack 可切换
- 单任务显式 override 仍然可用
- runtime session、handoff、follow-up chat、verification contract 全部可观测
- 回滚路径保持可执行

## 2. 当前切换能力

当前已经具备的切换能力：
- 系统级默认 stack：`FINDING_RUNTIME_STACK_DEFAULT`
- 单任务显式 override：`finding_runtime_stack=legacy|runtime`
- 任务列表/详情可观测最终解析后的 stack
- finding runtime session 可独立查看、追问、继续执行
- finding -> verification handoff 已有显式持久化和会话展示

当前默认值：
- `legacy`

切换优先级：
1. 任务请求体显式传入 `finding_runtime_stack`
2. 若未显式传入，则回退到 `FINDING_RUNTIME_STACK_DEFAULT`
3. 非法值统一归一到 `legacy`

## 3. 切换前检查

上线前必须确认：
- 后端 targeted tests 通过
- 前端 `type-check` 通过
- `app.main` 导入通过
- 新 finding runtime 能创建 `audit_sessions`
- finding task 列表和详情都能回显 `finding_runtime_stack`
- `audit_sessions/{id}` 页面可打开
- follow-up chat 能继续写回同一 session
- handoff 在 `audit_handoffs` 与 transcript 中都能看到
- verification 仍能按旧 contract 收到 handoff payload

建议上线前执行：
```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests\api\test_agent_tasks_runtime_session.py tests\api\test_audit_sessions_api.py tests\agent\test_agent_contracts.py::test_finding_runtime_stack_preserves_verification_handoff_contract -q
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, r'.'); import app.main; print('app-main-import-ok')"
cd ..
npm --prefix frontend run type-check
```

## 4. 灰度切换步骤

### 阶段 A：保持默认 legacy，只做单任务 runtime 验证

操作：
- 保持 `FINDING_RUNTIME_STACK_DEFAULT=legacy`
- 手动创建少量任务，显式传 `finding_runtime_stack=runtime`
- 验证 runtime session、follow-up、handoff、verification

放行条件：
- 至少 3 个不同项目成功跑完 finding -> verification
- 未出现 runtime session 丢失
- 未出现 verification handoff 缺字段
- 未出现 follow-up chat 写入错误 session

### 阶段 B：小流量默认 runtime

操作：
- 将 `FINDING_RUNTIME_STACK_DEFAULT` 改为 `runtime`
- 保留请求级 override，允许临时指定 `legacy`
- 持续观察任务列表中的 stack 标识

重点观察：
- runtime task 占比
- finding task 失败率
- finding 无结果率
- runtime session 建立成功率
- follow-up chat 成功率
- verification 接收 handoff 成功率

建议灰度门槛：
- 连续 1 到 2 天无 P1/P2 故障
- runtime finding 成功率不低于 legacy 基线
- verification handoff 成功率 100%

### 阶段 C：默认 runtime，legacy 仅保留回滚

操作：
- 继续保留 override，但默认全部走 runtime
- 仅对异常项目或紧急回滚任务使用 `legacy`

放行条件：
- 主流项目类型均已覆盖
- 审计会话页已被日常使用
- 团队确认可以通过 session 页面完成复核和追问

## 5. 回滚方案

如果出现以下任一情况，应立即回滚默认值到 legacy：
- finding runtime 无法稳定创建 session
- follow-up chat 出现上下文错乱
- verification handoff 丢字段或 contract 破坏
- finding runtime 在关键项目类型上明显低于 legacy
- runtime 失败率显著高于 legacy

回滚动作：
1. 将 `FINDING_RUNTIME_STACK_DEFAULT` 改回 `legacy`
2. 保留已生成的 runtime sessions，不做删除
3. 新任务默认回到 legacy
4. 用显式 `finding_runtime_stack=runtime` 继续做问题复现

回滚后必须保留：
- `audit_sessions`
- `audit_handoffs`
- 相关 transcript
- 问题任务样本

## 6. 旧 finding stack 下线门槛

只有满足以下全部条件，才允许进入删除 legacy finding path 的实施阶段：
- 默认 runtime 已稳定运行至少一个完整迭代周期
- 没有再需要紧急指定 `legacy` 的生产任务
- verification handoff 没有兼容性投诉
- runtime session 页面已成为 finding 复核主入口
- 现有 targeted tests 全绿
- 全链路人工审计走查通过
- 已知环境问题已清理
  当前仍存在一组与本轮逻辑无关的 Windows `Temp` 目录 `PermissionError` 测试问题，正式下线前建议先处理

## 7. 旧 finding stack 真正下线时要做的代码动作

下线 legacy finding stack 时，必须至少完成：
- 删除 `FindingAgent.run()` 中 legacy/runtime 双分支，只保留 runtime path
- 清理 `finding_runtime_stack=legacy` 的前端选项和后端 fallback 文案
- 清理旧 finding-only prompt loop 代码和只服务于 legacy path 的测试
- 保留 runtime session、handoff、follow-up chat 相关表和 API
- 保留 verification contract，不允许顺手重构

不应在下线阶段顺带做的事：
- 重写 verification agent
- 顺手重构 audit session 数据模型
- 改动 findings 输出协议
- 改动 recon 输入契约

## 8. 实际审计流程验证步骤

建议你按下面步骤真跑一遍：

### 8.1 创建任务

方式一：通过 UI 创建 Agent 审计任务
- 创建后检查任务列表是否显示 `runtime` 或 `legacy` badge

方式二：通过 API 显式指定 runtime
```json
POST /api/v1/agent-tasks/
{
  "project_id": "<project-id>",
  "name": "runtime finding validation",
  "finding_runtime_stack": "runtime"
}
```

### 8.2 观察 finding 执行

检查点：
- 任务详情能正常打开
- `runtime_session_id` 出现在任务详情或列表中
- 可以进入 `/audit-sessions/{runtime_session_id}`

### 8.3 检查 session transcript

在审计会话页确认至少出现：
- skill route system message
- memory attachments
- user task message
- assistant messages
- tool use / tool result
- handoff message

### 8.4 检查 verification handoff

确认：
- handoff 面板有记录
- handoff payload 中包含给 verification 的上下文
- verification 阶段继续运行，没有 contract 报错

### 8.5 检查 follow-up chat

finding 结束后，在审计会话页追问：
- “这个漏洞的完整利用链是什么？”
- “给我一个更具体的 POC 构造方式。”
- “这个结论依赖了哪些代码证据？”

通过标准：
- 新 user message 写入同一 session
- assistant follow-up 回复继续写入同一 session
- 不新建第二个无关 finding session

## 9. 当前建议

当前最合理的下一步不是立刻删 legacy，而是：
1. 保持默认 `legacy`
2. 开始真实项目 runtime 灰度
3. 跑完至少一轮人工审计验证
4. 再决定是否把默认值切到 `runtime`
5. 默认 runtime 稳定后，再进入 legacy 下线实施