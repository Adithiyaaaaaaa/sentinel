"use client";

import { useCallback, useDeferredValue, useEffect, useRef, useState } from "react";
import { Activity, ArrowLeft, ArrowRight, Box, Check, CheckCircle2, ChevronDown, ChevronRight, Circle, Code2, Database, FileCode2, Files, Folder, FolderGit2, FolderOpen, GitBranch, History, LayoutDashboard, LoaderCircle, LockKeyhole, Menu, Plus, RefreshCw, Search, Settings2, Shield, Terminal, X } from "lucide-react";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Button } from "@/components/ui/button";
import { api, formatBytes, formatDate, formatNumber, type Directory, type FilePage, type IndexedFile, type Repository, type Scan, type Settings } from "@/lib/api";

import { AnalysisOverview, FindingsView, CodePanel } from "@/components/findings";

import { RepositoryMap, SemanticSearch } from "@/components/repository-map";

type View = "map" | "search" | "findings" | "overview" | "files" | "history" | "privacy";
const COLORS = ["#c5ed72", "#77c9a4", "#8baad9", "#c0a5df", "#e1bd7b", "#d793a2", "#7dc7d0", "#94a49b"];
const NAV: { id: View; label: string; icon: typeof LayoutDashboard }[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "findings", label: "Findings", icon: Shield },
  { id: "map", label: "Repository map", icon: GitBranch },
  { id: "search", label: "Semantic search", icon: Search },
  { id: "files", label: "Repository files", icon: Files },
  { id: "history", label: "Scan history", icon: History },
];
const isActive = (scan: Scan | null) => !!scan && ["queued", "running"].includes(scan.status);
const errorMessage = (error: unknown) => error instanceof Error ? error.message : "An unexpected error occurred.";

export default function Home() {
  const [view, setView] = useState<View>("overview");
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [repository, setRepository] = useState<Repository | null>(null);
  const [scan, setScan] = useState<Scan | null>(null);
  const [history, setHistory] = useState<Scan[]>([]);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [health, setHealth] = useState<{ status: string; database: string; version: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showOpen, setShowOpen] = useState(false);
  const [mobileMenu, setMobileMenu] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [healthData, settingsData, repos] = await Promise.all([
        api<{ status: string; database: string; version: string }>("/health"), api<Settings>("/settings"), api<Repository[]>("/repositories"),
      ]);
      setHealth(healthData); setSettings(settingsData); setRepositories(repos);
      let savedId: string | null = null;
      try { savedId = localStorage.getItem("sentinel.repository"); } catch { /* Storage is optional. */ }
      const selected = repos.find((item) => item.id === savedId) ?? repos[0] ?? null;
      setRepository(selected); setScan(selected?.latest_scan ?? null);
    } catch (err) { setError(errorMessage(err)); setHealth(null); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); setShowOpen(true); }
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, []);

  useEffect(() => {
    if (!repository) { setHistory([]); return; }
    let cancelled = false;
    api<Scan[]>(`/repositories/${repository.id}/scans`).then((items) => { if (!cancelled) setHistory(items); }).catch((err: unknown) => { if (!cancelled) setError(errorMessage(err)); });
    try { localStorage.setItem("sentinel.repository", repository.id); } catch { /* Storage is optional. */ }
    return () => { cancelled = true; };
  }, [repository?.id, scan?.status]); // Refresh persisted history when a scan finishes.

  useEffect(() => {
    if (!scan || !isActive(scan)) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await api<Scan>(`/scans/${scan.id}`);
        if (stopped) return;
        setRepositories((items) => items.map((item) => item.id === next.repository_id ? { ...item, latest_scan: next } : item));
        setScan(next);
        if (isActive(next)) timer = setTimeout(() => { void poll(); }, 850);
      } catch (err) {
        if (!stopped) { setError(errorMessage(err)); timer = setTimeout(() => { void poll(); }, 2500); }
      }
    };
    timer = setTimeout(() => { void poll(); }, 300);
    return () => { stopped = true; clearTimeout(timer); };
  }, [scan?.id, scan?.status]);

  async function startScan(repo: Repository) {
    setBusy(true); setError(null);
    try {
      const next = await api<Scan>(`/repositories/${repo.id}/scans`, { method: "POST" });
      setRepository(repo); setScan(next); setView("overview");
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }

  async function openRepository(path: string, ignorePatterns: string[] = []) {
    const repo = await api<Repository>("/repositories", { method: "POST", body: JSON.stringify({ path, ignore_patterns: ignorePatterns }) });
    const next = await api<Scan>(`/repositories/${repo.id}/scans`, { method: "POST" });
    setRepository(repo); setScan(next); setView("overview"); setError(null);
    const repos = await api<Repository[]>("/repositories");
    setRepositories(repos); setShowOpen(false);
  }

  async function openDemo() {
    if (!settings) return;
    setBusy(true); setError(null);
    try { await openRepository(settings.demo_path); }
    catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }

  function switchRepository(id: string) {
    const selected = repositories.find((item) => item.id === id) ?? null;
    setRepository(selected); setScan(selected?.latest_scan ?? null); setView("overview"); setError(null);
  }

  return <div className="app-shell">
    <aside className={`sidebar ${mobileMenu ? "sidebar-open" : ""}`}>
      <a className="brand" href="/" aria-label="SENTINEL home"><span className="brand-mark"><Shield size={19} strokeWidth={2.4} /></span><span>SENTINEL<span className="brand-dot">.</span></span><span className="version-label">LOCAL</span></a>
      <div className="workspace-label">WORKSPACE</div>
      <div className="repository-select"><FolderGit2 size={18} /><select aria-label="Selected repository" value={repository?.id ?? ""} onChange={(event) => switchRepository(event.target.value)}>
        {!repository && <option value="">No repository</option>}{repositories.map((repo) => <option value={repo.id} key={repo.id}>{repo.name}</option>)}
      </select><ChevronDown size={13} /></div>
      <button className="add-repository" onClick={() => setShowOpen(true)}><Plus size={14} /> Open repository <kbd>Ctrl K</kbd></button>
      <div className="nav-label">INTELLIGENCE</div>
      <nav aria-label="Main navigation">{NAV.map(({ id, label, icon: Icon }) => <button key={id} className={`nav-link ${view === id ? "nav-active" : ""}`} onClick={() => { setView(id); setMobileMenu(false); }}><Icon size={17} />{label}{id === "files" && scan?.status === "completed" && <span className="nav-count">{formatNumber(scan.total_files)}</span>}</button>)}</nav>
      <div className="sidebar-bottom">
        <div className="local-card"><div><span className="status-dot" /><span>Local by design</span><LockKeyhole size={13} /></div><p>Your repository.<br />Your machine. Your control.</p></div>
        <button className={`nav-link ${view === "privacy" ? "nav-active" : ""}`} onClick={() => { setView("privacy"); setMobileMenu(false); }}><Settings2 size={17} />Settings & privacy</button>
        <div className="sidebar-footer"><span>ENGINE v{health?.version ?? "0.5.0"}</span><span className={health ? "text-accent" : "text-muted"}>{health ? "● ONLINE" : "○ OFFLINE"}</span></div>
      </div>
    </aside>
    {mobileMenu && <button aria-label="Close navigation" className="sidebar-backdrop" onClick={() => setMobileMenu(false)} />}
    <div className="main-shell">
      <header className="topbar"><div className="breadcrumbs"><button className="mobile-toggle" aria-label="Open navigation" onClick={() => setMobileMenu(true)}><Menu size={18} /></button><FolderGit2 size={16} /><span>{repository?.name ?? "Workspace"}</span><ChevronRight size={13} /><span className="breadcrumb-current">{view === "privacy" ? "Settings & privacy" : NAV.find((item) => item.id === view)?.label}</span></div><div className="topbar-right"><span className="local-badge"><span className="status-dot" /> LOCAL ANALYSIS</span><span className="topbar-divider" /><span className="keyboard-hint">Ctrl K</span><button className="avatar" aria-label="Open privacy settings" onClick={() => setView("privacy")}>S</button></div></header>
      <main>
        {error && <div className="error-banner" role="alert"><span>{error}</span><div><Button variant="ghost" size="sm" onClick={() => void load()}><RefreshCw size={13} />Reconnect</Button><button aria-label="Dismiss error" onClick={() => setError(null)}><X size={16} /></button></div></div>}
        {loading ? <div className="loading-state"><LoaderCircle className="spin" size={25} /><h1>Connecting to your local engine</h1><p>Reading repositories and persisted scan history.</p></div> : view === "privacy" ? <Privacy settings={settings} health={health} /> : !repository ? <Welcome onOpen={() => setShowOpen(true)} onDemo={() => void openDemo()} busy={busy} connected={!!settings} /> : <>
          <div className="page-heading"><div><div className="eyebrow">REPOSITORY INTELLIGENCE</div><h1>{view === "overview" ? "Repository overview" : view === "files" ? "Repository files" : view === "findings" ? "Findings & evidence" : view === "map" ? "Repository map" : view === "search" ? "Semantic code search" : "Scan history"}</h1><p>{view === "overview" ? "A clear view of your codebase. Entirely on your machine." : view === "files" ? "Explore indexed files, code, and extracted symbols." : view === "findings" ? "Review deterministic matches and inspect the code behind them." : view === "map" ? "Inspect local code relationships, coupling, and dependency cycles." : view === "search" ? "Find repository code by meaning. Powered by local embeddings." : "Every scan, persisted locally. Select a run to inspect its index."}</p></div><Button onClick={() => void startScan(repository)} disabled={busy || isActive(scan)}>{busy || isActive(scan) ? <LoaderCircle size={15} className="spin" /> : <RefreshCw size={15} />}{isActive(scan) ? "Analyzing repository" : "Run scan"}</Button></div>
          <div className="repository-bar"><div className="repository-bar-name"><FolderGit2 size={17} /><strong>{repository.name}</strong><span className="branch-tag"><GitBranch size={12} />{scan?.branch ?? "No Git branch"}</span></div><span className="repository-path" title={repository.path}>{repository.path}</span><span className="index-mode">READ-ONLY ANALYSIS</span></div>
          {scan && <ScanStatus scan={scan} />}
          {view === "overview" && <Overview scan={scan} onFindings={() => setView("findings")} onFiles={() => setView("files")} onHistory={() => setView("history")} onScan={() => void startScan(repository)} busy={busy} />}
          {view === "findings" && <FindingsView scan={scan} />}
          {view === "map" && <RepositoryMap scan={scan} />}
          {view === "search" && <SemanticSearch scan={scan} />}
          {view === "files" && <FilesView scan={scan} />}
          {view === "history" && <HistoryView scans={history} selectedId={scan?.id ?? null} onSelect={(selected) => { setScan(selected); setView("overview"); }} />}
        </>}
        <footer className="main-footer"><span><Shield size={13} /> Source code stays on this machine</span><span>DETECT WITH CODE. VERIFY WITH EVIDENCE.</span></footer>
      </main>
    </div>
    {showOpen && <OpenRepositoryDialog onClose={() => setShowOpen(false)} onOpen={openRepository} settings={settings} />}
  </div>;
}

function Welcome({ onOpen, onDemo, busy, connected }: { onOpen: () => void; onDemo: () => void; busy: boolean; connected: boolean }) {
  return <section className="welcome"><div className="eyebrow"><span className="status-dot" /> YOUR LOCAL ENGINEERING WORKSPACE</div><div className="welcome-symbol"><FolderGit2 size={36} strokeWidth={1.3} /><span className="welcome-symbol-small"><Check size={14} /></span></div><h1>Understand your codebase.<br /><span>Keep it yours.</span></h1><p>Connect a local repository to discover its languages, map its files,<br className="desktop-only" /> and build a reliable foundation for engineering intelligence.</p><div className="welcome-actions"><Button onClick={onOpen} disabled={!connected}><FolderOpen size={16} />Open repository<ArrowRight size={15} /></Button><Button variant="outline" onClick={onDemo} disabled={busy || !connected}>{busy ? <LoaderCircle size={15} className="spin" /> : <Terminal size={15} />}Scan sample repository</Button></div><span className="welcome-hint">No account. No uploads. No cloud dependency.</span><div className="pipeline">{[{ icon: FolderOpen, name: "Discover", detail: "Safe, local file traversal" }, { icon: Code2, name: "Identify", detail: "Languages & tooling" }, { icon: Database, name: "Index", detail: "Content fingerprints" }, { icon: Activity, name: "Inspect", detail: "A persistent repository view" }].map(({ icon: Icon, name, detail }, index) => <div key={name} className="pipeline-step"><div className="pipeline-number">0{index + 1}</div><Icon size={19} /><h3>{name}</h3><p>{detail}</p></div>)}</div><div className="phase-note"><span className="tiny-badge">PHASE 05</span>Static analysis & code evidence<span className="text-muted">Python, JavaScript, and TypeScript AST analysis. Optional local Ollama reasoning.</span></div></section>;
}

function ScanStatus({ scan }: { scan: Scan }) {
  if (isActive(scan)) return <div className="scan-progress" aria-live="polite"><div><div className="scan-progress-title"><LoaderCircle size={16} className="spin" /><strong>{scan.stage || "Preparing repository index"}</strong><span>{scan.progress}%</span></div><div className="progress-track" role="progressbar" aria-label="Indexing progress" aria-valuenow={scan.progress} aria-valuemin={0} aria-valuemax={100}><div style={{ width: `${scan.progress}%` }} /></div></div><p>Indexing runs in the background. Your source files are never executed.</p></div>;
  if (scan.status === "failed") return <div className="error-banner" role="alert"><span><strong>Scan failed.</strong> {scan.error ?? "The index could not be completed. Try running the scan again."}</span></div>;
  return null;
}

function Overview({ scan, onFindings, onFiles, onHistory, onScan, busy }: { scan: Scan | null; onFindings: () => void; onFiles: () => void; onHistory: () => void; onScan: () => void; busy: boolean }) {
  if (!scan || scan.status !== "completed") return <div className="panel waiting-panel"><div className="panel-icon"><Database size={25} /></div><h2>{isActive(scan) ? "Building your repository index" : "Your repository is ready to index"}</h2><p>{isActive(scan) ? "File counts, languages, and tooling will appear when the scan completes." : "Run a scan to discover the structure and composition of this codebase."}</p>{!isActive(scan) && <Button variant="outline" onClick={onScan} disabled={busy}><RefreshCw size={14} />Run scan</Button>}</div>;
  const languages = Object.entries(scan.languages).sort((a, b) => b[1].lines - a[1].lines).map(([name, info], i) => ({ name, ...info, fill: COLORS[i % COLORS.length] }));
  const duration = scan.duration_ms == null ? "—" : scan.duration_ms < 1000 ? `${scan.duration_ms} ms` : `${(scan.duration_ms / 1000).toFixed(2)} s`;
  const stats = [
    { label: "Files indexed", value: formatNumber(scan.total_files), detail: `${formatNumber(scan.skipped_files)} skipped by indexing rules`, icon: Files },
    { label: "Lines indexed", value: formatNumber(scan.total_lines), detail: `${formatBytes(scan.total_bytes)} · includes blanks & comments`, icon: Code2 },
    { label: "Languages", value: formatNumber(languages.length), detail: languages[0] ? `${languages[0].name} is the primary language` : "No supported source files found", icon: Box },
    { label: "Declared dependencies", value: formatNumber(scan.dependency_count), detail: "Read directly from manifests", icon: GitBranch },
  ];
  return <>
    <AnalysisOverview scan={scan} onFindings={onFindings} />
    <div className="metrics-grid">{stats.map(({ label, value, detail, icon: Icon }) => <div className="metric-card" key={label}><div className="metric-label">{label}<Icon size={16} /></div><div className="metric-value">{value}</div><div className="metric-detail">{detail}</div></div>)}</div>
    <div className="overview-grid"><section className="panel language-panel"><div className="panel-heading"><div><h2>Language composition</h2><p>Indexed lines across source, configuration, and documentation</p></div><span className="tiny-badge">{languages.length} LANGUAGES</span></div>{languages.length ? <><div className="language-distribution" aria-label="Language proportions">{languages.map((language) => <span key={language.name} title={`${language.name}: ${formatNumber(language.lines)} lines`} style={{ flexGrow: Math.max(language.lines, 1), background: language.fill }} />)}</div><div className="language-chart" role="img" aria-label={languages.map((language) => `${language.name}: ${language.lines} lines`).join(", ")}><ResponsiveContainer width="100%" height={Math.max(160, Math.min(languages.length, 7) * 35)}><BarChart data={languages.slice(0, 7)} layout="vertical" margin={{ left: 0, right: 45, top: 0, bottom: 0 }} barSize={9}><XAxis type="number" hide /><YAxis type="category" dataKey="name" width={90} axisLine={false} tickLine={false} tick={{ fill: "#b3b9b4", fontSize: 11 }} /><Tooltip cursor={{ fill: "#ffffff03" }} contentStyle={{ background: "#1b201c", border: "1px solid #343b35", color: "#e9ede9", borderRadius: 6 }} formatter={(value) => [`${formatNumber(Number(value))} lines`, "Indexed"]} /><Bar dataKey="lines" radius={[0, 3, 3, 0]}>{languages.slice(0, 7).map((language) => <Cell key={language.name} fill={language.fill} />)}</Bar></BarChart></ResponsiveContainer></div><div className="language-legend">{languages.map((language) => <div key={language.name}><span className="language-dot" style={{ background: language.fill }} /><span>{language.name}</span><strong>{scan.total_lines ? ((language.lines / scan.total_lines) * 100).toFixed(1) : "0"}%</strong></div>)}</div></> : <div className="empty-inline">No recognized source languages were found in this repository.</div>}</section>
      <section className="panel profile-panel"><div className="panel-heading"><div><h2>Repository profile</h2><p>Detected from files and manifests</p></div><Code2 size={17} className="text-muted" /></div><ProfileRow label="Frameworks" values={scan.frameworks} empty="None detected" /><ProfileRow label="Package managers" values={scan.package_managers} empty="None detected" /><ProfileRow label="Test frameworks" values={scan.test_frameworks} empty="None detected" /><div className="profile-row"><span>Infrastructure</span><div className="tag-row"><span className={`detected-tag ${scan.has_docker ? "is-detected" : ""}`}>{scan.has_docker ? <Check size={11} /> : <Circle size={9} />}Docker</span><span className={`detected-tag ${scan.has_ci ? "is-detected" : ""}`}>{scan.has_ci ? <Check size={11} /> : <Circle size={9} />}CI configuration</span></div></div><div className="profile-footer"><LockKeyhole size={14} /><p>Detection reads repository metadata.<br />No scripts or dependencies are executed.</p></div></section></div>
    <div className="overview-bottom"><section className="panel scan-panel"><div className="panel-heading"><div><h2>Latest selected scan</h2><p>A reproducible snapshot of your repository</p></div><span className="complete-badge"><CheckCircle2 size={12} />Complete</span></div><div className="scan-facts"><div><span>COMPLETED</span><strong>{formatDate(scan.completed_at)}</strong></div><div><span>DURATION</span><strong>{duration}</strong></div><div><span>COMMIT</span><strong className="mono">{scan.commit?.slice(0, 8) ?? "Not a Git repository"}</strong></div></div><div className="panel-bottom"><span className="mono text-muted">SCAN {scan.id.slice(0, 8)}</span><button className="text-button" onClick={onHistory}>View scan history<ArrowRight size={14} /></button></div></section><section className="panel index-panel"><div className="panel-heading"><div><h2>Your index is ready</h2><p>Explore what makes up your codebase.</p></div><div className="index-icon"><FolderOpen size={23} strokeWidth={1.4} /></div></div><p className="index-description">Browse {formatNumber(scan.total_files)} indexed files with language detection, line counts, and content fingerprints.</p><Button variant="outline" onClick={onFiles}>Explore repository<ArrowRight size={14} /></Button></section></div>
    {scan.warnings.length > 0 && <section className="panel warning-panel"><h2>Indexing notes <span className="tiny-badge">{scan.warnings.length}</span></h2><ul>{scan.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></section>}

  </>;
}

function ProfileRow({ label, values, empty }: { label: string; values: string[]; empty: string }) {
  return <div className="profile-row"><span>{label}</span><div className="tag-row">{values.length ? values.map((value) => <span className="detected-tag" key={value}>{value}</span>) : <span className="text-muted">{empty}</span>}</div></div>;
}

function FilesView({ scan }: { scan: Scan | null }) {
  const searchRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState(""); const deferredQuery = useDeferredValue(query);
  const [language, setLanguage] = useState(""); const [offset, setOffset] = useState(0);
  const [data, setData] = useState<FilePage | null>(null); const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null); const [selected, setSelected] = useState<IndexedFile | null>(null);
  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      if (event.key === "/" && !event.ctrlKey && !event.metaKey && !(event.target instanceof HTMLInputElement) && !(event.target instanceof HTMLTextAreaElement) && !(event.target instanceof HTMLSelectElement)) { event.preventDefault(); searchRef.current?.focus(); }
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, []);
  useEffect(() => { setOffset(0); setSelected(null); }, [deferredQuery, language, scan?.id]);
  useEffect(() => {
    if (!scan || scan.status !== "completed") return;
    let cancelled = false; setLoading(true); setError(null);
    const params = new URLSearchParams({ q: deferredQuery, language, offset: String(offset), limit: "25" });
    api<FilePage>(`/scans/${scan.id}/files?${params}`).then((result) => { if (!cancelled) setData(result); }).catch((err: unknown) => { if (!cancelled) setError(errorMessage(err)); }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [scan?.id, scan?.status, deferredQuery, language, offset]);
  if (!scan || scan.status !== "completed") return <div className="panel empty-inline">Complete a repository scan to browse its file index.</div>;
  return <><section className="panel files-panel"><div className="files-toolbar"><label className="search-field"><Search size={15} /><input ref={searchRef} aria-label="Search indexed files" placeholder="Search files by path…" value={query} onChange={(event) => setQuery(event.target.value)} /><kbd>/</kbd></label><select aria-label="Filter by language" className="filter-select" value={language} onChange={(event) => setLanguage(event.target.value)}><option value="">All languages</option>{Object.keys(scan.languages).sort().map((name) => <option key={name}>{name}</option>)}</select><span className="files-count">{loading ? "Loading…" : `${formatNumber(data?.total ?? 0)} files`}</span></div>{error && <div className="error-banner" role="alert">{error}</div>}<div className="table-scroll"><table className="file-table"><thead><tr><th>FILE PATH</th><th>LANGUAGE</th><th className="numeric">LINES</th><th className="numeric">SIZE</th><th /></tr></thead><tbody>{data?.items.map((file) => <tr key={file.id} className={selected?.id === file.id ? "selected-row" : ""}><td><button className="file-link" onClick={() => setSelected(file)}><FileCode2 size={15} /><span>{file.path}</span></button></td><td><span className="language-pill">{file.language}</span></td><td className="numeric mono">{formatNumber(file.lines)}</td><td className="numeric mono text-muted">{formatBytes(file.size_bytes)}</td><td><button aria-label={`Inspect ${file.path}`} className="inspect-button" onClick={() => setSelected(file)}><ChevronRight size={14} /></button></td></tr>)}</tbody></table>{!loading && !data?.items.length && <div className="empty-inline"><Search size={22} /><p>No files match these filters.</p></div>}</div><div className="table-pagination"><span>{data?.total ? `${offset + 1}–${Math.min(offset + 25, data.total)} of ${formatNumber(data.total)}` : "0 files"}</span><div><Button variant="ghost" size="sm" disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - 25))}><ArrowLeft size={14} />Previous</Button><Button variant="ghost" size="sm" disabled={!data || offset + 25 >= data.total || loading} onClick={() => setOffset(offset + 25)}>Next<ArrowRight size={14} /></Button></div></div></section>{selected && <section className="panel file-inspector"><div className="panel-heading"><div><h2><FileCode2 size={16} />File metadata</h2><p className="mono">{selected.path}</p></div><Button variant="ghost" size="icon" onClick={() => setSelected(null)} aria-label="Close file details"><X size={16} /></Button></div><div className="inspector-grid"><div><span>LANGUAGE</span><strong>{selected.language}</strong></div><div><span>LINES</span><strong>{formatNumber(selected.lines)}</strong></div><div><span>SIZE</span><strong>{formatBytes(selected.size_bytes)}</strong></div></div><label>SHA-256 CONTENT FINGERPRINT</label><code className="file-hash">{selected.sha256}</code><p className="text-muted">This index stores metadata and a content fingerprint. Source code is not stored in the database.</p><CodePanel scanId={scan.id} path={selected.path} /></section>}</>;
}

function HistoryView({ scans, selectedId, onSelect }: { scans: Scan[]; selectedId: string | null; onSelect: (scan: Scan) => void }) {
  return <section className="panel history-panel"><div className="panel-heading"><div><h2>Scan runs</h2><p>Historical indexes for the selected repository</p></div><span className="tiny-badge">{scans.length} RUNS</span></div>{!scans.length ? <div className="empty-inline">No scans yet. Run a scan to create your first snapshot.</div> : <div className="table-scroll"><table className="history-table"><thead><tr><th>SCAN</th><th>STARTED</th><th>STATUS</th><th>FILES</th><th>LINES</th><th>DURATION</th><th /></tr></thead><tbody>{scans.map((item) => <tr key={item.id} className={selectedId === item.id ? "selected-row" : ""}><td className="mono">{item.id.slice(0, 8)}</td><td>{formatDate(item.started_at)}</td><td><span className={`status-pill status-${item.status}`}>{item.status === "completed" ? <Check size={11} /> : item.status === "failed" ? <X size={11} /> : <LoaderCircle className="spin" size={11} />}{item.status}</span></td><td className="mono">{item.status === "completed" ? formatNumber(item.total_files) : "—"}</td><td className="mono">{item.status === "completed" ? formatNumber(item.total_lines) : "—"}</td><td className="mono text-muted">{item.duration_ms == null ? "—" : `${(item.duration_ms / 1000).toFixed(2)} s`}</td><td><Button variant="ghost" size="sm" onClick={() => onSelect(item)}>Inspect<ArrowRight size={13} /></Button></td></tr>)}</tbody></table></div>}</section>;
}

function Privacy({ settings, health }: { settings: Settings | null; health: { status: string; database: string; version: string } | null }) {
  return <><div className="page-heading"><div><div className="eyebrow">YOUR MACHINE. YOUR CONTROL.</div><h1>Settings & privacy</h1><p>A transparent view of how SENTINEL accesses your repository.</p></div><span className="local-badge"><LockKeyhole size={12} />LOCAL BY DEFAULT</span></div><section className="panel privacy-hero"><div className="privacy-icon"><Shield size={27} strokeWidth={1.5} /></div><div><h2>What leaves your machine?</h2><p className="privacy-answer">{settings && !settings.source_upload && !settings.telemetry ? "Nothing." : "Engine configuration unavailable."}</p><p>Repository indexing runs locally. The interface connects only to your configured SENTINEL API.</p></div></section><div className="privacy-grid"><section className="panel"><div className="panel-heading"><div><h2>Data & inference</h2><p>Current capabilities and network behavior</p></div></div><SettingRow label="Source code upload" value={settings ? (settings.source_upload ? "Enabled" : "Disabled") : "Unavailable"} /><SettingRow label="Telemetry" value={settings ? (settings.telemetry ? "Enabled" : "Disabled") : "Unavailable"} /><SettingRow label="AI inference" value={settings ? (settings.ai_enabled ? "Available via local Ollama" : "Not enabled") : "Unavailable"} /><SettingRow label="Repository execution" value="Never executed during indexing" /><SettingRow label="Stored data" value="Metadata, opinions, vectors & patch backups" /></section><section className="panel"><div className="panel-heading"><div><h2>Local engine</h2><p>Connection and filesystem boundaries</p></div></div><SettingRow label="API connection" value={health ? "Connected" : "Unavailable"} /><SettingRow label="Database" value={health?.database ?? "Unavailable"} /><SettingRow label="Engine version" value={health?.version ?? "Unavailable"} /><div className="roots-setting"><span>ALLOWED REPOSITORY ROOTS</span>{settings?.allowed_roots.map((root) => <code key={root}><Folder size={13} />{root}</code>)}<p>Only folders within these configured roots can be opened. Configure SENTINEL_ALLOWED_ROOTS on the backend to add a trusted location.</p></div></section></div></>;
}

function SettingRow({ label, value }: { label: string; value: string }) {
  return <div className="setting-row"><span>{label}</span><strong>{value}</strong></div>;
}

function OpenRepositoryDialog({ onClose, onOpen, settings }: { onClose: () => void; onOpen: (path: string, ignores: string[]) => Promise<void>; settings: Settings | null }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [path, setPath] = useState(""); const [ignores, setIgnores] = useState("");
  const [directory, setDirectory] = useState<Directory | null>(null); const [browsing, setBrowsing] = useState(false);
  const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null);
  useEffect(() => { dialogRef.current?.showModal(); }, []);
  async function browse(nextPath?: string) {
    setBrowsing(true); setError(null);
    try { const result = await api<Directory>(`/browse${nextPath ? `?path=${encodeURIComponent(nextPath)}` : ""}`); setDirectory(result); setPath(result.path); }
    catch (err) { setError(errorMessage(err)); }
    finally { setBrowsing(false); }
  }
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!path.trim()) return;
    setBusy(true); setError(null);
    try { await onOpen(path.trim(), ignores.split("\n").map((item) => item.trim()).filter(Boolean)); }
    catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }
  return <dialog className="open-dialog" ref={dialogRef} onCancel={(event) => { event.preventDefault(); if (!busy) onClose(); }} onClick={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }} aria-labelledby="open-title"><div className="dialog-heading"><div className="dialog-icon"><FolderOpen size={23} /></div><Button variant="ghost" size="icon" onClick={onClose} disabled={busy} aria-label="Close repository picker"><X size={18} /></Button></div><h2 id="open-title">Open a repository</h2><p className="dialog-description">Choose a local folder. SENTINEL indexes your files without running repository code.</p><form onSubmit={(event) => void submit(event)}><label htmlFor="repository-path">REPOSITORY PATH</label><div className="path-input-row"><input id="repository-path" autoFocus placeholder={settings?.allowed_roots[0] ?? "Absolute path to your repository"} value={path} onChange={(event) => setPath(event.target.value)} disabled={busy} required /><Button type="button" variant="outline" onClick={() => void browse(path || undefined)} disabled={busy || browsing}>{browsing ? <LoaderCircle size={15} className="spin" /> : <Folder size={15} />}Browse</Button></div>{directory && <div className="directory-browser"><div className="directory-current"><button type="button" aria-label="Parent directory" disabled={!directory.parent || browsing} onClick={() => void browse(directory.parent ?? undefined)}><ArrowLeft size={14} /></button><span title={directory.path}>{directory.path}</span></div>{directory.roots.length > 1 && <select aria-label="Allowed root" className="root-select" onChange={(event) => void browse(event.target.value)} value=""><option value="" disabled>Switch allowed root…</option>{directory.roots.map((root) => <option key={root} value={root}>{root}</option>)}</select>}<div className="directory-list">{directory.directories.length ? directory.directories.map((item) => <button type="button" key={item.path} onClick={() => void browse(item.path)} disabled={browsing}><Folder size={15} /><span>{item.name}</span><ChevronRight size={13} /></button>) : <p>No subdirectories. You can select this folder.</p>}</div>{directory.truncated && <p className="text-muted">Large folder: showing a limited listing. Enter the full folder path to select another directory.</p>}</div>}<details className="ignore-details"><summary>Custom ignore patterns <span>Optional</span></summary><label htmlFor="ignore-patterns">ONE GITIGNORE-STYLE PATTERN PER LINE</label><textarea id="ignore-patterns" placeholder={"generated/\n*.min.js"} value={ignores} onChange={(event) => setIgnores(event.target.value)} disabled={busy} /><p>Build outputs, dependency folders, binaries, and repository ignore rules are excluded automatically.</p></details>{error && <div className="dialog-error" role="alert">{error}</div>}<div className="dialog-footer"><span><LockKeyhole size={12} />Read-only discovery</span><Button type="submit" disabled={busy || !path.trim()}>{busy ? <LoaderCircle size={14} className="spin" /> : <ArrowRight size={14} />}{busy ? "Opening repository…" : "Open & scan"}</Button></div></form></dialog>;
}


