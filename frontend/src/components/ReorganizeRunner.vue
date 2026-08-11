<template>
  <div class="space-y-6">
    <div class="card">
      <label class="label">Sesión de análisis</label>
      <div class="flex gap-2">
        <select v-model.number="sessionId" class="input" @change="loadTree">
          <option :value="0" disabled>Selecciona una sesión…</option>
          <option v-for="s in sessions" :key="s.id" :value="s.id">
            #{{ s.id }} · {{ s.root }} · {{ s.total_files }} archivos
          </option>
        </select>
      </div>
    </div>

    <AlertBox v-if="!sessionId" variant="info"
      message="Elige una sesión ya analizada. La reorganización mueve archivos según su fecha, sin tocar metadatos." />

    <template v-else>
      <FolderTreeSelector :tree="tree" @update:selected="selected = $event" />

      <div class="card space-y-4">
        <p class="font-semibold text-slate-700">Carpeta base</p>
        <div class="flex flex-wrap gap-4 text-sm text-slate-700">
          <label class="flex items-center gap-2">
            <input type="radio" value="auto" v-model="baseMode" />
            Quitar automáticamente las subcarpetas de fecha (recomendado)
          </label>
          <label class="flex items-center gap-2">
            <input type="radio" value="root" v-model="baseMode" />
            Raíz de la sesión
          </label>
          <label class="flex items-center gap-2">
            <input type="radio" value="manual" v-model="baseMode" />
            Carpeta manual
          </label>
        </div>
        <FolderBrowser v-if="baseMode === 'manual'" v-model="baseFolder"
                       label="Carpeta base" :placeholder="sessionRoot" />
        <p v-if="baseMode === 'auto'" class="text-xs text-slate-500">
          Ejemplo: <code>fotos/2009/08/02/IMG.jpg</code> → carpeta base <code>fotos/</code>.
        </p>
      </div>

      <div class="card space-y-4">
        <p class="font-semibold text-slate-700">Estructura de carpetas destino</p>
        <div class="flex flex-wrap gap-2">
          <button v-for="p in presets" :key="p.key" type="button"
                  class="rounded-full border px-3 py-1 text-xs"
                  :class="layout === p.layout ? 'border-brand-500 bg-brand-50 text-brand-700'
                                              : 'border-slate-200 text-slate-600 hover:bg-slate-50'"
                  @click="layout = p.layout">
            {{ p.label }}
          </button>
        </div>
        <div>
          <label class="label">Patrón personalizado (tokens AAAA/MM/DD)</label>
          <input v-model="layout" class="input font-mono" placeholder="AAAA/MM" />
        </div>
        <p class="text-xs text-slate-500">
          Ejemplo con la fecha 2020-07-02: <code>{{ layoutExample }}</code>
        </p>
      </div>

      <div class="card space-y-4">
        <p class="font-semibold text-slate-700">Fecha a usar</p>
        <div class="flex flex-wrap gap-4 text-sm text-slate-700">
          <label class="flex items-center gap-2">
            <input type="radio" value="session" v-model="dateSource" />
            Fecha de la sesión (recomendada / ya corregida)
          </label>
          <label class="flex items-center gap-2">
            <input type="radio" value="exif_live" v-model="dateSource" />
            Releer el EXIF actual del archivo
          </label>
        </div>
        <p class="text-xs text-slate-500">
          Nunca se fabrica una fecha: un archivo sin fecha fiable se omite y se reporta.
        </p>
      </div>

      <div class="card space-y-4">
        <div class="flex items-center gap-3">
          <label class="flex items-center gap-2 text-sm font-medium text-slate-700">
            <input type="radio" :value="true" v-model="dryRun" /> Simulación (dry-run)
          </label>
          <label class="flex items-center gap-2 text-sm font-medium text-slate-700">
            <input type="radio" :value="false" v-model="dryRun" /> Reorganización real
          </label>
        </div>

        <AlertBox v-if="dryRun" variant="info"
          message="Modo simulación: NO se mueve nada. Verás qué movimientos se propondrían." />
        <template v-else>
          <AlertBox variant="warning"
            message="Modo REAL: se moverán tus archivos a la nueva estructura de carpetas. Cada movimiento queda registrado para poder deshacerlo. Si demasiados archivos fallan, se aborta y se deshace." />
          <label class="flex items-start gap-2 text-sm text-slate-700">
            <input type="checkbox" v-model="confirmReal" class="mt-0.5 rounded border-slate-300" />
            <span>Confirmo que quiero mover los archivos seleccionados a la nueva estructura
              de carpetas.</span>
          </label>
        </template>

        <button class="btn-primary" :class="{ 'btn-danger': !dryRun }"
                :disabled="running || (!dryRun && !confirmReal) || !layout" @click="run">
          <LoadingSpinner v-if="running" label="Iniciando…" />
          <span v-else>{{ dryRun ? 'Simular reorganización' : 'Ejecutar reorganización real' }}</span>
        </button>

        <AlertBox v-if="error" variant="error" :message="error" />
      </div>

      <AnalysisProgress v-if="runId" kind="run" :id="runId" :key="runId"
                        @done="onRunDone" />

      <ReorganizeResults v-if="finishedRunId" :run-id="finishedRunId" :key="'res-' + finishedRunId" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { api, ApiError } from '../api/client';
import type {
  BaseMode, DateSource, FolderNode, LayoutPreset, ProgressEvent, SessionSummary,
} from '../types/api';
import AlertBox from './AlertBox.vue';
import AnalysisProgress from './AnalysisProgress.vue';
import FolderBrowser from './FolderBrowser.vue';
import FolderTreeSelector from './FolderTreeSelector.vue';
import LoadingSpinner from './LoadingSpinner.vue';
import ReorganizeResults from './ReorganizeResults.vue';

const sessions = ref<SessionSummary[]>([]);
const sessionId = ref(0);
const tree = ref<FolderNode[]>([]);
const selected = ref<string[]>([]);

const baseMode = ref<BaseMode>('auto');
const baseFolder = ref('');
const presets = ref<LayoutPreset[]>([]);
const layout = ref('AAAA/MM');
const dateSource = ref<DateSource>('session');

const dryRun = ref(true);
const confirmReal = ref(false);
const running = ref(false);
const runId = ref('');
const finishedRunId = ref('');
const error = ref('');

const sessionRoot = computed(() =>
  sessions.value.find((s) => s.id === sessionId.value)?.root || '');

const layoutExample = computed(() => {
  const dt = { y: 2020, m: '07', d: '02' };
  return layout.value
    .replace(/AAAA/g, String(dt.y)).replace(/AA/g, String(dt.y).slice(-2))
    .replace(/MM/g, dt.m).replace(/DD/g, dt.d) || '—';
});

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
  if (q) { sessionId.value = Number(q); await loadTree(); }
});

async function loadTree() {
  if (!sessionId.value) return;
  try {
    tree.value = (await api.getTree(sessionId.value)).tree;
  } catch { tree.value = []; }
}

async function run() {
  running.value = true;
  error.value = '';
  runId.value = '';
  finishedRunId.value = '';
  try {
    const res = await api.startReorganize({
      session_id: sessionId.value,
      subfolders: selected.value,
      dry_run: dryRun.value,
      confirm_real_write: !dryRun.value && confirmReal.value,
      base_mode: baseMode.value,
      base_folder: baseMode.value === 'manual' ? baseFolder.value : undefined,
      layout: layout.value,
      date_source: dateSource.value,
    });
    runId.value = res.run_id;
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : String(e);
  } finally {
    running.value = false;
  }
}
</script>
