from __future__ import annotations

from daylib_ursa.aws_usage import (
    AWS_USAGE_CACHE_TTL_SECONDS,
    AwsUsageReportService,
    _budget_tag_filters,
    _ce_tag_value,
    _month_to_date_window,
)


class FakeStsClient:
    def __init__(self) -> None:
        self.calls = 0

    def get_caller_identity(self):
        self.calls += 1
        return {"Account": "123456789012"}


class FakeBudgetsClient:
    def __init__(self) -> None:
        self.calls = 0

    def describe_budgets(self, **_kwargs):
        self.calls += 1
        return {
            "Budgets": [
                {
                    "BudgetName": "da-us-west-2d-cluster-a",
                    "BudgetLimit": {"Amount": "200", "Unit": "USD"},
                    "CalculatedSpend": {
                        "ActualSpend": {"Amount": "125.25", "Unit": "USD"},
                        "ForecastedSpend": {"Amount": "150", "Unit": "USD"},
                    },
                    "CostFilters": {
                        "TagKeyValue": [
                            "user:aws-parallelcluster-project$project-a",
                            "user:aws-parallelcluster-clustername$cluster-a",
                        ]
                    },
                },
                {
                    "BudgetName": "unrelated",
                    "BudgetLimit": {"Amount": "10", "Unit": "USD"},
                    "CalculatedSpend": {"ActualSpend": {"Amount": "1", "Unit": "USD"}},
                    "CostFilters": {},
                },
            ]
        }


class FakeCostExplorerClient:
    def __init__(self) -> None:
        self.calls = 0

    def get_cost_and_usage(self, **kwargs):
        self.calls += 1
        tag_key = kwargs["GroupBy"][0]["Key"]
        groups = []
        if tag_key == "aws-parallelcluster-project":
            groups = [
                {
                    "Keys": [
                        "aws-parallelcluster-project$project-a",
                        "Amazon Elastic Compute Cloud - Compute",
                    ],
                    "Metrics": {"AmortizedCost": {"Amount": "42.50", "Unit": "USD"}},
                }
            ]
        elif tag_key == "aws-parallelcluster-clustername":
            groups = [
                {
                    "Keys": [
                        "aws-parallelcluster-clustername$cluster-a",
                        "Amazon Elastic Compute Cloud - Compute",
                    ],
                    "Metrics": {"AmortizedCost": {"Amount": "42.50", "Unit": "USD"}},
                }
            ]
        return {"ResultsByTime": [{"Groups": groups}]}


class FakeTaggingClient:
    def __init__(self) -> None:
        self.calls = 0

    def get_resources(self, **kwargs):
        self.calls += 1
        tag_key = kwargs["TagFilters"][0]["Key"]
        mappings = []
        if tag_key == "aws-parallelcluster-project":
            mappings = [
                {
                    "ResourceARN": "arn:aws:ec2:us-west-2:123456789012:instance/i-1",
                    "Tags": [{"Key": tag_key, "Value": "project-a"}],
                },
                {
                    "ResourceARN": "arn:aws:fsx:us-west-2:123456789012:file-system/fs-1",
                    "Tags": [{"Key": tag_key, "Value": "project-a"}],
                },
            ]
        elif tag_key == "aws-parallelcluster-clustername":
            mappings = [
                {
                    "ResourceARN": "arn:aws:ec2:us-west-2:123456789012:instance/i-1",
                    "Tags": [{"Key": tag_key, "Value": "cluster-a"}],
                }
            ]
        return {"ResourceTagMappingList": mappings}


class FakeSession:
    def __init__(self, factory: "FakeSessionFactory", *, region_name: str | None) -> None:
        self.factory = factory
        self.region_name = region_name

    def client(self, service_name: str):
        self.factory.client_names.append((service_name, self.region_name))
        if service_name == "sts":
            return self.factory.sts
        if service_name == "budgets":
            return self.factory.budgets
        if service_name == "ce":
            return self.factory.ce
        if service_name == "resourcegroupstaggingapi":
            return self.factory.tagging
        raise AssertionError(f"Unexpected client: {service_name}")


class FakeSessionFactory:
    def __init__(self) -> None:
        self.client_names: list[tuple[str, str | None]] = []
        self.sts = FakeStsClient()
        self.budgets = FakeBudgetsClient()
        self.ce = FakeCostExplorerClient()
        self.tagging = FakeTaggingClient()

    def __call__(self, *, profile_name: str, region_name: str | None = None):
        assert profile_name == "lsmc"
        return FakeSession(self, region_name=region_name)


def test_budget_and_cost_tag_helpers() -> None:
    assert _budget_tag_filters({"TagKeyValue": ["user:aws-parallelcluster-project$project-a"]}) == {
        "aws-parallelcluster-project": "project-a"
    }
    assert (
        _ce_tag_value(
            "aws-parallelcluster-clustername$cluster-a", "aws-parallelcluster-clustername"
        )
        == "cluster-a"
    )
    assert _month_to_date_window()[0].endswith("-01")


def test_aws_usage_report_parses_budget_costs_inventory_and_caches() -> None:
    session_factory = FakeSessionFactory()
    service = AwsUsageReportService(
        aws_profile="lsmc",
        regions=["us-west-2"],
        session_factory=session_factory,
    )

    first = service.get_report().to_dict()
    second = service.get_report().to_dict()

    assert first == second
    assert first["ttl_seconds"] == AWS_USAGE_CACHE_TTL_SECONDS
    assert first["account_id"] == "123456789012"
    assert first["budgets"] == []
    assert first["cost_basis_tag_key"] == "aws-parallelcluster-clustername"
    assert first["total_cost_amount"] == 42.5
    assert {
        (row["tag_key"], row["tag_value"], row["service"], row["amount"])
        for row in first["costs_by_tag_service"]
    } == {
        (
            "aws-parallelcluster-clustername",
            "cluster-a",
            "Amazon Elastic Compute Cloud - Compute",
            42.5,
        ),
        (
            "aws-parallelcluster-project",
            "project-a",
            "Amazon Elastic Compute Cloud - Compute",
            42.5,
        ),
    }
    assert {
        (row["tag_key"], row["tag_value"], row["service"], row["resource_count"])
        for row in first["resource_inventory"]
    } == {
        ("aws-parallelcluster-clustername", "cluster-a", "ec2", 1),
        ("aws-parallelcluster-project", "project-a", "ec2", 1),
        ("aws-parallelcluster-project", "project-a", "fsx", 1),
    }
    assert session_factory.sts.calls == 1
    assert session_factory.budgets.calls == 0
