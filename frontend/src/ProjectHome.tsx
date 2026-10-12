import {useEffect,useState} from 'react';
import {api} from './client';

type Project={id:string;name:string;description:string;created_at?:string};
type Summary={datasets:number;derived:number;dashboards:number;latest_activity:string|null};
type Health={ai_configured:boolean;memory_limit:string;max_upload_gb:number}|null;
const format=(value:number)=>new Intl.NumberFormat('es-ES').format(value);
const countLabel=(value:number,singular:string,plural:string)=>`${format(value)} ${value===1?singular:plural}`;
const date=(value?:string|null)=>value?new Intl.DateTimeFormat('es-ES',{day:'numeric',month:'short',year:'numeric'}).format(new Date(value)):null;

export function ProjectHome({projects,health,busy,onOpen,onCreate}:{projects:Project[];health:Health;busy:boolean;onOpen:(id:string)=>void;onCreate:()=>void}){
  const [summaries,setSummaries]=useState<Record<string,Summary>>({}),[loaded,setLoaded]=useState(false),[query,setQuery]=useState('');
  useEffect(()=>{let active=true;void api<Record<string,Summary>>('/project-summaries').then(result=>{if(active){setSummaries(result);setLoaded(true);}}).catch(()=>{if(active)setLoaded(false);});return()=>{active=false;};},[projects]);
  const totalDatasets=Object.values(summaries).reduce((n,s)=>n+s.datasets,0);
  const totalDashboards=Object.values(summaries).reduce((n,s)=>n+s.dashboards,0);
  const visible=projects.filter(p=>p.name.toLocaleLowerCase('es').includes(query.toLocaleLowerCase('es')));
  return <section className="project-home">
    <div className="home-hero">
      <div className="home-hero-copy"><p className="home-kicker">ANALYTICS WORKSPACE / INICIO</p><h2>Tu laboratorio de datos.</h2><p>Retoma un análisis, explora nuevas preguntas y convierte tus datos en resultados reproducibles.</p><button className="home-create" disabled={busy} onClick={onCreate}>+ Nuevo proyecto</button></div>
      <div className="home-workflow" aria-label="Flujo de trabajo: importar, preparar, explorar y presentar"><div className="workflow-head"><span>FLUJO DE ANÁLISIS</span><span className="workflow-local">LOCAL</span></div><ol>{[['01','Importar','CSV · Parquet · JSON · Excel'],['02','Preparar','Calidad y transformaciones'],['03','Explorar','Distribución y comparación'],['04','Presentar','Dashboard · HTML offline']].map(([n,title,text])=><li key={n}><span className="workflow-number">{n}</span><div><strong>{title}</strong><small>{text}</small></div></li>)}</ol></div>
    </div>
    <div className="home-metrics" aria-label="Resumen del espacio de trabajo"><div><span className="home-metric-icon">▦</span><div><strong>{format(projects.length)}</strong><span>Proyectos guardados</span></div></div><div><span className="home-metric-icon">▤</span><div><strong>{loaded?format(totalDatasets):'—'}</strong><span>Tablas en proyectos</span></div></div><div><span className="home-metric-icon">◫</span><div><strong>{loaded?format(totalDashboards):'—'}</strong><span>Dashboards guardados</span></div></div><div><span className="home-metric-icon">◉</span><div><strong>{health?.memory_limit||'—'}</strong><span>Presupuesto del motor</span></div></div></div>
    <div className="home-project-heading"><div><p className="home-kicker">BIBLIOTECA DE PROYECTOS</p><h2>Continúa donde lo dejaste</h2></div>{projects.length>3&&<input aria-label="Buscar proyecto" placeholder="Buscar proyecto…" value={query} onChange={e=>setQuery(e.target.value)}/>}</div>
    <div className="home-project-grid">{visible.map((project,index)=>{const summary=summaries[project.id];const created=date(project.created_at);const activity=date(summary?.latest_activity);return <button className={'home-project-card home-tone-'+index%4} key={project.id} disabled={busy} onClick={()=>onOpen(project.id)} aria-label={`Abrir proyecto ${project.name}`}><div className="home-project-top"><span className="home-project-icon">▦</span><span className="home-project-arrow" aria-hidden="true">↗</span></div><h3>{project.name}</h3><p>{project.description||'Datos, procesos y visualizaciones reunidos en un mismo espacio.'}</p><div className="home-project-counts">{loaded?<><span>{countLabel(summary?.datasets||0,'tabla','tablas')}</span><span>{countLabel(summary?.dashboards||0,'dashboard','dashboards')}</span>{!!summary?.derived&&<span>{countLabel(summary.derived,'resultado derivado','resultados derivados')}</span>}</>:<span>Proyecto guardado</span>}</div><div className="home-project-bottom"><span>{activity?'Actividad: '+activity:created?'Creado: '+created:'Disponible en local'}</span><strong>Abrir proyecto →</strong></div></button>;})}
      {!query&&<button className="home-new-card" disabled={busy} onClick={onCreate}><span>+</span><h3>Empieza otro análisis</h3><p>Crea un proyecto para organizar nuevos archivos y resultados.</p><strong>Crear proyecto →</strong></button>}
    </div>
    {!!query&&!visible.length&&<p className="empty">No hay proyectos que coincidan con «{query}».</p>}
    <div className="home-status-strip"><span><span className="local-dot"/>Datos y cálculos en local</span><span>Originales conservados · Historial reproducible</span><span className={health?.ai_configured?'home-ai-ready':''}>{health?.ai_configured?'Asistente IA configurado':'Exploración disponible sin IA'}</span></div>
  </section>;
}
