"""CashFlowManager — 30-day forecasting and health scoring (Layer 5, paper §4.5).

Forecasts from historical flows with evidence-discounted confidence, distills
the forecast into a health score, and generates actionable recommendations.
Warning fires when the score falls below 70.
"""
import datetime
import statistics
import uuid
from collections import defaultdict
from typing import Dict, List


class CashFlowManager:
    """30-day fund forecast, health scoring, recommendations, and
    inflow/outflow structure analysis."""

    HEALTH_THRESHOLDS = {'excellent': 85, 'good': 70, 'warning': 50, 'critical': 30}

    def __init__(self):
        self.cash_flows: List[dict] = []
        self.forecasts: List[dict] = []
        self.current_balance: float = 0.0

    # -- recording -----------------------------------------------------------------
    def record_cash_flow(self, amount: float, flow_type: str, category: str,
                       description: str,
                       flow_date: datetime.date = None):
        """Record one cash flow (inflow/outflow) and update the balance."""
        flow = {'id': str(uuid.uuid4())[:8], 'amount': amount,
                'type': flow_type, 'category': category,
                'description': description,
                'date': (flow_date or datetime.date.today()).isoformat(),
                'recorded_at': datetime.datetime.now().isoformat()}
        self.cash_flows.append(flow)
        if flow_type == 'inflow':
            self.current_balance += amount
        else:
            self.current_balance -= amount

    # -- forecasting --------------------------------------------------------------------
    def forecast_30_days(self) -> dict:
        """Forecast the next 30 days from historical daily means (conservative
        defaults when history is sparse); confidence = min(0.85, 0.5 + 0.01n)."""
        inflows = [f['amount'] for f in self.cash_flows if f['type'] == 'inflow']
        outflows = [f['amount'] for f in self.cash_flows if f['type'] == 'outflow']

        avg_daily_inflow = statistics.mean(inflows) if inflows else 10000
        avg_daily_outflow = statistics.mean(outflows) if outflows else 8000

        forecast_inflow = avg_daily_inflow * 30
        forecast_outflow = avg_daily_outflow * 30
        net = forecast_inflow - forecast_outflow

        health_score = self._calculate_health_score(net, self.current_balance)
        confidence = min(0.85, 0.5 + len(self.cash_flows) * 0.01)

        if health_score < self.HEALTH_THRESHOLDS['critical']:
            risk_level = 'critical'
        elif health_score < self.HEALTH_THRESHOLDS['warning']:
            risk_level = 'high'
        elif health_score < self.HEALTH_THRESHOLDS['good']:
            risk_level = 'medium'
        else:
            risk_level = 'low'

        recommendations = self._generate_recommendations(
            health_score, net, self.current_balance)

        forecast = {
            'forecast_id': str(uuid.uuid4())[:8],
            'forecast_date': datetime.date.today(), 'period_days': 30,
            'inflow_forecast': round(forecast_inflow, 2),
            'outflow_forecast': round(forecast_outflow, 2),
            'net_forecast': round(net, 2),
            'confidence_score': round(confidence, 3),
            'health_score': round(health_score, 1),
            'risk_level': risk_level,
            'recommendations': recommendations,
        }
        self.forecasts.append(forecast)
        return forecast

    # -- health scoring -----------------------------------------------------------------
    @staticmethod
    def _calculate_health_score(net_flow: float, balance: float) -> float:
        """Base 60, adjusted by net-flow direction (max +/-20 at 10k/point)
        and balance adequacy (from -30 when negative to +20 above 500k)."""
        score = 60.0
        if net_flow > 0:
            score += min(20, net_flow / 10000)
        else:
            score -= min(20, abs(net_flow) / 10000)

        if balance > 500000:
            score += 20
        elif balance > 100000:
            score += 10
        elif balance < 0:
            score -= 30
        elif balance < 50000:
            score -= 15

        return max(0.0, min(100.0, score))

    @staticmethod
    def _generate_recommendations(health_score: float, net: float,
                                balance: float) -> List[str]:
        """Score-conditioned advice, from emergency financing to idle-fund
        investment."""
        recs = []
        if health_score < CashFlowManager.HEALTH_THRESHOLDS['critical']:
            recs.append("资金状况严峻，建议立即寻求短期融资或信用贷款")
            recs.append("加速应收账款回收，优先催收超期款项")
        elif health_score < CashFlowManager.HEALTH_THRESHOLDS['warning']:
            recs.append("建议提前申请授信额度，做好融资预案")
            recs.append("优化付款节奏，延缓非紧急支出")
        if net < 0:
            recs.append("预计净流出为负，需关注现金储备")
        if balance > 2000000:
            recs.append("闲置资金较多，建议配置短期理财产品提升收益")
        return recs

    # -- structure analysis --------------------------------------------------------------
    def _structure(self, flow_type: str) -> dict:
        flows = [f for f in self.cash_flows if f['type'] == flow_type]
        by_category = defaultdict(float)
        for f in flows:
            by_category[f['category']] += f['amount']
        total = sum(by_category.values())
        return {'total': total, 'by_category': dict(by_category),
                'ratios': {k: round(v / total * 100, 2)
                           for k, v in by_category.items()} if total > 0 else {}}

    def analyze_inflow_structure(self) -> dict:
        """Inflow decomposition by category with percentage ratios."""
        return self._structure('inflow')

    def analyze_outflow_structure(self) -> dict:
        """Outflow decomposition by category with percentage ratios."""
        return self._structure('outflow')

    # -- reports ---------------------------------------------------------------------------
    def get_health_report(self) -> dict:
        """Latest health report with an alert flag (score < 50)."""
        forecast = self.forecast_30_days()
        return {'current_balance': self.current_balance,
                'health_score': forecast['health_score'],
                'risk_level': forecast['risk_level'],
                'forecast_30d': {'inflow': forecast['inflow_forecast'],
                                'outflow': forecast['outflow_forecast'],
                                'net': forecast['net_forecast']},
                'confidence': forecast['confidence_score'],
                'recommendations': forecast['recommendations'],
                'alert': forecast['health_score']
                < self.HEALTH_THRESHOLDS['good'],
                'generated_at': datetime.datetime.now().isoformat()}

    def get_monthly_summary(self, months: int = 6) -> List[dict]:
        """Monthly inflow/outflow/net trajectory."""
        monthly = defaultdict(lambda: {'inflow': 0.0, 'outflow': 0.0})
        for f in self.cash_flows:
            monthly[f['date'][:7]][f['type']] += f['amount']
        return [{'month': m,
                 'inflow': round(d['inflow'], 2),
                 'outflow': round(d['outflow'], 2),
                 'net': round(d['inflow'] - d['outflow'], 2)}
                for m, d in sorted(monthly.items())[-months:]]
