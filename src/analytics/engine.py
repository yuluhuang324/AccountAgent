"""DataAnalyticsEngine — rules, trends, anomalies, dashboard (Layer 3, paper §4.4).

Fuses three method families: graded rule thresholds, moving-average / OLS trend
models, and 2-sigma anomaly detection — all over the unified data store.
"""
import datetime
import statistics
import uuid
from typing import Dict, List


class DataAnalyticsEngine:
    """Rule alerts, moving averages, OLS forecasting, product profitability,
    2-sigma anomaly detection, and dashboard generation."""

    def __init__(self):
        self.historical_data: List[dict] = []
        self.alerts: List[dict] = []
        self._init_default_rules()

    # -- rules ----------------------------------------------------------------
    def _init_default_rules(self):
        """Default analysis-and-warning rules (paper Table 3)."""
        self._alert_rules = [
            {'name': '成本异常预警', 'metric': 'cost_ratio', 'threshold': 0.8,
             'operator': '>', 'level': 'WARNING',
             'message': '成本占收入比例超过 80%，请关注成本控制'},
            {'name': '资金短缺预警', 'metric': 'cash_balance', 'threshold': 100000,
             'operator': '<', 'level': 'CRITICAL',
             'message': '现金余额低于 10 万元，存在资金短缺风险'},
            {'name': '应收账款超期预警', 'metric': 'overdue_receivables_ratio',
             'threshold': 0.3, 'operator': '>', 'level': 'WARNING',
             'message': '超期应收账款占比超过 30%，请加强催收'},
            {'name': '利润率下滑预警', 'metric': 'profit_margin', 'threshold': 0.05,
             'operator': '<', 'level': 'WARNING',
             'message': '利润率低于 5%，经营状况需关注'},
        ]

    def add_data_point(self, period: str, metrics: dict):
        """Record one period's financial metrics."""
        self.historical_data.append({
            'period': period,
            'timestamp': datetime.datetime.now().isoformat(), **metrics})

    def check_alerts(self, current_metrics: dict) -> List[dict]:
        """Evaluate all rules against current metrics; critical alerts set an
        action-required flag."""
        new_alerts = []
        for rule in self._alert_rules:
            value = current_metrics.get(rule['metric'])
            if value is None:
                continue
            triggered = ((rule['operator'] == '>' and value > rule['threshold'])
                         or (rule['operator'] == '<' and value < rule['threshold'])
                         or (rule['operator'] == '==' and value == rule['threshold']))
            if triggered:
                alert = {
                    'alert_id': str(uuid.uuid4())[:8], 'level': rule['level'],
                    'title': rule['name'],
                    'message': f"{rule['message']} (当前值: {value})",
                    'module': '数据分析',
                    'action_required': rule['level'] in ('CRITICAL', 'EMERGENCY'),
                    'is_read': False,
                }
                new_alerts.append(alert)
                self.alerts.append(alert)
        return new_alerts

    # -- trend models -------------------------------------------------------------
    @staticmethod
    def calculate_moving_average(values: List[float], window: int = 3) -> List[float]:
        """Moving average with prefix warm-up."""
        if len(values) < window:
            return values
        result = []
        for i in range(len(values)):
            if i < window - 1:
                result.append(sum(values[:i + 1]) / (i + 1))
            else:
                result.append(sum(values[i - window + 1:i + 1]) / window)
        return result

    @staticmethod
    def linear_regression_forecast(values: List[float],
                                 periods: int = 3) -> List[float]:
        """OLS trend forecast: y_hat = alpha + beta * t."""
        n = len(values)
        if n < 2:
            return [values[-1]] * periods if values else [0.0] * periods
        x_mean = (n - 1) / 2
        y_mean = sum(values) / n
        numerator = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        slope = numerator / denominator if denominator != 0 else 0
        intercept = y_mean - slope * x_mean
        return [intercept + slope * (n + i) for i in range(periods)]

    def analyze_revenue_cost_trend(self, periods: int = 6) -> dict:
        """Revenue/cost trend analysis with moving averages and three-period
        forecasts plus average profit margin."""
        data = self.historical_data[-periods:] \
            if len(self.historical_data) >= periods else self.historical_data
        revenues = [d.get('revenue', 0) for d in data]
        costs = [d.get('cost', 0) for d in data]
        profits = [r - c for r, c in zip(revenues, costs)]

        margins = [(r - c) / r for r, c in zip(revenues, costs) if r > 0]
        return {
            'periods': [d.get('period') for d in data],
            'revenues': revenues, 'costs': costs, 'profits': profits,
            'revenue_ma': self.calculate_moving_average(revenues),
            'cost_ma': self.calculate_moving_average(costs),
            'forecast_revenue': self.linear_regression_forecast(revenues, 3),
            'forecast_cost': self.linear_regression_forecast(costs, 3),
            'avg_profit_margin': statistics.mean(margins) if margins else 0,
        }

    # -- profitability & anomalies -----------------------------------------------------
    @staticmethod
    def analyze_product_profitability(product_data: List[dict]) -> List[dict]:
        """Per-product margin with health status (healthy > 20%, warning > 5%,
        critical otherwise), sorted by margin."""
        results = []
        for product in product_data:
            revenue = product.get('revenue', 0)
            cost = product.get('cost', 0)
            profit = revenue - cost
            margin = profit / revenue if revenue > 0 else 0
            results.append({**product, 'profit': profit,
                           'margin': round(margin * 100, 2),
                           'status': 'healthy' if margin > 0.2
                           else ('warning' if margin > 0.05 else 'critical')})
        return sorted(results, key=lambda x: x['margin'], reverse=True)

    @staticmethod
    def detect_cost_anomalies(cost_data: List[float],
                             std_multiplier: float = 2.0) -> List[int]:
        """Indices of observations deviating from the mean by more than
        std_multiplier * sigma."""
        if len(cost_data) < 3:
            return []
        mean = statistics.mean(cost_data)
        std = statistics.stdev(cost_data)
        if std == 0:
            return []
        return [i for i, val in enumerate(cost_data)
                if abs(val - mean) > std_multiplier * std]

    # -- dashboard ---------------------------------------------------------------------
    def generate_dashboard_data(self, current_metrics: dict) -> dict:
        """Operating-dashboard bundle: current metrics, fresh alerts, trend."""
        alerts = self.check_alerts(current_metrics)
        trend = self.analyze_revenue_cost_trend()
        return {
            'summary': current_metrics,
            'alerts': [{'id': a['alert_id'], 'level': a['level'],
                        'title': a['title'], 'message': a['message']}
                       for a in alerts],
            'trend': trend,
            'generated_at': datetime.datetime.now().isoformat(),
        }

    # -- alert bookkeeping ----------------------------------------------------------------
    def get_unread_alerts(self) -> List[dict]:
        return [a for a in self.alerts if not a['is_read']]

    def mark_alerts_read(self, alert_ids: List[str]):
        for alert in self.alerts:
            if alert['alert_id'] in alert_ids:
                alert['is_read'] = True
