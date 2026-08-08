<template>
  <div class="card">
    <p class="mb-3 font-semibold text-slate-700">Análisis recientes</p>
    <LoadingSpinner v-if="loading" label="Cargando…" />
    <p v-else-if="sessions.length === 0" class="text-sm text-slate-400">
      Aún no hay análisis. Empieza en <a class="text-brand-600 hover:underline" href="/analysis">Análisis</a>.
    </p>
    <ul v-else class="divide-y divide-slate-100">
      <li v-for="s in sessions" :key="s.id" class="flex items-center justify-between py-2">
        <div>
          <a :href="`/results/${s.id}`" class="font-medium text-brand-700 hover:underline">
            #{{ s.id }} · {{ s.root }}
          </a>
          <p class="text-xs text-slate-400">
            {{ s.status }} · {{ s.total_files }} archivos · {{ s.needs_correction }} a corregir
          </p>
        </div>
        <span class="text-xs text-slate-400">{{ s.finished_at || s.started_at }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { api } from '../api/client';
import type { SessionSummary } from '../types/api';
import LoadingSpinner from './LoadingSpinner.vue';

const sessions = ref<SessionSummary[]>([]);
const loading = ref(true);

onMounted(async () => {
  try {
    sessions.value = (await api.listSessions()).sessions;
  } catch { /* ignore */ } finally {
    loading.value = false;
  }
});
</script>
