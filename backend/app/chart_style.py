"""Shared technical presentation for application and standalone dashboards."""

import hashlib
import json

PRESENTATION_VERSION = "technical-1"
PALETTE = [
    "#2563eb",
    "#ea580c",
    "#0891b2",
    "#7c3aed",
    "#16a34a",
    "#db2777",
    "#ca8a04",
    "#4f46e5",
    "#0d9488",
    "#dc2626",
    "#475569",
    "#9333ea",
]


def color(value):
    key = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return PALETTE[int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % len(PALETTE)]


def style_figure(spec, rows, traces, layout):
    layout.update(
        colorway=PALETTE,
        paper_bgcolor="#ffffff",
        plot_bgcolor="#f8fafc",
        font={"family": "Segoe UI, system-ui, sans-serif", "size": 12, "color": "#334155"},
        hoverlabel={"bgcolor": "#0f172a", "font": {"color": "#ffffff"}, "bordercolor": "#334155"},
        legend={"orientation": "h", "y": -0.22, "x": 0, "font": {"size": 12}},
        margin={"t": 58, "l": 72, "r": 28, "b": 90},
    )
    for axis in ("xaxis", "yaxis"):
        layout.setdefault(axis, {}).update(
            gridcolor="#e2e8f0",
            zerolinecolor="#cbd5e1",
            linecolor="#cbd5e1",
            showline=True,
            ticks="outside",
            tickcolor="#94a3b8",
            automargin=True,
        )
    if spec.kind == "correlation":
        for trace in traces:
            trace.update(
                colorscale=[[0, "#2563eb"], [0.5, "#f8fafc"], [1, "#ea580c"]],
                zmid=0,
                colorbar={"title": {"text": "Pearson r"}, "thickness": 14},
            )
        return traces
    if spec.kind == "box" and traces:
        original = traces[0]
        boxes = []
        for i, row in enumerate(rows):
            tone = (
                color({"column": spec.group or spec.x, "value": row.get("group")})
                if spec.group
                else PALETTE[0]
            )
            box = {
                **original,
                "name": original["x"][i],
                "marker": {"color": tone},
                "line": {"color": tone, "width": 2},
                "fillcolor": f"rgba({int(tone[1:3], 16)},{int(tone[3:5], 16)},{int(tone[5:7], 16)},0.16)",
                "showlegend": bool(spec.group),
            }
            for key in ("x", "q1", "median", "q3", "lowerfence", "upperfence", "customdata"):
                box[key] = [original[key][i]]
            boxes.append(box)
        return boxes
    groups = list(dict.fromkeys(r.get("series", r.get(spec.group)) for r in rows))
    for index, trace in enumerate(traces):
        group = groups[index] if index < len(groups) else None
        tone = color({"column": spec.group, "value": group}) if spec.group else PALETTE[0]
        marker = {"color": tone}
        if spec.kind == "bar" and not spec.group:
            marker["color"] = [
                color({"column": spec.x, "value": value}) for value in trace.get("x", [])
            ]
            marker["line"] = {"color": "#ffffff", "width": 1}
        if spec.kind == "scatter":
            marker.update(size=6, opacity=0.7)
        trace.update(marker=marker)
        if spec.kind == "line":
            trace.update(line={"color": tone, "width": 2.5})
    return traces
