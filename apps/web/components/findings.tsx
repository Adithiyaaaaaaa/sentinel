"use client";

import { useDeferredValue, useEffect, useState } from "react";
import { AlertTriangle, ArrowLeft, ArrowRight, CheckCircle2, Code2, FileCode2, LoaderCircle, Search, Shield, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { LocalReasoning } from "@/components/local-reasoning";
import { PatchReview } from "@/components/patch-review";
import { api, formatNumber, type CodeEntity, type Finding, type FindingPage, type FindingStatus, type Scan, type SourceExcerpt } from "@/lib/api";

const message = (error: unknown) => error instanceof Error ? error.message : "Unable to load analysis.";
const statuses: FindingStatus[] = ["open", "confirmed", "false_positive", "fixed", "ignored"];
const label = (value: string) => value.replaceAll("_", " ");

export function AnalysisOverview({scan, onFindings}: {scan: Scan; onFindings: () => void}) {
  const summary = scan.analysis_summary;
  if (!summary.ruleset_version) return <div className="scope-note"><Shield size={15} /><span>This historical scan predates static analysis. Run a new scan to collect findings.</span></div>;
  return <section className="panel analysis-overview">
    <div className="panel-heading"><div><h2><Shield size={17} />Deterministic analysis</h2><p>Evidence from syntax trees. No AI conclusions.</p></div><Button variant="outline" onClick={onFindings}>Explore findings<ArrowRight size={14} /></Button></div>
    <div className="severity-grid">{["critical", "high", "medium", "low"].map(severity => <button key={severity} onClick={onFindings} className={`severity-metric severity-${severity}`}><span>{severity.toUpperCase()}</span><strong>{summary.severity_counts?.[severity] ?? 0}</strong></button>)}</div>
    <div className="analysis-coverage"><span><CheckCircle2 size={13} />{summary.parsed_files} files parsed</span><span>{formatNumber(summary.entity_count ?? 0)} code entities</span><span>{summary.rule_count} rules · v{summary.ruleset_version}</span></div>
    <p className="analysis-limit">AST coverage: {summary.supported_languages?.join(", ")}. {summary.unsupported_files} other files indexed only. {(summary.failed_files ?? 0) + (summary.unprocessed_files ?? 0)} supported files could not be analyzed. A zero count does not certify security.</p>
  </section>;
}

export function FindingsView({scan}: {scan: Scan | null}) {
  const [query, setQuery] = useState(""); const deferredQuery = useDeferredValue(query);
  const [severity, setSeverity] = useState(""); const [category, setCategory] = useState("");
  const [language, setLanguage] = useState(""); const [status, setStatus] = useState("");
  const [confidence, setConfidence] = useState("0"); const [cwe, setCwe] = useState(""); const [owasp, setOwasp] = useState("");
  const [sort, setSort] = useState("risk"); const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<FindingPage | null>(null); const [selected, setSelected] = useState<Finding | null>(null);
  const [loading, setLoading] = useState(false); const [error, setError] = useState<string | null>(null); const [revision, setRevision] = useState(0);
  useEffect(() => { setOffset(0); }, [deferredQuery, severity, category, language, status, confidence, cwe, owasp, sort, scan?.id]);
  useEffect(() => {setSelected(null); setPage(null);}, [scan?.id]);
  useEffect(() => {
    if (!scan || scan.status !== "completed" || !scan.analysis_summary.ruleset_version) return;
    const controller = new AbortController(); setLoading(true); setError(null);
    const params = new URLSearchParams({q: deferredQuery, sort, min_confidence: confidence, offset: String(offset), limit: "25"});
    for (const [key, value] of Object.entries({severity, category, language, status, cwe, owasp})) if (value) params.set(key, value);
    api<FindingPage>(`/scans/${scan.id}/findings?${params}`, {signal: controller.signal}).then(setPage)
      .catch((e: unknown) => {if (!controller.signal.aborted) setError(message(e));})
      .finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [scan?.id, scan?.status, deferredQuery, severity, category, language, status, confidence, cwe, owasp, sort, offset, revision]);
  if (!scan || scan.status !== "completed") return <div className="panel empty-inline">Complete a scan to inspect findings.</div>;
  if (!scan.analysis_summary.ruleset_version) return <div className="panel empty-inline">Run a new scan to add deterministic analysis. This historical index has no finding results.</div>;
  return <>
    <div className="findings-intro"><Shield size={16} /><span>{scan.analysis_summary.rule_count} deterministic rules · {scan.analysis_summary.parsed_files} files parsed · <strong>Matches need engineering review.</strong></span></div>
    <section className="panel findings-panel"><div className="findings-toolbar">
      <label className="search-field"><Search size={15}/><input aria-label="Search findings" placeholder="Search title or file path…" value={query} onChange={e => setQuery(e.target.value)}/></label>
      <select aria-label="Finding severity" value={severity} onChange={e => setSeverity(e.target.value)}><option value="">All severities</option>{["critical","high","medium","low"].map(s => <option key={s} value={s}>{s}</option>)}</select>
      <select aria-label="Finding category" value={category} onChange={e => setCategory(e.target.value)}><option value="">All categories</option>{["security","quality","performance","reliability"].map(s => <option key={s} value={s}>{s}</option>)}</select>
      <select aria-label="Finding status" value={status} onChange={e => setStatus(e.target.value)}><option value="">All statuses</option>{statuses.map(s => <option key={s} value={s}>{label(s)}</option>)}</select>
      <select aria-label="Finding sort" value={sort} onChange={e => setSort(e.target.value)}><option value="risk">Priority</option><option value="severity">Severity</option><option value="confidence">Confidence</option><option value="file">File</option><option value="detected_at">Detection time</option></select>
    </div><details className="finding-advanced"><summary>More filters</summary><div>
      <label>Language<select aria-label="Finding language" value={language} onChange={e => setLanguage(e.target.value)}><option value="">All languages</option>{scan.analysis_summary.supported_languages?.map(l => <option key={l}>{l}</option>)}</select></label>
      <label>Minimum confidence<select aria-label="Minimum confidence" value={confidence} onChange={e => setConfidence(e.target.value)}><option value="0">Any</option><option value="0.8">80%</option><option value="0.9">90%</option><option value="0.95">95%</option></select></label>
      <label>CWE<input aria-label="CWE filter" placeholder="CWE-89" value={cwe} onChange={e => setCwe(e.target.value)}/></label>
      <label>OWASP<input aria-label="OWASP filter" placeholder="A03:2021" value={owasp} onChange={e => setOwasp(e.target.value)}/></label>
    </div></details>
    {error && <div className="error-banner" role="alert">{error}</div>}
    <div className="finding-results-label" aria-live="polite">{loading ? "Loading findings…" : `${page?.total ?? 0} findings match these filters`}</div>
    <div className="finding-list">{page?.items.map(finding => <button key={finding.id} onClick={() => setSelected(finding)} className={`finding-row ${selected?.id === finding.id ? "finding-selected" : ""}`}>
      <span className={`severity-label severity-${finding.severity}`}>{finding.severity}</span><span className="finding-row-main"><strong>{finding.title}</strong><span className="mono">{finding.file}:{finding.line}</span><span>{finding.rule_id} · {finding.category} · {label(finding.status)}</span></span>
      <span className="finding-row-risk"><strong>{finding.risk}</strong><span>PRIORITY</span><small>{Math.round(finding.confidence * 100)}% confidence</small></span><ArrowRight size={14}/>
    </button>)}</div>
    {!loading && !error && !page?.items.length && <div className="empty-inline"><CheckCircle2 size={24}/><p>No findings match. Check analysis coverage before drawing security conclusions.</p></div>}
    <div className="table-pagination"><span>{page?.total ? `${offset + 1}–${Math.min(offset + 25, page.total)} of ${page.total}` : "0 findings"}</span><div><Button variant="ghost" size="sm" disabled={!offset || loading} onClick={() => setOffset(Math.max(0, offset - 25))}><ArrowLeft size={14}/>Previous</Button><Button variant="ghost" size="sm" disabled={!page || offset + 25 >= page.total || loading} onClick={() => setOffset(offset + 25)}>Next<ArrowRight size={14}/></Button></div></div></section>
    {selected && <FindingDetail key={selected.id} finding={selected} onClose={() => setSelected(null)} onUpdate={updated => {setSelected(updated); setRevision(r => r + 1);}}/>}
  </>;
}

function FindingDetail({finding, onClose, onUpdate}: {finding: Finding; onClose: () => void; onUpdate: (f: Finding) => void}) {
  const [reviewStatus, setReviewStatus] = useState<FindingStatus>(finding.status);
  const [saving, setSaving] = useState(false); const [error, setError] = useState<string | null>(null);
  async function save() {
    setSaving(true); setError(null);
    try {onUpdate(await api<Finding>(`/findings/${finding.id}/status`, {method:"POST",body:JSON.stringify({status:reviewStatus})}));}
    catch (e) {setError(message(e));} finally {setSaving(false);}
  }
  return <section className="panel finding-detail" aria-label="Finding details"><div className="panel-heading"><div><div className="detail-kicker">{finding.rule_id} · {finding.cwe ?? "QUALITY RULE"} · {finding.owasp ?? finding.category}</div><h2>{finding.title}</h2><p className="mono">{finding.file}:{finding.line} · {finding.symbol}</p></div><Button variant="ghost" size="icon" aria-label="Close finding details" onClick={onClose}><X size={16}/></Button></div>
    <div className="finding-detail-grid"><div className="finding-reasoning">
      <div className="verdict-line"><span className={`severity-label severity-${finding.severity}`}>{finding.severity}</span><span>{finding.verdict === "confirmed" ? "Confirmed pattern" : `${finding.verdict} issue`}</span><strong>{Math.round(finding.confidence*100)}% rule confidence</strong></div>
      <p className="pattern-disclaimer">Pattern confidence is a rule heuristic, not an exploit probability. Exploitability has not been verified.</p>
      <h3>Why it was flagged</h3><p>{finding.explanation}</p><h3>Deterministic evidence</h3>{finding.evidence.map((item,i) => <div className="evidence-card" key={i}><span className="mono">L{item.line}{item.end_line !== item.line ? `–${item.end_line}` : ""} · AST</span><p>{item.description}</p></div>)}
      <h3>Potential impact</h3><p>{finding.impact}</p><h3>What needs verification</h3><p>{finding.exploitability}</p><h3>Recommended change</h3><p>{finding.recommendation}</p>
      <div className="priority-explanation"><strong>Priority {finding.risk}/100</strong><code>{finding.risk_basis.severity_weight} severity weight × {finding.confidence} confidence</code><span>{finding.risk_basis.meaning}</span></div>
      <div className="triage-controls"><label htmlFor={`review-${finding.id}`}>Review status</label><select id={`review-${finding.id}`} value={reviewStatus} onChange={e => setReviewStatus(e.target.value as FindingStatus)}>{statuses.map(s => <option key={s} value={s}>{label(s)}</option>)}</select><Button variant="outline" onClick={() => void save()} disabled={saving || reviewStatus === finding.status}>{saving ? <LoaderCircle size={14} className="spin"/> : <CheckCircle2 size={14}/>}Save status</Button><p>Manual review status applies to this scan only. “Fixed” does not verify a code change; rescan to check.</p>{error && <div role="alert" className="dialog-error">{error}</div>}</div>
    </div><CodePanel scanId={finding.scan_id} path={finding.file} line={finding.line} endLine={finding.end_line}/></div><LocalReasoning findingId={finding.id}/>{finding.language === "Python" && <PatchReview key={finding.id} findingId={finding.id}/>}
  </section>;
}

export function CodePanel({scanId,path,line=1,endLine=line}: {scanId:string;path:string;line?:number;endLine?:number}) {
  const [excerpt,setExcerpt] = useState<SourceExcerpt | null>(null); const [entities,setEntities] = useState<CodeEntity[]>([]);
  const [focus,setFocus] = useState(line); const [error,setError] = useState<string | null>(null); const [loading,setLoading] = useState(true);
  const [testEntity,setTestEntity] = useState("");
  useEffect(()=>setTestEntity(""),[scanId,path]);
  useEffect(() => {setFocus(line);}, [line,path,scanId]);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true);setError(null);setExcerpt(null);
    api<SourceExcerpt>(`/scans/${scanId}/source?${new URLSearchParams({path,line:String(focus),context:"12"})}`,{signal:controller.signal})
      .then(setExcerpt).catch((e:unknown) => {if (!controller.signal.aborted) setError(message(e));}).finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [scanId,path,focus]);
  useEffect(() => {
    const controller = new AbortController(); setEntities([]);
    api<{items:CodeEntity[]}>(`/scans/${scanId}/entities?${new URLSearchParams({path,limit:"500"})}`, {signal:controller.signal})
      .then(data => setEntities(data.items)).catch(() => { /* Source remains usable if optional outline cannot load. */ });
    return () => controller.abort();
  }, [scanId,path]);
  const symbols = entities.filter(e => ["class","function","method","api"].includes(e.kind));
  return <section className="code-panel" aria-label="Source code"><div className="code-panel-header"><FileCode2 size={15}/><span className="mono">{path}</span><span>{excerpt?.language ?? "SOURCE"}</span></div>
    {symbols.length > 0 && <div className="symbol-picker"><Code2 size={14}/><select aria-label="Jump to symbol" value="" onChange={e => setFocus(Number(e.target.value))}><option value="" disabled>Jump to symbol ({symbols.length})</option>{symbols.map(e => <option key={e.id} value={e.start_line}>{e.kind} {e.name} · L{e.start_line} · complexity {e.complexity}</option>)}</select></div>}
    {loading && <div className="empty-inline"><LoaderCircle size={20} className="spin"/>Verifying file fingerprint…</div>}
    {error && <div className="source-error" role="alert"><AlertTriangle size={20}/><p>{error}</p></div>}
    {excerpt && <><div className="code-lines" role="region" aria-label={`Source excerpt from ${path}`} tabIndex={0}>{excerpt.lines.map(row => <div key={row.number} className={`code-line ${row.number >= line && row.number <= endLine ? "code-highlight" : ""}`}><span className="line-number">{row.number}</span><code>{highlight(row.text)}{row.truncated ? " … [line truncated]" : ""}</code></div>)}</div><div className="code-context-controls"><Button variant="ghost" size="sm" disabled={excerpt.start_line<=1} onClick={() => setFocus(Math.max(1,focus-24))}><ArrowLeft size={13}/>Earlier</Button><span>L{excerpt.start_line}–{excerpt.end_line} / {excerpt.total_lines}</span><Button variant="ghost" size="sm" disabled={excerpt.end_line>=excerpt.total_lines} onClick={() => setFocus(Math.min(excerpt.total_lines,focus+24))}>Later<ArrowRight size={13}/></Button></div><p className="source-integrity"><CheckCircle2 size={12}/>SHA-256 matches this scan. Detected secret assignments are redacted.</p></>}
    {excerpt?.language === "Python" && symbols.some(e=>e.kind==="function"||e.kind==="method") && <div className="function-tests"><label>Test generation target<select aria-label="Test generation function" value={testEntity} onChange={e=>setTestEntity(e.target.value)}><option value="">Select a function</option>{symbols.filter(e=>e.kind==="function"||e.kind==="method").map(e=><option key={e.id} value={e.id}>{e.name} · L{e.start_line}</option>)}</select></label>{testEntity&&<PatchReview key={testEntity} entityId={testEntity}/>}</div>}
  </section>;
}

function highlight(source: string) {
  // Token spans are React text nodes, never untrusted HTML. This is lexical
  // display coloring; correctness and evidence come from the backend parsers.
  const tokens = source.split(/("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|#.*$|\/\/.*$|\b(?:def|class|return|import|from|if|else|elif|for|while|try|except|pass|raise|async|await|const|let|function|export|new|throw|catch|None|True|False|null|true|false)\b|\b\d+(?:\.\d+)?\b)/g);
  return tokens.map((token,index) => <span key={index} className={/^["']/.test(token) ? "token-string" : /^(#|\/\/)/.test(token) ? "token-comment" : /^(def|class|return|import|from|if|else|elif|for|while|try|except|pass|raise|async|await|const|let|function|export|new|throw|catch|None|True|False|null|true|false)$/.test(token) ? "token-keyword" : /^\d/.test(token) ? "token-number" : undefined}>{token}</span>);
}
