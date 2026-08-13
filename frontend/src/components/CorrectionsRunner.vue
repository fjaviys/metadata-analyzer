<template>
  <div class="space-y-6">
    <div class="card">
      <label class="label">Sesión de análisis</label>
      <div class="flex gap-2">
        <select v-model.number="sessionId" class="input" @change="load">
          <option :value="0" disabled>Selecciona una sesión…</option>
          <option v-for="s in sessions" :key="s.id" :value="s.id">
            #{{ s.id }} · {{ s.root }} · {{ s.needs_correction }} a corregir
          </option>
        </select>
      </div>
    </div>

    <AlertBox v-if="!sessionId" variant="info"
      message="Elige una sesión ya analizada. Recuerda: el análisis es obligatorio antes de corregir." />

    <template v-else>
      <LoadingSpinner v-if="loadingFiles" label="Cargando archivos…" />
      <div v-else class="card">
        <MetadataTree :session-id="sessionId" :root="sessionRoot" :files="files"
                      @changed="changed = true" />
      </div>

      <AlertBox v-if="changed" variant="info"
        message="Has cambiado decisiones. Vuelve a simular para ver el resultado actualizado." />

      <div class="card space-y-4">
        <div class="flex items-center gap-3">
          <label class="flex items-center gap-2 text-sm font-medium text-slate-700">
            <input type="radio" :value="true" v-model="dryRun" /> Simulación (dry-run)
          </label>
          <label class="flex items-center gap-2 text-sm font-medium text-slate-700">
            <input type="radio" :value="false" v-model="dryRun" /> Corrección real
          </label>
        </div>

        <AlertBox v-if="dryRun" variant="info"
          message="Modo simulación: NO se escribe nada. Verás qué cambios se propondrían." />
        <template v-else>
          <AlertBox variant="warning"
            message="Modo REAL: se escribirá sobre tus archivos. Antes de cada cambio se hace un backup y después se verifica el resultado. Si demasiados archivos fallan, se aborta y se restaura." />
          <label class="flex items-start gap-2 text-sm text-slate-700">
            <input type="checkbox" v-model="confirmReal" class="mt-0.5 rounded border-slate-300" />
            <span>Confirmo que quiero modificar los metadatos de los archivos seleccionados.
              He leído que se hará backup y verificación.</span>
          </label>
        </template>

        <button class="btn-primary" :class="{ 'btn-danger': !dryRun }"
                :disabled="running || (!dryRun && !confirmReal)" @click="run">
          <LoadingSpinner v-if="running" label="Iniciando…" />
          <span v-else>{{ dryRun ? 'Simular corrección' : 'Ejecutar corrección real' }}</span>
        </button>

        <AlertBox v-if="error" variant="error" :message="error" />
      </div>

      <AnalysisProgress v-if="runId" kind="run" :id="runId" :key="runId" @done="onRunDone" />

      <AlertBox v-if="showReanalyzeReminder" variant="warning" title="Vuelve a analizar antes de reestructurar">
        Has aplicado una corrección real de metadatos. Antes de pasar a
        <a class="font-medium underline" href="/reorganize">reestructurar carpetas</a>,
        <a class="font-medium underline" :href="`/analysis?root=${encodeURIComponent(sessionRoot)}`">vuelve a analizar esta carpeta</a>
        para que el paso de estructura trabaje con datos actualizados.
      </AlertBox>

      <CorrectionResults v-if="finishedRunId" :run-id="finishedRunId" :key="'res-' + finishedRunId" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { api, ApiError } from '../api/client';
import type { AnalyzedFile, ProgressEvent, SessionSummary } from '../types/api';
import AlertBox from './AlertBox.vue';
import AnalysisProgress from './AnalysisProgress.vue';
import CorrectionResults from './CorrectionResults.vue';
import LoadingSpinner from './LoadingSpinner.vue';
import MetadataTree from './MetadataTree.vue';

const sessions = ref<SessionSummary[]>([]);
const sessionId = ref(0);
const files = ref<AnalyzedFile[]>([]);
const loadingFiles = ref(false);
const dryRun = ref(true);
const confirmReal = ref(false);
const running = ref(false);
const runId = ref('');
const finishedRunId = ref('');
const changed = ref(false);
const error = ref('');
const showReanalyzeReminder = ref(false);

const sessionRoot = computed(() =>
  sessions.value.find((s) => s.id === sessionId.value)?.root || '');

function onRunDone(ev: ProgressEvent) {
  if (ev.status === 'completed') {
    finishedRunId.value = runId.value;
    if (!dryRun.value) showReanalyzeReminder.value = true;
  }
}

onMounted(async () => {
  try {
    sessions.value = (await api.listSessions()).sessions.filter((s) => s.status === 'completed');
  } catch { /* ignore */ }
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
}

async function run() {
  running.value = true;
  error.value = '';
  runId.value = '';
  finishedRunId.value = '';
  changed.value = false;
  showReanalyzeReminder.value = false;
  try {
    const res = await api.startCorrection({
      session_id: sessionId.value,
      dry_run: dryRun.value,
      confirm_real_write: !dryRun.value && confirmReal.value,
    });
    runId.value = res.run_id;
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : String(e);
  } finally {
    running.value = false;
  }
}
</script>
