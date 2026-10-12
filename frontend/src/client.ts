export async function api<T>(path:string,body?:unknown):Promise<T>{
  const response=await fetch('/api'+path,{method:body===undefined?'GET':'POST',headers:body instanceof FormData?{}:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:body instanceof FormData?body:JSON.stringify(body)});
  if(!response.ok){const error=await response.json().catch(()=>({detail:'Error de conexión'}));throw new Error(typeof error.detail==='string'?error.detail:JSON.stringify(error.detail));}
  return response.json();
}

export async function compute<T>(projectId:string,datasetId:string,request:unknown):Promise<T>{
  const job=await api<{id:string}>(`/projects/${projectId}/datasets/${datasetId}/analyses`,request);
  for(;;){
    const current=await api<{status:string;message:string;result?:T}>(`/jobs/${job.id}`);
    if(current.status==='succeeded')return current.result as T;
    if(['failed','cancelled','interrupted'].includes(current.status))throw new Error(current.message);
    await new Promise(resolve=>setTimeout(resolve,500));
  }
}
