"""AccountSubjectManager — chart of accounts and subject matching (Layer 1, paper §4.2).

Maintains a 44-subject chart aligned with Chinese enterprise accounting
standards and maps free-text descriptions onto subject codes via a keyword
knowledge base (embedding retrieval plus model disambiguation in production).
"""
from enum import Enum
from typing import Dict, List, Optional


class AccountType(Enum):
    ASSET = "资产"
    LIABILITY = "负债"
    EQUITY = "所有者权益"
    REVENUE = "收入"
    EXPENSE = "费用"


class AccountSubjectManager:
    """Subject tree with keyword matching and balance maintenance."""

    def __init__(self):
        self.subjects: Dict[str, dict] = {}
        self._init_default_subjects()

    def _init_default_subjects(self):
        """Seed the 44-subject chart (assets 1001-1701, liabilities 2001-2501,
        equity 4001-4104, profit-and-loss 5001-6801)."""
        defaults = [
            ("1001", "库存现金", AccountType.ASSET), ("1002", "银行存款", AccountType.ASSET),
            ("1012", "其他货币资金", AccountType.ASSET), ("1101", "短期投资", AccountType.ASSET),
            ("1121", "应收票据", AccountType.ASSET), ("1122", "应收账款", AccountType.ASSET),
            ("1123", "预付账款", AccountType.ASSET), ("1131", "应收股利", AccountType.ASSET),
            ("1132", "应收利息", AccountType.ASSET), ("1221", "其他应收款", AccountType.ASSET),
            ("1401", "材料采购", AccountType.ASSET), ("1402", "在途物资", AccountType.ASSET),
            ("1403", "原材料", AccountType.ASSET), ("1405", "库存商品", AccountType.ASSET),
            ("1601", "固定资产", AccountType.ASSET), ("1602", "累计折旧", AccountType.ASSET),
            ("1701", "无形资产", AccountType.ASSET),
            ("2001", "短期借款", AccountType.LIABILITY), ("2201", "应付票据", AccountType.LIABILITY),
            ("2202", "应付账款", AccountType.LIABILITY), ("2203", "预收账款", AccountType.LIABILITY),
            ("2211", "应付职工薪酬", AccountType.LIABILITY), ("2221", "应交税费", AccountType.LIABILITY),
            ("2231", "应付利息", AccountType.LIABILITY), ("2241", "应付股利", AccountType.LIABILITY),
            ("2251", "其他应付款", AccountType.LIABILITY), ("2501", "长期借款", AccountType.LIABILITY),
            ("4001", "实收资本", AccountType.EQUITY), ("4002", "资本公积", AccountType.EQUITY),
            ("4101", "盈余公积", AccountType.EQUITY), ("4103", "本年利润", AccountType.EQUITY),
            ("4104", "利润分配", AccountType.EQUITY),
            ("5001", "生产成本", AccountType.EXPENSE), ("5101", "制造费用", AccountType.EXPENSE),
            ("6001", "主营业务收入", AccountType.REVENUE), ("6051", "其他业务收入", AccountType.REVENUE),
            ("6111", "投资收益", AccountType.REVENUE), ("6301", "营业外收入", AccountType.REVENUE),
            ("6401", "主营业务成本", AccountType.EXPENSE), ("6402", "其他业务成本", AccountType.EXPENSE),
            ("6601", "销售费用", AccountType.EXPENSE), ("6602", "管理费用", AccountType.EXPENSE),
            ("6603", "财务费用", AccountType.EXPENSE), ("6711", "营业外支出", AccountType.EXPENSE),
            ("6801", "所得税费用", AccountType.EXPENSE),
        ]
        for code, name, atype in defaults:
            self.subjects[code] = {"code": code, "name": name, "type": atype, "balance": 0.0}

    def get_subject(self, code: str) -> Optional[dict]:
        """Look up a subject by chart code."""
        return self.subjects.get(code)

    # Keyword knowledge base: description keywords -> subject code.
    KEYWORD_MAP = {
        "工资": "2211", "薪酬": "2211", "采购": "1403", "原材料": "1403",
        "销售": "6001", "收入": "6001", "费用": "6602", "管理": "6602",
        "税": "2221", "增值税": "2221", "银行": "1002", "存款": "1002",
        "现金": "1001", "固定资产": "1601", "折旧": "1602", "借款": "2001",
    }
    FALLBACK_CODE = "6602"  # 管理费用 — unmatched documents land somewhere reviewable

    def ai_match_subject(self, description: str, amount: float = 0) -> Optional[dict]:
        """Map a free-text description onto the chart of accounts.

        Unmatched descriptions fall back to a conservative default so they land
        in a reviewable place rather than being dropped.
        """
        for kw, code in self.KEYWORD_MAP.items():
            if kw in description:
                return self.subjects.get(code)
        return self.subjects.get(self.FALLBACK_CODE)

    def update_balance(self, code: str, debit: float, credit: float):
        """Post an entry to a subject balance (debit-positive for assets and
        expenses, credit-positive otherwise)."""
        subject = self.subjects.get(code)
        if subject is None:
            return
        if subject["type"] in (AccountType.ASSET, AccountType.EXPENSE):
            subject["balance"] += debit - credit
        else:
            subject["balance"] += credit - debit

    def get_by_type(self, account_type: AccountType) -> List[dict]:
        return [s for s in self.subjects.values() if s["type"] == account_type]
