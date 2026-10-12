import {useEffect,useState} from 'react';
import {api,compute} from './client';
import type {Column,Metadata} from './exploration-types';

const semanticNames:Record<Metadata['semantic_type'],string>={continuous:'Numérica continua',discrete:'Numérica discreta',nominal:'Nominal',ordinal:'Ordinal',binary:'Binaria',date:'Fecha',identifier:'Identificador'};
export function Dictionary({projectId,datasetId,columns,onSaved}:{projectId:string;datasetId:string;columns:Column[];onSaved:()=>Promise<void>}){
  const [dictionary,setDictionary]=useState<Record<string,Metadata>>({});
  const [selected,setSelected]=useState(columns[0]?.name||'');
  const [draft,setDraft]=useState<Metadata|null>(null),[labels,setLabels]=useState('{}'),[expected,setExpected]=useState('[]');
  const [keys,setKeys]=useState<string[]>([]),[exact,setExact]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
  useEffect(()=>{let active=true;void api<{columns:Record<string,Metadata>}>(`/projects/${projectId}/datasets/${datasetId}/dictionary`).then(r=>{if(active){setDictionary(r.columns);setSelected(columns[0]?.name||'');}}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[projectId,datasetId]);
  useEffect(()=>{const m=dictionary[selected];if(m){setDraft({...m});setLabels(JSON.stringify(m.labels||{},null,2));setExpected(JSON.stringify(m.expected_categories||[]));}},[selected,dictionary]);
  async function perform(fn:()=>Promise<void>){setBusy(true);setError('');setMessage('');try{await fn();}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
  async function save(){if(!draft)return;await perform(async()=>{
    const {suggested:_,lineage:__,...body}=draft;
    const result=await api<{columns:Record<string,Metadata>}>(`/projects/${projectId}/datasets/${datasetId}/dictionary`,{columns:{[selected]:{...body,labels:JSON.parse(labels),expected_categories:JSON.parse(expected)}}});
    setDictionary(result.columns);await onSaved();setMessage('Diccionario guardado. Recalcula calidad y gráficos para aplicar los significados nuevos.');
  });}
  return <>
    <section className="card"><h2>Diccionario de datos</h2><p className="muted">El tipo físico describe el almacenamiento; el semántico define qué cálculos tienen sentido. Las sugerencias se pueden corregir. Un código entero puede ser una categoría.</p>
      <label>Variable del diccionario<select value={selected} onChange={e=>setSelected(e.target.value)}>{columns.map(c=><option key={c.name}>{c.name}</option>)}</select></label>
      {draft&&<><p className="small">Tipo físico: {columns.find(c=>c.name===selected)?.type} · {draft.suggested?'Sugerencia automática pendiente de revisión':'Definición editada por el usuario'}</p><div className="form-grid">
        <label>Descripción<input value={draft.description} onChange={e=>setDraft({...draft,description:e.target.value})}/></label>
        <label>Unidad<input value={draft.unit} onChange={e=>setDraft({...draft,unit:e.target.value})}/></label>
        <label>Tipo semántico<select value={draft.semantic_type} onChange={e=>setDraft({...draft,semantic_type:e.target.value as Metadata['semantic_type']})}>{Object.entries(semanticNames).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>
        <label>Procedencia<input value={draft.provenance} onChange={e=>setDraft({...draft,provenance:e.target.value})}/></label>
        <label>Códigos y etiquetas (JSON)<textarea aria-label="Códigos y etiquetas" value={labels} onChange={e=>setLabels(e.target.value)}/></label>
        <label>Categorías esperadas (JSON)<textarea aria-label="Categorías esperadas" value={expected} onChange={e=>setExpected(e.target.value)}/></label>
        <label>Mínimo permitido<input type="number" value={draft.minimum??''} onChange={e=>setDraft({...draft,minimum:e.target.value===''?null:Number(e.target.value)})}/></label>
        <label>Máximo permitido<input type="number" value={draft.maximum??''} onChange={e=>setDraft({...draft,maximum:e.target.value===''?null:Number(e.target.value)})}/></label>
      </div><div className="check-columns"><label><input type="checkbox" checked={draft.nullable} onChange={e=>setDraft({...draft,nullable:e.target.checked})}/>Permitir valores ausentes</label><label><input type="checkbox" checked={draft.is_target} onChange={e=>setDraft({...draft,is_target:e.target.checked})}/>Variable objetivo definida por el usuario</label></div>
      {draft.is_target&&<label>Significado y procedencia del objetivo<textarea value={draft.target_meaning} onChange={e=>setDraft({...draft,target_meaning:e.target.value})}/></label>}
      <button disabled={busy} onClick={()=>void save()}>Guardar diccionario</button>
      <details><summary>Trazabilidad de la variable</summary><pre>{JSON.stringify(draft.lineage,null,2)}</pre></details></>}
      {error&&<p role="alert" className="message error">{error}</p>}{message&&<p role="status">{message}</p>}
    </section>
    <section className="card"><h2>Calidad detallada y duplicados</h2><p className="muted">Calcula duplicados exactos, reglas e IQR sin eliminar filas. El cálculo se ejecuta en un trabajo cancelable. Los cuartiles aproximados usan T-Digest; la opción exacta puede requerir más memoria.</p>
      <div className="check-columns"><p>Claves para comparar duplicados (opcional)</p>{columns.map(c=><label key={c.name}><input type="checkbox" checked={keys.includes(c.name)} onChange={()=>setKeys(keys.includes(c.name)?keys.filter(k=>k!==c.name):[...keys,c.name])}/>{c.name}</label>)}</div>
      <label className="check-columns"><input type="checkbox" checked={exact} onChange={e=>setExact(e.target.checked)}/>Cuartiles exactos (interpolación tipo 7)</label>
      <button disabled={busy} onClick={()=>void perform(async()=>{await compute(projectId,datasetId,{kind:'quality',quality:{duplicate_keys:keys,exact_quantiles:exact}});await onSaved();setMessage('Calidad recalculada sobre todo el dataset.');})}>{busy?'Calculando…':'Recalcular calidad'}</button>
    </section>
  </>;
}
