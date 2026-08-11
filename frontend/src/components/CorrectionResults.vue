<template>
  <div class="card">
    <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
      <div>
        <p class="font-semibold text-slate-700">
          {{ isDryRun ? 'Resultado de la simulación' : 'Resultado de la corrección' }}
        </p>
        <p class="text-xs text-slate-500">
          <span v-for="(n, s) in stats" :key="s" class="mr-3">
            <b>{{ n }}</b> {{ statusLabel(String(s)) }}
          </span>
        </p>
      </div>
      <div class="flex items-center gap-3">
        <label class="flex items-center gap-2 text-sm text-slate-600">
          <input type="checkbox" v-model="onlyChanges" @change="reload(0)"
                 class="rounded border-slate-300" />
          Solo cambios
        </label>
        <button class="btn-ghost" @click="exportCsv" :disabled="rows.length === 0">
          Exportar CSV
        </button>
      </div>
    </div>

    <LoadingSpinner v-if="loading" label="Cargando resultados…" />

    <div v-else class="overflow-x-auto">
      <table class="w-full text-left text-sm">
        <thead class="border-b border-slate-200 text-xs uppercase text-slate-500">
          <tr>
            <th class="py-2 pr-3">Archivo</th>
            <th class="py-2 pr-3">Fecha anterior</th>
            <th class="py-2 pr-3"></th>
            <th class="py-2 pr-3">Fecha {{ isDryRun ? 'propuesta' : 'nueva' }}</th>
            <th class="py-2 pr-3">Origen</th>
            <th class="py-2 pr-3">Estado</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id" class="border-b border-slate-100">
            <td class="max-w-xs truncate py-2 pr-3 text-slate-700" :title="r.path">
              {{ short(r.path) }}
            </td>
            <td class="whitespace-nowrap py-2 pr-3 font-mono text-xs text-slate-500">
              {{ r.original_value || '—' }}
            </td>
            <td class="py-2 pr-1 text-slate-300">→</td>
            <td class="whitespace-nowrap py-2 pr-3 font-mono text-xs"
                :class="r.correction_type === 'cleanup' ? 'text-red-600' : 'text-slate-800'">
              {{ r.new_value || '—' }}
            </td>
            <td class="py-2 pr-3">
              <span class="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                {{ r.source || r.correction_type }}
                <template v-if="r.precision"> · {{ r.precision }}</template>
              </span>
            </td>
            <td class="py-2 pr-3">
              <span :class="badgeClass(r.status)">{{ statusLabel(r.status) }}</span>
              <span v-if="r.error" class="ml-1 text-xs text-red-500" :title="r.error">⚠</span>
            </td>
          </tr>
          <tr v-if="rows.length === 0">
            <td colspan="6" class="py-4 text-center text-slate-400">Sin filas.</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="mt-3 flex items-center justify-between text-sm text-slate-500">
      <span>{{ total }} fila(s)</span>
      <div class="flex gap-2">
        <button class="btn-ghost" :disabled="offset === 0" @click="reload(offset - limit)">Anterior</button>
        <button class="btn-ghost" :disabled="offset + limit >= total" @click="reload(offset + limit)">Siguiente</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { api } from '../api/client';
import type { CorrectionRow } from '../types/api';
import LoadingSpinner from './LoadingSpinner.vue';

const props = defineProps<{ runId: string }>();

const rows = ref<CorrectionRow[]>([]);
const stats = ref<Record<string, number>>({});
const total = ref(0);
const loading = ref(false);
const onlyChanges = ref(true);
const limit = 50;
const offset = ref(0);

const isDryRun = computed(() => rows.value[0]?.dry_run === 1
  || (stats.value['dry-run'] ?? 0) > 0);

const LABELS: Record<string, string> = {
  'dry-run': 'propuesto', verified: 'verificado', failed: 'fallido',
  reverted: 'revertido', skipped: 'sin cambios', applied: 'aplicado',
};
const statusLabel = (s: string) => LABELS[s] ?? s;

function badgeClass(status: string) {
  const map: Record<string, string> = {
    'dry-run': 'bg-blue-50 text-blue-700',
    verified: 'bg-green-50 text-green-700',
    failed: 'bg-red-50 text-red-700',
    reverted: 'bg-amber-50 text-amber-700',
    skipped: 'bg-slate-100 text-slate-500',
  };
  return `rounded px-2 py-0.5 text-xs ${map[status] ?? 'bg-slate-100 text-slate-600'}`;
}

function short(p: string) {
  return p.split('/').slice(-3).join('/');
}

async function reload(newOffset = offset.value) {
  offset.value = Math.max(0, newOffset);
  loading.value = true;
  try {
    const r = await api.getCorrectionRun(props.runId, {
      only_changes: onlyChanges.value, limit, offset: offset.value,
    });
    rows.value = r.corrections;
    stats.value = r.stats;
    total.value = r.total;
  } finally {
    loading.value = false;
  }
}

async function exportCsv() {
  // descarga TODAS las filas del filtro actual
  const all = await api.getCorrectionRun(props.runId, {
    only_changes: onlyChanges.value, limit: 5000, offset: 0,
  });
  const header = ['archivo', 'fecha_anterior', 'fecha_nueva', 'origen', 'precision', 'estado'];
  const lines = all.corrections.map((r) => [
    r.path, r.original_value ?? '', r.new_value ?? '',
    r.source ?? r.correction_type, r.precision ?? '', r.status,
  ].map((v) => `"${String(v).replace(/"/g, '""')}"`).join(','));
  const csv = [header.join(','), ...lines].join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `correccion_${props.runId}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

watch(() => props.runId, () => reload(0));
onMounted(() => reload(0));
</script>
