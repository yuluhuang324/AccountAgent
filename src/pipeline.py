"""End-to-end pipeline orchestrating the five layers (paper §3, §4).

Run from the repository root:
    python src/pipeline.py      (or: python -m src.pipeline)
"""
import logging
import os
import sys
from typing import Dict, List

# Allow "python src/pipeline.py" as well as "python -m src.pipeline".
if __package__ in (None, ''):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.voucher import OCREngine, AccountSubjectManager, VoucherManager
from src.voucher.ocr import VoucherType
from src.integration import BusinessFinanceIntegration
from src.analytics import DataAnalyticsEngine
from src.tax import TaxComplianceManager
from src.tax.compliance import TaxType
from src.fund import CashFlowManager

logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger('pipeline')


class AccountAgentPipeline:
    """Wires the five layers together and runs the full accounting loop:
    recognize -> post -> integrate -> analyze -> comply -> forecast."""

    def __init__(self):
        # Layer 1
        self.ocr = OCREngine()
        self.subjects = AccountSubjectManager()
        self.vouchers = VoucherManager(self.subjects)
        # Layer 2
        self.integration = BusinessFinanceIntegration(self.vouchers)
        # Layer 3
        self.analytics = DataAnalyticsEngine()
        # Layer 4
        self.tax = TaxComplianceManager()
        # Layer 5
        self.fund = CashFlowManager()
        self.integration.register_handler(
            'sales_order_confirmed',
            lambda order: self.fund.record_cash_flow(
                order['total'], 'inflow', '销售回款',
                f"销售订单{order['order_id']}"))

    # -- Layer 1 ---------------------------------------------------------------
    def process_documents(self, image_paths: List[str]) -> Dict:
        """Recognize documents, generate vouchers, run them through the
        maker-checker workflow, and post them."""
        results = self.ocr.batch_recognize(image_paths)
        created = []
        for r in results:
            voucher = self.vouchers.create_from_ocr(r, creator='SYSTEM')
            if voucher:
                created.append(voucher)
        # Workflow: submit then approve (posting happens at approval).
        for v in created:
            self.vouchers.submit_for_review(v['voucher_id'])
        batch = self.vouchers.batch_process(
            [v['voucher_id'] for v in created], 'approve', 'AUDITOR')
        return {'ocr_stats': self.ocr.get_stats(),
                'vouchers_created': len(created),
                'posted': len(batch['success']),
                'summary': self.vouchers.get_summary()}

    # -- Layer 2 ---------------------------------------------------------------
    def run_business_events(self) -> Dict:
        """Confirm a sales order and a purchase receipt; both post vouchers
        immediately through the event bus."""
        sales = self.integration.confirm_sales_order(
            'SO-001', '客户甲', 50000.0)
        purchase = self.integration.complete_purchase_receipt(
            'PO-001', '供应商乙', 30000.0)
        return {'sales_order': sales['order_id'],
                'sales_voucher': sales['voucher_id'],
                'purchase_order': purchase['order_id'],
                'purchase_voucher': purchase['voucher_id'],
                'receivables_aging': self.integration.get_receivables_aging()}

    # -- Layer 3 ---------------------------------------------------------------
    def run_analysis(self, metrics: Dict) -> Dict:
        """Record one period of metrics, evaluate alert rules, and produce the
        dashboard bundle with OLS trends."""
        self.analytics.add_data_point(metrics.get('period', '2026-08'), metrics)
        return self.analytics.generate_dashboard_data(metrics)

    # -- Layer 4 ---------------------------------------------------------------
    def run_tax_compliance(self, financial_data: Dict,
                          period: str = '2026-08') -> Dict:
        """Generate and submit the VAT declaration, then check compliance."""
        record = self.tax.generate_declaration(
            period, TaxType.VAT, financial_data)
        submission = self.tax.submit_declaration(record['record_id'])
        return {'record': record, 'submission': submission,
                'issues': self.tax.policy_compliance_check({}),
                'deadlines': self.tax.get_upcoming_deadlines()}

    # -- Layer 5 ---------------------------------------------------------------
    def run_fund_forecast(self) -> Dict:
        """Produce the 30-day forecast and health report."""
        return self.fund.get_health_report()

    # -- end to end ---------------------------------------------------------------
    def run_demo(self) -> Dict:
        """Run the full closed accounting loop and report layer results."""
        logger.info("Layer 1: voucher processing")
        l1 = self.process_documents(
            [f'doc_{i}.jpg' for i in range(5)])

        logger.info("Layer 2: business-finance integration")
        l2 = self.run_business_events()

        logger.info("Layer 3: analysis and warning")
        l3 = self.run_analysis({'period': '2026-08', 'revenue': 600000,
                               'cost': 420000, 'cash_balance': 300000,
                               'profit_margin': 0.30,
                               'cost_ratio': 0.70,
                               'overdue_receivables_ratio': 0.10})

        logger.info("Layer 4: tax compliance")
        l4 = self.run_tax_compliance({'sales': 600000, 'purchases': 420000})

        logger.info("Layer 5: fund management")
        self.fund.record_cash_flow(400000, 'inflow', '销售回款', '回款')
        self.fund.record_cash_flow(250000, 'outflow', '采购付款', '付款')
        l5 = self.run_fund_forecast()

        return {'layer1': l1, 'layer2': l2, 'layer3': l3, 'layer4': l4,
                'layer5': l5,
                'subject_balances': {
                    f"{s['code']} {s['name']}": round(s['balance'], 2)
                    for s in self.subjects.subjects.values()
                    if abs(s['balance']) > 0.01}}


def main():
    pipeline = AccountAgentPipeline()
    results = pipeline.run_demo()
    print("\n" + "=" * 60)
    print("AccountAgent end-to-end pipeline — results by layer")
    print("=" * 60)
    print(f"\n[Layer 1] OCR stats: {results['layer1']['ocr_stats']}")
    print(f"[Layer 1] Vouchers created/posted: "
          f"{results['layer1']['vouchers_created']}/{results['layer1']['posted']}")
    print(f"\n[Layer 2] {results['layer2']['sales_order']} -> "
          f"{results['layer2']['sales_voucher']}, "
          f"{results['layer2']['purchase_order']} -> "
          f"{results['layer2']['purchase_voucher']}")
    print(f"[Layer 2] Receivables aging: {results['layer2']['receivables_aging']}")
    print(f"\n[Layer 3] Alerts: "
          f"{[(a['level'], a['title']) for a in results['layer3']['alerts']]}")
    print(f"[Layer 3] Revenue forecast (3 periods): "
          f"{[round(x) for x in results['layer3']['trend']['forecast_revenue']]}")
    print(f"\n[Layer 4] VAT payable: "
          f"{results['layer4']['record']['tax_amount']} "
          f"(rate {results['layer4']['record']['tax_rate']}), "
          f"submitted: {results['layer4']['submission']['success']}")
    print(f"[Layer 4] Upcoming deadlines: "
          f"{[(d['rule'], d['deadline']) for d in results['layer4']['deadlines']]}")
    print(f"\n[Layer 5] Health score: {results['layer5']['health_score']} "
          f"({results['layer5']['risk_level']}), "
          f"net 30d: {results['layer5']['forecast_30d']['net']}")
    print(f"[Layer 5] Recommendations: {results['layer5']['recommendations']}")
    print(f"\nPosted subject balances: {results['subject_balances']}")
    print("\nPipeline completed successfully.")


if __name__ == '__main__':
    main()
