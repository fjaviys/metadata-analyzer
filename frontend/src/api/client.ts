// Cliente de la API del Metadata Analyzer (REST + WebSocket).

import type {
  AnalysisRequest, AnalysisStarted, AnalyzedFile, ConnectionTestRequest,
  ConnectionTestResult, CorrectionRequest, CorrectionStarted, FolderNode,
  ProgressEvent, SessionSummary,
} from '../types/api';

const API_BASE = (import.meta.env.PUBLIC_API_BASE_URL as string) || '/api';
const WS_BASE = (import.meta.env.PUBLIC_WS_BASE_URL as string) || '';

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
    request<{ allowed_media_roots: string[]; exiftool_available: boolean }>('/config/roots'),

  testConnection: (body: ConnectionTestRequest) =>
    request<ConnectionTestResult>('/config/test', {
      method: 'POST', body: JSON.stringify(body),
    }),

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

  getCorrectionRun: (runId: string) =>
    request<{ run_id: string; stats: Record<string, number>;
              corrections: Array<Record<string, unknown>> }>(`/corrections/${runId}`),
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
