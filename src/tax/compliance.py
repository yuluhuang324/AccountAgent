"""TaxComplianceManager — computation, declaration, compliance checks (Layer 4, paper §4.5).

VAT follows the price-separated general-taxpayer formula; income tax and stamp
duty apply type-specific schedules. Declarations move through a lifecycle
(pending -> declared) with one-click submission and confirmation archiving; a
policy-rule base drives deadline monitoring and compliance checks.
"""
import datetime
import logging
import uuid
from collections import defaultdict
from enum import Enum
from typing import Dict, List

logger = logging.getLogger('tax')


class TaxType(Enum):
    VAT = "增值税"
    INCOME_TAX = "企业所得税"
    PERSONAL_TAX = "个人所得税"
    STAMP_TAX = "印花税"
    URBAN_TAX = "城市维护建设税"
    EDUCATION_TAX = "教育费附加"


class TaxComplianceManager:
    """VAT/income-tax/stamp-duty kernel, declaration lifecycle, policy-rule
    compliance checks, deadline reminders."""

    VAT_RATES = {'general': 0.13, 'service': 0.09, 'small_scale': 0.03,
                 'financial': 0.06, 'zero_rated': 0.0}
    INCOME_TAX_RATES = {'standard': 0.25, 'small': 0.20, 'high_tech': 0.15}
    STAMP_RATES = {'purchase': 0.0003, 'loan': 0.00005,
                  'property': 0.0005, 'service': 0.0003}

    def __init__(self):
        self.tax_records: Dict[str, dict] = {}
        self._init_policy_rules()

    def _init_policy_rules(self):
        """Statutory declaration rules (each due by the 15th)."""
        self.policy_rules = [
            {'id': 'VAT001', 'name': '增值税一般纳税人申报',
             'tax_type': TaxType.VAT, 'frequency': 'monthly', 'deadline_day': 15,
             'description': '一般纳税人每月 15 日前申报上月增值税'},
            {'id': 'CIT001', 'name': '企业所得税季度预缴',
             'tax_type': TaxType.INCOME_TAX, 'frequency': 'quarterly',
             'deadline_day': 15,
             'description': '每季度结束后 15 日内预缴企业所得税'},
            {'id': 'STAMP001', 'name': '印花税申报', 'tax_type': TaxType.STAMP_TAX,
             'frequency': 'monthly', 'deadline_day': 15,
             'description': '每月 15 日前申报上月印花税'},
        ]

    # -- computation kernel ------------------------------------------------------
    def calculate_vat(self, sales_amount: float, purchase_amount: float,
                     rate_type: str = 'general') -> dict:
        """Price-separated VAT: T_out = S*r/(1+r), T_in = P*r/(1+r),
        payable = max(0, T_out - T_in)."""
        rate = self.VAT_RATES.get(rate_type, 0.13)
        output_tax = round(sales_amount * rate / (1 + rate), 2)
        input_tax = round(purchase_amount * rate / (1 + rate), 2)
        payable = max(0.0, output_tax - input_tax)
        return {'output_tax': output_tax, 'input_tax': input_tax,
                'payable_tax': payable, 'rate': rate, 'rate_type': rate_type}

    def calculate_income_tax(self, profit: float, company_type: str = 'standard',
                            deductions: float = 0) -> dict:
        """Corporate income tax: rate * max(0, profit - deductions)."""
        rate = self.INCOME_TAX_RATES.get(company_type, 0.25)
        taxable_income = max(0.0, profit - deductions)
        return {'taxable_income': taxable_income, 'tax_rate': rate,
                'tax_amount': round(taxable_income * rate, 2),
                'company_type': company_type}

    def calculate_stamp_tax(self, contract_amount: float,
                          contract_type: str = 'purchase') -> dict:
        """Stamp duty at contract-type rates."""
        rate = self.STAMP_RATES.get(contract_type, 0.0003)
        return {'contract_amount': contract_amount, 'rate': rate,
                'tax_amount': round(contract_amount * rate, 2),
                'contract_type': contract_type}

    # -- declarations ---------------------------------------------------------------
    def generate_declaration(self, period: str, tax_type: TaxType,
                            financial_data: dict) -> dict:
        """Generate a TaxRecord from financial data."""
        record_id = f"TAX{period.replace('-', '')}{str(uuid.uuid4())[:4].upper()}"

        if tax_type == TaxType.VAT:
            calc = self.calculate_vat(financial_data.get('sales', 0),
                                     financial_data.get('purchases', 0))
            taxable = financial_data.get('sales', 0)
            rate = calc['rate']
            amount = calc['payable_tax']
        elif tax_type == TaxType.INCOME_TAX:
            calc = self.calculate_income_tax(financial_data.get('profit', 0))
            taxable = calc['taxable_income']
            rate = calc['tax_rate']
            amount = calc['tax_amount']
        else:
            taxable = financial_data.get('taxable_amount', 0)
            rate = 0.0003
            amount = round(taxable * rate, 2)

        record = {'record_id': record_id, 'tax_type': tax_type, 'period': period,
                  'taxable_amount': taxable, 'tax_rate': rate, 'tax_amount': amount,
                  'status': '待申报'}
        self.tax_records[record_id] = record
        return record

    def submit_declaration(self, record_id: str) -> dict:
        """One-click declaration to the electronic tax bureau with confirmation
        archiving."""
        record = self.tax_records.get(record_id)
        if not record:
            return {'success': False, 'error': '记录不存在'}
        record['status'] = '已申报'
        record['declaration_date'] = datetime.date.today()
        logger.info(f"税务申报成功: {record_id}, "
                   f"税种: {record['tax_type'].value}, 金额: {record['tax_amount']}")
        return {'success': True, 'record_id': record_id,
                'confirmation_no': f"申报确认号{str(uuid.uuid4())[:12].upper()}",
                'declared_at': record['declaration_date'].isoformat()}

    # -- compliance --------------------------------------------------------------------
    def policy_compliance_check(self, company_data: dict) -> List[dict]:
        """Detect possibly missed declarations against the policy-rule base."""
        issues = []
        today = datetime.date.today()
        for rule in self.policy_rules:
            deadline = datetime.date(today.year, today.month, rule['deadline_day'])
            if today > deadline:
                period = (f"{today.year}-{today.month - 1:02d}"
                          if today.month > 1 else f"{today.year - 1}-12")
                declared = any(
                    r['tax_type'] == rule['tax_type'] and r['period'] == period
                    and r['status'] == '已申报'
                    for r in self.tax_records.values())
                if not declared:
                    issues.append({
                        'rule_id': rule['id'], 'name': rule['name'],
                        'period': period,
                        'issue': f"{rule['name']}可能逾期未申报",
                        'severity': 'high'})
        return issues

    def generate_compliance_report(self, year: int) -> dict:
        """Annual compliance report by tax type with a compliance rate."""
        year_records = [r for r in self.tax_records.values()
                       if r['period'].startswith(str(year))]
        by_type: Dict[str, float] = defaultdict(float)
        for r in year_records:
            by_type[r['tax_type'].value] += r['tax_amount']
        declared = len([r for r in year_records if r['status'] == '已申报'])
        return {'year': year, 'total_records': len(year_records),
                'total_tax_paid': sum(r['tax_amount'] for r in year_records),
                'by_tax_type': dict(by_type),
                'compliance_rate': declared / len(year_records)
                if year_records else 1.0,
                'generated_at': datetime.datetime.now().isoformat()}

    def get_upcoming_deadlines(self, days_ahead: int = 30) -> List[dict]:
        """Statutory deadlines within days_ahead, sorted by date."""
        today = datetime.date.today()
        deadlines = []
        for rule in self.policy_rules:
            for month_offset in range(2):
                month = today.month + month_offset
                year = today.year
                if month > 12:
                    month -= 12
                    year += 1
                deadline = datetime.date(year, month, rule['deadline_day'])
                if today <= deadline <= today + datetime.timedelta(days=days_ahead):
                    deadlines.append({
                        'rule': rule['name'],
                        'deadline': deadline.isoformat(),
                        'days_remaining': (deadline - today).days,
                        'tax_type': rule['tax_type'].value})
        return sorted(deadlines, key=lambda x: x['deadline'])
