import html
import json
from pathlib import Path

from plotly.offline import get_plotlyjs

from .metadata import dictionary, numeric_type


def safe_json(value):
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def export_dashboard(engine, relation, request, output: Path, provenance, dataset=None):
    names = {c["name"] for c in engine.schema(relation)}
    if not set(request.filter_columns) <= names:
        raise ValueError("Filtro desconocido.")
    metadata = dictionary(dataset) if dataset else None
    results = [
        engine.chart(relation, chart, limit=request.limit, metadata=metadata, dataset=dataset)
        for chart in request.charts
    ]
    legacy = all(
        c.kind in ("bar", "line") and c.aggregation is None and c.y and c.measure == "count"
        for c in request.charts
    )
    supported = [
        key
        for key in request.filter_columns
        if legacy and all(key in r["rows"][0] for r in results if r["rows"])
    ]
    disabled = [key for key in request.filter_columns if key not in supported]
    filter_note = (
        "Filtros locales: seleccionan únicamente observaciones precomputadas incluidas; no recalculan agregaciones ni porcentajes."
        if supported
        else "Instantánea estadística: los filtros del cálculo están fijados. Para recalcular con otros filtros utiliza la aplicación."
    )
    if disabled:
        filter_note += (
            " Filtros desactivados (necesitan backend o datos no incluidos): "
            + ", ".join(disabled)
            + "."
        )
    truncated = any(r["truncated"] for r in results)
    sampled = any(r["provenance"]["sampled"] for r in results)
    rows = results[0]["rows"] if legacy else []
    used_columns = (
        {c.x for c in request.charts}
        | {c.y for c in request.charts if c.y}
        | {c.group for c in request.charts if c.group}
    )
    payload = {
        "rows": rows,
        "charts": [c.model_dump() for c in request.charts],
        "results": results,
        "filters": supported,
        "disabled_filters": disabled,
        "filter_note": filter_note,
        "provenance": provenance,
        "truncated": truncated,
        "sampled": sampled,
        "labels": {n: metadata[n].get("labels", {}) for n in used_columns}
        if metadata and legacy
        else {},
        "numeric_columns": [
            c["name"]
            for c in engine.schema(relation)
            if c["name"] in used_columns and numeric_type(c["type"])
        ],
    }
    title = html.escape(request.title)
    note = (
        "Vista parcial de valores precomputados."
        if truncated
        else "Cálculos sobre el dataset completo filtrado."
    )
    if sampled:
        note += " La dispersión incluye una muestra reproducible identificada en su procedencia."
    document = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITLE__</title>
<style>body{margin:0;background:#edf1f7;color:#1e293b;font:14px "Segoe UI",system-ui,sans-serif}main{max-width:none;margin:0 auto;padding:28px 32px}h1{font-size:28px;letter-spacing:-.5px}.controls{display:flex;gap:16px;flex-wrap:wrap}select{padding:10px;max-width:260px;border:1px solid #cbd5e1;border-radius:5px;color:#334155}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,600px),1fr));gap:20px}.chart{background:white;border:1px solid #d5deeb;border-top:3px solid #2563eb;border-radius:6px;padding:18px;min-width:0}.chart:nth-child(4n+2){border-top-color:#ea580c}.chart:nth-child(4n+3){border-top-color:#0891b2}.chart:nth-child(4n+4){border-top-color:#7c3aed}.plot{height:460px;overflow:hidden}.note,footer{font-size:12px;color:#64748b;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f7fc;padding:12px}summary{color:#2563eb;cursor:pointer}@media(max-width:650px){main{padding:18px 12px}.plot{height:370px}.chart{padding:12px}}</style>
<script>__PLOTLY__</script></head><body><main><p>DATA SCIENCE WORKBENCH · EXPORTACIÓN AUTÓNOMA</p>
<h1>__TITLE__</h1><p>__NOTE__</p><p class="note" id="filter-note"></p>
<p class="note">Descripción, comparación y asociación en este dataset. No demuestra causalidad, no estima probabilidades individuales y no entrena modelos.</p>
<div class="controls" id="filters"></div><p id="count"></p><div class="grid" id="charts"></div><footer id="provenance"></footer></main>
<script>const data=JSON.parse(__DATA__);
const selected={};
document.getElementById('filter-note').textContent=data.filter_note;
for(const key of data.filters){const label=document.createElement('label');label.textContent=key+' ';const select=document.createElement('select');const all=document.createElement('option');all.value='';all.textContent='Todos';select.appendChild(all);
const values=[...new Set(data.rows.map(r=>JSON.stringify(r[key])))];
for(const value of values.slice(0,200)){const option=document.createElement('option');option.value=value;option.textContent=String(JSON.parse(value)??'(ausente)');select.appendChild(option);}
if(values.length>200){const note=document.createElement('small');note.textContent=' (hasta 200 valores disponibles)';label.appendChild(note);}
select.onchange=()=>{selected[key]=select.value;render();};label.appendChild(select);document.getElementById('filters').appendChild(label);}
data.results.forEach((r,i)=>{const card=document.createElement('section');card.className='chart';const div=document.createElement('div');div.id='chart-'+i;div.className='plot';card.appendChild(div);
const note=document.createElement('p');note.className='note';note.textContent=r.scope+' · '+r.warnings.join(' ');card.appendChild(note);
const details=document.createElement('details');const summary=document.createElement('summary');summary.textContent='Método, denominadores y procedencia';details.appendChild(summary);const pre=document.createElement('pre');pre.textContent=JSON.stringify(r.provenance,null,2);details.appendChild(pre);card.appendChild(details);document.getElementById('charts').appendChild(card);});
function render(){const visible=data.rows.filter(r=>Object.entries(selected).every(([k,v])=>!v||JSON.stringify(r[k])===v));document.getElementById('count').textContent=data.rows.length?visible.length+' filas visibles de '+data.rows.length:'Resultados agregados o muestras; consulta las filas utilizadas en cada gráfico.';
data.results.forEach((r,i)=>{let figure=r.figure;
if(data.filters.length&&Object.values(selected).some(Boolean)){const rows=r.rows.filter(r=>Object.entries(selected).every(([k,v])=>!v||JSON.stringify(r[k])===v));const c=r.spec;const groups=[...new Set(rows.map(r=>r[c.group]))];const label=(v,k)=>v==null?'(ausente)':(Object.hasOwn(data.labels,k)&&Object.hasOwn(data.labels[k],String(v))?data.labels[k][String(v)]:String(v));const numeric=v=>v==null?null:Number(v);figure={layout:r.figure.layout,data:groups.map(g=>{const part=rows.filter(r=>r[c.group]===g);const name=c.group?label(g,c.group):c.y;const original=r.figure.data.find(t=>t.name===name)||r.figure.data[0];const xs=part.map(r=>c.kind==='bar'?label(r[c.x],c.x):data.numeric_columns.includes(c.x)?numeric(r[c.x]):r[c.x]);const marker=original?.marker?{...original.marker}:undefined;if(marker&&Array.isArray(marker.color))marker.color=xs.map(x=>original.marker.color[original.x.indexOf(x)]);return {type:c.kind==='bar'?'bar':'scatter',mode:'lines+markers',x:xs,y:part.map(r=>numeric(r[c.y])),name,marker,line:original?.line};})};}
Plotly.react('chart-'+i,figure.data,figure.layout,{responsive:true,displaylogo:false});});}
document.getElementById('provenance').textContent='Procedencia: '+JSON.stringify(data.provenance);render();</script></body></html>"""
    document = (
        document.replace("__PLOTLY__", get_plotlyjs())
        .replace("__TITLE__", title)
        .replace("__NOTE__", html.escape(note))
        .replace("__DATA__", safe_json(safe_json(payload)))
    )
    output.write_text(document, encoding="utf-8")
    return {
        "rows": len(rows) if legacy else sum(len(r["rows"]) for r in results),
        "truncated": truncated,
        "sampled": sampled,
        "filter_mode": "precomputed_observations" if supported else "fixed_snapshot",
        "disabled_filters": disabled,
        "calculation_version": results[0]["provenance"]["calculation_version"],
    }
