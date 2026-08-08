<template>
  <div class="space-y-6">
    <div class="card space-y-4">
      <div>
        <label class="label">Carpeta a analizar</label>
        <input v-model="rootPath" class="input" placeholder="/media/fotos" />
        <p v-if="roots.length" class="mt-1 text-xs text-slate-400">
          Raíces permitidas: {{ roots.join(', ') }}
        </p>
      </div>
      <label class="flex items-center gap-2 text-sm text-slate-600">
        <input type="checkbox" v-model="detectDuplicates" class="rounded border-slate-300" />
        Detectar archivos duplicados
      </label>

      <AlertBox variant="info"
        message="El análisis es de solo lectura: no modifica ningún archivo. Genera un informe PDF y prepara los datos para una posible corrección posterior." />

      <div class="flex items-center gap-3">
        <button class="btn-primary" :disabled="running || !rootPath" @click="start">
          <LoadingSpinner v-if="running" label="Iniciando…" />
          <span v-else>Iniciar análisis</span>
        </button>
        <span v-if="sessionId" class="text-sm text-slate-500">Sesión #{{ sessionId }}</span>
      </div>

      <AlertBox v-if="error" variant="error" :message="error" />
    </div>

    <AnalysisProgress v-if="sessionId" kind="session" :id="sessionId" @done="onDone" />

    <div v-if="finished" class="card flex items-center justify-between">
      <p class="text-slate-700">Análisis terminado.</p>
      <div class="flex gap-2">
        <a class="btn-ghost" :href="reportUrl" target="_blank" rel="noopener">Ver informe PDF</a>
        <a class="btn-primary" :href="`/results/${sessionId}`">Ver resultados</a>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { api, ApiError } from '../api/client';
import type { ProgressEvent } from '../types/api';
import AlertBox from './AlertBox.vue';
import AnalysisProgress from './AnalysisProgress.vue';
import LoadingSpinner from './LoadingSpinner.vue';

const rootPath = ref('');
const detectDuplicates = ref(true);
const roots = ref<string[]>([]);
const running = ref(false);
const finished = ref(false);
const sessionId = ref<number | null>(null);
const error = ref('');

const reportUrl = computed(() => sessionId.value ? api.reportUrl(sessionId.value) : '#');

onMounted(async () => {
  try {
    const r = await api.getRoots();
    roots.value = r.allowed_media_roots;
  } catch { /* ignore */ }
  const stored = localStorage.getItem('ma_config');
  if (stored) {
    const cfg = JSON.parse(stored);
    if (cfg.type === 'local' && cfg.root_path) rootPath.value = cfg.root_path;
  }
  if (!rootPath.value && roots.value.length) rootPath.value = roots.value[0];
});

async function start() {
  running.value = true;
  error.value = '';
  finished.value = false;
  sessionId.value = null;
  try {
    const res = await api.startAnalysis({
      root_path: rootPath.value, connection_type: 'local',
      detect_duplicates: detectDuplicates.value,
    });
    sessionId.value = res.session_id;
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : String(e);
  } finally {
    running.value = false;
  }
}

function onDone(ev: ProgressEvent) {
  if (ev.status === 'completed') finished.value = true;
}
</script>
