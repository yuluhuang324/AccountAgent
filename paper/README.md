# Paper — AccountAgent

**AccountAgent**(AI 会计助手系统)是一个将多模态大语言模型与确定性财务引擎相耦合的端到端智能会计平台。本目录包含该系统的完整学术论文(编译好的 PDF)。

> **Paper**: [`AccountAgent.pdf`](AccountAgent.pdf) — 15 pages

## 论文速览

**AccountAgent** 以多模态大模型为核心、以确定性财务引擎为基础重构会计工作流,推动会计职能从"核算型"走向"管理型"。

### 核心贡献

1. **端到端系统设计** — 五层云原生架构,统一凭证处理、业财一体化、多维分析预警、税务合规与资金管理
2. **混合神经-符号方法论** — 视觉语言模型(14×14 patch ViT 编码器 · 24 层 · 两层 MLP 投影器 · 解码器 LLM)负责文档感知与解释;借贷平衡、税额计算、预测评分全部由可审计的确定性引擎完成
3. **可运行的参考实现** — 约 500 行 Python 标准库实现,五层全部可执行,`python src/pipeline.py` 一键复现论文流程
4. **评估与诚实的边界说明** — 主要指标与论文中披露的实现边界(开源版识别器为可插拔模拟器,生产版使用完整多模态模型)

### 主要指标

| 维度 | 指标 | 结果 |
|---|---|---|
| 凭证识别 | 字段准确率(30+ 票据类型) | **>99%** |
| 凭证处理 | 月度过账后错误率 | **<0.3%** |
| 业财一体化 | 月度结账时间 | **数天 → 1 天** |
| 资金管理 | 预测窗口 / 预警阈值 | **30 天 / 评分 < 70** |

### 引用

```bibtex
@article{huang2026accountagent,
  title   = {AccountAgent: An End-to-End AI Accounting Assistant System
             with Multimodal Voucher Processing and Intelligent Financial Control},
  author  = {Huang, Yulu and Yu, Niannian and Yang, Yaxin and Lv, Jinpeng},
  journal = {Project Report, Jiangxi University of Finance and Economics},
  year    = {2026}
}
```

### 许可

手稿(`AccountAgent.pdf`)采用 [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) 许可,见 [LICENSE-paper.md](LICENSE-paper.md)。
