"""Local semantic dictionary. Suggestions are conservative and always editable."""

from copy import deepcopy

from .models import ColumnMetadata


NUMERIC_TYPES = {
    "TINYINT",
    "SMALLINT",
    "INTEGER",
    "BIGINT",
    "HUGEINT",
    "UTINYINT",
    "USMALLINT",
    "UINTEGER",
    "UBIGINT",
    "UHUGEINT",
    "FLOAT",
    "REAL",
    "DOUBLE",
    "DECIMAL",
}
QUANTITATIVE = {"continuous", "discrete"}


def numeric_type(physical):
    return physical.split("(", 1)[0].upper() in NUMERIC_TYPES


def suggest(column):
    name, physical = column["name"], column["type"]
    lower = name.lower()
    if lower == "id" or lower.endswith("_id"):
        semantic = "identifier"
    elif "DATE" in physical or "TIME" in physical:
        semantic = "date"
    elif physical == "BOOLEAN":
        semantic = "binary"
    elif any(word in lower for word in ("codigo", "código", "code", "category", "categoria")):
        semantic = "nominal"
    elif numeric_type(physical):
        semantic = "discrete" if "INT" in physical else "continuous"
    else:
        semantic = "nominal"
    return {
        **ColumnMetadata(semantic_type=semantic).model_dump(),
        "suggested": True,
        "lineage": [{"operation": "import", "column": name}],
    }


def dictionary(data):
    saved = data.get("dictionary", {})
    return {
        c["name"]: deepcopy(saved.get(c["name"], suggest(c))) for c in data["profile"]["columns"]
    }


def derive(current, step, schema, other=None):
    """Retain meanings only where the transformation preserves them."""
    result = deepcopy(current)
    if step.op == "rename":
        result[step.alias] = result.pop(step.column)
    elif step.op in ("date_part", "ratio"):
        result[step.alias] = suggest(next(c for c in schema if c["name"] == step.alias))
        result[step.alias]["semantic_type"] = "discrete" if step.op == "date_part" else "continuous"
        result[step.alias]["suggested"] = True
        result[step.alias]["provenance"] = (
            f"{step.op}: {step.column} / {step.denominator or step.part}"
        )
        result[step.alias]["lineage"] = deepcopy(current[step.column].get("lineage", []))
    elif step.op == "aggregate":
        result = {n: result[n] for n in step.columns}
        for metric in step.metrics:
            meta = suggest(next(c for c in schema if c["name"] == metric.alias))
            meta["semantic_type"] = "discrete" if metric.function == "count" else "continuous"
            if metric.column and metric.function != "count":
                meta["unit"] = current[metric.column].get("unit", "")
                meta["lineage"] = deepcopy(current[metric.column].get("lineage", []))
            meta["provenance"] = f"{metric.function}({metric.column or '*'})"
            result[metric.alias] = meta
    elif step.op == "join" and other:
        used = {n.casefold() for n in result}
        for name, meta in other.items():
            if name == step.right_key:
                continue
            alias = name if name.casefold() not in used else name + "_right"
            while alias.casefold() in used:
                alias += "_right"
            used.add(alias.casefold())
            result[alias] = deepcopy(meta)
    elif step.op == "concat" and other:
        for name in result:
            if name in other and any(
                result[name].get(k) != other[name].get(k)
                for k in ("semantic_type", "unit", "labels", "expected_categories")
            ):
                result[name] = suggest(next(c for c in schema if c["name"] == name))
                result[name]["provenance"] = (
                    "Concatenación: definiciones incompatibles; revisar significado y códigos."
                )
    if step.op in ("cast", "fill_null") and step.column in result:
        result[step.column]["provenance"] = (
            f"{step.op}: revisar restricciones y significado tras la transformación."
        )
    names = {c["name"] for c in schema}
    result = {n: meta for n, meta in result.items() if n in names}
    for name in names:
        result.setdefault(name, suggest(next(c for c in schema if c["name"] == name)))
        result[name].setdefault("lineage", []).append(
            {"operation": step.op, "source_column": step.column, "source_dataset": step.dataset_id}
        )
    return result
