# 场景拆解：AutoCVE 如何从 GitHub 项目筛选走到 CVE 报告复制

> 适合平台：先知社区、FreeBuf、安全客、公众号、知乎  
> 建议标题：一键 CVE 挖掘不是一句口号：AutoCVE 的批次任务链路拆解  
> 建议配图：一键 CVE 页面、候选项目列表、漏洞管理、CVE 报告标签页

## 开头

很多人听到“一键 CVE”会本能警惕，因为这四个字很容易被讲成夸张营销。

所以先说清楚：AutoCVE 的“一键 CVE”不是保证自动拿编号，也不是鼓励批量无授权测试。它更准确的定位是：

**自动发现 CVE 候选项目，自动启动 Agent 审计，自动沉淀漏洞和报告材料，最后由安全研究员人工复核并负责任披露。**

这篇文章从实际链路拆一下 AutoCVE 的一键 CVE 功能。

项目地址：`<GitHub 仓库链接>`

## CVE 挖掘的重复流程

手工挖 CVE 时，很多步骤都非常重复：

1. 找项目。
2. 判断项目是否活跃。
3. 看有没有 release/tag。
4. 看是否有 SECURITY.md。
5. 看是否支持 GitHub private vulnerability reporting。
6. 导入仓库。
7. 创建审计任务。
8. 等待扫描或人工阅读。
9. 整理 finding。
10. 写报告。
11. 按平台字段提交。

其中真正需要人判断的是漏洞证据、影响范围和披露策略。

但前面的项目筛选、任务创建、结果整理，其实非常适合系统自动做。

AutoCVE 的一键 CVE 就是从这里切入。

## 第一步：输入目标数量

用户在一键 CVE 页面输入目标数量，比如：

```text
目标 CVE 候选数量：5
```

系统会创建一个 batch。

这个 batch 的状态包括：

- pending
- running
- completed
- failed
- cancelled
- exhausted

它不是单次任务，而是一个批次调度器：会持续筛项目、导入、审计、统计结果，直到达到目标数量或者候选耗尽。

## 第二步：GitHub 候选项目筛选

AutoCVE 会从 GitHub 搜索候选项目。

候选筛选会关注几个信号：

- star 数
- 最近 push 时间
- 是否归档
- 是否 fork
- 项目描述和语言
- 是否存在 security advisories
- advisory 数量
- 是否存在 SECURITY.md
- 是否开启 private vulnerability reporting
- latest release / latest tag / default branch

这里的思路很现实：不是所有项目都适合优先挖。

一个近期活跃、有安全响应入口、有 release/tag、维护状态较好的项目，更适合做负责任披露和 CVE 跟进。

## 第三步：自动导入项目

选到候选项目后，AutoCVE 会把项目作为 repository 类型导入。

如果项目已经存在，会复用已有记录。

如果当前用户已经对同一项目和同一版本产生过漏洞管理记录，系统会跳过，避免重复审计同一版本。

导入项目时会记录：

- GitHub full name
- repository url
- description
- language
- stars
- default branch
- version label
- version source
- security advisory 信号
- private vulnerability reporting 信号

这使得后续漏洞结果能关联回具体项目和版本。

## 第四步：自动创建 Agent 审计任务

每个候选项目会创建一个 AgentTask。

任务里会带上一键 CVE 的上下文：

- batch id
- GitHub full name
- version label
- version source
- advisory count
- private vulnerability reporting 状态

同时会设置一些默认排除规则，例如：

- `node_modules`
- `__pycache__`
- `.git`
- `*.min.js`
- `dist`
- `build`
- `vendor`

这样可以减少无关文件对审计的干扰。

## 第五步：Agent 审计

审计任务会进入 AutoCVE 的 Agent 工作流。

根据配置，系统可以执行：

- Recon：项目结构和攻击面识别
- Scan：自动化扫描
- Triage：候选复核
- Finding：源码深挖
- Verification：沙箱验证

如果目标是 CVE 挖掘，Finding Agent 是最核心的。

它会通过 ReAct loop 多轮阅读代码、搜索调用链、补充证据，并最终通过 `FinalizeFinding` 提交结构化漏洞结果。

## 第六步：统计 findings

每个项目审计完成后，batch 会统计该任务产生的非误报 findings。

如果发现数量达到用户请求的目标数量，batch 完成。

如果候选项目跑完还不够，则标记为 exhausted。

这个设计比“跑一个项目然后结束”更接近真实工作流，因为 CVE 挖掘本来就不是每个项目都能稳定产出高价值漏洞。

## 第七步：进入漏洞管理

审计结果会进入漏洞管理模块。

这里可以做几件事：

- 查看漏洞列表
- 按项目、版本、漏洞类型、CVE 状态筛选
- 人工确认或标记误报
- 编辑漏洞名称、等级、CVE 状态
- 打开漏洞报告
- 复制或导出 Markdown

这一步很关键。

AutoCVE 不希望用户把模型输出直接当成最终结论，而是提供一个管理和复核界面，让安全研究员继续把关。

## 第八步：生成可复制报告

漏洞报告通常包含三个标签：

- 中文报告
- English Report
- CVE 报告

报告内容会围绕披露和提交场景组织，包括：

- Summary
- Details
- PoC
- Impact
- Remediation
- Affected products
- CWE
- CVSS
- Suggested CVE description
- References

如果通过 GitHub Advisory 报告漏洞，Summary、Details、PoC、Impact 等字段可以直接作为基础材料复制过去，再根据项目实际情况人工修改。

如果走 CNA 或其他平台，CVE 报告页也提供了更贴近 CVE 提交流程的字段。

## 为什么不是全自动提交

AutoCVE 没有设计成“自动提交 CVE”。

原因很简单：负责任披露需要人工判断。

自动提交可能带来几个问题：

- 漏洞误报骚扰维护者
- 影响范围不准确
- 复现步骤不完整
- 披露对象不合适
- 时间线和协调流程不合规
- 对开源社区造成负担

所以 AutoCVE 更适合定位为：

```text
CVE candidate discovery + evidence collection + report drafting
```

最终提交仍然应该由研究员完成。

## 这个功能适合什么场景

适合：

- 想批量寻找高价值审计目标
- 想减少重复导入和建任务操作
- 想统一管理漏洞和报告
- 想研究 AI Agent 在代码审计中的落地方式
- 想做 CVE 候选发现和报告辅助

不适合：

- 未授权扫描
- 自动骚扰维护者
- 把模型结果不复核就提交
- 期待系统保证拿到 CVE 编号

## 总结

AutoCVE 的一键 CVE 功能，本质上是在自动化 CVE 挖掘中的重复工程步骤：

```text
GitHub 项目筛选
-> 项目导入
-> Agent 审计任务创建
-> 漏洞结果统计
-> 漏洞管理
-> 报告生成
-> 人工复核和披露
```

它的价值不是替代安全研究员，而是让研究员把更多时间花在漏洞判断和证据复核上。

如果你也经常在“找项目、建任务、整理报告”之间消耗大量时间，可以试试 AutoCVE。

项目地址：`<GitHub 仓库链接>`

