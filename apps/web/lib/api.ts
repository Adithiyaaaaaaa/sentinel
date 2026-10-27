export type Scan = {
  id: string; repository_id: string; status: "queued" | "running" | "completed" | "failed";
  progress: number; stage: string; started_at: string | null; completed_at: string | null;
  duration_ms: number | null; total_files: number; total_lines: number; total_bytes: number;
  skipped_files: number; languages: Record<string, { files: number; lines: number }>;
  frameworks: string[]; package_managers: string[]; test_frameworks: string[];
  has_docker: boolean; has_ci: boolean; branch: string | null; commit: string | null;
  dependency_count: number; warnings: string[]; error: string | null;
  analysis_summary: Partial<AnalysisSummary>;
};
export type Repository = { id: string; name: string; path: string; created_at: string; latest_scan: Scan | null };
export type IndexedFile = { id: string; path: string; language: string; lines: number; size_bytes: number; sha256: string };
export type FilePage = { items: IndexedFile[]; total: number; offset: number; limit: number };
export type Settings = { allowed_roots: string[]; demo_path: string; telemetry: boolean; source_upload: boolean; ai_enabled: boolean; phase: number };
export type Directory = { path: string; parent: string | null; directories: { name: string; path: string }[]; roots: string[]; truncated?: boolean };

export type AnalysisSummary = {
  ruleset_version: string; supported_languages: string[]; parsed_files: number; failed_files: number;
  unsupported_files: number; unprocessed_files: number; entity_count: number; finding_count: number;
  severity_counts: Record<string, number>; rule_count: number; scope: string;
};
export type FindingStatus = "open" | "confirmed" | "false_positive" | "fixed" | "ignored";
export type Finding = {
  id: string; scan_id: string; rule_id: string; fingerprint: string; file: string; language: string;
  line: number; end_line: number; symbol: string; title: string; severity: string; category: string;
  cwe: string | null; owasp: string | null; confidence: number; verdict: string; status: FindingStatus;
  risk: number; risk_basis: {formula: string; severity_weight: number; confidence: number; meaning: string};
  explanation: string; impact: string; exploitability: string; recommendation: string; detected_at: string;
  evidence: {line: number; end_line: number; kind: string; description: string}[];
};
export type FindingPage = {items: Finding[]; total: number; offset: number; limit: number};
export type CodeEntity = {id: string; key: string; file: string; language: string; kind: string; name: string;
  start_line: number; end_line: number; parent: string | null; complexity: number; callees: string[]; features: string[]; dependencies: string[]};
export type SourceExcerpt = {path: string; language: string; sha256: string; verified: boolean; start_line: number;
  end_line: number; total_lines: number; lines: {number: number; text: string; redacted: boolean; truncated: boolean}[]};

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, { ...init, headers: { "Content-Type": "application/json", ...init?.headers }, cache: "no-store" });
  if (!response.ok) {
    const data: unknown = await response.json().catch(() => null);
    const detail = data && typeof data === "object" && "detail" in data ? (data as { detail: unknown }).detail : null;
    throw new Error(typeof detail === "string" ? detail : `Request failed (${response.status}). Please try again.`);
  }
  return response.json() as Promise<T>;
}

export function formatNumber(value: number) { return new Intl.NumberFormat("en", { maximumFractionDigits: 0 }).format(value); }
export function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}
export function formatDate(value: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}
