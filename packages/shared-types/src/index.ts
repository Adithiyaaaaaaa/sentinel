export type ScanStatus = "queued" | "running" | "completed" | "failed";

export interface LanguageStatistics {
  files: number;
  lines: number;
}

export interface Scan {
  id: string;
  repository_id: string;
  status: ScanStatus;
  progress: number;
  stage: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  total_files: number;
  total_lines: number;
  total_bytes: number;
  skipped_files: number;
  languages: Record<string, LanguageStatistics>;
  frameworks: string[];
  package_managers: string[];
  test_frameworks: string[];
  has_docker: boolean;
  has_ci: boolean;
  branch: string | null;
  commit: string | null;
  dependency_count: number;
  warnings: string[];
  error: string | null;
}

export interface Repository {
  id: string;
  name: string;
  path: string;
  ignore_patterns: string[];
  created_at: string;
  latest_scan: Scan | null;
}

export interface IndexedFile {
  id: string;
  path: string;
  language: string;
  lines: number;
  size_bytes: number;
  sha256: string;
}

export interface FilePage {
  items: IndexedFile[];
  total: number;
  offset: number;
  limit: number;
}

export interface DirectoryListing {
  path: string;
  parent: string | null;
  directories: { name: string; path: string }[];
  roots: string[];
  truncated: boolean;
}

export interface LocalSettings {
  allowed_roots: string[];
  demo_path: string;
  telemetry: false;
  source_upload: false;
  ai_enabled: false;
  phase: 1;
}
