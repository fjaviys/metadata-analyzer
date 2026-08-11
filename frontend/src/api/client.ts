// Cliente de la API del Metadata Analyzer (REST + WebSocket).

import type {
  AnalysisRequest, AnalysisStarted, AnalyzedFile, BrowseResult, ConnectionTestRequest,
  ConnectionTestResult, CorrectionRequest, CorrectionRow, CorrectionStarted, FolderNode,
  FormatCatalog, LayoutPreset, ProgressEvent, ReorganizeMove, ReorganizeRequest,
  ReorganizeRunSummary, ReorganizeStarted, SessionSummary,
} from '../types/api';

// Config de runtime inyectada por el servidor (window.__MA_CONFIG__ en MainLayout).
// Permite que una imagen ya construida apunte a cualquier backend sin recompilar.
// Prioridad: runtime (window) > variable de build (PUBLIC_*) > valor relativo.
interface RuntimeConfig { apiBase?: string; wsBase?: string }
function runtimeConfig(): RuntimeConfig {
  if (typeof window !== 'undefined' && (window as any).__MA_CONFIG__) {
    return (window as any).__MA_CONFIG__ as RuntimeConfig;
  }
  return {};
}

const API_BASE =
  runtimeConfig().apiBase || (import.meta.env.PUBLIC_API_BASE_URL as string) || '/api';
const WS_BASE =
  runtimeConfig().wsBase || (import.meta.env.PUBLIC_WS_BASE_URL as string) || '';

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || body.error || detail;
    } catch { /* ignore */ }
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as T;
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
    this.name = 'ApiError';
  }
}

export const api = {
  // --- config / conexiones ---
  getRoots: () =>
    request<{ allowed_media_roots: string[]; exiftool_available: boolean;
              detector_version: number }>('/config/roots'),

  testConnection: (body: ConnectionTestRequest) =>
    request<ConnectionTestResult>('/config/test', {
      method: 'POST', body: JSON.stringify(body),
    }),

  browse: (path: string) =>
    request<BrowseResult>(`/config/browse?path=${encodeURIComponent(path)}`),

  getFormats: () => request<FormatCatalog>('/config/formats'),

  // --- análisis ---
  startAnalysis: (body: AnalysisRequest) =>
    request<AnalysisStarted>('/analysis', { method: 'POST', body: JSON.stringify(body) }),

  listSessions: () =>
    request<{ sessions: SessionSummary[] }>('/analysis/sessions'),

  getSession: (id: number) =>
    request<SessionSummary>(`/analysis/sessions/${id}`),

  // --- resultados ---
  getSummary: (id: number) => request<SessionSummary>(`/results/${id}/summary`),

  getFiles: (id: number, opts: { needs_correction?: boolean; folder?: string;
                                  limit?: number; offset?: number } = {}) => {
    const q = new URLSearchParams();
    if (opts.needs_correction !== undefined) q.set('needs_correction', String(opts.needs_correction));
    if (opts.folder) q.set('folder', opts.folder);
    if (opts.limit) q.set('limit', String(opts.limit));
    if (opts.offset) q.set('offset', String(opts.offset));
    return request<{ total: number; count: number; offset: number; files: AnalyzedFile[] }>(
      `/results/${id}/files?${q.toString()}`);
  },

  getTree: (id: number) => request<{ tree: FolderNode[] }>(`/results/${id}/tree`),

  getDuplicates: (id: number) =>
    request<{ duplicates: Array<Record<string, unknown>> }>(`/results/${id}/duplicates`),

  reportUrl: (id: number) => `${API_BASE}/results/${id}/report`,

  // --- correcciones ---
  startCorrection: (body: CorrectionRequest) =>
    request<CorrectionStarted>('/corrections', { method: 'POST', body: JSON.stringify(body) }),

  getPatternPresets: () =>
    request<{ presets: Array<{ key: string; label: string; pattern: string; source: string }> }>(
      '/corrections/pattern-presets'),

  createOverride: (body: { session_id: number; folder: string; pattern: string; source?: string }) =>
    request<{ id: number; folder: string; pattern: string; source: string; affected: number;
              rescued: number;
              preview: Array<{ path: string; old: string | null; new: string;
                               precision: string; rescued: boolean }> }>(
      '/corrections/overrides', { method: 'POST', body: JSON.stringify(body) }),

  listOverrides: (sessionId: number) =>
    request<{ overrides: Array<{ id: number; folder: string; pattern: string; source: string }> }>(
      `/corrections/overrides?session_id=${sessionId}`),

  deleteOverride: (id: number) =>
    request<{ deleted: number }>(`/corrections/overrides/${id}`, { method: 'DELETE' }),

  getDateOptions: (sessionId: number, path: string) =>
    request<{ path: string; media_type: string; exif: string | null;
              recommended: string | null; needs_correction: boolean;
              options: Array<{ source: string; label: string; value: string;
                               precision: string | null }> }>(
      `/corrections/date-options?session_id=${sessionId}&path=${encodeURIComponent(path)}`),

  setFileOverride: (body: { session_id: number; path: string; kind: string;
                            value?: string; precision?: string }) =>
    request<{ id: number; path: string; kind: string; new: string | null; precision: string | null }>(
      '/corrections/file-overrides', { method: 'POST', body: JSON.stringify(body) }),

  listFileOverrides: (sessionId: number) =>
    request<{ file_overrides: Array<{ id: number; path: string; kind: string;
                                      value: string | null; precision: string | null }> }>(
      `/corrections/file-overrides?session_id=${sessionId}`),

  deleteFileOverride: (sessionId: number, path: string) =>
    request<{ deleted: string }>(
      `/corrections/file-overrides?session_id=${sessionId}&path=${encodeURIComponent(path)}`,
      { method: 'DELETE' }),

  getCorrectionRun: (runId: string, opts: { only_changes?: boolean;
                                            limit?: number; offset?: number } = {}) => {
    const q = new URLSearchParams();
    if (opts.only_changes) q.set('only_changes', 'true');
    if (opts.limit) q.set('limit', String(opts.limit));
    if (opts.offset) q.set('offset', String(opts.offset));
    return request<{
      run_id: string; stats: Record<string, number>; total: number; count: number;
      offset: number; corrections: CorrectionRow[];
    }>(`/corrections/${runId}?${q.toString()}`);
  },

  // --- reorganización (Fase 2) ---
  startReorganize: (body: ReorganizeRequest) =>
    request<ReorganizeStarted>('/reorganize', { method: 'POST', body: JSON.stringify(body) }),

  getLayoutPresets: () =>
    request<{ presets: LayoutPreset[] }>('/reorganize/layout-presets'),

  listReorganizeRuns: (sessionId: number) =>
    request<{ runs: ReorganizeRunSummary[] }>(`/reorganize/runs?session_id=${sessionId}`),

  getReorganizeRun: (runId: string, opts: { only_changes?: boolean;
                                            limit?: number; offset?: number } = {}) => {
    const q = new URLSearchParams();
    if (opts.only_changes) q.set('only_changes', 'true');
    if (opts.limit) q.set('limit', String(opts.limit));
    if (opts.offset) q.set('offset', String(opts.offset));
    return request<{
      run_id: string; stats: Record<string, number>; total: number; count: number;
      offset: number; moves: ReorganizeMove[];
    }>(`/reorganize/${runId}?${q.toString()}`);
  },

  undoReorganize: (runId: string) =>
    request<{ undone: number; failed: Array<{ path: string; error: string }> }>(
      `/reorganize/${runId}/undo`, { method: 'POST' }),
};

// --- WebSocket de progreso ---

function wsUrl(path: string): string {
  if (WS_BASE) return `${WS_BASE}${path}`;
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${location.host}${path}`;
}

export interface ProgressSocket {
  close: () => void;
}

export function subscribeProgress(
  kind: 'session' | 'run',
  id: string | number,
  onEvent: (ev: ProgressEvent) => void,
  onClose?: () => void,
): ProgressSocket {
  const url = wsUrl(`/ws/progress/${kind}/${id}`);
  let closed = false;
  let ws: WebSocket;

  const connect = () => {
    ws = new WebSocket(url);
    ws.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data) as ProgressEvent;
        if (data.type === 'ping') return;
        onEvent(data);
        if (data.status === 'completed' || data.status === 'failed') {
          closed = true;
          ws.close();
        }
      } catch { /* ignore */ }
    };
    ws.onclose = () => {
      if (!closed) {
        // reconexión simple tras breve espera
        setTimeout(() => { if (!closed) connect(); }, 1500);
      } else {
        onClose?.();
      }
    };
    ws.onerror = () => ws.close();
  };

  connect();
  return { close: () => { closed = true; ws?.close(); } };
}
