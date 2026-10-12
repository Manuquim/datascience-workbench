/* Run against a fresh local instance. Uses Playwright without contacting an AI provider. */
const fs=require('node:fs');
const path=require('node:path');
const {createRequire}=require('node:module');
const requireFrontend=createRequire(path.resolve(__dirname,'../frontend/package.json'));
const {chromium}=process.env.DSW_PLAYWRIGHT_MODULE?require(process.env.DSW_PLAYWRIGHT_MODULE):requireFrontend('playwright');

(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.DSW_CHROMIUM_PATH||undefined,args:process.env.DSW_CHROMIUM_PATH?['--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--no-zygote']:[]});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:1000}});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.goto(process.env.DSW_BASE_URL||'http://127.0.0.1:8765');
    await page.getByRole('button',{name:'+ Nuevo proyecto',exact:true}).click();
    await page.getByLabel('Nombre del proyecto').fill('Análisis de demostración');
    await page.getByRole('button',{name:'Crear proyecto',exact:true}).click();
    await page.getByRole('heading',{name:'Análisis de demostración',exact:true}).waitFor();
    await page.locator('input[type=file]').setInputFiles(path.resolve(__dirname,'../examples/ventas.csv'));
    await page.getByRole('heading',{name:'Vista previa',exact:true}).waitFor({timeout:30000});
    await page.getByRole('button',{name:'Pipeline',exact:true}).click();
    await page.getByText('Editar el plan completo · JSON',{exact:true}).click();
    const plan=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../examples/pipeline-ventas.json'),'utf8'));
    await page.getByLabel('Plan JSON').fill(JSON.stringify(plan,null,2));
    await page.getByRole('button',{name:'▷ Ejecutar pipeline',exact:true}).click();
    await page.getByRole('status').filter({hasText:'Ejecución completada'}).waitFor({timeout:30000});
    await page.getByRole('button',{name:'Dashboard',exact:true}).click();
    await page.locator('.plot .main-svg').first().waitFor({timeout:15000});
    await page.getByLabel('region',{exact:true}).check();
    await page.getByRole('button',{name:'Guardar dashboard',exact:true}).click();
    await page.getByRole('status').filter({hasText:'Dashboard guardado'}).waitFor();
    const screenshotDir=process.env.DSW_QA_DIR;
    if(screenshotDir)await page.screenshot({path:path.join(screenshotDir,'dashboard.png'),fullPage:true});
    const [download]=await Promise.all([page.waitForEvent('download'),page.getByRole('button',{name:'↓ Descargar dashboard HTML',exact:true}).click()]);
    const target=path.resolve(process.env.DSW_QA_DIR||process.cwd(),'dashboard-test.html');
    await download.saveAs(target);
    // A separate offline browser context demonstrates that the exported file is autonomous.
    const offline=await browser.newContext({offline:true});
    const exportPage=await offline.newPage();
    exportPage.on('pageerror',e=>errors.push(e.message));
    await exportPage.goto('file://'+target);
    await exportPage.locator('#chart-0 .main-svg').first().waitFor();
    const filter=exportPage.locator('#filters select');
    await filter.selectOption(JSON.stringify('Norte'));
    const count=await exportPage.locator('#count').textContent();
    if(!count.startsWith('1 filas visibles'))throw new Error('El filtro offline no redujo el resultado: '+count);
    await offline.close();
    await page.getByRole('button',{name:'Datos y calidad',exact:true}).click();
    await page.setViewportSize({width:390,height:844});
    await page.getByRole('heading',{name:'Vista previa',exact:true}).waitFor();
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+2);
    if(overflow)throw new Error('La página desborda horizontalmente en móvil');
    if(screenshotDir)await page.screenshot({path:path.join(screenshotDir,'mobile.png'),fullPage:true});
    if(errors.length)throw new Error(errors.join('\n'));
    console.log(JSON.stringify({ui:'passed',pipeline:'passed',chart:'passed',saved_dashboard:'passed',offline_export_and_filter:'passed',mobile_width:'passed',console_errors:0},null,2));
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
