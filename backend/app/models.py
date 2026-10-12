from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)


class Metric(StrictModel):
    column: str | None = None
    function: Literal["sum", "avg", "min", "max", "count"]
    alias: str = Field(min_length=1, max_length=120)


class Step(StrictModel):
    op: Literal[
        "select",
        "filter",
        "deduplicate",
        "drop_nulls",
        "fill_null",
        "cast",
        "rename",
        "join",
        "concat",
        "aggregate",
        "date_part",
        "ratio",
        "sort",
    ]
    columns: list[str] = Field(default_factory=list, max_length=100)
    column: str | None = None
    operator: (
        Literal["eq", "ne", "gt", "ge", "lt", "le", "contains", "is_null", "not_null"] | None
    ) = None
    value: str | int | float | bool | None = None
    target_type: Literal["VARCHAR", "DOUBLE", "BIGINT", "DATE", "TIMESTAMP", "BOOLEAN"] | None = (
        None
    )
    alias: str | None = Field(default=None, max_length=120)
    dataset_id: str | None = None
    left_key: str | None = None
    right_key: str | None = None
    how: Literal["left", "inner"] = "left"
    allow_many_to_many: bool = False
    metrics: list[Metric] = Field(default_factory=list, max_length=20)
    part: Literal["year", "month", "day", "quarter", "week", "dow"] | None = None
    denominator: str | None = None
    descending: bool = False


class DataFilter(StrictModel):
    column: str = Field(min_length=1, max_length=200)
    operator: Literal["eq", "ne", "gt", "ge", "lt", "le", "contains", "is_null", "not_null"] = "eq"
    value: str | int | float | bool | None = None


class ColumnMetadata(StrictModel):
    description: str = Field(default="", max_length=2000)
    unit: str = Field(default="", max_length=100)
    semantic_type: Literal[
        "continuous", "discrete", "nominal", "ordinal", "binary", "date", "identifier"
    ]
    labels: dict[str, str] = Field(default_factory=dict, max_length=200)
    expected_categories: list[str | int | float | bool] = Field(
        default_factory=list, max_length=200
    )
    minimum: float | None = Field(default=None, allow_inf_nan=False)
    maximum: float | None = Field(default=None, allow_inf_nan=False)
    nullable: bool = True
    is_target: bool = False
    target_meaning: str = Field(default="", max_length=2000)
    provenance: str = Field(default="", max_length=2000)


class DictionaryUpdate(StrictModel):
    columns: dict[str, ColumnMetadata] = Field(max_length=200)


class QualityRequest(StrictModel):
    duplicate_keys: list[str] = Field(default_factory=list, max_length=20)
    exact_quantiles: bool = False


class ChartSpec(StrictModel):
    kind: Literal["bar", "line", "scatter", "histogram", "box", "correlation"] = "bar"
    x: str = Field(min_length=1, max_length=200)
    y: str | None = None
    title: str = Field(default="", max_length=200)
    group: str | None = None
    aggregation: Literal["count", "sum", "avg", "min", "max", "median"] | None = None
    measure: Literal["count", "percentage"] = "count"
    denominator: Literal["used", "filtered", "group"] = "used"
    missing: Literal["exclude", "include"] = "include"
    filters: list[DataFilter] = Field(default_factory=list, max_length=10)
    order: Literal["x", "value", "value_desc"] = "x"
    bar_mode: Literal["group", "stack"] = "group"
    bins: int = Field(default=20, ge=2, le=100)
    bin_start: float | None = Field(default=None, allow_inf_nan=False)
    bin_end: float | None = Field(default=None, allow_inf_nan=False)
    sample_size: int = Field(default=5000, ge=1, le=20000)
    seed: int = Field(default=42, ge=0, le=2147483647)
    columns: list[str] = Field(default_factory=list, max_length=12)
    category_limit: int = Field(default=100, ge=1, le=200)
    x_label: str = Field(default="", max_length=200)
    y_label: str = Field(default="", max_length=200)
    x_unit: str = Field(default="", max_length=100)
    y_unit: str = Field(default="", max_length=100)


class AnalysisRequest(StrictModel):
    kind: Literal["chart", "quality", "export", "categories"]
    chart: ChartSpec | None = None
    quality: QualityRequest | None = None
    export: "ExportRequest | None" = None
    category_column: str | None = None


class Plan(StrictModel):
    name: str = Field(default="Análisis", max_length=120)
    explanation: str = Field(default="", max_length=2000)
    steps: list[Step] = Field(default_factory=list, max_length=30)
    charts: list[ChartSpec] = Field(default_factory=list, max_length=8)
    questions: list[str] = Field(default_factory=list, max_length=8)


class RunRequest(StrictModel):
    dataset_id: str
    plan: Plan


class SampleConsent(StrictModel):
    dataset_ids: list[str] = Field(min_length=1, max_length=20)
    columns: list[str] = Field(min_length=1, max_length=100)
    rows: int = Field(default=5, ge=1, le=10)


class InterpretRequest(StrictModel):
    dataset_id: str
    instruction: str = Field(min_length=3, max_length=4000)
    consent_id: str | None = None


class ExportRequest(StrictModel):
    charts: list[ChartSpec] = Field(min_length=1, max_length=8)
    title: str = Field(default="Dashboard", max_length=200)
    filter_columns: list[str] = Field(default_factory=list, max_length=3)
    limit: int = Field(default=5000, ge=1, le=20000)


class DashboardCreate(ExportRequest):
    dataset_id: str


AnalysisRequest.model_rebuild()
