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
          <input type="checkbox" v-model="onlyChanges" @change="reload"
                 class="rounded border-slate-300" />
          Solo cambios
        </label>
        <button class="btn-ghost" @click="exportCsv" :disabled="rows.length === 0">
          Exportar CSV
        </button>
      </div>
    </div>

    <AlertBox v-if="changed" variant="info"
      message="Has ajustado la fecha de algún archivo. Vuelve a simular (o ejecuta la corrección real) para aplicar tus cambios." />

    <LoadingSpinner v-if="loading" label="Cargando resultados…" />
    <p v-else-if="rows.length === 0" class="py-4 text-center text-sm text-slate-400">
      Sin filas.
    </p>
    <CorrectionTree v-else :session-id="sessionId" :root="root" :rows="rows"
                    @changed="changed = true; emit('changed')" />

    <p class="mt-3 text-xs text-slate-500">{{ rows.length }} archivo(s) mostrados.</p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { api } from '../api/client';
import type { CorrectionRow } from '../types/api';
import AlertBox from './AlertBox.vue';
import CorrectionTree from './CorrectionTree.vue';
import LoadingSpinner from './LoadingSpinner.vue';

const props = defineProps<{ runId: string; sessionId: number; root?: string }>();
const emit = defineEmits<{ (e: 'changed'): void }>();

const rows = ref<CorrectionRow[]>([]);
const stats = ref<Record<string, number>>({});
const loading = ref(false);
const onlyChanges = ref(true);
const changed = ref(false);

const isDryRun = computed(() => rows.value[0]?.dry_run === 1
  || (stats.value['dry-run'] ?? 0) > 0);

const LABELS: Record<string, string> = {
  'dry-run': 'propuesto', verified: 'verificado', failed: 'fallido',
  reverted: 'revertido', skipped: 'sin cambios', applied: 'aplicado',
};
const statusLabel = (s: string) => LABELS[s] ?? s;

async function reload() {
  loading.value = true;
  try {
    // el árbol carga todas las filas del run (hasta un tope alto)
    const r = await api.getCorrectionRun(props.runId, {
      only_changes: onlyChanges.value, limit: 5000, offset: 0,
    });
    rows.value = r.corrections;
    stats.value = r.stats;
  } finally {
    loading.value = false;
  }
}

async function exportCsv() {
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

watch(() => props.runId, reload);
onMounted(reload);
</script>
