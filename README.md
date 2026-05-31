# 法规对比工具原型

这是一个本地 Web 原型，用于上传两份 PDF 法规/标准文件，按条款提取文本、自动匹配相似条款，并输出可追溯的差异列表。

## 当前能力

- 上传两个 PDF。
- 提取每页文本。
- 按常见编号、章节、条款、Annex / Appendix 切分。
- 用文本相似度匹配左右条款。
- 标记新增、删除、数值变化、引用标准变化、测试方法变化、适用范围变化、定义变化等类型。
- 展示左右原文、页码、匹配度、风险等级和证据片段。

## 启动

使用 Codex 自带 Python：

```powershell
& 'C:\Users\chich\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' app.py
```

然后打开：

```text
http://127.0.0.1:8000
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
& 'C:\Users\chich\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' tools\download_un_r13.py
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
& 'C:\Users\chich\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' tools\build_regulation_corpus.py
```

总清单在 `data/regulations/manifest.json`。UN/EU/US 可公开下载文本已落地；中国 GB/GB-T、ISO、SAE 中无法公开直接下载的条目以 metadata JSON 占位。

## 批量自检

按同一技术领域自动两两对比法规库中的已下载文本：

```powershell
& 'C:\Users\chich\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' tools\evaluate_category_comparisons.py
```

输出：

- `data/evaluations/category_comparison_report.json`
- `data/evaluations/category_comparison_report.md`

这个自检用于发现目录、封面、页码、短标题和跨体系法规结构差异造成的误报。
