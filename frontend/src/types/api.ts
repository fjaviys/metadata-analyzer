// Tipos compartidos con la API del backend.

export type ConnectionType = 'local' | 'immich' | 'omv';

export interface ConnectionTestRequest {
  type: ConnectionType;
  root_path?: string;
  base_url?: string;
  api_key?: string;
  username?: string;
  password?: string;
}

export interface ConnectionTestResult {
  ok: boolean;
  message: string;
  details?: Record<string, unknown>;
}

export interface AnalysisRequest {
  root_path: string;
  connection_type?: ConnectionType;
  max_depth?: number | null;
  detect_duplicates?: boolean;
  include_extensions?: string[] | null;
  exclude_extensions?: string[] | null;
}

export interface BrowseEntry {
  name: string;
  path: string;
}

export interface BrowseResult {
  path: string;
  parent: string | null;
  dirs: BrowseEntry[];
}

export interface FormatCatalog {
  image: string[];
  raw: string[];
  video: string[];
}

export interface AnalysisStarted {
  session_id: number;
  status: string;
  root_path: string;
}

export interface SessionSummary {
  id: number;
  root: string;
  status: string;
  started_at?: string;
  finished_at?: string;
  total_files: number;
  photos: number;
  videos: number;
  with_exif_date: number;
  without_exif_date: number;
  corrupt: number;
  inconsistent: number;
  needs_correction: number;
  duplicates_count: number;
  report_path?: string | null;
}

export interface AnalyzedFile {
  id: number;
  path: string;
  folder_l1: string;
  folder_l2: string;
  media_type: string;
  exif_date?: string | null;
  exif_date_tag?: string | null;
  has_exif_date: number;
  is_corrupt: number;
  filename_date?: string | null;
  path_date?: string | null;
  inconsistencies: string[];
  needs_correction: number;
  recommended_date?: string | null;
  recommended_precision?: string | null;
  recommended_source?: string | null;
}

export interface FolderNode {
  folder: string;
  total: number;
  needs: number;
  children?: FolderNode[];
}

export interface CorrectionRequest {
  session_id: number;
  subfolders?: string[];
  dry_run: boolean;
  confirm_real_write?: boolean;
}

export interface CorrectionStarted {
  run_id: string;
  dry_run: boolean;
  total_candidates: number;
  status: string;
}

export interface CorrectionRow {
  id: number;
  path: string;
  dry_run: number;
  correction_type: string;      // set_date | cleanup | skip
  tag?: string | null;
  original_value?: string | null;
  new_value?: string | null;
  precision?: string | null;
  source?: string | null;
  status: string;               // dry-run | verified | failed | reverted | skipped
  verified: number;
  error?: string | null;
  created_at?: string;
}

export interface ProgressEvent {
  phase?: 'analysis' | 'correction';
  type?: string;
  status?: string;
  current_file?: string;
  processed?: number;
  total?: number;
  percent?: number;
  inconsistencies?: number;
  needs_correction?: number;
  verified?: number;
  failed?: number;
  skipped?: number;
  reverted?: number;
  applied?: number;
  planned?: number;
  aborted?: boolean;
  abort_reason?: string | null;
  dry_run?: boolean;
  error?: string;
  report_path?: string | null;
  duplicates?: number;
}
