<template>
  <div class="space-y-6">
    <div class="card">
      <label class="label">Sesión de análisis</label>
      <div class="flex gap-2">
        <select v-model.number="sessionId" class="input" @change="loadTree">
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
      <FolderTreeSelector :tree="tree" @update:selected="selected = $event" />

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

      <AnalysisProgress v-if="runId" kind="run" :id="runId" :key="runId" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { api, ApiError } from '../api/client';
import type { FolderNode, SessionSummary } from '../types/api';
import AlertBox from './AlertBox.vue';
import AnalysisProgress from './AnalysisProgress.vue';
import FolderTreeSelector from './FolderTreeSelector.vue';
import LoadingSpinner from './LoadingSpinner.vue';

const sessions = ref<SessionSummary[]>([]);
const sessionId = ref(0);
const tree = ref<FolderNode[]>([]);
const selected = ref<string[]>([]);
const dryRun = ref(true);
const confirmReal = ref(false);
const running = ref(false);
const runId = ref('');
const error = ref('');

onMounted(async () => {
  try {
    sessions.value = (await api.listSessions()).sessions.filter((s) => s.status === 'completed');
  } catch { /* ignore */ }
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
  try {
    const res = await api.startCorrection({
      session_id: sessionId.value,
      subfolders: selected.value,
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
