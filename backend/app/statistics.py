"""Bounded DuckDB descriptive calculations; never materialize whole data in Python."""

import math
import hashlib
import json
from datetime import datetime, timezone

import duckdb

from .engine import identifier, json_value, literal, rows_json
from .metadata import QUANTITATIVE, numeric_type, suggest
from .chart_style import PRESENTATION_VERSION, style_figure

CALCULATION_VERSION = "exploration-1"


def calculation_key(data, parameters):
    identity = {
        "dataset": data["id"],
        "version": data.get("job_id", data.get("path")),
        "dictionary_revision": data.get("dictionary_revision", 0),
        "parameters": parameters,
        "algorithm": CALCULATION_VERSION,
        "duckdb": duckdb.__version__,
        "presentation": PRESENTATION_VERSION,
    }
    return hashlib.sha256(
        json.dumps(identity, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()


def finite(column, physical):
    return (
        f"({column} IS NOT NULL AND isfinite(CAST({column} AS DOUBLE)))"
        if numeric_type(physical)
        else f"{column} IS NOT NULL"
    )


def profile(engine, relation, metadata=None, quality=None):
    schema = engine.schema(relation)
    if len(schema) > 200:
        raise ValueError("Máximo 200 columnas por tabla.")
    metadata = metadata or {c["name"]: suggest(c) for c in schema}
    total = engine.con.execute(f"SELECT count(*) FROM {relation}").fetchone()[0]
    columns = []
    for col in schema:
        name, physical = col["name"], col["type"]
        q = identifier(name)
        meta = metadata.get(name, suggest(col))
        valid = finite(q, physical)
        n, nulls, nonfinite, distinct = engine.con.execute(
            f"SELECT count(*) FILTER(WHERE {valid}), count(*) FILTER(WHERE {q} IS NULL), "
            f"count(*) FILTER(WHERE {q} IS NOT NULL AND NOT ({valid})), approx_count_distinct({q}) FROM {relation}"
        ).fetchone()
        item = {
            **col,
            "semantic_type": meta["semantic_type"],
            "valid": n,
            "nulls": nulls,
            "nonfinite": nonfinite,
            "null_pct": round(100 * nulls / total, 2) if total else 0,
            "cardinality": distinct,
            "cardinality_method": "approx_count_distinct (HyperLogLog)",
            "counts_method": "exact",
            "suggested": meta.get("suggested", True),
        }
        if meta["semantic_type"] in QUANTITATIVE and numeric_type(physical):
            quantile = "quantile_cont" if quality and quality.exact_quantiles else "approx_quantile"
            values = engine.con.execute(
                f"SELECT min({q}),max({q}),avg({q}),stddev_samp({q}),{quantile}({q},[0.25,0.5,0.75]) "
                f"FROM {relation} WHERE {valid}"
            ).fetchone()
            qs = values[4] or [None, None, None]
            item.update(
                min=json_value(values[0]),
                max=json_value(values[1]),
                mean=json_value(values[2]),
                stddev=json_value(values[3]),
                q1=json_value(qs[0]),
                median=json_value(qs[1]),
                q3=json_value(qs[2]),
                statistics_method="min/max/avg/stddev_samp exactos; desviación n−1",
                quantile_method="exact: quantile_cont, interpolación tipo 7"
                if quantile == "quantile_cont"
                else "approximate: approx_quantile, T-Digest",
            )
            if all(v is not None for v in qs):
                iqr = float(qs[2]) - float(qs[0])
                low, high = float(qs[0]) - 1.5 * iqr, float(qs[2]) + 1.5 * iqr
                outliers = engine.con.execute(
                    f"SELECT count(*) FROM {relation} WHERE {valid} AND ({q} < {literal(low)} OR {q} > {literal(high)})"
                ).fetchone()[0]
                item.update(
                    iqr=iqr,
                    outliers=outliers,
                    fences=[low, high],
                    outlier_method="IQR: fuera de Q1−1.5×IQR, Q3+1.5×IQR; conteo exacto con estos umbrales",
                )
        if meta["semantic_type"] in {"nominal", "ordinal", "binary", "discrete"}:
            item["frequencies"] = rows_json(
                engine.con.execute(
                    f"SELECT {q} AS value,count(*) AS count FROM {relation} GROUP BY {q} ORDER BY count DESC, CAST({q} AS VARCHAR) NULLS LAST LIMIT 21"
                )
            )
            item["categories_truncated"] = len(item["frequencies"]) > 20
            item["frequencies"] = item["frequencies"][:20]
            item["frequencies_method"] = "exact: top 20; ausentes incluidos; no renormalizado"
        rules = []
        if not meta.get("nullable", True):
            rules.append(f"{q} IS NULL")
        if meta.get("expected_categories"):
            codes = ",".join(
                literal(str(v).lower() if isinstance(v, bool) else str(v))
                for v in meta["expected_categories"]
            )
            rules.append(f"({q} IS NOT NULL AND CAST({q} AS VARCHAR) NOT IN ({codes}))")
        for key, op in (("minimum", "<"), ("maximum", ">")):
            if meta.get(key) is not None:
                rules.append(
                    f"(TRY_CAST({q} AS DOUBLE) IS NULL AND {q} IS NOT NULL OR TRY_CAST({q} AS DOUBLE) {op} {literal(meta[key])})"
                )
        item["rule_violations"] = (
            engine.con.execute(
                f"SELECT count(*) FROM {relation} WHERE " + " OR ".join(f"({r})" for r in rules)
            ).fetchone()[0]
            if rules
            else 0
        )
        item["rules_defined"] = bool(rules)
        columns.append(item)
    result = {
        "rows": total,
        "columns": columns,
        "preview": engine.preview(relation),
        "scope": "Conteos sobre toda la tabla; cuartiles aproximados salvo solicitud exacta; vista previa hasta 50 filas.",
        "calculation_version": CALCULATION_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "limitations": [
            "Cardinalidad aproximada; frecuencias: hasta 20 categorías por columna.",
            "Los atípicos IQR son señales descriptivas; no se elimina ninguna fila.",
            "Cuartiles exactos y duplicados requieren trabajo explícito y pueden agotar memoria en datos muy grandes.",
        ],
    }
    if quality:
        names = {c["name"] for c in schema}
        if not set(quality.duplicate_keys) <= names:
            raise ValueError("Clave de duplicados desconocida.")
        full = engine.con.execute(
            f"SELECT count(*) FROM (SELECT DISTINCT * FROM {relation})"
        ).fetchone()[0]
        result["exact_duplicates"] = total - full
        result["duplicates_definition"] = (
            "Filas excedentes respecto a combinaciones distintas; NULL se agrupa con NULL. No se eliminan."
        )
        if quality.duplicate_keys:
            keys = ",".join(identifier(k) for k in quality.duplicate_keys)
            unique = engine.con.execute(
                f"SELECT count(*) FROM (SELECT DISTINCT {keys} FROM {relation})"
            ).fetchone()[0]
            result["key_duplicates"] = {
                "keys": quality.duplicate_keys,
                "count": total - unique,
                "method": "exact",
            }
    return result


def filter_relation(engine, relation, filters):
    from .models import Step

    for condition in filters:
        sql, _ = engine.compile_step(relation, Step(op="filter", **condition.model_dump()))
        relation = f"({sql})"
    return relation


def axis_label(spec, field, metadata):
    name = getattr(spec, field) or "Frecuencia"
    label = getattr(spec, field + "_label") or name
    unit = getattr(spec, field + "_unit") or metadata.get(name, {}).get("unit", "")
    return f"{label} ({unit})" if unit else label


def label_value(value, name, metadata):
    if value is None:
        return "(ausente)"
    code = str(value).lower() if isinstance(value, bool) else str(value)
    return metadata.get(name, {}).get("labels", {}).get(code, code)


def plot_number(value):
    # Decimal values stay exact strings in result tables, but Plotly needs numeric axes.
    return float(value) if isinstance(value, str) else value


def calculate_chart(engine, relation, spec, limit=5000, metadata=None, dataset=None):
    schema = {c["name"]: c["type"] for c in engine.schema(relation)}
    metadata = metadata or {n: suggest({"name": n, "type": t}) for n, t in schema.items()}
    refs = (
        [spec.x]
        + ([spec.y] if spec.y else [])
        + ([spec.group] if spec.group else [])
        + spec.columns
    )
    if not set(refs) <= set(schema):
        raise ValueError("El gráfico referencia una columna que no existe.")
    if spec.measure == "percentage" and spec.kind not in ("bar", "histogram"):
        raise ValueError("El porcentaje se admite en barras e histogramas.")
    if spec.measure == "percentage" and spec.aggregation not in (None, "count"):
        raise ValueError("El porcentaje describe frecuencias; selecciona agregación count.")
    if spec.denominator == "group" and not spec.group:
        raise ValueError("El denominador por grupo requiere una columna de agrupación.")
    if spec.kind == "correlation" and spec.group:
        raise ValueError(
            "Pearson muestra un mapa del dataset filtrado; usa filtros para seleccionar un grupo."
        )
    if spec.kind == "line" and spec.aggregation is not None:
        if metadata[spec.x]["semantic_type"] not in QUANTITATIVE | {"date"}:
            raise ValueError(
                "Las líneas agregadas necesitan tiempo u otro eje cuantitativo ordenado; usa barras para categorías."
            )
        if spec.order != "x":
            raise ValueError(
                "Las líneas agregadas se ordenan por X para conservar el significado del eje."
            )
    filtered = filter_relation(engine, relation, spec.filters)
    total = engine.con.execute(f"SELECT count(*) FROM {relation}").fetchone()[0]
    filtered_rows = engine.con.execute(f"SELECT count(*) FROM {filtered}").fetchone()[0]
    warnings = []
    source = filtered
    x = identifier(spec.x)
    group = identifier(spec.group) if spec.group else None
    requirements = []

    def quantitative(name):
        if (
            not name
            or not numeric_type(schema[name])
            or metadata[name]["semantic_type"] not in QUANTITATIVE
        ):
            raise ValueError(
                f"{name}: requiere una variable numérica continua/discreta; revisa el diccionario (no códigos nominales ni identificadores)."
            )

    if spec.kind in ("histogram", "box", "scatter"):
        quantitative(spec.x)
        requirements.append(finite(x, schema[spec.x]))
    elif spec.missing == "exclude" and spec.kind != "correlation":
        requirements.append(finite(x, schema[spec.x]))
    elif spec.kind != "correlation" and numeric_type(schema[spec.x]):
        requirements.append(f"({x} IS NULL OR isfinite(CAST({x} AS DOUBLE)))")
    if spec.y and (
        spec.kind == "scatter"
        or spec.aggregation not in (None, "count")
        or (spec.kind in ("bar", "line") and spec.aggregation is None and spec.measure == "count")
    ):
        if spec.aggregation is not None or spec.kind == "scatter":
            quantitative(spec.y)
        elif not numeric_type(schema[spec.y]):
            raise ValueError("La columna Y debe ser numérica.")
        requirements.append(finite(identifier(spec.y), schema[spec.y]))
    if group and spec.missing == "exclude":
        requirements.append(finite(group, schema[spec.group]))
    elif group and numeric_type(schema[spec.group]):
        requirements.append(f"({group} IS NULL OR isfinite(CAST({group} AS DOUBLE)))")
    if requirements:
        source = f"(SELECT * FROM {filtered} WHERE {' AND '.join(requirements)})"
    used = engine.con.execute(f"SELECT count(*) FROM {source}").fetchone()[0]
    if filtered_rows != used:
        warnings.append(
            f"{filtered_rows - used} filas excluidas por ausentes o valores no finitos en las variables del gráfico."
        )
    rows, traces, sampled, truncated = [], [], False, False
    methods = []
    denominators = []
    layout = {
        "title": {"text": spec.title or spec.x},
        "barmode": spec.bar_mode,
        "xaxis": {"title": {"text": axis_label(spec, "x", metadata)}},
        "yaxis": {
            "title": {
                "text": "Porcentaje (%)"
                if spec.measure == "percentage"
                else axis_label(spec, "y", metadata)
            }
        },
    }
    if spec.measure != "percentage" and (spec.kind == "histogram" or spec.aggregation == "count"):
        layout["yaxis"] = {"title": {"text": spec.y_label or "Frecuencia"}}
    if spec.kind == "correlation":
        candidates = [
            n
            for n in schema
            if numeric_type(schema[n]) and metadata[n]["semantic_type"] in QUANTITATIVE
        ]
        requested = spec.columns or candidates[:12]
        if not spec.columns and len(candidates) > 12:
            warnings.append(
                "Pearson limitado a las primeras 12 variables cuantitativas; selecciona las columnas explícitamente."
            )
        selected = [
            n
            for n in requested
            if numeric_type(schema[n]) and metadata[n]["semantic_type"] in QUANTITATIVE
        ]
        excluded = [n for n in requested if n not in selected]
        if len(selected) < 2:
            raise ValueError(
                "Pearson requiere al menos dos variables cuantitativas compatibles; excluye códigos e identificadores."
            )
        if excluded:
            warnings.append("Excluidas por semántica: " + ", ".join(excluded))
        z, pairs = [], []
        for a in selected:
            zs, ns = [], []
            for b in selected:
                aq, bq = identifier(a), identifier(b)
                good = finite(aq, schema[a]) + " AND " + finite(bq, schema[b])
                n, sx, sy, r = engine.con.execute(
                    f"SELECT count(*),stddev_pop({aq}),stddev_pop({bq}),corr({aq},{bq}) FROM {filtered} WHERE {good}"
                ).fetchone()
                r = json_value(r) if n >= 2 and sx and sy else None
                zs.append(r)
                ns.append(n)
                rows.append({"x": a, "y": b, "value": r, "n": n})
            z.append(zs)
            pairs.append(ns)
        traces = [
            {
                "type": "heatmap",
                "x": selected,
                "y": selected,
                "z": z,
                "zmin": -1,
                "zmax": 1,
                "colorscale": "RdBu",
                "customdata": pairs,
                "hovertemplate": "%{x} / %{y}<br>Pearson=%{z}<br>Pares válidos=%{customdata}<extra></extra>",
            }
        ]
        methods.append(
            "Pearson exacto sobre pares finitos, eliminación por pares; constante o n<2: no definido; máximo 12 columnas"
        )
        warnings.append(
            "Asociación descriptiva en este dataset; no demuestra causalidad ni predicción individual. Cada celda puede usar pares diferentes."
        )
        used = filtered_rows
        layout["xaxis"] = {}
        layout["yaxis"] = {}
    elif (
        spec.kind in ("bar", "line")
        and spec.aggregation is None
        and spec.y
        and spec.measure == "count"
    ):
        # Backwards-compatible precomputed values; never claim a complete distribution.
        projection = ",".join(
            identifier(n)
            for n in dict.fromkeys([spec.x, spec.y] + ([spec.group] if spec.group else []))
        )
        rows = engine.preview(
            f"(SELECT {projection} FROM {source} ORDER BY {x})", min(limit, spec.sample_size) + 1
        )
        truncated = len(rows) > min(limit, spec.sample_size)
        rows = rows[: min(limit, spec.sample_size)]
        for g in dict.fromkeys(r.get(spec.group) for r in rows):
            part = [r for r in rows if r.get(spec.group) == g]
            traces.append(
                {
                    "type": "bar" if spec.kind == "bar" else "scatter",
                    "mode": "lines+markers",
                    "name": label_value(g, spec.group, metadata) if spec.group else spec.y,
                    "x": [
                        label_value(r[spec.x], spec.x, metadata)
                        if spec.kind == "bar"
                        else plot_number(r[spec.x])
                        if numeric_type(schema[spec.x])
                        else r[spec.x]
                        for r in part
                    ],
                    "y": [plot_number(r[spec.y]) for r in part],
                }
            )
        methods.append("legacy: valores Y precomputados, sin reagregación; orden X")
        if truncated:
            warnings.append(
                "Vista parcial de valores precomputados. No usarla como distribución del dataset completo; selecciona una agregación explícita."
            )
    elif spec.kind == "scatter":
        if not spec.y:
            raise ValueError("Dispersión requiere X e Y.")
        size = min(5000, spec.sample_size)
        # Fixed input order, single-thread scan, seed and algorithm version in provenance.
        engine.con.execute("SET threads=1")
        projection = ",".join(
            identifier(n)
            for n in dict.fromkeys([spec.x, spec.y] + ([spec.group] if spec.group else []))
        )
        position = "__dsw_sample_position"
        while position.casefold() in {name.casefold() for name in schema}:
            position += "_"
        position = identifier(position)
        rows = rows_json(
            engine.con.execute(
                f"SELECT {projection} FROM (SELECT *, row_number() OVER () AS {position} FROM {source}) ORDER BY hash({position},{spec.seed}),{position} LIMIT {size}"
            )
        )
        sampled = used > size
        groups = list(dict.fromkeys(r.get(spec.group) for r in rows))
        if len(groups) > spec.category_limit:
            raise ValueError("Demasiados grupos de dispersión; filtra o reduce categorías.")
        for g in groups:
            part = [r for r in rows if r.get(spec.group) == g]
            traces.append(
                {
                    "type": "scattergl",
                    "mode": "markers",
                    "name": label_value(g, spec.group, metadata) if spec.group else "Observaciones",
                    "x": [plot_number(r[spec.x]) for r in part],
                    "y": [plot_number(r[spec.y]) for r in part],
                }
            )
        methods.append(
            f"Muestra por top-k hash(posición,{spec.seed}), lectura monohilo; estable para este Parquet, filtros y versión DuckDB {duckdb.__version__}"
        )
        warnings.append(
            "Asociación descriptiva; no implica causalidad ni probabilidades individuales."
        )
    elif spec.kind == "box":
        if group:
            group_values = rows_json(
                engine.con.execute(
                    f"SELECT {group} AS value, count(*) AS n FROM {source} GROUP BY {group} ORDER BY CAST({group} AS VARCHAR) NULLS LAST LIMIT {spec.category_limit + 1}"
                )
            )
        else:
            group_values = [{"value": None, "n": used}]
        if len(group_values) > spec.category_limit:
            raise ValueError("Demasiados grupos de box plot; aplica filtros.")
        for g in group_values:
            cond = f"WHERE {group} IS NOT DISTINCT FROM {literal(g['value'])}" if group else ""
            part = f"(SELECT * FROM {source} {cond})"
            q = engine.con.execute(
                f"SELECT quantile_cont({x},[0.25,0.5,0.75]) FROM {part}"
            ).fetchone()[0]
            if not q or any(v is None for v in q):
                continue
            q = [float(v) for v in q]
            iqr = q[2] - q[0]
            lo, hi = q[0] - 1.5 * iqr, q[2] + 1.5 * iqr
            lower, upper, out = engine.con.execute(
                f"SELECT min({x}) FILTER(WHERE {x}>={literal(lo)}),max({x}) FILTER(WHERE {x}<={literal(hi)}),count(*) FILTER(WHERE {x}<{literal(lo)} OR {x}>{literal(hi)}) FROM {part}"
            ).fetchone()
            rows.append(
                {
                    "group": g["value"],
                    "n": g["n"],
                    "q1": q[0],
                    "median": q[1],
                    "q3": q[2],
                    "lower_whisker": float(lower) if lower is not None else None,
                    "upper_whisker": float(upper) if upper is not None else None,
                    "outliers": out,
                }
            )
        traces = [
            {
                "type": "box",
                "name": spec.x,
                "x": [
                    label_value(r["group"], spec.group, metadata) if spec.group else spec.x
                    for r in rows
                ],
                "q1": [r["q1"] for r in rows],
                "median": [r["median"] for r in rows],
                "q3": [r["q3"] for r in rows],
                "lowerfence": [r["lower_whisker"] for r in rows],
                "upperfence": [r["upper_whisker"] for r in rows],
                "boxpoints": False,
                "customdata": [[r["n"], r["outliers"]] for r in rows],
                "hovertemplate": "n=%{customdata[0]}<br>Atípicos=%{customdata[1]}<extra></extra>",
            }
        ]
        layout["yaxis"] = {"title": {"text": axis_label(spec, "x", metadata)}}
        layout["xaxis"] = {"title": {"text": spec.group or "Dataset"}}
        methods.append(
            "Cuartiles exactos quantile_cont tipo 7; bigotes: valores observados extremos dentro de Q1−1.5 IQR y Q3+1.5 IQR; atípicos contados, sin datos individuales"
        )
    else:
        histogram = spec.kind == "histogram"
        if histogram:
            mn, mx = engine.con.execute(f"SELECT min({x}),max({x}) FROM {source}").fetchone()
            if mn is None:
                low = spec.bin_start if spec.bin_start is not None else 0.0
                high = spec.bin_end if spec.bin_end is not None else low + 1.0
            else:
                low = spec.bin_start if spec.bin_start is not None else float(mn)
                high = spec.bin_end if spec.bin_end is not None else float(mx)
            if high == low:
                low -= 0.5
                high += 0.5
            if not math.isfinite(low) or not math.isfinite(high) or high <= low:
                raise ValueError("Intervalos inválidos: fin debe ser mayor que inicio.")
            width = (high - low) / spec.bins
            if not math.isfinite(width) or width <= 0:
                raise ValueError("Rango no representable; transforma la escala explícitamente.")
            before_range = used
            source = f"(SELECT * FROM {source} WHERE {x}>={literal(low)} AND {x}<={literal(high)})"
            used = engine.con.execute(f"SELECT count(*) FROM {source}").fetchone()[0]
            if before_range != used:
                warnings.append(f"{before_range - used} valores fuera del intervalo solicitado.")
            key = f"least({spec.bins - 1},CAST(floor(({x}-{literal(low)})/{literal(width)}) AS INTEGER))"
            methods.append(
                f"Histograma exacto; {spec.bins} intervalos comunes a todos los grupos, [inicio,fin), último cerrado: [{low},{high}]"
            )
        else:
            key = x
            if spec.kind == "line" and spec.aggregation is None:
                raise ValueError("Las líneas requieren agregación explícita o Y precomputada.")
        agg = "count" if histogram else spec.aggregation or "count"
        if agg != "count" and not spec.y:
            raise ValueError("La agregación requiere una variable Y.")
        value = (
            "count(*)"
            if agg == "count"
            else (
                f"quantile_cont({identifier(spec.y)},0.5)"
                if agg == "median"
                else f"{agg}({identifier(spec.y)})"
            )
        )
        group_expr = group or "NULL"
        sql = (
            f"SELECT {key} AS x,{group_expr} AS series,{value} AS value,count(*) AS n FROM {source} GROUP BY {key}"
            + (f",{group}" if group else "")
        )
        order = (
            "x,CAST(series AS VARCHAR)"
            if spec.order == "x"
            else "value "
            + ("DESC" if spec.order == "value_desc" else "ASC")
            + ",CAST(x AS VARCHAR),CAST(series AS VARCHAR)"
        )
        max_results = spec.bins * spec.category_limit if histogram else spec.category_limit
        rows = rows_json(
            engine.con.execute(
                f"SELECT * FROM ({sql}) ORDER BY {order} NULLS LAST LIMIT {max_results + 1}"
            )
        )
        if len(rows) > max_results:
            raise ValueError(
                f"El gráfico supera {max_results} resultados agregados. Aplica filtros o reduce categorías; no se exporta un porcentaje parcial."
            )
        if histogram:
            # Include zero-frequency intervals so each group uses identical bin edges.
            groups = list(dict.fromkeys(r["series"] for r in rows)) or ([None] if not group else [])
            lookup = {(r["series"], r["x"]): r for r in rows}
            rows = [
                lookup.get((g, i), {"x": i, "series": g, "value": 0, "n": 0})
                for g in groups
                for i in range(spec.bins)
            ]
            for r in rows:
                r["bin_start"] = low + r["x"] * width
                r["bin_end"] = low + (r["x"] + 1) * width
        if spec.measure == "percentage":
            bases = {}
            denominator_source = filtered if spec.denominator == "filtered" else source
            if spec.denominator == "group":
                for r in rows:
                    bases[r["series"]] = bases.get(r["series"], 0) + r["n"]
            else:
                bases[None] = engine.con.execute(
                    f"SELECT count(*) FROM {denominator_source}"
                ).fetchone()[0]
            for r in rows:
                n = bases[r["series"] if spec.denominator == "group" else None]
                r["denominator"] = n
                r["value"] = 100 * r["n"] / n if n else None
            denominators = [{"group": json_value(g), "n": n} for g, n in bases.items()]
            methods.append(
                f"Porcentaje=100×frecuencia/denominador {spec.denominator}; no renormaliza categorías"
            )
        for g in dict.fromkeys(r["series"] for r in rows):
            part = [r for r in rows if r["series"] == g]
            xs = [
                (r["bin_start"] + r["bin_end"]) / 2
                if histogram
                else (
                    label_value(r["x"], spec.x, metadata)
                    if spec.kind == "bar"
                    else plot_number(r["x"])
                    if numeric_type(schema[spec.x])
                    else r["x"]
                )
                for r in part
            ]
            trace = {
                "type": "bar" if histogram or spec.kind == "bar" else "scatter",
                "mode": "lines+markers",
                "name": label_value(g, spec.group, metadata) if spec.group else agg,
                "x": xs,
                "y": [plot_number(r["value"]) for r in part],
                "customdata": [[r["n"], r.get("denominator")] for r in part],
                "hovertemplate": "%{x}<br>Valor=%{y}<br>n=%{customdata[0]}<br>Denominador=%{customdata[1]}<extra></extra>",
            }
            if histogram:
                trace["width"] = width * (0.9 if spec.bar_mode == "group" else 1)
            traces.append(trace)
        methods.append(f"Agregación {agg} exacta sobre toda la tabla filtrada; orden {spec.order}")
        if any(
            0 < sum(r["n"] for r in rows if r["series"] == g) < 20
            for g in dict.fromkeys(r["series"] for r in rows)
        ):
            warnings.append(
                "Hay grupos con menos de 20 observaciones; describe sus tamaños y evita generalizar a una población."
            )
    provenance = {
        "dataset_id": (dataset or {}).get("id"),
        "dataset_version": (dataset or {}).get("job_id", (dataset or {}).get("id")),
        "dictionary_revision": (dataset or {}).get("dictionary_revision", 0),
        "filters": [f.model_dump() for f in spec.filters],
        "population": "Filas de este dataset que cumplen los filtros; no se presupone una muestra representativa de una población externa.",
        "total_rows": total,
        "filtered_rows": filtered_rows,
        "used_rows": used,
        "displayed_rows": len(rows),
        "sampled": sampled,
        "approximate": False,
        "truncated": truncated,
        "seed": spec.seed if sampled else None,
        "denominators": denominators,
        "method": methods,
        "calculation_version": CALCULATION_VERSION,
        "duckdb_version": duckdb.__version__,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    traces = style_figure(spec, rows, traces, layout)
    return {
        "spec": spec.model_dump(),
        "rows": rows,
        "figure": {"data": traces, "layout": layout},
        "truncated": truncated,
        "scope": "Muestra reproducible"
        if sampled
        else "Vista parcial precomputada"
        if truncated
        else "Dataset completo filtrado",
        "provenance": provenance,
        "warnings": warnings,
    }
