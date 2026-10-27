"use client";

import { useEffect, useState } from "react";
import { FileDiff, LoaderCircle, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, formatDate } from "@/lib/api";

type Proposal = {id:string;kind:string;path:string;status:string;model:string;created_at:string;review_hash:string|null;diff:string|null;tests:string|null;explanation:string|null;risks:string[];error:string|null;test_runs?:{id:string;status:string;error:string|null;result:{exit_code?:number;reported_counts?:Record<string,number>;scope?:string;output?:string;output_truncated?:boolean}}[]};
type Preview = {context_hash:string;package:unknown;persistence:string};
type Capability = {sandbox:{available:boolean;error:string|null;image:string};limits:string};
const errorText = (e:unknown) => e instanceof Error ? e.message : "Unable to load reviewed changes.";

export function PatchReview({findingId,entityId}: {findingId?:string;entityId?:string}) {
  const [open,setOpen] = useState(false);
  const [models,setModels] = useState<{name:string}[]>([]); const [model,setModel] = useState("");
  const [preview,setPreview] = useState<Preview|null>(null); const [capability,setCapability] = useState<Capability|null>(null);
  const [job,setJob] = useState<Proposal|null>(null); const [history,setHistory] = useState<Proposal[]>([]);
  const [busy,setBusy] = useState(false); const [error,setError] = useState<string|null>(null); const [reviewed,setReviewed] = useState(false);
  const [refresh,setRefresh] = useState(0);
  const kind = entityId ? "tests" : "fix";
  const running = job?.status === "generating" || job?.status === "validating";
  useEffect(()=>{setOpen(false);setJob(null);setPreview(null);setHistory([]);setReviewed(false);setError(null);},[findingId,entityId]);
  useEffect(()=>{
    if (!open) return;
    const controller = new AbortController(); const init = {signal:controller.signal};
    setBusy(true);setError(null);setPreview(null);
    const target = findingId ? {finding_id:findingId,kind} : {entity_id:entityId,kind};
    Promise.allSettled([
      api<{models:{name:string}[];error:string|null}>("/llm/models",init).then(data=>{setModels(data.models);setModel(current=>data.models.some(m=>m.name===current)?current:data.models[0]?.name??"");if(data.error)setError(data.error);}),
      api<Capability>("/patches/capabilities",init).then(setCapability),
      api<Preview>("/patches/preview",{...init,method:"POST",body:JSON.stringify(target)}).then(setPreview),
      api<Proposal[]>(`/patches?${new URLSearchParams(findingId?{finding_id:findingId}:{entity_id:entityId!})}`,init).then(async items=>{setHistory(items);setJob(items[0]?await api<Proposal>(`/patches/${items[0].id}`,init):null);}),
    ]).then(results=>{if(!controller.signal.aborted){const failure=results.find(r=>r.status==="rejected");if(failure?.status==="rejected")setError(errorText(failure.reason));setBusy(false);}});
    return ()=>controller.abort();
  },[open,findingId,entityId,kind,refresh]);
  useEffect(()=>{
    if(!running||!job)return;
    let stopped=false;let timer:ReturnType<typeof setTimeout>;
    const poll=async()=>{try{const next=await api<Proposal>(`/patches/${job.id}`);if(stopped)return;setJob(next);if(!["generating","validating"].includes(next.status))setHistory(items=>[next,...items.filter(i=>i.id!==next.id)]);else timer=setTimeout(poll,1500);}catch(e){if(!stopped){setError(errorText(e));timer=setTimeout(poll,4000);}}};
    timer=setTimeout(poll,1000);return()=>{stopped=true;clearTimeout(timer);};
  },[job?.id,running]);
  useEffect(()=>setReviewed(false),[job?.id,job?.status]);
  async function generate(){
    if(!preview)return;setBusy(true);setError(null);
    try{setJob(await api<Proposal>("/patches",{method:"POST",body:JSON.stringify({finding_id:findingId,entity_id:entityId,kind,model,context_hash:preview.context_hash})}));}
    catch(e){setError(errorText(e));}finally{setBusy(false);}
  }
  async function action(action:"validate"|"apply"|"rollback"){
    if(!job||!reviewed)return;setBusy(true);setError(null);
    try{const next=await api<Proposal>(`/patches/${job.id}/${action}`,{method:"POST",body:JSON.stringify({review_hash:job.review_hash,approved:true})});setJob(next);setHistory(items=>[next,...items.filter(i=>i.id!==next.id)]);setReviewed(false);}
    catch(e){setError(errorText(e));}finally{setBusy(false);}
  }
  function downloadTests(){
    if(!job?.tests)return;const url=URL.createObjectURL(new Blob([job.tests],{type:"text/x-python;charset=utf-8"}));const anchor=document.createElement("a");anchor.href=url;anchor.download="sentinel_generated_test.py";anchor.click();URL.revokeObjectURL(url);
  }
  return <section className="patch-review local-reasoning" aria-label={entityId?"Generated function tests":"Reviewed fix"}>
    <div className="panel-heading"><div><h3><FileDiff size={17}/>{entityId?"Tests for this function":"Reviewed changes"}</h3><p>{entityId?"Generate pytest suggestions for the selected function.":"Review a proposed fix before any file changes."}</p></div><Button variant="outline" onClick={()=>setOpen(v=>!v)}>{open?"Hide changes":entityId?"Generate tests":"Review a fix"}</Button></div>
    {open&&<>
      <p className="ai-boundary">Python only. Proposals are unverified model output. Successful proposals store the original file, replacement, diff, and tests locally for rollback. Files with detected secrets are excluded. Test execution requires your approval and a configured Docker sandbox.</p>
      {error&&<div role="alert" className="error-banner">{error}</div>}
      {capability&&!capability.sandbox.available&&<div className="scope-note"><ShieldCheck size={16}/><span>{capability.sandbox.error} Generation and diff review remain available; validation and apply stay disabled.</span></div>}
      <div className="ai-controls"><label>Local model<select aria-label="Patch model" value={model} onChange={e=>setModel(e.target.value)} disabled={busy||running}><option value="" disabled>Select a model</option>{models.map(m=><option key={m.name}>{m.name}</option>)}</select></label><Button onClick={()=>void generate()} disabled={busy||running||!model||!preview}>{busy||running?<LoaderCircle size={14} className="spin"/>:<FileDiff size={14}/>}Generate {kind==="fix"?"fix":"pytest tests"}</Button><Button variant="ghost" disabled={busy||running} onClick={()=>setRefresh(n=>n+1)}>Refresh context & sandbox</Button></div>
      {preview&&<details className="ai-context"><summary>Inspect source context sent to local Ollama</summary><pre>{JSON.stringify(preview.package,null,2)}</pre></details>}
      {history.length>0&&<label className="ai-history">Proposal history<select aria-label="Proposal history" value={job?.id??""} disabled={busy||running} onChange={async e=>{setError(null);try{setJob(await api<Proposal>(`/patches/${e.target.value}`));}catch(error){setError(errorText(error));}}}>{history.map(item=><option value={item.id} key={item.id}>{formatDate(item.created_at)} · {item.kind} · {item.status}</option>)}</select></label>}
      {job&&<div className="patch-result"><div className="ai-opinion-label">{job.status.replaceAll("_"," ").toUpperCase()} · {job.model}</div><p>{job.path} · {formatDate(job.created_at)}</p>{job.error&&<div className="error-banner" role="alert">{job.error}</div>}
        {running&&<p role="status"><LoaderCircle size={14} className="spin"/> {job.status==="generating"?"Generating and checking the proposal…":"Testing the staged change in Docker…"}</p>}
        {job.explanation&&<p>{job.explanation}</p>}
        {!!job.risks.length&&<><h4>Risks and limitations</h4><ul>{job.risks.map((risk,i)=><li key={i}>{risk}</li>)}</ul></>}
        {job.diff&&<><h4>Proposed diff</h4><pre className="patch-diff" aria-label="Proposed patch diff">{job.diff.split("\n").map((line,i)=><span key={i} className={line.startsWith("+")?"diff-add":line.startsWith("-")?"diff-remove":""}>{line}{"\n"}</span>)}</pre></>}
        {job.tests&&<><h4>Generated pytest tests · review required</h4><pre className="patch-diff" aria-label="Generated pytest source">{job.tests}</pre><Button variant="outline" onClick={downloadTests}>Download test source</Button></>}
        {job.test_runs?.map(run=><div key={run.id}><div className="scope-note"><span>Validation: {run.status}{run.result.exit_code!==undefined?` · exit ${run.result.exit_code}`:""}{run.result.reported_counts?` · ${Object.entries(run.result.reported_counts).map(([key,value])=>`${value} ${key}`).join(" · ")}`:""}. {run.error??run.result.scope} Coverage delta is not measured.</span></div>{run.result.output&&<details><summary>Sandbox output · may contain repository text{run.result.output_truncated?" · truncated":""}</summary><pre className="patch-diff">{run.result.output}</pre></details>}</div>)}
        {job.review_hash&&!running&&<><label className="patch-approval"><input type="checkbox" checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/>I reviewed the diff, tests, and risks. I approve the action I select below.</label><div className="ai-controls">
          {["ready","validated","validation_failed"].includes(job.status)&&<Button variant="outline" disabled={!reviewed||busy||!capability?.sandbox.available} onClick={()=>void action("validate")}>Validate in sandbox</Button>}
          {job.kind==="fix"&&job.status==="validated"&&<Button disabled={!reviewed||busy} onClick={()=>void action("apply")}>Apply reviewed fix</Button>}
          {job.status==="applied"&&<Button variant="outline" disabled={!reviewed||busy} onClick={()=>void action("rollback")}>Roll back this fix</Button>}
        </div><p className="pattern-disclaimer">Validation changes an isolated copy. Failed tests discard that copy. Apply and rollback check file fingerprints and never update finding status automatically. Rescan after a change.</p></>}
      </div>}
    </>}
  </section>;
}
