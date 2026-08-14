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
      message="Elige una sesión ya analizada. La carpeta raíz analizada nunca se mueve." />

    <AlertBox v-else-if="gateBlocked" variant="warning" title="Hace falta re-analizar">
      {{ gateReason }}
      <a class="font-medium underline" :href="`/analysis?root=${encodeURIComponent(sessionRoot)}`">
        Vuelve a analizar esta carpeta
      </a> y elige la sesión nueva para continuar.
    </AlertBox>

    <template v-else-if="sessionId">
      <!-- sub-paso 1: el patrón -->
      <div class="card space-y-4">
        <div>
          <p class="font-semibold text-slate-700">1 · Patrón de carpetas</p>
          <p class="mt-1 text-xs text-slate-600">
            Un único patrón para todo el análisis. Los archivos se agrupan por fecha
            <b>dentro de su carpeta raíz</b>: se considera raíz la carpeta que no es
            solo una fecha (p. ej. <code>vacaciones 2009</code>), y esa carpeta se
            conserva. Las subcarpetas de fecha pura (<code>2009/08/02</code>) se
            sustituyen por el patrón elegido.
          </p>
          <p class="mt-1 text-xs text-slate-500">
            Ejemplo con <code>AAAA/MM</code>:
            <span class="font-mono">vacaciones 2009/2009/08/02/IMG.jpg</span> →
            <span class="font-mono">vacaciones 2009/2009/08/IMG.jpg</span>
          </p>
        </div>

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

        <div class="flex flex-wrap items-center gap-3">
          <button class="btn-primary" :disabled="!layout || loadingPreview" @click="showResult">
            <LoadingSpinner v-if="loadingPreview" label="Calculando…" />
            <span v-else>Ver cómo queda</span>
          </button>
          <span v-if="stale" class="text-xs text-amber-700">
            El patrón ha cambiado: pulsa «Ver cómo queda» para recalcular.
          </span>
        </div>

        <AlertBox v-if="previewError" variant="error" :message="previewError" />
      </div>

      <!-- sub-paso 2: el árbol resultante (solo lectura) -->
      <div v-if="preview" class="card" :class="{ 'opacity-50': stale }">
        <StructurePreviewTree :root="sessionRoot" :preview="preview" />
      </div>

      <div v-if="preview && !stale" class="card space-y-4">
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
            <span>Confirmo que quiero mover los archivos tal y como se muestra arriba.</span>
          </label>
        </template>

        <button class="btn-primary" :class="{ 'btn-danger': !dryRun }"
                :disabled="running || (!dryRun && !confirmReal)" @click="run">
          <LoadingSpinner v-if="running" label="Iniciando…" />
          <span v-else>{{ dryRun ? 'Simular reorganización' : 'Ejecutar reorganización real' }}</span>
        </button>

        <AlertBox v-if="error" variant="error" :message="error" />
      </div>

      <AnalysisProgress v-if="runId" kind="run" :id="runId" :key="runId" @done="onRunDone" />

      <ReorganizeResults v-if="finishedRunId" :run-id="finishedRunId" :key="'res-' + finishedRunId" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { api, ApiError } from '../api/client';
import type {
  DateSource, LayoutPreset, ProgressEvent, ReorganizePreviewResult, SessionSummary,
} from '../types/api';
import AlertBox from './AlertBox.vue';
import AnalysisProgress from './AnalysisProgress.vue';
import LoadingSpinner from './LoadingSpinner.vue';
import ReorganizeResults from './ReorganizeResults.vue';
import StructurePreviewTree from './StructurePreviewTree.vue';

const sessions = ref<SessionSummary[]>([]);
const sessionId = ref(0);
const gateBlocked = ref(false);
const gateReason = ref('');

const presets = ref<LayoutPreset[]>([]);
const layout = ref('AAAA/MM');
const dateSource = ref<DateSource>('session');

const preview = ref<ReorganizePreviewResult | null>(null);
const loadingPreview = ref(false);
const previewError = ref('');
// Firma del patrón con el que se calculó la preview: si cambia, la vista queda
// desactualizada y no se puede lanzar un run contra algo que no se ha visto.
const previewKey = ref('');

const dryRun = ref(true);
const confirmReal = ref(false);
const running = ref(false);
const runId = ref('');
const finishedRunId = ref('');
const error = ref('');

const sessionRoot = computed(() =>
  sessions.value.find((s) => s.id === sessionId.value)?.root || '');
const currentKey = computed(() => `${sessionId.value}|${layout.value}|${dateSource.value}`);
const stale = computed(() => !!preview.value && previewKey.value !== currentKey.value);

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
  preview.value = null;
  previewError.value = '';
  gateBlocked.value = false;
  if (!sessionId.value) return;
  try {
    const gate = await api.getReorganizeGate(sessionId.value);
    gateBlocked.value = gate.blocked;
    gateReason.value = gate.reason || '';
  } catch { /* ignore */ }
}

async function showResult() {
  if (!sessionId.value || gateBlocked.value) return;
  loadingPreview.value = true;
  previewError.value = '';
  const key = currentKey.value;
  try {
    preview.value = await api.getReorganizePreview({
      session_id: sessionId.value,
      base_mode: 'auto',          // la raíz se detecta sola (carpeta con texto)
      layout: layout.value,
      date_source: dateSource.value,
    });
    previewKey.value = key;
  } catch (e) {
    preview.value = null;
    previewError.value = e instanceof ApiError ? e.message : String(e);
  } finally {
    loadingPreview.value = false;
  }
}

// cambiar de modo real->dry-run obliga a re-confirmar
watch(dryRun, () => { confirmReal.value = false; });

async function run() {
  running.value = true;
  error.value = '';
  runId.value = '';
  finishedRunId.value = '';
  try {
    const res = await api.startReorganize({
      session_id: sessionId.value,
      dry_run: dryRun.value,
      confirm_real_write: !dryRun.value && confirmReal.value,
      base_mode: 'auto',
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
