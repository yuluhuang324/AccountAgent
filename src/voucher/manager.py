"""VoucherManager — voucher lifecycle with hard double-entry validation (Layer 1, paper §4.2/§4.6).

Workflow: pending -> reviewing -> approved/rejected -> completed. Ledger effects
occur only at approval (posting). Vouchers violating |sum(debit)-sum(credit)| < 0.01
are rejected at creation; subject codes are validated against the chart.
"""
import datetime
import threading
import uuid
from enum import Enum
from typing import Dict, List, Optional

from .subject import AccountSubjectManager
from .ocr import OCRResult, VoucherType


class WorkflowStatus(Enum):
    PENDING = "待处理"
    REVIEWING = "审核中"
    APPROVED = "已审批"
    REJECTED = "已拒绝"
    COMPLETED = "已完成"


class VoucherManager:
    """Creation with balance validation, OCR-to-voucher conversion, workflow
    transitions, batch processing, multi-condition queries."""

    def __init__(self, subject_manager: AccountSubjectManager):
        self.subject_manager = subject_manager
        self.vouchers: Dict[str, dict] = {}
        self._sequence = 0
        self._lock = threading.Lock()

    def _generate_id(self) -> str:
        with self._lock:
            self._sequence += 1
            date_str = datetime.date.today().strftime('%Y%m%d')
            return f"PZ{date_str}{self._sequence:04d}"

    # -- creation ------------------------------------------------------------
    def create_voucher(self, voucher_type, entries: List[dict],
                      creator: str, remark: str = "") -> dict:
        """Create a voucher; raises ValueError when debits and credits do not balance."""
        vid = self._generate_id()
        voucher = {
            'voucher_id': vid, 'voucher_type': voucher_type,
            'voucher_date': datetime.date.today(), 'entries': entries,
            'status': WorkflowStatus.PENDING, 'creator': creator, 'remark': remark,
            'created_at': datetime.datetime.now(),
        }
        if not self.is_balanced(voucher):
            raise ValueError(
                f"凭证借贷不平衡: 借方{self._total_debit(voucher)}, "
                f"贷方{self._total_credit(voucher)}")
        self.vouchers[vid] = voucher
        return voucher

    def create_from_ocr(self, ocr_result: OCRResult, creator: str) -> Optional[dict]:
        """Generate a balanced voucher from a recognition result via the
        per-type double-entry templates."""
        if not ocr_result.success:
            return None
        fields = ocr_result.fields
        amount = fields.get('amount', 0)
        tax = fields.get('tax_amount', 0)

        def entry(account, name, debit=0.0, credit=0.0):
            return {'entry_id': str(uuid.uuid4())[:8], 'account': account,
                    'name': name, 'debit': debit, 'credit': credit}

        vtype = ocr_result.voucher_type
        if vtype == VoucherType.VAT_INVOICE:
            entries = [entry('1403', '原材料', debit=amount),
                       entry('2221', '应交税费', debit=tax),
                       entry('2202', '应付账款', credit=amount + tax)]
        elif vtype == VoucherType.BANK_STATEMENT:
            entries = [entry('1002', '银行存款', debit=amount),
                      entry('6001', '主营业务收入', credit=amount)]
        elif vtype == VoucherType.EXPENSE_REPORT:
            entries = [entry('6602', '管理费用', debit=amount),
                      entry('1002', '银行存款', credit=amount)]
        else:
            return None
        return self.create_voucher(vtype, entries, creator, remark="OCR 自动生成")

    # -- workflow -------------------------------------------------------------
    def submit_for_review(self, voucher_id: str) -> bool:
        v = self.vouchers.get(voucher_id)
        if v and v['status'] == WorkflowStatus.PENDING:
            v['status'] = WorkflowStatus.REVIEWING
            v['updated_at'] = datetime.datetime.now()
            return True
        return False

    def approve_voucher(self, voucher_id: str, approver: str) -> bool:
        """Approve and post: applies each entry to subject balances
        (debit-positive for assets and expenses, credit-positive otherwise)."""
        v = self.vouchers.get(voucher_id)
        if not v or v['status'] != WorkflowStatus.REVIEWING:
            return False
        v['status'] = WorkflowStatus.APPROVED
        v['approver'] = approver
        v['updated_at'] = datetime.datetime.now()
        for e in v['entries']:
            self.subject_manager.update_balance(
                e['account'], e.get('debit', 0), e.get('credit', 0))
        return True

    def reject_voucher(self, voucher_id: str, reviewer: str, reason: str) -> bool:
        v = self.vouchers.get(voucher_id)
        if not v:
            return False
        v['status'] = WorkflowStatus.REJECTED
        v['reviewer'] = reviewer
        v['remark'] += f" | 拒绝原因: {reason}"
        v['updated_at'] = datetime.datetime.now()
        return True

    def batch_process(self, voucher_ids: List[str], action: str,
                     operator: str) -> Dict[str, List[str]]:
        """Apply a workflow action (submit/approve) to many vouchers at once."""
        results = {'success': [], 'failed': []}
        for vid in voucher_ids:
            try:
                if action == 'submit':
                    ok = self.submit_for_review(vid)
                elif action == 'approve':
                    ok = self.approve_voucher(vid, operator)
                else:
                    ok = False
                (results['success'] if ok else results['failed']).append(vid)
            except Exception:
                results['failed'].append(vid)
        return results

    # -- query / validation ----------------------------------------------------
    def query_vouchers(self, status: Optional[WorkflowStatus] = None,
                      voucher_type: Optional[VoucherType] = None,
                      start_date=None, end_date=None) -> List[dict]:
        """Query vouchers with optional status / type / date-range filters."""
        results = list(self.vouchers.values())
        if status:
            results = [v for v in results if v['status'] == status]
        if voucher_type:
            results = [v for v in results if v['voucher_type'] == voucher_type]
        if start_date:
            results = [v for v in results if v['voucher_date'] >= start_date]
        if end_date:
            results = [v for v in results if v['voucher_date'] <= end_date]
        return sorted(results, key=lambda v: v['created_at'], reverse=True)

    def validate_voucher(self, voucher: dict) -> List[str]:
        """Structural validation: non-empty entries, balance, creator, subject codes."""
        errors = []
        if not voucher['entries']:
            errors.append("凭证无分录")
        if not self.is_balanced(voucher):
            errors.append("借贷不平衡")
        if not voucher['creator']:
            errors.append("缺少制单人")
        for e in voucher['entries']:
            if self.subject_manager.get_subject(e['account']) is None:
                errors.append(f"科目代码不存在: {e['account']}")
        return errors

    def get_summary(self) -> Dict[str, int]:
        """Voucher counts by status and by type."""
        by_status: Dict[str, int] = {}
        by_type: Dict[str, int] = {}
        for v in self.vouchers.values():
            by_status[v['status'].value] = by_status.get(v['status'].value, 0) + 1
            name = getattr(v['voucher_type'], 'value', str(v['voucher_type']))
            by_type[name] = by_type.get(name, 0) + 1
        return {'total': len(self.vouchers),
                'by_status': by_status, 'by_type': by_type}

    # -- balance helpers ---------------------------------------------------------
    @staticmethod
    def _total_debit(voucher) -> float:
        return sum(e.get('debit', 0) for e in voucher['entries'])

    @staticmethod
    def _total_credit(voucher) -> float:
        return sum(e.get('credit', 0) for e in voucher['entries'])

    @classmethod
    def is_balanced(cls, voucher) -> bool:
        return abs(cls._total_debit(voucher) - cls._total_credit(voucher)) < 0.01
