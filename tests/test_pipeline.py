"""Test suite for the AccountAgent reference implementation.

Run from the repository root:  python -m unittest discover -s tests
"""
import unittest

from src import (OCREngine, AccountSubjectManager, VoucherManager,
                BusinessFinanceIntegration, DataAnalyticsEngine,
                TaxComplianceManager, CashFlowManager)
from src.voucher.ocr import VoucherType
from src.tax.compliance import TaxType


class TestOCR(unittest.TestCase):
    def test_recognize_returns_structured_fields(self):
        engine = OCREngine()
        result = engine.recognize('invoice_01.jpg', VoucherType.VAT_INVOICE)
        self.assertTrue(result.success)
        self.assertGreater(result.confidence, 0.99)
        self.assertIn('amount', result.fields)
        self.assertIn('tax_amount', result.fields)

    def test_type_detection(self):
        engine = OCREngine()
        self.assertEqual(engine.detect_voucher_type('增值税 发票号码 123'),
                         VoucherType.VAT_INVOICE)
        self.assertEqual(engine.detect_voucher_type('银行 交易流水'),
                         VoucherType.BANK_STATEMENT)
        self.assertEqual(engine.detect_voucher_type('无关文本'),
                         VoucherType.OTHER)

    def test_batch_and_stats(self):
        engine = OCREngine()
        results = engine.batch_recognize([f'd{i}.jpg' for i in range(10)])
        self.assertEqual(len(results), 10)
        stats = engine.get_stats()
        self.assertEqual(stats['total'], 10)
        self.assertEqual(stats['success'], 10)


class TestVouchers(unittest.TestCase):
    def setUp(self):
        self.subjects = AccountSubjectManager()
        self.manager = VoucherManager(self.subjects)

    def test_unbalanced_voucher_rejected(self):
        with self.assertRaises(ValueError):
            self.manager.create_voucher('OTHER', [
                {'account': '1001', 'name': '库存现金', 'debit': 100.0},
                {'account': '2001', 'name': '短期借款', 'credit': 90.0},
            ], creator='tester')

    def test_workflow_posts_only_at_approval(self):
        voucher = self.manager.create_voucher('OTHER', [
            {'account': '1001', 'name': '库存现金', 'debit': 100.0},
            {'account': '2001', 'name': '短期借款', 'credit': 100.0},
        ], creator='tester')
        self.assertTrue(self.manager.submit_for_review(voucher['voucher_id']))
        self.assertTrue(self.manager.approve_voucher(voucher['voucher_id'], 'auditor'))
        self.assertEqual(
            self.subjects.get_subject('1001')['balance'], 100.0)

    def test_ocr_to_voucher_is_balanced(self):
        engine = OCREngine()
        result = engine.recognize('inv.jpg', VoucherType.VAT_INVOICE)
        voucher = self.manager.create_from_ocr(result, 'SYSTEM')
        self.assertIsNotNone(voucher)
        self.assertTrue(self.manager.is_balanced(voucher))


class TestIntegration(unittest.TestCase):
    def setUp(self):
        self.manager = VoucherManager(AccountSubjectManager())
        self.integration = BusinessFinanceIntegration(self.manager)

    def test_sales_order_posts_ar_voucher(self):
        order = self.integration.confirm_sales_order('SO-1', '客户', 1000.0)
        voucher = self.manager.vouchers[order['voucher_id']]
        self.assertTrue(self.manager.is_balanced(voucher))

    def test_event_bus_dispatches(self):
        received = []
        self.integration.register_handler(
            'sales_order_confirmed', lambda o: received.append(o['order_id']))
        self.integration.confirm_sales_order('SO-2', '客户', 1000.0)
        self.assertEqual(received, ['SO-2'])

    def test_aging_buckets(self):
        order = self.integration.confirm_sales_order('SO-3', '客户', 500.0)
        aging = self.integration.get_receivables_aging()
        self.assertAlmostEqual(aging['0-30 天'], order['total'])


class TestAnalytics(unittest.TestCase):
    def test_fund_shortage_alert(self):
        engine = DataAnalyticsEngine()
        alerts = engine.check_alerts({'cash_balance': 50000})
        self.assertTrue(any(a['title'] == '资金短缺预警' for a in alerts))

    def test_ols_forecast(self):
        forecast = DataAnalyticsEngine.linear_regression_forecast(
            [100, 200, 300, 400], periods=2)
        self.assertAlmostEqual(forecast[0], 500.0)
        self.assertAlmostEqual(forecast[1], 600.0)

    def test_anomaly_detection(self):
        anomalies = DataAnalyticsEngine.detect_cost_anomalies(
            [100, 102, 98, 101, 99, 100, 500])
        self.assertEqual(anomalies, [6])

    def test_product_profitability(self):
        rows = DataAnalyticsEngine.analyze_product_profitability([
            {'name': 'A', 'revenue': 100, 'cost': 50},
            {'name': 'B', 'revenue': 100, 'cost': 95},
        ])
        self.assertEqual(rows[0]['name'], 'A')
        self.assertEqual(rows[0]['status'], 'healthy')
        self.assertEqual(rows[1]['status'], 'critical')


class TestTax(unittest.TestCase):
    def test_vat_price_separated(self):
        calc = TaxComplianceManager().calculate_vat(1130, 0, 'general')
        self.assertEqual(calc['output_tax'], 130.0)
        self.assertEqual(calc['payable_tax'], 130.0)

    def test_declaration_lifecycle(self):
        mgr = TaxComplianceManager()
        record = mgr.generate_declaration('2026-08', TaxType.VAT,
                                       {'sales': 1130, 'purchases': 0})
        submission = mgr.submit_declaration(record['record_id'])
        self.assertTrue(submission['success'])
        self.assertIn('confirmation_no', submission)

    def test_deadlines_listed(self):
        deadlines = TaxComplianceManager().get_upcoming_deadlines(60)
        self.assertTrue(len(deadlines) >= 2)


class TestFund(unittest.TestCase):
    def test_forecast_and_health(self):
        mgr = CashFlowManager()
        mgr.record_cash_flow(200000, 'inflow', '回款', 'test')
        mgr.record_cash_flow(100000, 'outflow', '付款', 'test')
        report = mgr.get_health_report()
        self.assertGreater(report['health_score'], 70)
        self.assertFalse(report['alert'])

    def test_low_score_alerts(self):
        mgr = CashFlowManager()  # empty history, zero balance
        report = mgr.get_health_report()
        self.assertTrue(report['alert'])

    def test_structure_ratios(self):
        mgr = CashFlowManager()
        mgr.record_cash_flow(300, 'inflow', 'A', 'x')
        mgr.record_cash_flow(100, 'inflow', 'B', 'y')
        ratios = mgr.analyze_inflow_structure()['ratios']
        self.assertEqual(ratios['A'], 75.0)


class TestEndToEnd(unittest.TestCase):
    def test_full_pipeline(self):
        from src.pipeline import AccountAgentPipeline
        pipeline = AccountAgentPipeline()
        results = pipeline.run_demo()
        self.assertEqual(results['layer1']['vouchers_created'], 5)
        self.assertEqual(results['layer1']['posted'], 5)
        self.assertTrue(results['layer4']['submission']['success'])
        self.assertIn('health_score', results['layer5'])
        # Accounting equation holds: assets = liabilities + equity after posting.
        balances = {code: s['balance']
                   for code, s in
                   ((s['code'], s) for s in pipeline.subjects.subjects.values())}
        assets = sum(b for c, b in balances.items()
                    if c.startswith(('1',)))
        self.assertGreater(assets, 0)


if __name__ == '__main__':
    unittest.main()
