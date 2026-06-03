# 内部功能测试执行报告 - 2026-06-02

测试范围：功能闭环，不评估法规答案精度  
测试环境：本机临时服务 `127.0.0.1:8091`  
测试账号：管理员 `xingchi.wang@zf.com`  
OCR：本轮 API 功能测试关闭 OCR，OCR 只做触发条件检查

## 1. 执行摘要

本轮已完成：

- 登录和会话检查
- 未登录接口保护检查
- 管理员后台接口检查
- 通用反馈提交和后台可见性检查
- 本地法规库问答检查
- FMVSS 223 参数证据命中检查
- 单文档 TXT 上传和问答检查
- 双文档 TXT 对比检查
- 页面可见中文文案检查
- 前端 JS 语法检查
- 静态 DOM 元素和 tab 绑定检查

总体结论：

- 主功能链路基本可用。
- 反馈能正确写入后台，并能被管理员读取。
- 管理员后台三个数据接口可用。
- 对比和上传功能 API 闭环可用。
- 页面中文文案在浏览器中正常显示。
- 存在一个与原始产品需求不一致的 P1：测试用户目前是邀请码登录即 approved，没有真正的管理员审批流。

## 2. 自动化检查结果

| ID | 检查项 | 结果 | 备注 |
| --- | --- | --- | --- |
| ENV-01 | `/healthz` | Pass | 返回 `ok=true` |
| ENV-03 | 未登录请求 `/api/ask` | Pass | 返回 401 |
| ENV-04 | 未登录请求 `/api/admin/feedback` | Pass | 返回 403 |
| AUTH-01 | 管理员登录 | Pass | 返回 `role=admin` |
| AUTH-06 | 会话保持 | Pass | `/api/session` 返回管理员用户 |
| FB-04 | 反馈提交 | Pass | 返回 `ok=true` |
| FB-05 | 管理员后台读取反馈 | Pass | 能看到 `AUTO_TEST_FEEDBACK_*` |
| ADM-02 | 管理员使用记录接口 | Pass | 有 usage 数据 |
| ADM-03 | 管理员归档法规接口 | Pass | endpoint 可访问 |
| QA-02 | 本地法规库问答 | Pass | 返回答案和证据 |
| QA-FMVSS223 | FMVSS 223 参数证据 | Pass | Top evidence 命中 `FMVSS 223` 且含 `50,000 N` |
| UP-01 | 单文档 TXT 上传 | Pass | 返回 doc_id、pages、clauses |
| QA-03 | 上传文档后定向问答 | Pass | 返回上传文档证据 |
| CMP-03 | TXT vs TXT 对比 | Pass | 返回 conclusion 和 results |
| UI-STATIC | 前端 JS 语法 | Pass | `node --check static/app.js` 通过 |
| UI-TEXT | 浏览器可见中文 | Pass | 浏览器正文中文正常，无 mojibake |
| UI-DOM | tab/dialog/admin 元素存在 | Pass | 主要元素和绑定函数存在 |

## 3. 已确认后台证据

反馈写入：

- `data/feedback.jsonl` 新增 `AUTO_TEST_FEEDBACK_*`
- 字段包含：`created_at`、`user`、`type`、`message`、`contact`、`context`
- 管理员 `/api/admin/feedback` 可读取到该条

使用记录：

- `data/usage.jsonl` 新增 login / ask 等记录
- 管理员 `/api/admin/usage` 可读取

归档法规：

- 单文档上传后生成 doc_id
- 管理员 `/api/admin/uploads` 可读取归档列表

## 4. Bug 清单

### BUG-20260602-001：测试用户没有真正进入待审批状态

严重程度：P1  
功能区：登录 / 管理员审批  
复现步骤：

1. 使用有效邀请码和新的普通邮箱登录。
2. 查看登录返回值和 `/api/admin/users`。

实际结果：

- 新测试用户直接返回 `status=approved`。
- `approved_at` 立即生成。
- 管理员不需要审批，用户已可直接使用。

期望结果：

- 普通用户首次使用邀请码后应进入 `pending` 或 `requested` 状态。
- 管理员在后台看到申请后点击 approve。
- 用户被 approve 后才能使用工具。

影响：

- 不符合“先给几个同事测试，管理员 approve 后使用”的内测管理设计。
- 管理员无法控制谁真正进入测试。

建议修复：

- `handle_login` 中新普通用户默认 `status=pending`。
- pending 用户登录后返回“等待管理员审批”，不创建可用 session 或只创建受限 session。
- 管理后台增加“用户审批”tab 或在现有后台增加待审批列表和 approve 按钮。

### BUG-20260602-002：usage 日志中的部分中文 detail 出现乱码

严重程度：P2  
功能区：管理后台 / 使用记录  
复现步骤：

1. 管理员登录。
2. 查看 `data/usage.jsonl` 或管理员使用记录。

实际结果：

- login 记录 detail 出现类似 `绠＄悊鍛?` 的乱码。

期望结果：

- 显示“管理员”或“测试用户”。

影响：

- 管理员后台可读性下降。
- 后续用 usage 做分析时需要清洗。

建议修复：

- 检查 `app.py` 中所有硬编码中文错误提示和 usage detail。
- 用 UTF-8 重新保存源码，避免 mojibake 文案继续写入数据文件。

### BUG-20260602-003：历史 feedback 行结构不一致

严重程度：P2  
功能区：反馈后台  
复现步骤：

1. 查看 `data/feedback.jsonl`。
2. 对比新旧反馈行。

实际结果：

- 旧行包含 `admin/user/type/message/contact`。
- 新行包含 `created_at/user/type/message/contact/context`。

期望结果：

- 管理后台能兼容旧结构，或迁移旧数据。
- 每条反馈都应有统一字段，至少有时间、用户、类型、内容、上下文。

影响：

- 管理后台表格可能显示旧行时间为空。
- 后续做反馈统计或 agent 优化数据集时格式不统一。

建议修复：

- 增加 feedback 读取时的 normalization。
- 给旧行补 `created_at` 或显示为“历史反馈”。

### BUG-20260602-004：JSON 请求带 UTF-8 BOM 时后端解析失败

严重程度：P3  
功能区：API 鲁棒性  
复现步骤：

1. 用 PowerShell 5 `Set-Content -Encoding UTF8` 写 JSON 请求体。
2. POST 到 `/api/ask`。

实际结果：

- 返回 `Unexpected UTF-8 BOM`。

期望结果：

- 后端使用 `utf-8-sig` 或去除 BOM 后解析。

影响：

- 浏览器正常请求不受影响。
- 外部脚本或测试工具可能踩坑。

建议修复：

- 所有 JSON body decode 改为 `decode("utf-8-sig")`。

## 5. 未完整执行的项目

| 项目 | 原因 | 建议 |
| --- | --- | --- |
| 真实 PDF 上传对比 | 本轮为快速功能闭环，使用 TXT 做最小文件验证 | 内测前用 2 组真实法规 PDF 再跑 |
| 移动端视觉截图 | 本轮未做截图基线 | 用浏览器 390px / 768px / 1440px 三档检查 |
| UN R93 实际 OCR 完成 | 本机没有 `ocrmypdf`，ECS 部署脚本会安装 | 在 ECS 首次预热后检查 OCR cache |
| 用户审批 UI | 当前产品没有审批 UI | 修复 BUG-001 后补测 |

## 6. 下一轮建议

优先修复：

1. P1 用户审批流。
2. 管理后台增加“用户审批”tab。
3. usage/feedback 数据格式 normalization。
4. JSON BOM 兼容。

然后再执行完整人工验收：

1. 管理员登录。
2. 普通测试用户申请。
3. 管理员 approve。
4. 测试用户完成对比、问答、提交三类反馈。
5. 管理员后台逐 tab 核查。
6. ECS 首次预热后复测 OCR 和缓存速度。

