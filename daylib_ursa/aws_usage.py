"""AWS usage reporting for DayEC and ParallelCluster resources."""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

import boto3


AWS_USAGE_CACHE_TTL_SECONDS = 15 * 60
AWS_BILLING_REGION = "us-east-1"
DAYEC_COST_BASIS_TAG_KEY = "aws-parallelcluster-clustername"
DAYEC_PARALLELCLUSTER_TAG_KEYS: tuple[str, ...] = (
    "aws-parallelcluster-project",
    "aws-parallelcluster-clustername",
    "aws-parallelcluster-username",
    "aws-parallelcluster-jobid",
    "aws-parallelcluster-enforce-budget",
    "aws-parallelcluster-daylily-git-deets",
    "aws-parallelcluster-monitor-bucket",
    "parallelcluster:cluster-name",
    "parallelcluster:compute-resource-name",
    "parallelcluster:node-type",
    "parallelcluster:version",
    "parallelcluster:queue-name",
    "parallelcluster:filesystem",
    "parallelcluster:networking",
    "parallelcluster:attributes",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _amount(value: Any) -> float:
    try:
        return float(str(value or "0"))
    except (TypeError, ValueError):
        return 0.0


def _money_amount(payload: dict[str, Any] | None) -> float:
    return _amount((payload or {}).get("Amount"))


def _money_unit(payload: dict[str, Any] | None) -> str:
    return str((payload or {}).get("Unit") or "USD")


def _budget_tag_filters(cost_filters: dict[str, Any] | None) -> dict[str, str]:
    tags: dict[str, str] = {}

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for child in value.values():
                visit(child)
            return
        if isinstance(value, list):
            for child in value:
                visit(child)
            return
        text = str(value or "").strip()
        for tag_key in DAYEC_PARALLELCLUSTER_TAG_KEYS:
            prefix = f"user:{tag_key}$"
            if text.startswith(prefix):
                tags[tag_key] = text[len(prefix) :]

    visit(cost_filters or {})
    return tags


def _ce_tag_value(raw_value: str, tag_key: str) -> str:
    value = str(raw_value or "").strip()
    for prefix in (f"{tag_key}$", f"user:{tag_key}$"):
        if value.startswith(prefix):
            return value[len(prefix) :]
    if "$" in value:
        return value.split("$", 1)[1]
    return value


def _arn_service(arn: str) -> str:
    parts = str(arn or "").split(":", 5)
    return parts[2] if len(parts) > 2 and parts[2] else "unknown"


def _month_to_date_window(today: date | None = None) -> tuple[str, str]:
    current = today or datetime.now(timezone.utc).date()
    return current.replace(day=1).isoformat(), (current + timedelta(days=1)).isoformat()


@dataclass(frozen=True)
class BudgetUsageRow:
    budget_name: str
    project: str
    cluster_name: str
    limit_amount: float
    actual_amount: float
    forecast_amount: float
    unit: str
    percent_used: float | None
    tag_filters: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "budget_name": self.budget_name,
            "project": self.project,
            "cluster_name": self.cluster_name,
            "limit_amount": self.limit_amount,
            "actual_amount": self.actual_amount,
            "forecast_amount": self.forecast_amount,
            "unit": self.unit,
            "percent_used": self.percent_used,
            "tag_filters": dict(self.tag_filters),
        }


@dataclass(frozen=True)
class TagServiceCostRow:
    tag_key: str
    tag_value: str
    service: str
    amount: float
    unit: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag_key": self.tag_key,
            "tag_value": self.tag_value,
            "service": self.service,
            "amount": self.amount,
            "unit": self.unit,
        }


@dataclass(frozen=True)
class TaggedResourceInventoryRow:
    tag_key: str
    tag_value: str
    service: str
    region: str
    resource_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag_key": self.tag_key,
            "tag_value": self.tag_value,
            "service": self.service,
            "region": self.region,
            "resource_count": self.resource_count,
        }


@dataclass(frozen=True)
class AwsUsageReport:
    aws_profile: str
    account_id: str
    regions: list[str]
    start_date: str
    end_date: str
    fetched_at: str
    cache_expires_at: str
    tag_keys: list[str]
    budgets: list[BudgetUsageRow]
    costs_by_tag_service: list[TagServiceCostRow]
    resource_inventory: list[TaggedResourceInventoryRow]

    def to_dict(self) -> dict[str, Any]:
        totals: dict[str, float] = defaultdict(float)
        service_totals: dict[str, float] = defaultdict(float)
        tag_value_totals: dict[tuple[str, str], float] = defaultdict(float)
        basis_rows = [
            row for row in self.costs_by_tag_service if row.tag_key == DAYEC_COST_BASIS_TAG_KEY
        ]
        for row in self.costs_by_tag_service:
            totals[row.tag_key] += row.amount
        for row in basis_rows:
            service_totals[row.service] += row.amount
            tag_value_totals[(row.tag_key, row.tag_value)] += row.amount
        return {
            "aws_profile": self.aws_profile,
            "account_id": self.account_id,
            "regions": list(self.regions),
            "start_date": self.start_date,
            "end_date": self.end_date,
            "fetched_at": self.fetched_at,
            "cache_expires_at": self.cache_expires_at,
            "ttl_seconds": AWS_USAGE_CACHE_TTL_SECONDS,
            "tag_keys": list(self.tag_keys),
            "cost_basis_tag_key": DAYEC_COST_BASIS_TAG_KEY,
            "budgets": [row.to_dict() for row in self.budgets],
            "costs_by_tag_service": [row.to_dict() for row in self.costs_by_tag_service],
            "cost_basis_rows": [row.to_dict() for row in basis_rows],
            "cost_totals_by_tag_key": dict(sorted(totals.items())),
            "cost_totals_by_service": [
                {"service": service, "amount": amount, "unit": "USD"}
                for service, amount in sorted(
                    service_totals.items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ],
            "cost_totals_by_tag_value": [
                {"tag_key": tag_key, "tag_value": tag_value, "amount": amount, "unit": "USD"}
                for (tag_key, tag_value), amount in sorted(
                    tag_value_totals.items(),
                    key=lambda item: (item[0][0], -item[1], item[0][1]),
                )
            ],
            "total_cost_amount": round(sum(service_totals.values()), 6),
            "resource_inventory": [row.to_dict() for row in self.resource_inventory],
        }


class AwsUsageReportService:
    """Cached read-only AWS billing and tag report service."""

    def __init__(
        self,
        *,
        aws_profile: str,
        regions: list[str],
        cache_ttl_seconds: int = AWS_USAGE_CACHE_TTL_SECONDS,
        session_factory: Callable[..., Any] = boto3.Session,
    ) -> None:
        profile = str(aws_profile or "").strip()
        if not profile:
            raise ValueError("aws_profile is required for AWS usage reporting")
        normalized_regions = [
            str(region or "").strip() for region in regions if str(region).strip()
        ]
        if not normalized_regions:
            raise ValueError("at least one AWS region is required for AWS usage reporting")
        self.aws_profile = profile
        self.regions = normalized_regions
        self.cache_ttl_seconds = int(cache_ttl_seconds)
        self.session_factory = session_factory
        self._cache: AwsUsageReport | None = None
        self._cache_time = 0.0
        self._lock = threading.RLock()

    def get_report(self, *, force_refresh: bool = False) -> AwsUsageReport:
        with self._lock:
            now = time.time()
            if (
                not force_refresh
                and self._cache is not None
                and (now - self._cache_time) < self.cache_ttl_seconds
            ):
                return self._cache
            report = self._build_report()
            self._cache = report
            self._cache_time = now
            return report

    def _session(self, *, region_name: str | None = None) -> Any:
        kwargs: dict[str, str] = {"profile_name": self.aws_profile}
        if region_name:
            kwargs["region_name"] = region_name
        return self.session_factory(**kwargs)

    def _build_report(self) -> AwsUsageReport:
        fetched_at = _utc_now_iso()
        start_date, end_date = _month_to_date_window()
        account_id = str(self._session().client("sts").get_caller_identity()["Account"])
        costs = self._costs_by_tag_service(start_date=start_date, end_date=end_date)
        inventory = self._resource_inventory()
        cache_expires_at = datetime.fromtimestamp(
            time.time() + self.cache_ttl_seconds,
            tz=timezone.utc,
        ).isoformat()
        return AwsUsageReport(
            aws_profile=self.aws_profile,
            account_id=account_id,
            regions=list(self.regions),
            start_date=start_date,
            end_date=end_date,
            fetched_at=fetched_at,
            cache_expires_at=cache_expires_at,
            tag_keys=list(DAYEC_PARALLELCLUSTER_TAG_KEYS),
            budgets=[],
            costs_by_tag_service=costs,
            resource_inventory=inventory,
        )

    def _list_budgets(self, account_id: str) -> list[BudgetUsageRow]:
        client = self._session(region_name=AWS_BILLING_REGION).client("budgets")
        rows: list[BudgetUsageRow] = []
        token: str | None = None
        while True:
            request: dict[str, Any] = {"AccountId": account_id}
            if token:
                request["NextToken"] = token
            response = client.describe_budgets(**request)
            for budget in response.get("Budgets", []):
                if not isinstance(budget, dict):
                    continue
                tag_filters = _budget_tag_filters(budget.get("CostFilters"))
                budget_name = str(budget.get("BudgetName") or "")
                if (
                    not tag_filters
                    and not budget_name.startswith("da-")
                    and budget_name != "daylily-global"
                ):
                    continue
                calculated = budget.get("CalculatedSpend") or {}
                actual = calculated.get("ActualSpend") or {}
                forecast = calculated.get("ForecastedSpend") or {}
                limit = budget.get("BudgetLimit") or {}
                limit_amount = _money_amount(limit)
                actual_amount = _money_amount(actual)
                percent_used = (
                    round((actual_amount / limit_amount) * 100, 2) if limit_amount > 0 else None
                )
                rows.append(
                    BudgetUsageRow(
                        budget_name=budget_name,
                        project=tag_filters.get("aws-parallelcluster-project", ""),
                        cluster_name=tag_filters.get("aws-parallelcluster-clustername", ""),
                        limit_amount=limit_amount,
                        actual_amount=actual_amount,
                        forecast_amount=_money_amount(forecast),
                        unit=_money_unit(limit or actual or forecast),
                        percent_used=percent_used,
                        tag_filters=tag_filters,
                    )
                )
            token = str(response.get("NextToken") or "").strip() or None
            if not token:
                break
        return sorted(rows, key=lambda item: (item.project, item.cluster_name, item.budget_name))

    def _costs_by_tag_service(self, *, start_date: str, end_date: str) -> list[TagServiceCostRow]:
        client = self._session(region_name=AWS_BILLING_REGION).client("ce")
        rows: list[TagServiceCostRow] = []
        for tag_key in DAYEC_PARALLELCLUSTER_TAG_KEYS:
            token: str | None = None
            while True:
                request: dict[str, Any] = {
                    "TimePeriod": {"Start": start_date, "End": end_date},
                    "Granularity": "MONTHLY",
                    "Metrics": ["AmortizedCost"],
                    "Filter": {
                        "Not": {
                            "Tags": {
                                "Key": tag_key,
                                "MatchOptions": ["ABSENT"],
                            }
                        }
                    },
                    "GroupBy": [
                        {"Type": "TAG", "Key": tag_key},
                        {"Type": "DIMENSION", "Key": "SERVICE"},
                    ],
                }
                if token:
                    request["NextPageToken"] = token
                response = client.get_cost_and_usage(**request)
                for result in response.get("ResultsByTime", []):
                    if not isinstance(result, dict):
                        continue
                    for group in result.get("Groups", []):
                        if not isinstance(group, dict):
                            continue
                        keys = list(group.get("Keys") or [])
                        if len(keys) < 2:
                            continue
                        metric = (group.get("Metrics") or {}).get("AmortizedCost") or {}
                        amount = _money_amount(metric)
                        if amount == 0:
                            continue
                        rows.append(
                            TagServiceCostRow(
                                tag_key=tag_key,
                                tag_value=_ce_tag_value(str(keys[0]), tag_key),
                                service=str(keys[1] or "unknown"),
                                amount=amount,
                                unit=_money_unit(metric),
                            )
                        )
                token = str(response.get("NextPageToken") or "").strip() or None
                if not token:
                    break
        return sorted(rows, key=lambda item: (item.tag_key, item.tag_value, item.service))

    def _resource_inventory(self) -> list[TaggedResourceInventoryRow]:
        counts: dict[tuple[str, str, str, str], int] = defaultdict(int)
        for region in self.regions:
            client = self._session(region_name=region).client("resourcegroupstaggingapi")
            for tag_key in DAYEC_PARALLELCLUSTER_TAG_KEYS:
                token: str | None = None
                while True:
                    request: dict[str, Any] = {
                        "ResourcesPerPage": 100,
                        "TagFilters": [{"Key": tag_key}],
                    }
                    if token:
                        request["PaginationToken"] = token
                    response = client.get_resources(**request)
                    for mapping in response.get("ResourceTagMappingList", []):
                        if not isinstance(mapping, dict):
                            continue
                        tags = {
                            str(item.get("Key") or ""): str(item.get("Value") or "")
                            for item in mapping.get("Tags", [])
                            if isinstance(item, dict)
                        }
                        if tag_key not in tags:
                            continue
                        service = _arn_service(str(mapping.get("ResourceARN") or ""))
                        counts[(tag_key, tags[tag_key], service, region)] += 1
                    token = str(response.get("PaginationToken") or "").strip() or None
                    if not token:
                        break
        return [
            TaggedResourceInventoryRow(
                tag_key=tag_key,
                tag_value=tag_value,
                service=service,
                region=region,
                resource_count=count,
            )
            for (tag_key, tag_value, service, region), count in sorted(counts.items())
        ]


__all__ = [
    "AWS_USAGE_CACHE_TTL_SECONDS",
    "DAYEC_COST_BASIS_TAG_KEY",
    "DAYEC_PARALLELCLUSTER_TAG_KEYS",
    "AwsUsageReport",
    "AwsUsageReportService",
    "BudgetUsageRow",
    "TagServiceCostRow",
    "TaggedResourceInventoryRow",
    "_budget_tag_filters",
    "_ce_tag_value",
    "_month_to_date_window",
]
