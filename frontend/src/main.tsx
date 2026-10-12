import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import Plotly from 'plotly.js-dist-min';
import './style.css';
import './technical.css';
import {api,compute} from './client';
import {Dictionary} from './Dictionary';
import {ChartBuilder} from './ChartBuilder';
import {ProjectHome} from './ProjectHome';
import type {Chart,ChartResult,Column,Metadata} from './exploration-types';

type Row = Record<string, unknown>;
type Project = {id:string;name:string;description:string};
type Plan = {name:string;explanation:string;steps:Record<string,unknown>[];charts:Chart[];questions:string[]};
type Dataset = {id:string;name:string;parent_id:string|null;dictionary?:Record<string,Metadata>;dictionary_revision?:number;profile_stale?:boolean;profile:{rows:number;columns:Column[];preview:Row[];scope:string;exact_duplicates?:number;key_duplicates?:{keys:string[];count:number};limitations?:string[]};plan?:Plan;history?:{step:Record<string,unknown>;rows:number;rows_before?:number;rows_delta?:number;warning:string|null}[]};
type Job = {id:string;status:string;action:string;message:string;result_id?:string;created_at:string};
type Dashboard = {id:string;dataset_id:string;charts:Chart[];filter_columns:string[];title:string};
type Consent = {id:string;expires_at:string;samples:{dataset_id:string;rows:Row[]}[]};
const emptyPlan = ():Plan=>({name:'Datos preparados',explanation:'',steps:[],charts:[],questions:[]});
const number = (n:number)=>new Intl.NumberFormat('es-ES').format(n);
const numeric = (c:Column)=>/INT|DOUBLE|FLOAT|DECIMAL/.test(c.type);
const display = (v:unknown)=>v===null||v===undefined?'—':typeof v==='object'?JSON.stringify(v):String(v);
const chartData=(projectId:string,datasetId:string,spec:Chart)=>compute<ChartResult>(projectId,datasetId,{kind:'chart',chart:spec});
function Table({rows}:{rows:Row[]}){
  const keys=Object.keys(rows[0]||{});
  if(!rows.length)return <p className="empty">No hay filas para mostrar.</p>;
  return <div className="table-scroll"><table><thead><tr>{keys.map(k=><th key={k}>{k}</th>)}</tr></thead><tbody>{rows.map((r,i)=><tr key={i}>{keys.map(k=><td key={k} title={display(r[k])}>{display(r[k])}</td>)}</tr>)}</tbody></table></div>;
}
function Plot({result}:{result:ChartResult}){
  const ref=useRef<HTMLDivElement>(null);
  useEffect(()=>{
    const el=ref.current;if(!el)return;
    void Plotly.react(el,result.figure.data,{...result.figure.layout,autosize:true},{responsive:true,displaylogo:false});
    const observer=new ResizeObserver(()=>Plotly.Plots.resize(el));observer.observe(el);
    return()=>{observer.disconnect();Plotly.purge(el);};
  },[result]);
  return <div className="plot" ref={ref}/>;
}
const operationNames:Record<string,string>={deduplicate:'Eliminar duplicados',filter:'Filtrar filas',drop_nulls:'Quitar filas con nulos',fill_null:'Rellenar nulos',cast:'Convertir tipo',rename:'Renombrar columna',select:'Seleccionar columnas',aggregate:'Agrupar y calcular',join:'Unir tablas',concat:'Concatenar tablas',date_part:'Extraer parte de fecha',ratio:'Calcular cociente',sort:'Ordenar'};
const statusNames:Record<string,string>={queued:'En cola',running:'En curso',succeeded:'Completado',failed:'Error',cancelled:'Cancelado',interrupted:'Interrumpido'};
function App(){
  const [assistantOpen,setAssistantOpen]=useState(false),[focusView,setFocusView]=useState(false),[wideCharts,setWideCharts]=useState(true);
  const assistantPanelRef=useRef<HTMLElement>(null);
  useEffect(()=>{
    if(!assistantOpen)return;
    const previous=document.activeElement as HTMLElement|null;
    assistantPanelRef.current?.querySelector<HTMLButtonElement>('button')?.focus();
    const handleKey=(event:KeyboardEvent)=>{
      if(event.key==='Escape'){setAssistantOpen(false);return;}
      if(event.key!=='Tab')return;
      const items=Array.from(assistantPanelRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),textarea:not(:disabled),select:not(:disabled),a[href]')||[]).filter(el=>el.getClientRects().length);
      const first=items[0],last=items[items.length-1];
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
    };
    document.addEventListener('keydown',handleKey);
    return()=>{document.removeEventListener('keydown',handleKey);if(previous?.isConnected)previous.focus();};
  },[assistantOpen]);
  const [closed,setClosed]=useState(false);
  const restoring=useRef<Record<string,unknown>|null>(null);
  const [projects,setProjects]=useState<Project[]>([]),[projectId,setProjectId]=useState('');
  const [dataProjectId,setDataProjectId]=useState('');
  const [datasets,setDatasets]=useState<Dataset[]>([]),[datasetId,setDatasetId]=useState('');
  const [jobs,setJobs]=useState<Job[]>([]),[tab,setTab]=useState('datos');
  const [health,setHealth]=useState<{status:string;ai_configured:boolean;memory_limit:string;max_upload_gb:number}|null>(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const [newName,setNewName]=useState(''),[newProject,setNewProject]=useState(false);
  const [instruction,setInstruction]=useState(''),[planText,setPlanText]=useState(JSON.stringify(emptyPlan(),null,2));
  const [consent,setConsent]=useState<Consent|null>(null),[sampleColumns,setSampleColumns]=useState<string[]>([]),[sampleApproved,setSampleApproved]=useState(false),[samplePanel,setSamplePanel]=useState(false);
  const [rows,setRows]=useState<Row[]>([]),[offset,setOffset]=useState(0),[lastJob,setLastJob]=useState('');
  const [op,setOp]=useState('deduplicate'),[column,setColumn]=useState(''),[value,setValue]=useState(''),[alias,setAlias]=useState(''),[operator,setOperator]=useState('gt'),[targetType,setTargetType]=useState('DOUBLE'),[otherId,setOtherId]=useState(''),[rightKey,setRightKey]=useState(''),[metricFunction,setMetricFunction]=useState('sum'),[metricColumn,setMetricColumn]=useState(''),[selectedColumns,setSelectedColumns]=useState<string[]>([]),[datePart,setDatePart]=useState('month'),[denominator,setDenominator]=useState('');
  const [chartKind,setChartKind]=useState<Chart['kind']>('bar'),[chartX,setChartX]=useState(''),[chartY,setChartY]=useState(''),[chartTitle,setChartTitle]=useState(''),[charts,setCharts]=useState<ChartResult[]>([]),[exportFilters,setExportFilters]=useState<string[]>([]),[exportTitle,setExportTitle]=useState('Dashboard del proyecto');
  const [chartDraft,setChartDraft]=useState<Chart>({kind:'bar',x:'',y:null,title:'',aggregation:'count',missing:'exclude'});
  const [filterOptions,setFilterOptions]=useState<Record<string,{value:unknown;count:number}[]>>({});
  const [dashboards,setDashboards]=useState<Dashboard[]>([]),[activeFilters,setActiveFilters]=useState<Record<string,string>>({});
  const [audit,setAudit]=useState<{id:string;action:string;details:unknown;created_at:string}[]>([]);
  const project=projects.find(p=>p.id===projectId),dataset=datasets.find(d=>d.id===datasetId),columns=(dataset?.profile.columns||[]).map(c=>dataset?.profile_stale?{...c,min:undefined,max:undefined,mean:undefined,median:undefined,stddev:undefined,q1:undefined,q3:undefined,iqr:undefined,outliers:undefined,rule_violations:undefined}:c);
  let parsedPlan:Plan|null=null;try{parsedPlan=JSON.parse(planText);}catch{/* User may be editing JSON. */}
  async function action(fn:()=>Promise<void>){setBusy(true);setError('');setNotice('');try{await fn();}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
  useEffect(()=>{void api<Project[]>('/projects').then(p=>{setProjects(p);}).catch(e=>setError(e.message));void api<typeof health>('/health').then(h=>{setHealth(h);setClosed(h?.status==='closed');}).catch(e=>setError(e.message));},[]);
  useEffect(()=>{
    setDatasets([]);setDatasetId('');setJobs([]);setLastJob('');setConsent(null);setSampleApproved(false);setCharts([]);setDashboards([]);
    if(!projectId)return;
    let active=true;
    const refresh=async()=>{try{const [d,j,b]=await Promise.all([api<Dataset[]>(`/projects/${projectId}/datasets`),api<Job[]>(`/projects/${projectId}/jobs`),api<Dashboard[]>(`/projects/${projectId}/dashboards`)]);if(active){setDataProjectId(projectId);setDatasets(d);setJobs(j);setDashboards(b);}}catch(e){if(active)setError(e instanceof Error?e.message:String(e));}};
    void refresh();const timer=setInterval(()=>void refresh(),2000);return()=>{active=false;clearInterval(timer);};
  },[projectId]);
  useEffect(()=>{if(datasets.length&&!datasets.some(d=>d.id===datasetId)){const savedId=restoring.current?.datasetId;setDatasetId(datasets.find(d=>d.id===savedId)?.id||datasets[0].id);}},[datasets,datasetId]);
  useEffect(()=>{const done=jobs.find(j=>j.id===lastJob);if(done?.status==='succeeded'&&done.result_id){setDatasetId(done.result_id);setLastJob('');setNotice('Ejecución completada. El resultado está disponible.');}else if(done&&['failed','cancelled','interrupted'].includes(done.status)){if(done.status==='failed')setError(done.message);setLastJob('');}},[jobs,lastJob]);
  useEffect(()=>{
    setOffset(0);setRows([]);setConsent(null);setSampleApproved(false);setSampleColumns([]);setSelectedColumns([]);setExportFilters([]);setActiveFilters({});setCharts([]);
    const d=datasets.find(x=>x.id===datasetId);setRows(d?.profile.preview||[]);setPlanText(JSON.stringify(emptyPlan(),null,2));
    setChartDraft({kind:'bar',x:d?.profile.columns[0]?.name||'',y:null,title:'',aggregation:'count',missing:'exclude'});setFilterOptions({});
    const c=d?.profile.columns||[];setColumn(c[0]?.name||'');setChartX(c.find(x=>!numeric(x))?.name||c[0]?.name||'');setChartY(c.find(numeric)?.name||'');setMetricColumn(c.find(numeric)?.name||'');
    let active=true;
    if(!restoring.current&&d?.plan?.charts.length){const specs=d.plan.charts;void Promise.all(specs.map(spec=>chartData(projectId,datasetId,spec))).then(c=>{if(active)setCharts(c);}).catch(e=>{if(active)setError(e.message);});}
    const saved=restoring.current;
    if(saved&&projectId&&dataProjectId===projectId&&((datasetId&&datasets.some(x=>x.id===datasetId))||!datasets.length)){restoring.current=null;
      if(saved.instruction!==undefined)setInstruction(saved.instruction as typeof instruction);
      if(saved.planText!==undefined)setPlanText(saved.planText as typeof planText);
      if(saved.tab!==undefined)setTab(saved.tab as typeof tab);
      if(saved.op!==undefined)setOp(saved.op as typeof op);
      if(saved.column!==undefined)setColumn(saved.column as typeof column);
      if(saved.value!==undefined)setValue(saved.value as typeof value);
      if(saved.alias!==undefined)setAlias(saved.alias as typeof alias);
      if(saved.operator!==undefined)setOperator(saved.operator as typeof operator);
      if(saved.targetType!==undefined)setTargetType(saved.targetType as typeof targetType);
      if(saved.otherId!==undefined)setOtherId(saved.otherId as typeof otherId);
      if(saved.rightKey!==undefined)setRightKey(saved.rightKey as typeof rightKey);
      if(saved.metricFunction!==undefined)setMetricFunction(saved.metricFunction as typeof metricFunction);
      if(saved.metricColumn!==undefined)setMetricColumn(saved.metricColumn as typeof metricColumn);
      if(saved.selectedColumns!==undefined)setSelectedColumns(saved.selectedColumns as typeof selectedColumns);
      if(saved.datePart!==undefined)setDatePart(saved.datePart as typeof datePart);
      if(saved.denominator!==undefined)setDenominator(saved.denominator as typeof denominator);
      if(saved.chartKind!==undefined)setChartKind(saved.chartKind as typeof chartKind);
      if(saved.chartX!==undefined)setChartX(saved.chartX as typeof chartX);
      if(saved.chartY!==undefined)setChartY(saved.chartY as typeof chartY);
      if(saved.chartTitle!==undefined)setChartTitle(saved.chartTitle as typeof chartTitle);
      if(saved.exportFilters!==undefined)setExportFilters(saved.exportFilters as typeof exportFilters);
      if(saved.exportTitle!==undefined)setExportTitle(saved.exportTitle as typeof exportTitle);
      if(saved.activeFilters!==undefined)setActiveFilters(saved.activeFilters as typeof activeFilters);
      if(saved.chartDraft)setChartDraft(saved.chartDraft as Chart);
      const specs=(saved.chartSpecs||[]) as Chart[];
      void Promise.all(specs.map(spec=>chartData(projectId,datasetId,spec))).then(c=>{if(active)setCharts(c);}).catch(e=>{if(active)setError(e.message);});
    }
    return()=>{active=false;};
  },[datasetId,projectId,dataProjectId]);
  useEffect(()=>{if(tab==='actividad'&&projectId)void api<typeof audit>(`/projects/${projectId}/audit`).then(setAudit).catch(e=>setError(e.message));},[tab,projectId,jobs]);
  const toggle=(array:string[],key:string)=>array.includes(key)?array.filter(x=>x!==key):[...array,key];
  const selectOptions=columns.map(c=><option key={c.name} value={c.name}>{c.name}</option>);
  async function uploadFiles(files:FileList|null){if(!files?.length||!projectId)return;await action(async()=>{for(const file of Array.from(files)){const form=new FormData();form.append('file',file);const job=await api<Job>(`/projects/${projectId}/uploads`,form);setLastJob(job.id);}setNotice('Archivos recibidos. La importación está en la cola de trabajo.');});}
  function addStep(){try{
    const p=JSON.parse(planText) as Plan;let s:Record<string,unknown>={op};
    if(['filter','fill_null','cast','rename','date_part','ratio'].includes(op))s.column=column;
    if(['select','drop_nulls','aggregate','sort'].includes(op))s.columns=selectedColumns;
    if(['filter','fill_null'].includes(op)){let v:unknown=value;try{v=JSON.parse(value);}catch{/* Strings need not be quoted. */}s.value=v;}
    if(op==='filter')s.operator=operator;
    if(op==='cast')s.target_type=targetType;
    if(['rename','date_part','ratio'].includes(op))s.alias=alias;
    if(op==='date_part')s.part=datePart;
    if(op==='ratio')s.denominator=denominator;
    if(op==='join'){s={op,dataset_id:otherId,left_key:column,right_key:rightKey,how:'left',allow_many_to_many:false};}
    if(op==='concat')s.dataset_id=otherId;
    if(op==='aggregate')s.metrics=[{function:metricFunction,column:metricFunction==='count'&&!metricColumn?null:metricColumn,alias:alias||'resultado'}];
    p.steps.push(s);p.questions=[];setPlanText(JSON.stringify(p,null,2));setNotice('Paso añadido al plan. Puedes revisarlo antes de ejecutar.');
  }catch(e){setError('El plan debe contener un JSON válido con una lista steps.');}}
  async function interpret(){await action(async()=>{
    const record=await api<{plan:Plan}>(`/projects/${projectId}/interpret`,{dataset_id:datasetId,instruction,consent_id:sampleApproved?consent?.id:null});setPlanText(JSON.stringify(record.plan,null,2));setSampleApproved(false);setConsent(null);setTab('pipeline');setAssistantOpen(false);setNotice(record.plan.questions.length?'La IA necesita aclaraciones. Responde en una nueva instrucción.':'Plan preparado. Revisa sus pasos antes de ejecutarlo.');
  });}
  async function runPlan(){await action(async()=>{
    const plan=JSON.parse(planText);const job=await api<Job>(`/projects/${projectId}/runs`,{dataset_id:datasetId,plan});setLastJob(job.id);setNotice('Pipeline en cola. El original se conserva.');
  });}
  async function paginate(next:number){await action(async()=>{const result=await api<{rows:Row[]}>(`/projects/${projectId}/datasets/${datasetId}/preview?offset=${next}&limit=50`);setOffset(next);setRows(result.rows);});}
  async function addChart(){await action(async()=>{const result=await chartData(projectId,datasetId,chartDraft);setCharts(c=>[...c,result]);});}
  async function refreshDataset(){setDatasets(await api<Dataset[]>(`/projects/${projectId}/datasets`));setCharts([]);}
  async function loadFilterOptions(){await action(async()=>{const options:typeof filterOptions={};for(const key of exportFilters){const result=await compute<{values:{value:unknown;count:number}[];truncated:boolean}>(projectId,datasetId,{kind:'categories',category_column:key});options[key]=result.values;if(result.truncated)setNotice('Hasta 200 categorías disponibles por filtro; escribe otros filtros en el contrato JSON.');}setFilterOptions(options);});}
  async function applyDashboardFilters(next:Record<string,string>){await action(async()=>{const filters=Object.entries(next).filter(([k,v])=>exportFilters.includes(k)&&v).map(([column,v])=>({column,operator:JSON.parse(v)===null?'is_null':'eq',value:JSON.parse(v)}));const results=await Promise.all(charts.map(c=>{const base=c.baseSpec||c.spec;return chartData(projectId,datasetId,{...base,filters:[...(base.filters||[]),...filters]}).then(r=>({...r,baseSpec:base}));}));setCharts(results);setActiveFilters(next);});}
  async function exportDashboard(){await action(async()=>{const result=await compute<{download_url:string;truncated:boolean;rows:number}>(projectId,datasetId,{kind:'export',export:{charts:charts.map(c=>c.spec),title:exportTitle,filter_columns:exportFilters,limit:5000}});const link=document.createElement('a');link.href=result.download_url;link.download='dashboard.html';link.click();setNotice(`Dashboard exportado: ${number(result.rows)} resultados representados${result.truncated?' (vista parcial precomputada)':''}. Funciona sin conexión; consulta su método y filtros.`);});}
  async function openProject(id:string){await action(async()=>{
    if(projectId)await saveProject();
    restoring.current=await api<Record<string,unknown>>(`/projects/${id}/open`,{});
    setInstruction('');setTab('datos');setExportTitle('Dashboard del proyecto');setChartTitle('');setSamplePanel(false);
    setProjectId(id);setNewProject(false);
  });}
  async function saveProject(){
    await api(`/projects/${projectId}/close`,{datasetId,chartDraft, instruction,planText,tab,op,column,value,alias,operator,targetType,otherId,rightKey,metricFunction,metricColumn,selectedColumns,datePart,denominator,chartKind,chartX,chartY,chartTitle,exportFilters,exportTitle,activeFilters,chartSpecs:charts.map(c=>c.spec)});
  }
  async function closeProject(){await action(async()=>{await saveProject();restoring.current=null;setAssistantOpen(false);setFocusView(false);setProjectId('');setNewProject(false);setNotice('Proyecto guardado. Puedes volver a abrirlo desde la lista de proyectos.');});}
  async function closeProgram(){if(projectId)return;await action(async()=>{await api('/shutdown',{});setClosed(true);});}
  async function restartProgram(){await action(async()=>{await api('/restart',{});window.location.reload();});}
  if(closed)return <main className="welcome card"><h1>Programa cerrado</h1><p>Todos los proyectos están guardados. Pulsa Reiniciar programa para volver a la pantalla inicial.</p><button className="primary" disabled={busy} onClick={()=>void restartProgram()}>{busy?'Reiniciando...':'Reiniciar programa'}</button>{error&&<p role="alert" className="message error">{error}</p>}</main>;
  return <div className={'app'+(focusView?' focus-view':'')+(wideCharts?' wide-charts':'')}>
    <aside className="sidebar"><div className="brand"><span className="brand-symbol">◈</span><div>Data Science<span>WORKBENCH</span></div></div><p className="sidebar-label">ESPACIO DE TRABAJO</p><button className="new-project" onClick={()=>setNewProject(!newProject)} disabled={busy}>+ Nuevo proyecto</button>
      {newProject&&<form className="new-form" onSubmit={e=>{e.preventDefault();void action(async()=>{const p=await api<Project>('/projects',{name:newName,description:''});if(projectId)await saveProject();restoring.current=await api<Record<string,unknown>>(`/projects/${p.id}/open`,{});setProjects(x=>[p,...x]);setProjectId(p.id);setNewProject(false);setNewName('');});}}><input aria-label="Nombre del proyecto" placeholder="Nombre del proyecto" value={newName} onChange={e=>setNewName(e.target.value)} required maxLength={120}/><button disabled={busy}>Crear proyecto</button></form>}
      <nav className="project-list">{projects.map(p=><button disabled={busy} key={p.id} className={p.id===projectId?'active':''} onClick={()=>{if(p.id!==projectId)void openProject(p.id);}}><span>▦</span>{p.name}</button>)}</nav>
      <div className="sidebar-bottom"><div className="local-dot"/> Ejecución local<div className="sidebar-small">Un trabajo pesado a la vez<br/>Motor: {health?.memory_limit||'4GB'} de presupuesto</div><span className="version">v0.1 · Preparación y visualización</span></div>
    </aside>
    <main className="main"><header className="topbar"><span>Proyectos <span className="crumb">/</span> {project?.name||'Inicio'}</span><div className="window-actions"><span className="badge">LOCAL FIRST</span>{projectId&&<><button className="view-toggle" aria-pressed={focusView} onClick={()=>setFocusView(!focusView)}>{focusView?'Mostrar proyectos':'Vista ampliada'}</button><button className="assistant-toggle" aria-expanded={assistantOpen} aria-controls="analysis-assistant" onClick={()=>setAssistantOpen(!assistantOpen)}>Asistente IA</button></>}{projectId?<button disabled={busy||jobs.some(j=>['queued','running'].includes(j.status))} onClick={()=>void closeProject()}>Cerrar proyecto</button>:<button disabled={busy} onClick={()=>void closeProgram()}>Cerrar programa</button>}</div></header>
      <div className="heading"><div><p className="eyebrow">WORKBENCH / EXPLORACIÓN DE DATOS</p><h1>{project?.name||'Tu espacio de análisis'}</h1><p className="subtitle">Explora datos, compara grupos y revisa resultados reproducibles.</p></div>{project&&<label className={'button primary upload '+(busy?'disabled':'')}>+ Importar archivos<input type="file" multiple accept=".csv,.parquet,.json,.jsonl,.ndjson,.xlsx" disabled={busy} onChange={e=>{void uploadFiles(e.target.files);e.target.value='';}}/></label>}</div>
      {error&&<div role="alert" className="message error">{error}<button onClick={()=>setError('')} aria-label="Cerrar error">×</button></div>}{notice&&<div role="status" className="message success">{notice}</div>}
      {!projectId?projects.length?<ProjectHome projects={projects} health={health} busy={busy} onOpen={id=>void openProject(id)} onCreate={()=>{setNewProject(true);requestAnimationFrame(()=>document.querySelector<HTMLInputElement>('.new-form input')?.focus());}}/>:<section className="welcome card"><div className="welcome-icon">◈</div><h2>Un proyecto. Un análisis reproducible.</h2><p>Crea un proyecto e importa tus archivos. Podrás combinar tablas, preparar datos y exportar dashboards que se abren sin instalar nada.</p><button className="primary" onClick={()=>setNewProject(true)}>Crear mi primer proyecto</button><div className="formats">CSV · PARQUET · JSON · EXCEL</div></section>:<>
      <section className="dataset-bar"><label>Tabla activa<select aria-label="Tabla activa" disabled={busy} value={datasetId} onChange={e=>setDatasetId(e.target.value)}><option value="">Selecciona un archivo</option>{datasets.map(d=><option key={d.id} value={d.id}>{d.parent_id?'↳ ':''}{d.name} · {number(d.profile.rows)} filas</option>)}</select></label><span>{dataset?.parent_id?'Resultado derivado · original conservado':'Los archivos originales se conservan'}</span>{dataset&&<a className="text-link" href={`/api/projects/${projectId}/datasets/${datasetId}/download`}>↓ Parquet</a>}</section>
      {jobs.some(j=>['queued','running'].includes(j.status))&&<div className="jobs-live">{jobs.filter(j=>['queued','running'].includes(j.status)).map(j=><div key={j.id}><span className="spinner"/><span><strong>{statusNames[j.status]}</strong> · {j.message}</span><button onClick={()=>void action(async()=>{await api(`/jobs/${j.id}/cancel`,{});})}>Cancelar</button></div>)}</div>}
      <nav className="tabs">{[['datos','Datos y calidad'],['pipeline','Pipeline'],['dashboard','Dashboard'],['actividad','Historial']].map(([key,label])=><button key={key} className={tab===key?'selected':''} onClick={()=>setTab(key)}>{label}</button>)}<span className="future">Modelado · Próxima fase</span></nav>
      <div className="workspace"><div className="content">
      {!dataset?<section className="card empty-state"><span className="welcome-icon">⇧</span><h2>Empieza por tus datos</h2><p>Importa uno o varios archivos. Los archivos grandes se procesan en segundo plano.</p><p className="muted">Hasta {health?.max_upload_gb||10} GB por archivo, 200 columnas. El tamaño procesable depende de la operación y del espacio libre.</p><p className="muted">Excel: primera hoja. CSV: cabecera y detección automática.</p></section>:<>
      {tab==='datos'&&<>{dataset.profile_stale&&<p className="question">El diccionario ha cambiado. Recalcula calidad para actualizar estadísticas semánticas, reglas y atípicos. Los conteos de filas y nulos siguen siendo válidos.</p>}<div className="stats"><article><span>FILAS</span><strong>{number(dataset.profile.rows)}</strong></article><article><span>COLUMNAS</span><strong>{columns.length}</strong></article><article><span>CON VALORES AUSENTES</span><strong>{columns.filter(c=>c.nulls>0).length}<small> columnas</small></strong></article></div>
        <section className="card"><div className="section-title"><h2>Vista previa</h2><span className="pill">{offset+1}–{Math.min(offset+rows.length,dataset.profile.rows)} de {number(dataset.profile.rows)}</span></div><Table rows={rows}/><div className="table-footer"><span>La vista previa es parcial. Las estadísticas cubren toda la tabla.</span><div><button disabled={busy||offset===0} onClick={()=>void paginate(Math.max(0,offset-50))}>Anterior</button><button disabled={busy||offset+50>=dataset.profile.rows} onClick={()=>void paginate(offset+50)}>Siguiente</button></div></div></section>
        <section className="card"><div className="section-title"><h2>Calidad y estructura</h2><span className="pill">Tabla completa</span></div><div className="table-scroll"><table><thead><tr><th>Columna</th><th>Tipo</th><th>Nulos</th><th>% nulos</th><th>Mínimo</th><th>Máximo</th><th>Media</th></tr></thead><tbody>{columns.map(c=><tr key={c.name}><td><strong>{c.name}</strong></td><td><code>{c.type}</code></td><td>{number(c.nulls)}</td><td><span className={c.nulls?'quality-warning':'quality-ok'}>{c.null_pct}%</span></td><td>{display(c.min)}</td><td>{display(c.max)}</td><td>{typeof c.mean==='number'?c.mean.toLocaleString('es-ES',{maximumFractionDigits:3}):display(c.mean)}</td></tr>)}</tbody></table></div></section>
        <section className="card"><h2>Estadísticas y reglas</h2><p className="muted">{dataset.profile.scope}</p>{dataset.profile.exact_duplicates!==undefined&&<p>Duplicados exactos: {number(dataset.profile.exact_duplicates)} filas excedentes. {dataset.profile.key_duplicates&&`Por claves ${dataset.profile.key_duplicates.keys.join(', ')}: ${number(dataset.profile.key_duplicates.count)}.`}</p>}<div className="table-scroll"><table><thead><tr><th>Variable</th><th>Semántica</th><th>Válidos</th><th>No finitos</th><th>Mediana</th><th>Desv. est. n−1</th><th>Q1</th><th>Q3</th><th>IQR</th><th>Atípicos IQR</th><th>Reglas incumplidas</th></tr></thead><tbody>{columns.map(c=><tr key={c.name}><td>{c.name}</td><td>{dataset.dictionary?.[c.name]?.semantic_type||c.semantic_type||'Sugerencia pendiente'}</td><td>{display(c.valid)}</td><td>{display(c.nonfinite)}</td><td>{display(c.median)}</td><td>{display(c.stddev)}</td><td>{display(c.q1)}</td><td>{display(c.q3)}</td><td>{display(c.iqr)}</td><td>{display(c.outliers)}</td><td>{display(c.rule_violations)}</td></tr>)}</tbody></table></div>{columns.map(c=><details key={c.name}><summary>{c.name}: cardinalidad {display(c.cardinality)} (aproximada), frecuencias y método</summary><p>{c.quantile_method||'Sin cuartiles para este tipo semántico.'}</p><p>{c.cardinality_method}</p>{c.frequencies&&<Table rows={c.frequencies.map(r=>({valor:r.value,frecuencia:r.count}))}/>}<p className="small">{c.categories_truncated?'Hasta 20 categorías con frecuencias exactas, sin renormalizar.':'Frecuencias sobre todo el dataset; los ausentes no se eliminan.'}</p></details>)}{dataset.profile.limitations?.map((note,i)=><p key={i} className="small muted">{note}</p>)}</section>
        <Dictionary projectId={projectId} datasetId={datasetId} columns={columns} onSaved={refreshDataset}/>
        {dataset.history&&<section className="card"><h2>Transformaciones aplicadas</h2>{dataset.history.map((h,i)=><div className="history-step" key={i}><span className="step-number">{i+1}</span><div><strong>{operationNames[String(h.step.op)]||String(h.step.op)}</strong><p>{number(h.rows)} filas resultantes{h.warning?' · '+h.warning:''}</p></div></div>)}</section>}
      </>}
      {tab==='pipeline'&&<><section className="card"><div className="section-title"><h2>Plan de preparación</h2><span className="pill">{parsedPlan?.steps?.length||0} pasos</span></div><p className="muted">La IA propone el plan. Tú puedes revisarlo y modificarlo antes de ejecutarlo.</p>
        {parsedPlan?.explanation&&<p className="plan-explanation">{parsedPlan.explanation}</p>}{parsedPlan?.questions?.map((q,i)=><p className="question" key={i}>Aclaración necesaria: {q}</p>)}
        <div className="step-list">{parsedPlan?.steps?.map((s,i)=><div className="history-step" key={i}><span className="step-number">{i+1}</span><div><strong>{operationNames[String(s.op)]||String(s.op)}</strong><p>{JSON.stringify(s)}</p></div><button aria-label={`Quitar paso ${i+1}`} onClick={()=>{const p=JSON.parse(planText);p.steps.splice(i,1);setPlanText(JSON.stringify(p,null,2));}}>×</button></div>)}</div>
        {datasets.some(d=>d.plan)&&<label>Reutilizar una receta del proyecto<select defaultValue="" onChange={e=>{const d=datasets.find(x=>x.id===e.target.value);if(d?.plan)setPlanText(JSON.stringify(d.plan,null,2));}}><option value="">Selecciona una receta guardada</option>{datasets.filter(d=>d.plan).map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label>}
        <details><summary>Editar el plan completo · JSON</summary><textarea className="code-editor" aria-label="Plan JSON" value={planText} onChange={e=>setPlanText(e.target.value)} spellCheck={false}/></details><div className="actions"><button className="primary" disabled={busy||!parsedPlan||!!parsedPlan.questions?.length||!!lastJob} onClick={()=>void runPlan()}>▷ Ejecutar pipeline</button><button onClick={()=>setPlanText(JSON.stringify(emptyPlan(),null,2))}>Vaciar plan</button></div><p className="muted small">Cada ejecución crea un nuevo resultado. Los tipos incompatibles producen un error; no se convierten silenciosamente a nulos.</p></section>
        <section className="card"><h2>Añadir una transformación</h2><div className="form-grid"><label>Operación<select value={op} onChange={e=>setOp(e.target.value)}>{Object.entries(operationNames).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>
          {['filter','fill_null','cast','rename','date_part','ratio','join'].includes(op)&&<label>Columna{op==='join'?' izquierda':''}<select value={column} onChange={e=>setColumn(e.target.value)}>{selectOptions}</select></label>}
          {op==='filter'&&<label>Condición<select value={operator} onChange={e=>setOperator(e.target.value)}>{[['gt','Mayor que'],['ge','Mayor o igual'],['lt','Menor que'],['le','Menor o igual'],['eq','Igual a'],['ne','Distinto de'],['contains','Contiene'],['is_null','Es nulo'],['not_null','No es nulo']].map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>}
          {['filter','fill_null'].includes(op)&&<label>Valor<input value={value} onChange={e=>setValue(e.target.value)} placeholder="100 o texto"/></label>}
          {op==='cast'&&<label>Tipo de destino<select value={targetType} onChange={e=>setTargetType(e.target.value)}>{['DOUBLE','BIGINT','VARCHAR','DATE','TIMESTAMP','BOOLEAN'].map(t=><option key={t}>{t}</option>)}</select></label>}
          {['rename','date_part','ratio','aggregate'].includes(op)&&<label>Nombre de salida<input value={alias} onChange={e=>setAlias(e.target.value)} placeholder="resultado"/></label>}
          {op==='date_part'&&<label>Parte de la fecha<select value={datePart} onChange={e=>setDatePart(e.target.value)}>{['year','month','day','quarter','week','dow'].map(p=><option key={p}>{p}</option>)}</select></label>}
          {op==='ratio'&&<label>Denominador<select value={denominator} onChange={e=>setDenominator(e.target.value)}><option value="">Selecciona</option>{selectOptions}</select></label>}
          {['join','concat'].includes(op)&&<label>Otra tabla<select value={otherId} onChange={e=>{setOtherId(e.target.value);setRightKey('');}}><option value="">Selecciona</option>{datasets.filter(d=>d.id!==datasetId).map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label>}
          {op==='join'&&<label>Clave derecha<select value={rightKey} onChange={e=>setRightKey(e.target.value)}><option value="">Selecciona</option>{datasets.find(d=>d.id===otherId)?.profile.columns.map(c=><option key={c.name}>{c.name}</option>)}</select></label>}
          {op==='aggregate'&&<><label>Métrica<select value={metricFunction} onChange={e=>setMetricFunction(e.target.value)}>{[['sum','Suma'],['avg','Media'],['min','Mínimo'],['max','Máximo'],['count','Conteo']].map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label><label>Columna de la métrica<select value={metricColumn} onChange={e=>setMetricColumn(e.target.value)}><option value="">Todas (solo conteo)</option>{selectOptions}</select></label></>}
          </div>{['select','drop_nulls','aggregate','sort'].includes(op)&&<div className="check-columns"><p className="muted">{op==='aggregate'?'Agrupar por (vacío = toda la tabla)':'Columnas'}</p>{columns.map(c=><label key={c.name}><input type="checkbox" checked={selectedColumns.includes(c.name)} onChange={()=>setSelectedColumns(toggle(selectedColumns,c.name))}/>{c.name}</label>)}</div>}
          <button onClick={addStep}>+ Añadir paso</button><p className="muted small">Los controles muestran las columnas de la tabla activa. Para columnas creadas por pasos anteriores, usa el editor JSON o las instrucciones a la IA.</p></section>
      </>}
      {tab==='dashboard'&&<><div className="visualization-toolbar"><span>VISUALIZACIÓN / DATA EXPLORER</span><div><button aria-pressed={wideCharts} onClick={()=>setWideCharts(true)}>Gráficos amplios</button><button aria-pressed={!wideCharts} onClick={()=>setWideCharts(false)}>Mosaico</button></div></div><ChartBuilder spec={chartDraft} onChange={setChartDraft} columns={columns.map(c=>({...c,semantic_type:dataset.dictionary?.[c.name]?.semantic_type||c.semantic_type}))} busy={busy||charts.length>=8} onAdd={()=>void addChart()}/>
        {exportFilters.length>0&&<section className="card"><h2>Filtros del dashboard</h2><button disabled={busy} onClick={()=>void loadFilterOptions()}>Cargar categorías del dataset</button><div className="form-grid">{exportFilters.map(key=><label key={key}>{key}<select aria-label={key} disabled={busy} value={activeFilters[key]||''} onChange={e=>void applyDashboardFilters({...activeFilters,[key]:e.target.value})}><option value="">Todos</option>{(filterOptions[key]||[]).map(r=><option key={JSON.stringify(r.value)} value={JSON.stringify(r.value)}>{display(r.value)} ({number(r.count)})</option>)}</select></label>)}</div><p className="small muted">En la aplicación, cada filtro recalcula sobre toda la tabla mediante un trabajo cancelable. En el HTML agregado los filtros quedan fijados; no se recalculan porcentajes offline.</p></section>}
        <div className="charts-grid">{charts.map((c,i)=><section className="card chart-card" key={i}><button className="remove-chart" aria-label={`Quitar gráfico ${i+1}`} onClick={()=>setCharts(x=>x.filter((_,j)=>i!==j))}>×</button><label>Título del gráfico<input value={c.spec.title} onChange={e=>setCharts(x=>x.map((r,j)=>j===i?{...r,spec:{...r.spec,title:e.target.value},baseSpec:r.baseSpec?{...r.baseSpec,title:e.target.value}:undefined,figure:{...r.figure,layout:{...r.figure.layout,title:{text:e.target.value}}}}:r))}/></label><Plot result={c}/><p className="small muted">{c.scope} · {number(c.provenance.used_rows)} filas utilizadas de {number(c.provenance.filtered_rows)} filtradas.</p>{c.warnings.map((w,j)=><p className="question" key={j}>{w}</p>)}<details><summary>Método, denominadores y procedencia</summary><pre>{JSON.stringify(c.provenance,null,2)}</pre></details><details><summary>Resultados calculados (hasta 200 registros)</summary><Table rows={c.rows.slice(0,200)}/>{c.rows.length>200&&<p className="small muted">Tabla parcial; la figura conserva todos los resultados calculados indicados en su procedencia.</p>}</details></section>)}</div>
        <section className="card"><div className="section-title"><h2>Exportación interactiva</h2><span className="pill">HTML · Sin conexión</span></div><p className="muted">Exporta los resultados estadísticos calculados sobre el dataset filtrado. Los gráficos agregados no incluyen filas individuales. El HTML conserva método, denominadores, fecha y limitaciones; sus filtros agregados quedan fijados.</p><label>Título del dashboard<input value={exportTitle} onChange={e=>setExportTitle(e.target.value)}/></label><div className="check-columns"><p className="muted">Filtros (hasta 3 columnas; 200 valores disponibles por filtro)</p>{columns.map(c=><label key={c.name}><input type="checkbox" checked={exportFilters.includes(c.name)} disabled={exportFilters.length>=3&&!exportFilters.includes(c.name)} onChange={()=>setExportFilters(toggle(exportFilters,c.name))}/>{c.name}</label>)}</div><div className="actions"><button disabled={busy||!charts.length} onClick={()=>void action(async()=>{const result=await api<Dashboard>(`/projects/${projectId}/dashboards`,{dataset_id:datasetId,charts:charts.map(c=>c.spec),title:exportTitle,filter_columns:exportFilters});setDashboards(x=>[result,...x]);setNotice('Dashboard guardado en el proyecto.');})}>Guardar dashboard</button><button className="primary" disabled={busy||!charts.length} onClick={()=>void exportDashboard()}>↓ Descargar dashboard HTML</button></div>
        {dashboards.some(d=>d.dataset_id===datasetId)&&<label>Dashboards guardados para esta tabla<select defaultValue="" onChange={e=>{const d=dashboards.find(x=>x.id===e.target.value);if(d)void action(async()=>{const loaded=await Promise.all(d.charts.map(spec=>chartData(projectId,datasetId,spec)));setCharts(loaded);setExportFilters(d.filter_columns);setActiveFilters({});setExportTitle(d.title);});}}><option value="">Selecciona un dashboard</option>{dashboards.filter(d=>d.dataset_id===datasetId).map(d=><option key={d.id} value={d.id}>{d.title}</option>)}</select></label>}</section>
      </>}
      {tab==='actividad'&&<><section className="card"><h2>Ejecuciones</h2>{!jobs.length&&<p className="muted">Todavía no hay ejecuciones.</p>}{jobs.map(j=><div className="job-row" key={j.id}><span className={'status '+j.status}>{statusNames[j.status]}</span><div><strong>{j.action==='import'?'Importación':j.action==='analysis'?'Exploración estadística':'Pipeline'}</strong><p>{j.message}</p><small>{new Date(j.created_at).toLocaleString('es-ES')}</small></div></div>)}</section><section className="card"><h2>Registro de actividad</h2>{audit.map(a=><details key={a.id}><summary>{new Date(a.created_at).toLocaleString('es-ES')} · {a.action}</summary><pre>{JSON.stringify(a.details,null,2)}</pre></details>)}</section></>}
      </>}
      </div>
      {assistantOpen&&<><button className="assistant-scrim" aria-label="Cerrar panel del asistente" tabIndex={-1} onClick={()=>setAssistantOpen(false)}/><aside ref={assistantPanelRef} id="analysis-assistant" role="dialog" aria-modal="true" aria-label="Asistente de análisis" className="assistant card"><button className="assistant-close" aria-label="Cerrar asistente" onClick={()=>setAssistantOpen(false)}>×</button><div className="assistant-heading"><span className="ai-icon">✧</span><div><h2>Asistente de análisis</h2><span>De tu pregunta a un plan verificable</span></div></div><div className={'ai-state '+(health?.ai_configured?'ready':'')}><span className="local-dot"/>{health?.ai_configured?'API configurada':'Configura tu API para activar la IA'}</div><p>Describe qué quieres preparar o visualizar. El asistente propondrá los pasos; tú decides cuándo ejecutarlos.</p><textarea aria-label="Instrucción para la IA" placeholder="Une las ventas con los productos, agrupa por categoría y muestra el ingreso total…" value={instruction} onChange={e=>setInstruction(e.target.value)} maxLength={4000}/><button className="primary" disabled={busy||!dataset||!health?.ai_configured||instruction.length<3} onClick={()=>void interpret()}>{busy?'Procesando…':'✧ Preparar plan'}</button><p className="small muted">Se envían tu instrucción, identificadores y nombres/tipos de columnas del proyecto. No se envían registros salvo autorización.</p>
        <button className="sample-toggle" disabled={!dataset} onClick={()=>setSamplePanel(!samplePanel)}>⌕ Revisar una muestra para la IA</button>
        {samplePanel&&dataset&&<div className="sample-panel"><p className="small">Selecciona solo las columnas que quieras compartir. Revisa hasta 5 filas antes de autorizar un único envío.</p><div className="sample-checks">{columns.map(c=><label key={c.name}><input type="checkbox" checked={sampleColumns.includes(c.name)} onChange={()=>{setSampleColumns(toggle(sampleColumns,c.name));setConsent(null);setSampleApproved(false);}}/>{c.name}</label>)}</div><button disabled={busy||!sampleColumns.length} onClick={()=>void action(async()=>{const c=await api<Consent>(`/projects/${projectId}/sample-consents`,{dataset_ids:[datasetId],columns:sampleColumns,rows:5});setConsent(c);setSampleApproved(false);})}>Previsualizar muestra</button>{consent&&<><Table rows={consent.samples[0]?.rows||[]}/><label className="consent-label"><input type="checkbox" checked={sampleApproved} onChange={e=>setSampleApproved(e.target.checked)}/>Autorizo enviar exactamente esta muestra al preparar el próximo plan.</label><p className="small muted">Un solo uso · caduca a las {new Date(consent.expires_at).toLocaleTimeString('es-ES')}</p></>}</div>}
        {error&&<div role="alert" className="message error">{error}</div>}<div className="assistant-tip"><strong>Prueba con una pregunta concreta</strong><p>«Elimina duplicados, descarta ventas sin fecha y calcula el total por mes».</p></div><div className="assistant-footer">Los cálculos los realiza el motor de datos. La IA interpreta tu intención.</div>
      </aside></>}</div></>}
      <footer className="app-footer">Datos originales conservados · Pasos reproducibles · Exportaciones independientes</footer>
    </main>
  </div>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
