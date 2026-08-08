<template>
  <div class="card">
    <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
      <p class="font-semibold text-slate-700">Archivos analizados</p>
      <label class="flex items-center gap-2 text-sm text-slate-600">
        <input type="checkbox" v-model="onlyNeeds" @change="reload" class="rounded border-slate-300" />
        Solo los que requieren corrección
      </label>
    </div>

    <LoadingSpinner v-if="loading" label="Cargando…" />

    <div v-else class="overflow-x-auto">
      <table class="w-full text-left text-sm">
        <thead class="border-b border-slate-200 text-xs uppercase text-slate-500">
          <tr>
            <th class="py-2 pr-3">Archivo</th>
            <th class="py-2 pr-3">Fecha EXIF</th>
            <th class="py-2 pr-3">Propuesta</th>
            <th class="py-2 pr-3">Precisión</th>
            <th class="py-2 pr-3">Estado</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="f in files" :key="f.id" class="border-b border-slate-100">
            <td class="max-w-xs truncate py-2 pr-3 text-slate-700" :title="f.path">
              {{ short(f.path) }}
            </td>
            <td class="py-2 pr-3 text-slate-500">{{ f.exif_date || '—' }}</td>
            <td class="py-2 pr-3 text-slate-700">{{ f.recommended_date || '—' }}</td>
            <td class="py-2 pr-3">
              <span class="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                {{ f.recommended_precision || '—' }}
              </span>
            </td>
            <td class="py-2 pr-3">
              <span v-if="f.is_corrupt" class="text-red-600">corrupto</span>
              <span v-else-if="f.needs_correction" class="text-amber-600">a corregir</span>
              <span v-else class="text-green-600">ok</span>
            </td>
          </tr>
          <tr v-if="files.length === 0">
            <td colspan="5" class="py-4 text-center text-slate-400">Sin resultados.</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="mt-3 flex items-center justify-between text-sm text-slate-500">
      <span>{{ total }} archivo(s) en total</span>
      <div class="flex gap-2">
        <button class="btn-ghost" :disabled="offset === 0" @click="page(-1)">Anterior</button>
        <button class="btn-ghost" :disabled="offset + limit >= total" @click="page(1)">Siguiente</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { api } from '../api/client';
import type { AnalyzedFile } from '../types/api';
import LoadingSpinner from './LoadingSpinner.vue';

const props = defineProps<{ sessionId: number }>();

const files = ref<AnalyzedFile[]>([]);
const total = ref(0);
const loading = ref(false);
const onlyNeeds = ref(true);
const limit = 50;
const offset = ref(0);

function short(p: string) {
  const parts = p.split('/');
  return parts.slice(-3).join('/');
}

async function reload() {
  loading.value = true;
  try {
    const r = await api.getFiles(props.sessionId, {
      needs_correction: onlyNeeds.value ? true : undefined,
      limit, offset: offset.value,
    });
    files.value = r.files;
    total.value = r.total;
  } finally {
    loading.value = false;
  }
}

function page(dir: number) {
  offset.value = Math.max(0, offset.value + dir * limit);
  reload();
}

onMounted(reload);
</script>
