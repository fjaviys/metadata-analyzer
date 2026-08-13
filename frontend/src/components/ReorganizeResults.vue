<template>
  <div class="card">
    <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
      <div>
        <p class="font-semibold text-slate-700">
          {{ isDryRun ? 'Resultado de la simulación' : 'Resultado de la reorganización' }}
        </p>
        <p class="text-xs text-slate-500">
          <span v-for="(n, s) in stats" :key="s" class="mr-3">
            <b>{{ n }}</b> {{ statusLabel(String(s)) }}
          </span>
        </p>
      </div>
      <div class="flex items-center gap-3">
        <label class="flex items-center gap-2 text-sm text-slate-600">
          <input type="checkbox" v-model="onlyChanges" @change="reload" class="rounded border-slate-300" />
          Solo cambios
        </label>
        <button v-if="canUndo" class="btn-ghost text-red-600" :disabled="undoing" @click="undo">
          {{ undoing ? 'Deshaciendo…' : 'Deshacer movimientos' }}
        </button>
      </div>
    </div>

    <AlertBox v-if="undoResult" variant="success"
      :message="`Deshecho: ${undoResult.undone} archivo(s) restaurados a su carpeta original.`" />
    <AlertBox v-if="undoResult && undoResult.failed.length" variant="error"
      :message="`${undoResult.failed.length} archivo(s) no se pudieron deshacer.`" />

    <LoadingSpinner v-if="loading" label="Cargando resultados…" />
    <p v-else-if="rows.length === 0" class="py-4 text-center text-sm text-slate-400">Sin filas.</p>
    <div v-else class="overflow-x-auto">
      <table class="w-full text-left text-sm">
        <thead class="border-b border-slate-200 text-xs uppercase text-slate-500">
          <tr>
            <th class="py-2 pr-3">Origen</th><th class="py-2 pr-3">Destino</th>
            <th class="py-2 pr-3">Estado</th><th class="py-2 pr-3">Motivo / error</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id" class="border-b border-slate-100">
            <td class="max-w-xs truncate py-2 pr-3 text-slate-700" :title="r.original_path">{{ short(r.original_path) }}</td>
            <td class="max-w-xs truncate py-2 pr-3 text-slate-700" :title="r.new_path || ''">
              {{ r.new_path ? short(r.new_path) : '—' }}
            </td>
            <td class="py-2 pr-3"><span :class="statusClass(r.status)">{{ statusLabel(r.status) }}</span></td>
            <td class="max-w-xs truncate py-2 pr-3 text-xs text-slate-500" :title="r.error || r.reason || ''">
              {{ r.error || r.reason || '—' }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <p class="mt-3 text-xs text-slate-500">{{ rows.length }} archivo(s) mostrados.</p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { api } from '../api/client';
import type { ReorganizeMove } from '../types/api';
import AlertBox from './AlertBox.vue';
import LoadingSpinner from './LoadingSpinner.vue';

const props = defineProps<{ runId: string }>();

const rows = ref<ReorganizeMove[]>([]);
const stats = ref<Record<string, number>>({});
const loading = ref(false);
const onlyChanges = ref(true);
const undoing = ref(false);
const undoResult = ref<{ undone: number; failed: Array<{ path: string; error: string }> } | null>(null);

const isDryRun = computed(() => rows.value[0]?.dry_run === 1 || (stats.value['dry-run'] ?? 0) > 0);
const canUndo = computed(() => !isDryRun.value && (stats.value['moved'] ?? 0) > 0);

const LABELS: Record<string, string> = {
  'dry-run': 'propuesto', moved: 'movido', failed: 'fallido',
  reverted: 'deshecho', skipped: 'sin cambios',
};
const statusLabel = (s: string) => LABELS[s] ?? s;
const statusClass = (s: string) => ({
  'dry-run': 'text-brand-700', moved: 'text-green-600', failed: 'text-red-600',
  reverted: 'text-slate-400 line-through', skipped: 'text-slate-400',
}[s] ?? 'text-slate-600');

function short(p: string) { return p.split('/').slice(-3).join('/'); }

async function reload() {
  loading.value = true;
  try {
    const r = await api.getReorganizeRun(props.runId, { only_changes: onlyChanges.value, limit: 5000, offset: 0 });
    rows.value = r.moves;
    stats.value = r.stats;
  } finally {
    loading.value = false;
  }
}

async function undo() {
  undoing.value = true;
  try {
    undoResult.value = await api.undoReorganize(props.runId);
    await reload();
  } finally {
    undoing.value = false;
  }
}

onMounted(reload);
</script>
