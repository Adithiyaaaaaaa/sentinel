"use client";

import { useEffect, useState } from "react";
import { Bot, LoaderCircle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, formatBytes, formatDate } from "@/lib/api";

type Model = {name: string; digest: string; size: number; parameters: string};
type Opinion = {verdict: string; severity: string; confidence: number; root_cause: string; impact: string;
  explanation: string; code_path: string; fix_strategy: string; fix_risks: string; tests_required: string[];
  uncertainty: string[]; evidence_refs: string[]};
type ContextSummary = {file: string; start_line: number; end_line: number; bytes: number; sha256: string;
  evidence: {id:string;file:string;line:number;description:string}[]; limitations: string[]};
type Preview = {context_hash: string; summary: ContextSummary; package: unknown};
type Analysis = {id:string; model:string;model_digest:string;status:string;created_at:string;error:string|null;
  response: Opinion|null;context_summary:ContextSummary};
const message = (e:unknown) => e instanceof Error ? e.message : "Unable to load local reasoning.";

export function LocalReasoning({findingId}: {findingId:string}) {
  const [expanded,setExpanded] = useState(false);
  const [models,setModels] = useState<Model[]>([]); const [model,setModel] = useState("");
  const [preview,setPreview] = useState<Preview|null>(null);
  const [job,setJob] = useState<Analysis|null>(null); const [history,setHistory] = useState<Analysis[]>([]);
  const [loading,setLoading] = useState(false); const [error,setError] = useState<string|null>(null);
  const [providerError,setProviderError] = useState<string|null>(null);
  const [refresh,setRefresh] = useState(0);
  useEffect(() => {
    if (!expanded) return;
    const controller = new AbortController(); setLoading(true);setError(null);setPreview(null);
    const init = {signal:controller.signal};
    Promise.allSettled([
      api<{available:boolean;models:Model[];error:string|null}>("/llm/models",init).then(data => {
        setModels(data.models);setProviderError(data.error);
        setModel(current => data.models.some(m => m.name === current) ? current : data.models[0]?.name ?? "");
      }),
      api<Preview>(`/findings/${findingId}/context`,init).then(setPreview),
      api<Analysis[]>(`/findings/${findingId}/analyses`,init).then(items => {setHistory(items);setJob(items[0] ?? null);}),
    ]).then(results => {
      if (!controller.signal.aborted) {
        const failure = results.find(r => r.status === "rejected");
        if (failure?.status === "rejected") setError(message(failure.reason));
        setLoading(false);
      }
    });
    return () => controller.abort();
  },[expanded,findingId,refresh]);
  useEffect(() => {
    if (job?.status !== "running") return;
    let stopped = false; let timer:ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await api<Analysis>(`/analyses/${job.id}`);
        if (stopped) return;
        setJob(next);
        if (next.status !== "running") setHistory(items => [next,...items.filter(i => i.id !== next.id)]);
        else timer = setTimeout(() => void poll(),1500);
      } catch(e) {if (!stopped) {setError(message(e));timer=setTimeout(() => void poll(),3000);}}
    };
    timer=setTimeout(() => void poll(),1000);
    return () => {stopped=true;clearTimeout(timer);};
  },[job?.id,job?.status]);
  async function run() {
    if (!preview) return;
    setLoading(true);setError(null);
    try {setJob(await api<Analysis>(`/findings/${findingId}/analyses`,{method:"POST",body:JSON.stringify({model,context_hash:preview.context_hash})}));}
    catch(e) {setError(message(e));} finally {setLoading(false);}
  }
  return <section className="local-reasoning" aria-label="Local AI reasoning"><div className="ai-heading"><div><h3><Bot size={17}/>Local AI reasoning</h3><p>A second opinion grounded in this finding’s evidence.</p></div><Button variant="outline" onClick={() => setExpanded(!expanded)}>{expanded ? "Hide reasoning" : "Ask local AI"}</Button></div>
    {expanded && <><p className="ai-boundary">Only the context shown below is sent to your local Ollama model. AI opinions do not change the finding, execute code, or verify a fix.</p>
      <div className="ai-controls"><label>Installed local model<select aria-label="Local model" value={model} onChange={e => setModel(e.target.value)} disabled={loading || job?.status === "running"}><option value="" disabled>Select a model</option>{models.map(m => <option key={m.name}>{m.name}</option>)}</select></label><Button variant="ghost" size="sm" onClick={() => setRefresh(n=>n+1)} disabled={loading || job?.status === "running"}><RefreshCw size={13}/>Refresh</Button><Button onClick={() => void run()} disabled={loading || !preview || !model || !!providerError || job?.status === "running"}>{loading || job?.status === "running" ? <LoaderCircle size={14} className="spin"/> : <Bot size={14}/>}Analyze locally</Button></div>
      {providerError && <p className="dialog-error" role="status">{providerError}</p>}
      {!providerError && !loading && !models.length && <p className="dialog-error">No installed local GGUF models found. Install a model in Ollama, then refresh. SENTINEL never downloads models automatically.</p>}
      {error && <p className="dialog-error" role="alert">{error}</p>}
      {preview && <details className="ai-context"><summary>Inspect context · {preview.summary.file} · L{preview.summary.start_line}–{preview.summary.end_line} · {formatBytes(preview.summary.bytes)}</summary><p>Source fingerprint verified. Detected secret assignments are redacted; undetected sensitive data may remain.</p><pre>{JSON.stringify(preview.package,null,2)}</pre></details>}
      {job?.status === "running" && <div className="ai-running" role="status"><LoaderCircle size={18} className="spin"/><span>Reasoning with {job.model} on this machine… You can navigate away and return; the request continues in the background.</span></div>}
      {job?.status === "failed" && <p className="dialog-error" role="alert">{job.error} No AI conclusion was accepted.</p>}
      {history.length > 1 && <label className="ai-history">Previous requests<select aria-label="Reasoning history" value={job?.id ?? ""} disabled={job?.status === "running"} onChange={e => setJob(history.find(i=>i.id===e.target.value) ?? null)}>{history.map(i=><option key={i.id} value={i.id}>{formatDate(i.created_at)} · {i.model} · {i.status}</option>)}</select></label>}
      {job?.status === "completed" && job.response && <OpinionView job={job} opinion={job.response}/>}
    </>}
  </section>;
}

function OpinionView({job,opinion}: {job:Analysis;opinion:Opinion}) {
  return <div className="ai-opinion"><div className="ai-opinion-label">MODEL OPINION · NOT VERIFIED</div><h3>{opinion.verdict.replaceAll("_"," ")} · {opinion.severity} severity</h3><p>{job.model} · {formatDate(job.created_at)} · {Math.round(opinion.confidence*100)}% self-reported confidence</p><p className="ai-boundary">Schema and evidence references were checked. The model’s factual claims and confidence are not independently verified. This result refers to the source fingerprint recorded with this request.</p>
    {[['Explanation',opinion.explanation],['Root cause',opinion.root_cause],['Code path',opinion.code_path],['Potential impact',opinion.impact],['Fix strategy',opinion.fix_strategy],['Fix risks',opinion.fix_risks]].map(([title,text]) => <div key={title}><h4>{title}</h4><p>{text}</p></div>)}
    <h4>Uncertainty & missing context</h4><ul>{opinion.uncertainty.map((s,i)=><li key={i}>{s}</li>)}</ul><h4>Tests to perform</h4><ul>{opinion.tests_required.map((s,i)=><li key={i}>{s}</li>)}</ul><h4>Cited evidence</h4>{opinion.evidence_refs.map(id=>{const e=job.context_summary.evidence.find(e=>e.id===id);return <p key={id}><strong>{id}</strong> · {e?.file}:{e?.line} · {e?.description}</p>;})}
  </div>;
}
