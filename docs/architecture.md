# AccountAgent — Architecture Summary

AccountAgent is a five-layer AI accounting assistant. Each architectural layer corresponds
one-to-one to a package under `src/` and to a section of the paper.

## Layered view

```
┌─────────────────────────────────────────────────────────────────────┐
│ Layer 5 · Intelligent Fund Management and Forecasting              │  src/fund/
│   30-day forecast · health score /100 · low-score warning         │
├─────────────────────────────────────────────────────────────────────┤
│ Layer 4 · Full-Pipeline Tax-Compliance Management                 │  src/tax/
│   VAT 13/9/6/3% · income tax · stamp duty · deadline calendar    │
├─────────────────────────────────────────────────────────────────────┤
│ Layer 3 · Multidimensional Data Analysis and Warning              │  src/analytics/
│   rule alerts · OLS trends · 2σ anomalies · drill-down dashboard │
├─────────────────────────────────────────────────────────────────────┤
│ Layer 2 · Business–Finance Integrated Data Coordination           │  src/integration/
│   event bus → AR/AP auto-posting → close: days → 1 day           │
├─────────────────────────────────────────────────────────────────────┤
│ Layer 1 · Intelligent Voucher Full-Pipeline Processing            │  src/voucher/
│   multimodal recognition → subject matching → balanced entries    │
└─────────────────────────────────────────────────────────────────────┘
```

The layers form a **closed accounting loop**: recognized vouchers drive business–finance
integration; integration surfaces the anomalies that analysis flags; the analysis conditions
the tax-compliance checks; and the fund forecast's gaps redirect attention to the modules
that can close them.

## Key design decision: model where recognition is needed, compute deterministically

- The multimodal model (14×14-patch ViT encoder · 24 blocks · 2-layer MLP projector ·
  decoder LLM) handles **perception** (reading documents) and **interpretation** (matching
  free text to accounting subjects).
- Every numerical result is produced by an auditable deterministic engine:
  balanced entries (|Σdebit − Σcredit| < 0.01), VAT/income-tax/stamp-duty computation,
  OLS forecasts, and health scores are all traceable to their source.

## Module–class correspondence

| Module | Core class(es) | Responsibilities |
|---|---|---|
| `src/voucher/ocr.py` | `OCREngine` | Recognition contract with per-type field patterns, keyword type detection, batch recognition, accuracy statistics. |
| `src/voucher/subject.py` | `AccountSubjectManager` | 44-subject chart of accounts, keyword/embedding subject matching, balance updates, balance-sheet aggregation. |
| `src/voucher/manager.py` | `VoucherManager` | Voucher ID generation (`PZ`+date+sequence), creation with balance validation, OCR-to-voucher conversion, workflow transitions, batch actions. |
| `src/integration/bus.py` | `BusinessFinanceIntegration` | Event bus, sales/purchase order confirmation with automatic AR/AP posting, month-end closing, receivables aging. |
| `src/analytics/engine.py` | `DataAnalyticsEngine` | Rule-based alerts, moving averages, OLS forecasting, product profitability, 2σ anomaly detection, dashboard generation. |
| `src/tax/compliance.py` | `TaxComplianceManager` | VAT/income/stamp computation, declaration generation and submission, policy compliance checks, deadline reminders. |
| `src/fund/manager.py` | `CashFlowManager` | 30-day forecasting, health scoring, recommendations, inflow/outflow structure analysis. |
| `src/pipeline.py` | — | End-to-end orchestrator wiring the five layers. |

## Headline results

| Dimension | Metric | Result |
|---|---|---|
| Voucher recognition | Field accuracy, 30+ receipt types | >99% |
| Voucher processing | Monthly post-approval error rate | <0.3% |
| Business–finance integration | Monthly closing time | days → 1 day |
| Fund management | Forecast horizon / warning trigger | 30 days / score < 70 |

Full result tables are in [`results/`](../results/); methodology and evaluation detail are in
the paper ([`paper/AccountAgent.pdf`](../paper/AccountAgent.pdf)).

## Integrity note

The reference implementation's document-recognition stage is deliberately **pluggable**: the
public build ships with a deterministic simulator behind the `OCREngine` interface (so the
repository runs without model weights or third-party OCR dependencies), while the production
deployment uses the full multimodal model. This keeps every downstream module — entry
generation, integration, analysis, compliance, forecasting — fully executable and testable
against the recognizer contract, independent of the model backend.
