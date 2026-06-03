# 法规对比工具原型

这是一个本地 Web 原型，用于上传两份 PDF 法规/标准文件，按条款提取文本、自动匹配相似条款，并输出可追溯的差异列表。

## 当前能力

- 上传两个 PDF。
- 提取每页文本。
- 按常见编号、章节、条款、Annex / Appendix 切分。
- 用文本相似度匹配左右条款。
- 标记新增、删除、数值变化、引用标准变化、测试方法变化、适用范围变化、定义变化等类型。
- 展示左右原文、页码、匹配度、风险等级和证据片段。
- 自动抽取带单位的关键参数，生成左右法规参数矩阵。
- 支持按实质差异、高风险、参数变化筛选差异列表。

## 启动

推荐使用便携启动脚本。移动硬盘换电脑后，直接在项目目录运行：

```powershell
.\start.ps1
```

脚本会优先使用当前 Windows 用户目录下的 Codex 自带 Python；如果没有，再尝试系统 `python` / `py`。

也可以手动指定当前电脑上的 Codex Python，例如：

```powershell
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -W ignore::DeprecationWarning app.py
```

然后打开：

```text
http://127.0.0.1:8000
```

## 反馈闭环

用户可以通过顶部“提交反馈”提交通用问题；完成对比后，也可以在差异详情中点击“反馈这条结果”；完成问答后，可以点击答案或依据旁边的反馈按钮。

反馈会写入：

```text
data/feedback.jsonl
```

每条反馈会保存反馈类型、用户文字、联系方式，以及自动绑定的上下文，例如问题、答案、命中的法规片段、差异类型、风险等级、页码和证据摘要。这个文件可作为后续 agent 优化、误报/漏报分析和评测集构建的输入。

## 内部测试登录与审批

默认管理员账号：

```text
xingchi.wang@zf.com
```

内测用户登录流程：

1. 用户输入公司邮箱和测试邀请码。
2. 如果是管理员邮箱，会直接获得管理员权限。
3. 普通同事首次登录会进入待审批状态。
4. 管理员进入“测试管理”页，批准同事后，对方再次登录即可测试。
5. 管理员可在“测试管理”页查看带上下文的反馈列表。

可通过环境变量修改管理员和邀请码：

```powershell
$env:REG_ASSISTANT_ADMIN_EMAIL="xingchi.wang@zf.com"
$env:REG_ASSISTANT_LOGIN_CODE="your-internal-test-code"
.\start.ps1
```

## DeepSeek / Alibaba Cloud LLM

问答接口会先做本地法规片段检索，再把命中的证据交给 DeepSeek 生成答案。默认策略：

- 普通参数问答使用 `deepseek-v4-flash`。
- 长问题、风险/合规/差异判断、较长上下文自动切到 `deepseek-v4-pro`。
- 如果没有配置 API Key，系统会自动回退到本地规则检索答案。

阿里云百炼部署推荐配置：

```powershell
$env:DASHSCOPE_API_KEY="your-dashscope-api-key"
$env:REG_ASSISTANT_LLM_FLASH_MODEL="deepseek-v4-flash"
$env:REG_ASSISTANT_LLM_PRO_MODEL="deepseek-v4-pro"
.\start.ps1
```

如需直连 DeepSeek 官方 API：

```powershell
$env:DEEPSEEK_API_KEY="your-deepseek-api-key"
$env:REG_ASSISTANT_LLM_BASE_URL="https://api.deepseek.com"
.\start.ps1
```

也可以显式指定 OpenAI-compatible endpoint：

```powershell
$env:REG_ASSISTANT_LLM_API_KEY="your-api-key"
$env:REG_ASSISTANT_LLM_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
```

也可以在项目根目录新建 `.env`，服务启动时会自动读取：

```text
DASHSCOPE_API_KEY=your-dashscope-api-key
REG_ASSISTANT_LLM_FLASH_MODEL=deepseek-v4-flash
REG_ASSISTANT_LLM_PRO_MODEL=deepseek-v4-pro
```

用户审批数据保存在：

```text
data/users.json
```

这个文件和 `data/feedback.jsonl` 都不建议提交到 Git。

## 阿里云内测部署建议

建议先用一台阿里云 ECS 做小范围测试：

- 安全组只开放 `80/443`，不要直接暴露 `8000` 到公网。
- 在 ECS 上用 Nginx 反向代理到 `127.0.0.1:8000`。
- 配置 HTTPS 证书；登录 cookie 当前适合内测，正式使用前建议接入公司 SSO/OIDC。
- 把 `REG_ASSISTANT_LOGIN_CODE` 设置成只有测试同事知道的邀请码。
- 定期备份 `data/feedback.jsonl` 和 `data/users.json`。

当前 ECS/域名部署目标：

```text
Instance: i-uf6ed0drmsvtd9sphf6h / CVSchinaAI
Public IP: 139.224.204.17
Domain: https://cvs-regulation-compare.dev.zf-cds.com/
App port: 8083
```

部署包会生成在：

```text
dist/regulation-assistant-deploy.tar.gz
```

如果本机可以 SSH 到 ECS，可直接运行：

```powershell
.\deploy\deploy_via_ssh.ps1 -HostName 139.224.204.17 -User root -Port 8083
```

如果通过阿里云控制台“云助手”执行，先把部署包上传到 ECS，然后在解压目录运行：

```bash
sudo REG_ASSISTANT_HOST=0.0.0.0 REG_ASSISTANT_PORT=8083 bash deploy/install_on_ubuntu.sh
```

部署后检查：

```bash
systemctl status reg-assistant
curl http://127.0.0.1:8083/healthz
```

## 下一步建议

第一批请准备 3 到 5 组真实 PDF：

- 同一法规的新旧版本。
- 中国法规/标准与 EU 或 US 相似法规。
- 含大量表格、限值和测试条件的法规。

有真实样本后，优先优化：

- 条款标题识别规则。
- 表格结构化提取。
- 扫描件 OCR。
- 大模型解释层，但每条结论必须绑定原文和页码。

## 测试样本

已下载一批 UN Regulation No. 13 官方样本文档和 GB 12676-2014 英文样页到 `data/sources/`，来源记录在
`data/sources/un_r13_sources.json`。

注意：`GB_12676_2014_EN_sample_preview.pdf` 是英文样页预览，不是完整标准。官方中文全文目前未能直接公开下载。

可重新下载：

```powershell
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" tools\download_un_r13.py
```

## 重型商用车法规资料库

已按技术领域和地区归档到 `data/regulations/`：

- `01_braking_base`
- `02_esc_evsc`
- `03_aeb_aebs`
- `04_ldws_lka`
- `05_bsis_mois`
- `06_steering_ad`
- `07_axle_suspension`
- `08_ev_safety_charging`
- `09_visibility_lighting`
- `10_underrun_protection`
- `11_emc_connectivity`
- `12_emissions_noise`
- `13_tires_wheels`
- `14_coupling_marking`

可重新构建：

```powershell
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" tools\build_regulation_corpus.py
```

总清单在 `data/regulations/manifest.json`。UN/EU/US 可公开下载文本已落地；中国 GB/GB-T、ISO、SAE 中无法公开直接下载的条目以 metadata JSON 占位。

## 批量自检

按同一技术领域自动两两对比法规库中的已下载文本：

```powershell
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" tools\evaluate_category_comparisons.py
```

输出：

- `data/evaluations/category_comparison_report.json`
- `data/evaluations/category_comparison_report.md`

这个自检用于发现目录、封面、页码、短标题和跨体系法规结构差异造成的误报。
