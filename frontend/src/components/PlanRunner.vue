<template>
  <div class="space-y-6">
    <div class="card">
      <label class="label">Sesión de análisis</label>
      <div class="flex gap-2">
        <select v-model.number="sessionId" class="input" @change="load">
          <option :value="0" disabled>Selecciona una sesión…</option>
          <option v-for="s in sessions" :key="s.id" :value="s.id">
            #{{ s.id }} · {{ s.root }} · {{ s.total_files }} archivos
          </option>
        </select>
      </div>
    </div>

    <AlertBox v-if="!sessionId" variant="info"
      message="Elige una sesión ya analizada. Cada carpeta empieza con 'metadatos: actualizar' + 'estructura: mantener' (el comportamiento seguro por defecto)." />

    <template v-else>
      <PatternOverrideEditor :session-id="sessionId" :root="sessionRoot"
                             @changed="changed = true; load()" />

      <div class="card space-y-4">
        <p class="font-semibold text-slate-700">Carpeta base para mover (cuando aplique)</p>
        <div class="flex flex-wrap gap-4 text-sm text-slate-700">
          <label class="flex items-center gap-2">
            <input type="radio" value="auto" v-model="baseMode" /> Quitar subcarpetas de fecha (recomendado)
          </label>
          <label class="flex items-center gap-2">
            <input type="radio" value="root" v-model="baseMode" /> Raíz de la sesión
          </label>
          <label class="flex items-center gap-2">
            <input type="radio" value="manual" v-model="baseMode" /> Carpeta manual
          </label>
        </div>
        <FolderBrowser v-if="baseMode === 'manual'" v-model="baseFolder" label="Carpeta base" />

        <p class="font-semibold text-slate-700">Layout por defecto (carpetas sin patrón propio)</p>
        <div class="flex flex-wrap gap-2">
          <button v-for="p in presets" :key="p.key" type="button"
                  class="rounded-full border px-3 py-1 text-xs"
                  :class="layout === p.layout ? 'border-brand-500 bg-brand-50 text-brand-700'
                                              : 'border-slate-200 text-slate-600 hover:bg-slate-50'"
                  @click="layout = p.layout">
            {{ p.label }}
          </button>
        </div>
        <input v-model="layout" class="input font-mono" placeholder="AAAA/MM" />
      </div>

      <LoadingSpinner v-if="loadingFiles" label="Cargando archivos…" />
      <div v-else class="card">
        <AssignmentTree :session-id="sessionId" :root="sessionRoot" :files="files"
                        :preview="preview" @changed="changed = true; refreshPreview()" />
      </div>

      <AlertBox v-if="changed" variant="info"
        message="Has cambiado decisiones. Vuelve a simular para ver el resultado actualizado." />

      <div class="card space-y-4">
        <div class="flex items-center gap-3">
          <label class="flex items-center gap-2 text-sm font-medium text-slate-700">
            <input type="radio" :value="true" v-model="dryRun" /> Simulación (dry-run)
          </label>
          <label class="flex items-center gap-2 text-sm font-medium text-slate-700">
            <input type="radio" :value="false" v-model="dryRun" /> Aplicar cambios reales
          </label>
        </div>

        <AlertBox v-if="dryRun" variant="info"
          message="Modo simulación: NO se escribe ni se mueve nada. Verás qué cambios se propondrían en ambos ejes." />
        <template v-else>
          <AlertBox variant="warning"
            message="Modo REAL: se corregirán metadatos y/o se moverán archivos según las decisiones del árbol. Backup + verificación en metadatos; movimientos registrados para poder deshacerlos." />
          <label class="flex items-start gap-2 text-sm text-slate-700">
            <input type="checkbox" v-model="confirmReal" class="mt-0.5 rounded border-slate-300" />
            <span>Confirmo que quiero aplicar estos cambios a los archivos seleccionados.</span>
          </label>
        </template>

        <button class="btn-primary" :class="{ 'btn-danger': !dryRun }"
                :disabled="running || (!dryRun && !confirmReal)" @click="run">
          <LoadingSpinner v-if="running" label="Iniciando…" />
          <span v-else>{{ dryRun ? 'Simular' : 'Aplicar cambios reales' }}</span>
        </button>

        <AlertBox v-if="error" variant="error" :message="error" />
      </div>

      <AnalysisProgress v-if="runId" kind="run" :id="runId" :key="runId" @done="onRunDone" />

      <PlanResults v-if="finishedRunId" :run-id="finishedRunId" :key="'res-' + finishedRunId"
                  @changed="changed = true" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { api, ApiError } from '../api/client';
import type {
  AnalyzedFile, BaseMode, LayoutPreset, PlanPreviewResult, ProgressEvent, SessionSummary,
} from '../types/api';
import AlertBox from './AlertBox.vue';
import AnalysisProgress from './AnalysisProgress.vue';
import AssignmentTree from './AssignmentTree.vue';
import FolderBrowser from './FolderBrowser.vue';
import LoadingSpinner from './LoadingSpinner.vue';
import PatternOverrideEditor from './PatternOverrideEditor.vue';
import PlanResults from './PlanResults.vue';

const sessions = ref<SessionSummary[]>([]);
const sessionId = ref(0);
const files = ref<AnalyzedFile[]>([]);
const loadingFiles = ref(false);
const preview = ref<PlanPreviewResult | null>(null);

const baseMode = ref<BaseMode>('auto');
const baseFolder = ref('');
const presets = ref<LayoutPreset[]>([]);
const layout = ref('AAAA/MM');

const dryRun = ref(true);
const confirmReal = ref(false);
const running = ref(false);
const runId = ref('');
const finishedRunId = ref('');
const changed = ref(false);
const error = ref('');

const sessionRoot = computed(() =>
  sessions.value.find((s) => s.id === sessionId.value)?.root || '');

function onRunDone(ev: ProgressEvent) {
  if (ev.status === 'completed') finishedRunId.value = runId.value;
}

onMounted(async () => {
  try {
    sessions.value = (await api.listSessions()).sessions.filter((s) => s.status === 'completed');
  } catch { /* ignore */ }
  try {
    presets.value = (await api.getLayoutPresets()).presets;
  } catch { presets.value = []; }
  const url = new URL(location.href);
  const q = url.searchParams.get('session');
  if (q) { sessionId.value = Number(q); await load(); }
});

async function load() {
  if (!sessionId.value) return;
  loadingFiles.value = true;
  try {
    files.value = (await api.getFiles(sessionId.value, { limit: 5000 })).files;
  } catch { files.value = []; } finally { loadingFiles.value = false; }
  refreshPreview();
}

// --- previsualización (debounced): destino real por archivo/carpeta sin ejecutar nada ---
let previewTimer: ReturnType<typeof setTimeout> | null = null;
function refreshPreview() {
  if (previewTimer) clearTimeout(previewTimer);
  previewTimer = setTimeout(async () => {
    if (!sessionId.value) { preview.value = null; return; }
    try {
      preview.value = await api.getPlanPreview({
        session_id: sessionId.value,
        base_mode: baseMode.value,
        base_folder: baseMode.value === 'manual' ? baseFolder.value : undefined,
        layout: layout.value,
      });
    } catch { preview.value = null; }
  }, 400);
}

watch([baseMode, baseFolder, layout], refreshPreview);

async function run() {
  running.value = true;
  error.value = '';
  runId.value = '';
  finishedRunId.value = '';
  changed.value = false;
  try {
    const res = await api.startPlanRun({
      session_id: sessionId.value,
      dry_run: dryRun.value,
      confirm_real_write: !dryRun.value && confirmReal.value,
      base_mode: baseMode.value,
      base_folder: baseMode.value === 'manual' ? baseFolder.value : undefined,
      layout: layout.value,
    });
    runId.value = res.run_id;
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : String(e);
  } finally {
    running.value = false;
  }
}
</script>
