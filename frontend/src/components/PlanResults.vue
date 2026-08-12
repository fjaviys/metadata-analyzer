<template>
  <div class="space-y-4">
    <div class="card">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <p class="font-semibold text-slate-700">Metadatos</p>
          <p class="text-xs text-slate-500">
            <span v-for="(n, s) in metadata.stats" :key="s" class="mr-3">
              <b>{{ n }}</b> {{ statusLabel(String(s)) }}
            </span>
            <span v-if="Object.keys(metadata.stats).length === 0" class="text-slate-400">
              sin cambios de metadatos en este run
            </span>
          </p>
        </div>
        <label class="flex items-center gap-2 text-sm text-slate-600">
          <input type="checkbox" v-model="onlyChanges" @change="reload" class="rounded border-slate-300" />
          Solo cambios
        </label>
      </div>
      <LoadingSpinner v-if="loading" label="Cargando…" />
      <p v-else-if="metadata.rows.length === 0" class="py-4 text-center text-sm text-slate-400">Sin filas.</p>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-left text-sm">
          <thead class="border-b border-slate-200 text-xs uppercase text-slate-500">
            <tr><th class="py-2 pr-3">Archivo</th><th class="py-2 pr-3">Antes</th>
                <th class="py-2 pr-3">Después</th><th class="py-2 pr-3">Estado</th></tr>
          </thead>
          <tbody>
            <tr v-for="r in metadata.rows" :key="r.id" class="border-b border-slate-100">
              <td class="max-w-xs truncate py-2 pr-3 text-slate-700" :title="r.path">{{ short(r.path) }}</td>
              <td class="py-2 pr-3 text-slate-500">{{ r.original_value || '—' }}</td>
              <td class="py-2 pr-3 text-slate-700">{{ r.new_value || '—' }}</td>
              <td class="py-2 pr-3"><span :class="statusClass(r.status)">{{ statusLabel(r.status) }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="card">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <p class="font-semibold text-slate-700">Estructura de carpetas</p>
          <p class="text-xs text-slate-500">
            <span v-for="(n, s) in structure.stats" :key="s" class="mr-3">
              <b>{{ n }}</b> {{ statusLabel(String(s)) }}
            </span>
            <span v-if="Object.keys(structure.stats).length === 0" class="text-slate-400">
              sin movimientos en este run
            </span>
          </p>
        </div>
        <button v-if="canUndo" class="btn-ghost text-red-600" :disabled="undoing" @click="undo">
          {{ undoing ? 'Deshaciendo…' : 'Deshacer movimientos' }}
        </button>
      </div>
      <AlertBox v-if="undoResult" variant="success"
        :message="`Deshecho: ${undoResult.undone} archivo(s) restaurados a su carpeta original.`" />
      <LoadingSpinner v-if="loading" label="Cargando…" />
      <p v-else-if="structure.rows.length === 0" class="py-4 text-center text-sm text-slate-400">Sin filas.</p>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-left text-sm">
          <thead class="border-b border-slate-200 text-xs uppercase text-slate-500">
            <tr><th class="py-2 pr-3">Origen</th><th class="py-2 pr-3">Destino</th>
                <th class="py-2 pr-3">Estado</th><th class="py-2 pr-3">Motivo</th></tr>
          </thead>
          <tbody>
            <tr v-for="r in structure.rows" :key="r.id" class="border-b border-slate-100">
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
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { api } from '../api/client';
import type { CorrectionRow, ReorganizeMove } from '../types/api';
import AlertBox from './AlertBox.vue';
import LoadingSpinner from './LoadingSpinner.vue';

const props = defineProps<{ runId: string }>();
const emit = defineEmits<{ (e: 'changed'): void }>();

const metadata = ref<{ stats: Record<string, number>; rows: CorrectionRow[] }>({ stats: {}, rows: [] });
const structure = ref<{ stats: Record<string, number>; rows: ReorganizeMove[] }>({ stats: {}, rows: [] });
const loading = ref(false);
const onlyChanges = ref(true);
const undoing = ref(false);
const undoResult = ref<{ undone: number; failed: Array<{ path: string; error: string }> } | null>(null);

const canUndo = computed(() => (structure.value.stats['moved'] ?? 0) > 0);

const LABELS: Record<string, string> = {
  'dry-run': 'propuesto', verified: 'verificado', failed: 'fallido', reverted: 'revertido',
  skipped: 'sin cambios', applied: 'aplicado', moved: 'movido',
};
const statusLabel = (s: string) => LABELS[s] ?? s;
const statusClass = (s: string) => ({
  'dry-run': 'text-brand-700', verified: 'text-green-600', moved: 'text-green-600',
  failed: 'text-red-600', reverted: 'text-slate-400 line-through', skipped: 'text-slate-400',
}[s] ?? 'text-slate-600');

function short(p: string) { return p.split('/').slice(-3).join('/'); }

async function reload() {
  loading.value = true;
  try {
    const r = await api.getPlanRun(props.runId, { only_changes: onlyChanges.value, limit: 5000, offset: 0 });
    metadata.value = r.metadata;
    structure.value = r.structure;
  } finally {
    loading.value = false;
  }
}

async function undo() {
  undoing.value = true;
  try {
    undoResult.value = await api.undoPlanRun(props.runId);
    await reload();
    emit('changed');
  } finally {
    undoing.value = false;
  }
}

onMounted(reload);
</script>
