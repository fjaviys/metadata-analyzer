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
      <label class="flex items-center gap-2 text-sm text-slate-600">
        <input type="checkbox" v-model="onlyChanges" @change="reload" class="rounded border-slate-300" />
        Solo cambios
      </label>
    </div>

    <LoadingSpinner v-if="loading" label="Cargando resultados…" />
    <p v-else-if="rows.length === 0" class="py-4 text-center text-sm text-slate-400">Sin filas.</p>
    <div v-else class="overflow-x-auto">
      <table class="w-full text-left text-sm">
        <thead class="border-b border-slate-200 text-xs uppercase text-slate-500">
          <tr>
            <th class="py-2 pr-3">Archivo</th><th class="py-2 pr-3">Antes</th>
            <th class="py-2 pr-3">Después</th><th class="py-2 pr-3">Fuente</th>
            <th class="py-2 pr-3">Estado</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id" class="border-b border-slate-100">
            <td class="max-w-xs truncate py-2 pr-3 text-slate-700" :title="r.path">{{ short(r.path) }}</td>
            <td class="py-2 pr-3 text-slate-500">{{ r.original_value || '—' }}</td>
            <td class="py-2 pr-3 text-slate-700">{{ r.new_value || '—' }}</td>
            <td class="py-2 pr-3 text-xs text-slate-500">{{ sourceLabel(r.source) }}</td>
            <td class="py-2 pr-3"><span :class="statusClass(r.status)">{{ statusLabel(r.status) }}</span></td>
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
import type { CorrectionRow } from '../types/api';
import LoadingSpinner from './LoadingSpinner.vue';

const props = defineProps<{ runId: string }>();

const rows = ref<CorrectionRow[]>([]);
const stats = ref<Record<string, number>>({});
const loading = ref(false);
const onlyChanges = ref(true);

const isDryRun = computed(() => rows.value[0]?.dry_run === 1 || (stats.value['dry-run'] ?? 0) > 0);

const LABELS: Record<string, string> = {
  'dry-run': 'propuesto', verified: 'verificado', failed: 'fallido',
  reverted: 'revertido', skipped: 'sin cambios', applied: 'aplicado',
};
const statusLabel = (s: string) => LABELS[s] ?? s;
const statusClass = (s: string) => ({
  'dry-run': 'text-brand-700', verified: 'text-green-600', failed: 'text-red-600',
  reverted: 'text-slate-400 line-through', skipped: 'text-slate-400',
}[s] ?? 'text-slate-600');
const SOURCE_LABELS: Record<string, string> = { filename: 'nombre de archivo', folder: 'carpeta contenedora' };
const sourceLabel = (s?: string | null) => (s ? SOURCE_LABELS[s] ?? s : '—');

function short(p: string) { return p.split('/').slice(-3).join('/'); }

async function reload() {
  loading.value = true;
  try {
    const r = await api.getCorrectionRun(props.runId, { only_changes: onlyChanges.value, limit: 5000, offset: 0 });
    rows.value = r.corrections;
    stats.value = r.stats;
  } finally {
    loading.value = false;
  }
}

onMounted(reload);
</script>
