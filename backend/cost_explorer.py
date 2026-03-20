from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Tuple

from botocore.exceptions import BotoCoreError, ClientError

from aws_session import get_boto3_session, is_aws_configured, use_simulation_mode


@dataclass(frozen=True)
class CostPoint:
    day: date
    amount_usd: float


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _parse_amount(value: str | None) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def get_daily_unblended_cost_usd(days: int = 30) -> Optional[List[CostPoint]]:
    """
    Returns daily UnblendedCost in USD for the last `days` (inclusive of end-1).
    Requires AWS Cost Explorer (ce:GetCostAndUsage).
    """
    if use_simulation_mode() or not is_aws_configured():
        return None

    end = _utc_today()
    start = end - timedelta(days=days)

    session = get_boto3_session()
    ce = session.client("ce")

    try:
        resp = ce.get_cost_and_usage(
            TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
            Granularity="DAILY",
            Metrics=["UnblendedCost"],
        )
    except (BotoCoreError, ClientError):
        return None

    points: List[CostPoint] = []
    for item in resp.get("ResultsByTime", []):
        day_str = item.get("TimePeriod", {}).get("Start")
        amount_str = (
            item.get("Total", {})
            .get("UnblendedCost", {})
            .get("Amount")
        )
        if not day_str:
            continue
        points.append(CostPoint(day=date.fromisoformat(day_str), amount_usd=_parse_amount(amount_str)))

    return points or None


def get_cost_last_complete_day_usd() -> Optional[float]:
    points = get_daily_unblended_cost_usd(days=3)
    if not points:
        return None
    # Cost Explorer can lag; take the most recent non-zero (or last) value.
    for p in reversed(points):
        if p.amount_usd >= 0:
            return float(p.amount_usd)
    return float(points[-1].amount_usd)


def get_cost_month_to_date_usd() -> Optional[float]:
    """
    Returns current-month-to-date UnblendedCost in USD.
    """
    if use_simulation_mode() or not is_aws_configured():
        return None

    today = _utc_today()
    start = today.replace(day=1)
    end = today + timedelta(days=1)

    session = get_boto3_session()
    ce = session.client("ce")

    try:
        resp = ce.get_cost_and_usage(
            TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
        )
    except (BotoCoreError, ClientError):
        return None

    results = resp.get("ResultsByTime", [])
    if not results:
        return None

    amount_str = (
        results[0]
        .get("Total", {})
        .get("UnblendedCost", {})
        .get("Amount")
    )
    return _parse_amount(amount_str)

