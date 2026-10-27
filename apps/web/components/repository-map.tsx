"use client";
import { useEffect, useState } from "react";
import { ArrowRight, GitBranch, LoaderCircle, Search } from "lucide-react";
import { api, formatDate, type Scan } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { CodePanel } from "@/components/findings";

type GraphNode = {id:string;name:string;kind:string;file:string|null;line:number|null;end_line?:number;language:string};
type Edge = {source:string;target:string;kind:string;file:string;line:number;basis:string};
type Graph = {available:boolean;nodes:GraphNode[];edges:Edge[];truncated:boolean;matching_nodes:number;
  summary:{nodes:number;edges:number;resolved_calls:number;unresolved_calls:number;cycle_count:number;cycles:string[][];scope:string;coupling:{file:string;fan_in:number;fan_out:number}[]};
  unresolved:{name:string;file:string;line:number;reason:string}[]};
const message = (e:unknown) => e instanceof Error ? e.message : "Unable to load repository intelligence.";

export function RepositoryMap({scan}: {scan:Scan|null}) {
  const [graph,setGraph]=useState<Graph|null>(null);const [view,setView]=useState("files");
  const [file,setFile]=useState("");const [selected,setSelected]=useState<GraphNode|null>(null);
  const [error,setError]=useState<string|null>(null);const [loading,setLoading]=useState(false);
  const [evidence,setEvidence]=useState<{file:string;line:number}|null>(null);
  useEffect(()=>{setFile("");setSelected(null);setEvidence(null);},[scan?.id]);
  useEffect(()=>{
    if(scan?.status!=="completed")return;
    const controller=new AbortController();setLoading(true);setError(null);setGraph(null);setSelected(null);setEvidence(null);
    api<Graph>(`/scans/${scan.id}/graph?${new URLSearchParams({view,...(file?{file}:{}),limit:"120"})}`,{signal:controller.signal})
      .then(setGraph).catch((e:unknown)=>{if(!controller.signal.aborted)setError(message(e));})
      .finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return()=>controller.abort();
  },[scan?.id,scan?.status,view,file]);
  if(!scan || scan.status!=="completed")return <div className="panel empty-inline">Complete a scan to build the repository map.</div>;
  const width=1000, columns=4, rowHeight=115;
  const positions=new Map(graph?.nodes.map((node,i)=>[node.id,{x:35+(i%columns)*245,y:35+Math.floor(i/columns)*rowHeight}]));
  const names=new Map(graph?.nodes.map(n=>[n.id,n.name]));
  const links=graph?.edges.filter(e=>e.source===selected?.id || e.target===selected?.id) ?? [];
  return <>
    <div className="map-toolbar"><label>Graph view<select aria-label="Graph view" value={view} onChange={e=>setView(e.target.value)}><option value="files">Files & dependencies</option><option value="symbols">Symbols & calls</option></select></label>{file && <Button variant="outline" onClick={()=>setFile("")}>Clear focus: {file}</Button>}<span>Click a node to inspect its relationships.</span></div>
    {error && <div className="error-banner" role="alert">{error}</div>}{loading && <div className="empty-inline"><LoaderCircle className="spin"/>Building graph view…</div>}
    {graph && !graph.available && <div className="panel empty-inline">This historical scan has no graph. Run a new repository scan.</div>}
    {graph?.available && <><div className="map-metrics"><span><strong>{graph.summary.nodes}</strong> nodes</span><span><strong>{graph.summary.edges}</strong> edges</span><span><strong>{graph.summary.resolved_calls}</strong> lexical calls matched</span><span><strong>{graph.summary.unresolved_calls}</strong> calls unresolved</span><span><strong>{graph.summary.cycle_count}</strong> module cycles</span></div>
      <p className="map-scope">{graph.summary.scope}</p>{graph.truncated && <p className="dialog-error">Partial graph view: showing {graph.nodes.length} of {graph.matching_nodes} matching nodes. Focus a file to inspect its neighborhood.</p>}
      <section className="panel graph-panel"><div className="graph-legend"><span>→ direction of dependency or call</span><span>File · symbol · external reference</span></div><div className="graph-scroll" role="region" aria-label="Interactive repository graph" tabIndex={0}><svg viewBox={`0 0 ${width} ${Math.max(240,Math.ceil(graph.nodes.length/columns)*rowHeight+40)}`} style={{minWidth:width}} aria-label="Repository relationship diagram">
        <defs><marker id="graph-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#779267"/></marker></defs>
        {graph.edges.map((edge,i)=>{const a=positions.get(edge.source),b=positions.get(edge.target);if(!a||!b)return null;const active=selected && (edge.source===selected.id||edge.target===selected.id);return <path key={i} d={`M ${a.x+100} ${a.y+55} C ${a.x+100} ${a.y+95}, ${b.x+100} ${b.y-30}, ${b.x+100} ${b.y}`} fill="none" stroke={active?"#c5ed72":"#536c4d"} strokeWidth={active?2.2:1} opacity={selected&&!active?0.18:0.7} markerEnd="url(#graph-arrow)"><title>{names.get(edge.source)} → {names.get(edge.target)} · {edge.kind}</title></path>;})}
        {graph.nodes.map(node=>{const p=positions.get(node.id)!;const choose=()=>{setSelected(node);setEvidence(node.file?{file:node.file,line:node.line??1}:null);};return <g key={node.id} transform={`translate(${p.x},${p.y})`} role="button" tabIndex={0} aria-label={`${node.kind}: ${node.name}`} onClick={choose} onKeyDown={e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();choose();}}} className="graph-node"><title>{node.name}</title><rect width="205" height="58" rx="7" fill={selected?.id===node.id?"#2d4023":"#18221b"} stroke={selected?.id===node.id?"#c5ed72":"#42573e"}/><text x="12" y="19" className="graph-node-kind">{node.kind.toUpperCase()}</text><text x="12" y="40" className="graph-node-name">{node.name.length>27?`…${node.name.slice(-26)}`:node.name}</text></g>;})}
      </svg></div></section>
      {selected && <section className="panel map-details"><div className="panel-heading"><div><h2>{selected.name}</h2><p>{selected.kind} · {selected.language}</p></div>{selected.file && <Button variant="outline" onClick={()=>{setFile(selected.file!);setView("symbols");}}>Focus file<ArrowRight size={13}/></Button>}</div><div className="map-relations">{links.length?links.map((edge,i)=><button key={i} onClick={()=>setEvidence({file:edge.file,line:edge.line})}><GitBranch size={14}/><span>{names.get(edge.source)} → {names.get(edge.target)}<small>{edge.kind} · {edge.file}:{edge.line} · {edge.basis}</small></span></button>):<p>No resolved relationships in this view.</p>}</div>{evidence && <CodePanel scanId={scan.id} path={evidence.file} line={evidence.line}/>}</section>}
      <div className="map-analysis-grid"><section className="panel"><div className="panel-heading"><div><h2>Module coupling</h2><p>Unique incoming and outgoing local file dependencies</p></div></div><div className="map-facts">{graph.summary.coupling.slice(0,12).map(row=><button key={row.file} onClick={()=>setFile(row.file)}><span>{row.file}</span><strong>{row.fan_in} in · {row.fan_out} out</strong></button>)}</div></section><section className="panel"><div className="panel-heading"><div><h2>Dependency cycles</h2><p>Strongly connected file groups; not automatically defects</p></div></div><div className="map-facts">{graph.summary.cycles.length?graph.summary.cycles.map((cycle,i)=><p key={i}>{cycle.join(" ↔ ")}</p>):<p>No cycles in the resolved graph. Unresolved calls can hide additional relationships.</p>}</div><details className="map-unresolved"><summary>Unresolved calls ({graph.summary.unresolved_calls})</summary>{graph.unresolved.map((r,i)=><p key={i}><code>{r.name}</code> · {r.file}:{r.line}<br/>{r.reason}</p>)}</details></section></div>
    </>}
  </>;
}

type Index = {id:string;model:string;status:string;total:number;indexed:number;skipped:number;dimensions:number;error:string|null;created_at:string};
type SearchHit = {key:string;name:string;file:string;kind:string;line:number;end_line:number;similarity:number;source_verified:boolean};
type SearchResult = {items:SearchHit[];meaning:string;model:string};

export function SemanticSearch({scan}:{scan:Scan|null}) {
  const [models,setModels]=useState<{name:string}[]>([]);const [model,setModel]=useState("");
  const [indexes,setIndexes]=useState<Index[]>([]);const [index,setIndex]=useState<Index|null>(null);
  const [query,setQuery]=useState("");const [result,setResult]=useState<SearchResult|null>(null);const [selected,setSelected]=useState<SearchHit|null>(null);
  const [busy,setBusy]=useState(false);const [error,setError]=useState<string|null>(null);const [refresh,setRefresh]=useState(0);
  useEffect(()=>{
    if(scan?.status!=="completed")return;
    let stopped=false;setError(null);setResult(null);setSelected(null);setIndex(null);setBusy(true);
    Promise.all([api<{available:boolean;models:{name:string}[];error:string|null}>("/embeddings/models"),api<Index[]>(`/scans/${scan.id}/embeddings`)])
      .then(([inventory,history])=>{if(stopped)return;setModels(inventory.models);setModel(inventory.models[0]?.name??"");setIndexes(history);setIndex(history[0]??null);if(inventory.error)setError(inventory.error);})
      .catch(e=>{if(!stopped)setError(message(e));}).finally(()=>{if(!stopped)setBusy(false);});
    return()=>{stopped=true;};
  },[scan?.id,scan?.status,refresh]);
  useEffect(()=>{
    if(index?.status!=="running")return;
    let stopped=false;let timer:ReturnType<typeof setTimeout>;
    const poll=async()=>{try{const next=await api<Index>(`/embeddings/${index.id}`);if(stopped)return;setIndex(next);setIndexes(items=>[next,...items.filter(i=>i.id!==next.id)]);if(next.status==="running")timer=setTimeout(()=>void poll(),1200);}catch(e){if(!stopped){setError(message(e));timer=setTimeout(()=>void poll(),3000);}}};
    timer=setTimeout(()=>void poll(),1000);return()=>{stopped=true;clearTimeout(timer);};
  },[index?.id,index?.status]);
  async function build(){if(!scan)return;setBusy(true);setError(null);setResult(null);setSelected(null);try{const next=await api<Index>(`/scans/${scan.id}/embeddings`,{method:"POST",body:JSON.stringify({model})});setIndex(next);setIndexes(items=>[next,...items]);}catch(e){setError(message(e));}finally{setBusy(false);}}
  async function search(){if(!index)return;setBusy(true);setError(null);setResult(null);setSelected(null);try{setResult(await api<SearchResult>(`/embeddings/${index.id}/search`,{method:"POST",body:JSON.stringify({query,limit:10})}));}catch(e){setError(message(e));}finally{setBusy(false);}}
  if(!scan||scan.status!=="completed")return <div className="panel empty-inline">Complete a scan before building a semantic index.</div>;
  const running=index?.status==="running";
  return <><section className="panel semantic-setup"><div className="panel-heading"><div><h2>Local semantic index</h2><p>Find code by meaning using real entity embeddings.</p></div></div><p>Build an index explicitly. Bounded source excerpts and AST metadata go only to local Ollama; detected secret assignments are redacted. Up to 1,000 callable entities are indexed. Vectors, not source excerpts, are stored.</p><div className="ai-controls"><label>Local embedding model<select aria-label="Embedding model" value={model} onChange={e=>setModel(e.target.value)} disabled={busy||running}><option value="" disabled>Select an embedding model</option>{models.map(m=><option key={m.name}>{m.name}</option>)}</select></label><Button onClick={()=>void build()} disabled={busy||running||!model}>{running?<LoaderCircle size={14} className="spin"/>:<GitBranch size={14}/>}Build semantic index</Button><Button variant="ghost" onClick={()=>setRefresh(n=>n+1)} disabled={busy||running}>Refresh models</Button></div>{!busy&&!models.length&&<p>No local embedding model is available. Install one in Ollama and refresh.</p>}
      {error&&<div className="dialog-error" role="alert">{error}</div>}{index&&<div className="semantic-status" role="status"><strong>{index.status}</strong> · {index.indexed} / {index.total} entities · {index.skipped} omitted by cap · {index.dimensions} dimensions{running&&<p>Building locally in the background. You can leave this view and return.</p>}{index.error&&<p>{index.error}</p>}</div>}
      {indexes.length>1&&<label className="ai-history">Index history<select aria-label="Embedding index history" value={index?.id??""} disabled={running||busy} onChange={e=>{setIndex(indexes.find(i=>i.id===e.target.value)??null);setResult(null);setSelected(null);}}>{indexes.map(i=><option key={i.id} value={i.id}>{formatDate(i.created_at)} · {i.model} · {i.status}</option>)}</select></label>}
    </section><form className="semantic-query" onSubmit={e=>{e.preventDefault();void search();}}><label className="search-field"><Search size={17}/><input aria-label="Semantic query" placeholder="e.g. payment failure handling" value={query} maxLength={500} onChange={e=>setQuery(e.target.value)}/></label><Button type="submit" disabled={busy||index?.status!=="completed"||!query.trim()}>{busy?<LoaderCircle size={14} className="spin"/>:<Search size={14}/>}Search code</Button></form>
    {result&&<section className="panel semantic-results"><p>{result.meaning}</p>{result.items.length?result.items.map(hit=><button key={hit.key} onClick={()=>setSelected(hit)} className="semantic-hit"><div><strong>{hit.name}</strong><span>{hit.file}:{hit.line} · {hit.kind}</span>{!hit.source_verified&&<small>Source changed or unavailable — rescan and rebuild.</small>}</div><span>{hit.similarity.toFixed(3)}<small>COSINE</small></span><ArrowRight size={14}/></button>):<div className="empty-inline">No entities are available in this index.</div>}</section>}
    {selected&&<div className="semantic-source"><CodePanel scanId={scan.id} path={selected.file} line={selected.line} endLine={selected.end_line}/></div>}
  </>;
}
