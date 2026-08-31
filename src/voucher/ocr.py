"""OCREngine — multimodal voucher recognition (Layer 1, paper §4.1).

The production system instantiates the recognition stage with a vision-language
model (14x14-patch ViT encoder, 24 blocks, 2-layer MLP projector, decoder
LLM). This reference implementation realizes the same interface with a
deterministic simulator (hash-seeded amounts, fixed confidence of 0.992) so
the repository runs end to end with zero third-party dependencies; every
downstream module depends only on the recognizer contract, not on the model
backend. Per-type field patterns and keyword type detection are shared between
both backends (they validate model output in production).
"""
import hashlib
import threading
import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class VoucherType(Enum):
    """Voucher types recognized by the system."""
    VAT_INVOICE = "增值税发票"
    BANK_STATEMENT = "银行回单"
    EXPENSE_REPORT = "费用报销单"
    PURCHASE_ORDER = "采购订单"
    SALES_ORDER = "销售订单"
    RECEIPT = "收据"
    CONTRACT = "合同"
    OTHER = "其他"


@dataclass
class OCRResult:
    """Result of recognizing one document image."""
    success: bool
    confidence: float
    voucher_type: VoucherType
    fields: Dict[str, object] = field(default_factory=dict)
    raw_text: str = ""
    processing_time: float = 0.0


class OCREngine:
    """Recognition engine: per-type field patterns, keyword type detection,
    batch recognition, and accuracy statistics."""

    VOUCHER_PATTERNS = {
        VoucherType.VAT_INVOICE: {
            'amount': r'金额[：:]\s*[¥￥]?\s*([\d,]+\.?\d*)',
            'tax_rate': r'税率[：:]\s*(\d+)%',
            'supplier': r'销售方[：:]\s*(.+?)(?:\n|$)',
            'invoice_no': r'发票号码[：:]\s*(\d+)',
            'date': r'开票日期[：:]\s*(\d{4}年\d{1,2}月\d{1,2}日)',
        },
        VoucherType.BANK_STATEMENT: {
            'amount': r'金额[：:]\s*[¥￥]?\s*([\d,]+\.?\d*)',
            'date': r'交易日期[：:]\s*(\d{4}-\d{2}-\d{2})',
            'counterparty': r'对方户名[：:]\s*(.+?)(?:\n|$)',
            'transaction_no': r'交易流水号[：:]\s*(\w+)',
        },
        VoucherType.EXPENSE_REPORT: {
            'amount': r'报销金额[：:]\s*[¥￥]?\s*([\d,]+\.?\d*)',
            'applicant': r'申请人[：:]\s*(.+?)(?:\n|$)',
            'department': r'部门[：:]\s*(.+?)(?:\n|$)',
            'date': r'日期[：:]\s*(\d{4}-\d{2}-\d{2})',
        },
    }

    KEYWORDS = {
        VoucherType.VAT_INVOICE: ('增值税', '发票号码', '销售方', '购买方'),
        VoucherType.BANK_STATEMENT: ('银行', '交易流水', '账号', '余额'),
        VoucherType.EXPENSE_REPORT: ('报销', '费用', '申请人', '审批'),
    }

    def __init__(self, default_tax_rate: int = 13):
        self.default_tax_rate = default_tax_rate
        self.recognition_count = 0
        self.success_count = 0
        self._lock = threading.Lock()

    # -- recognition --------------------------------------------------------
    def recognize(self, image_path: str,
                  voucher_type: Optional[VoucherType] = None) -> OCRResult:
        """Recognize one voucher image and extract structured fields.

        The simulator derives a deterministic amount from the image path so runs
        are reproducible; the field schema matches the production model output.
        """
        with self._lock:
            self.recognition_count += 1

        seed = int(hashlib.md5(image_path.encode('utf-8')).hexdigest(), 16)
        amount = round(1000 + seed % 50000, 2)
        detected = self.detect_voucher_type(image_path)
        # Simulator default: unrecognized paths become VAT invoices so every
        # simulated document produces a voucher template.
        vtype = voucher_type or (detected if detected != VoucherType.OTHER
                                else VoucherType.VAT_INVOICE)

        fields = {
            'amount': amount,
            'date': datetime.date.today().strftime('%Y-%m-%d'),
            'supplier': '示例供应商有限公司',
            'tax_rate': self.default_tax_rate,
        }
        fields['tax_amount'] = round(amount * fields['tax_rate'] / 100, 2)

        with self._lock:
            self.success_count += 1

        return OCRResult(success=True, confidence=0.992, voucher_type=vtype,
                        fields=fields, raw_text=image_path)

    def batch_recognize(self, image_paths: List[str],
                       voucher_type: Optional[VoucherType] = None) -> List[OCRResult]:
        """Recognize a batch of voucher images, reporting per-document success."""
        results = [self.recognize(p, voucher_type) for p in image_paths]
        ok = sum(1 for r in results if r.success)
        print(f"批量识别完成，共{len(image_paths)}张，成功{ok}张")
        return results

    # -- classification ------------------------------------------------------
    def detect_voucher_type(self, text: str) -> VoucherType:
        """Keyword-scoring classification of recognized text."""
        scores = {vtype: sum(kw in text for kw in kws)
                 for vtype, kws in self.KEYWORDS.items()}
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else VoucherType.OTHER

    # -- statistics -----------------------------------------------------------
    def get_stats(self) -> Dict[str, float]:
        """Recognition statistics: total, successful, accuracy rate."""
        rate = self.success_count / self.recognition_count \
            if self.recognition_count > 0 else 0
        return {'total': self.recognition_count,
                'success': self.success_count,
                'accuracy_rate': round(rate * 100, 2)}
