/* Isolated Windows browser check. Uses local synthetic data; never calls external AI. */
const fs=require('node:fs');
const path=require('node:path');
const {spawn}=require('node:child_process');
const net=require('node:net');
const {createRequire}=require('node:module');
const {chromium}=createRequire(path.resolve(__dirname,'../frontend/package.json'))('playwright');
(async()=>{
 const root=path.resolve(__dirname,'..');
 const data=fs.mkdtempSync(path.join(root,'.qa-exploration-ui-'));
 const port=await new Promise((resolve,reject)=>{const listener=net.createServer();listener.on('error',reject);listener.listen(0,'127.0.0.1',()=>{const port=listener.address().port;listener.close(()=>resolve(port));});});
 const base=`http://127.0.0.1:${port}`;
 const python=process.platform==='win32'?path.join(root,'.venv/Scripts/python.exe'):path.join(root,'.venv/bin/python');
 const code="import sys;sys.path.insert(0,'backend');from pathlib import Path;from app.main import create_app;from app.config import Settings;import uvicorn;app=create_app(Settings(data_dir=Path(sys.argv[1]),memory_limit='128MB',threads=1));server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=int(sys.argv[2])));app.state.shutdown_callback=lambda:setattr(server,'should_exit',True);server.run()";
 const server=spawn(python,['-c',code,data,String(port)],{cwd:root,windowsHide:true,stdio:'ignore'});
 let browser;
 try{
  let ready=false;
  for(let i=0;i<100;i++){try{if((await fetch(base+'/api/health')).ok){ready=true;break;}}catch{} await new Promise(r=>setTimeout(r,100));}
  if(!ready)throw Error('Test server did not start');
  browser=await chromium.launch({headless:true,channel:process.platform==='win32'?'msedge':undefined});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base);
  await page.getByRole('button',{name:'+ Nuevo proyecto',exact:true}).click();
  await page.getByLabel('Nombre del proyecto').fill('Exploration QA');
  await page.getByRole('button',{name:'Crear proyecto',exact:true}).click();
  const records=['cohort,answer,value,paired,code'];
  for(let i=0;i<25050;i++)records.push(`${i<20000?'A':'B'},${i%2?'yes':'no'},${i%100},${i%100*2},${i%2}`);
  await page.locator('input[type=file]').setInputFiles({name:'groups.csv',mimeType:'text/csv',buffer:Buffer.from(records.join('\n'))});
  await page.getByRole('heading',{name:'Vista previa',exact:true}).waitFor({timeout:30000});
  await page.getByLabel('Variable del diccionario').selectOption('code');
  await page.getByLabel('Tipo semántico').selectOption('nominal');
  await page.getByLabel('Códigos y etiquetas').fill('{"0":"Zero","1":"One"}');
  await page.getByRole('button',{name:'Guardar diccionario',exact:true}).click();
  await page.getByRole('status').filter({hasText:'Diccionario guardado'}).waitFor();
  await page.getByRole('button',{name:'Recalcular calidad',exact:true}).click();
  await page.getByRole('status').filter({hasText:'Calidad recalculada'}).waitFor({timeout:30000});
  await page.getByRole('button',{name:'Dashboard',exact:true}).click();
  await page.getByLabel('Eje X',{exact:true}).selectOption('answer');
  await page.getByLabel('Agrupar por',{exact:true}).selectOption('cohort');
  await page.getByLabel('Medida',{exact:true}).selectOption('percentage');
  await page.getByLabel('Denominador',{exact:true}).selectOption('group');
  await page.getByRole('button',{name:'+ Añadir gráfico',exact:true}).click();
  await page.locator('.plot .main-svg').first().waitFor({timeout:30000});
  const seriesColors=await page.locator('.plot').first().evaluate(el=>Object.fromEntries(el.data.map(t=>[t.name,t.marker.color])));
  if(new Set(Object.values(seriesColors)).size<2)throw Error('Grouped chart colors are not distinct');
  const contentWidth=await page.locator('.content').evaluate(el=>el.getBoundingClientRect().width);
  const mainWidth=await page.locator('main.main').evaluate(el=>el.getBoundingClientRect().width);
  if(contentWidth<mainWidth-70)throw Error('Data area still loses width to a permanent assistant column');
  await page.getByRole('button',{name:'Vista ampliada',exact:true}).click();
  if(await page.locator('.sidebar').isVisible())throw Error('Expanded view does not hide navigation');
  await page.getByRole('button',{name:'Mostrar proyectos',exact:true}).click();
  await page.getByRole('button',{name:'Asistente IA',exact:true}).click();
  await page.getByRole('dialog',{name:'Asistente de análisis',exact:true}).waitFor();
  await page.keyboard.press('Escape');
  if(await page.getByRole('dialog').count())throw Error('Assistant does not close with Escape');
  await page.waitForFunction(()=>{const plot=document.querySelector('.plot');return plot&&Math.abs(Number(plot.querySelector('.main-svg')?.getAttribute('width'))-plot.clientWidth)<3;});
  await page.screenshot({path:path.join(data,'grouped-desktop.png'),fullPage:true});
  const used=await page.locator('.chart-card').first().textContent();
  if(!used.includes('25.050 filas utilizadas'))throw Error('Full dataset population not shown: '+used);
  await page.getByLabel('cohort',{exact:true}).check();
  await page.getByRole('button',{name:'Cargar categorías del dataset',exact:true}).click();
  const cohort=page.getByRole('heading',{name:'Filtros del dashboard'}).locator('..').getByLabel('cohort',{exact:true});
  await cohort.selectOption(JSON.stringify('B'));
  await page.getByText('5.050 filas utilizadas',{exact:false}).waitFor({timeout:30000});
  await page.waitForFunction(()=>{const plot=document.querySelector('.plot');return plot?.data?.length===1&&plot.data[0].name==='B';});
  const filteredColor=await page.locator('.plot').first().evaluate(el=>el.data[0].marker.color);
  if(filteredColor!==seriesColors.B)throw Error('Group color changed after filtering');
  const [download]=await Promise.all([page.waitForEvent('download'),page.getByRole('button',{name:'↓ Descargar dashboard HTML',exact:true}).click()]);
  const target=path.join(data,'aggregate.html');await download.saveAs(target);
  const offline=await browser.newContext({offline:true});const exported=await offline.newPage();exported.on('pageerror',e=>errors.push(e.message));
  await exported.goto('file:///'+target.replaceAll('\\','/'));
  await exported.locator('#chart-0 .main-svg').first().waitFor();
  if(await exported.locator('#filters select').count())throw Error('Aggregate filter must be disabled offline');
  const filterNote=await exported.locator('#filter-note').textContent();
  if(!filterNote.includes('desactivados'))throw Error('Missing offline scope warning');
  const appFigure=await page.locator('.plot').first().evaluate(el=>({x:el.data.map(t=>t.x),y:el.data.map(t=>t.y),colors:el.data.map(t=>t.marker.color)}));
  const exportFigure=await exported.locator('#chart-0').evaluate(el=>({x:el.data.map(t=>t.x),y:el.data.map(t=>t.y),colors:el.data.map(t=>t.marker.color)}));
  if(JSON.stringify(appFigure)!==JSON.stringify(exportFigure))throw Error('App/export figures differ');
  await page.setViewportSize({width:390,height:844});
  await page.waitForFunction(()=>{const plot=document.querySelector('.plot');const svg=plot?.querySelector('.main-svg');return !!svg&&Number(svg.getAttribute('width'))<=plot.clientWidth+2;});
  await page.screenshot({path:path.join(data,'mobile.png'),fullPage:true});
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2)){const overflow=await page.evaluate(()=>[...document.querySelectorAll('body *')].map(el=>({tag:el.tagName,className:String(el.className),right:Math.round(el.getBoundingClientRect().right),text:el.textContent?.slice(0,60)})).filter(el=>el.right>innerWidth+2).slice(0,12));throw Error('Mobile horizontal overflow: '+JSON.stringify(overflow)+'; QA: '+data);}
  await page.setViewportSize({width:1440,height:1000});await page.waitForFunction(()=>{const plot=document.querySelector('.plot');return plot&&Number(plot.querySelector('.main-svg')?.getAttribute('width'))>=plot.clientWidth-2;});await page.screenshot({path:path.join(data,'desktop.png'),fullPage:true});
  if(errors.length)throw Error(errors.join('\n'));
  console.log('Dictionary, full-data percentages, quality, backend filters, offline figure consistency and mobile layout passed. QA artifacts: '+data);
 }finally{
  if(browser)await browser.close();
  try{const projects=await(await fetch(base+'/api/projects')).json();for(const project of projects){const jobs=await(await fetch(base+`/api/projects/${project.id}/jobs`)).json();for(const job of jobs)if(['queued','running'].includes(job.status))await fetch(base+`/api/jobs/${job.id}/cancel`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});await fetch(base+`/api/projects/${project.id}/close`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});}await fetch(base+'/api/shutdown',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});}catch{}
  if(server.exitCode===null){await Promise.race([new Promise(r=>server.once('exit',r)),new Promise(r=>setTimeout(r,3000))]);if(server.exitCode===null)server.kill();}
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
