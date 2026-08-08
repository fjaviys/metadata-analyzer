<template>
  <div class="space-y-6">
    <LoadingSpinner v-if="loading" label="Cargando resultados…" />

    <template v-else-if="summary">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 class="text-xl font-semibold text-slate-800">Resultados · sesión #{{ summary.id }}</h1>
          <p class="text-sm text-slate-500">{{ summary.root }}</p>
        </div>
        <div class="flex gap-2">
          <a class="btn-ghost" :href="reportUrl" target="_blank" rel="noopener">Informe PDF</a>
          <a class="btn-primary" :href="`/corrections?session=${summary.id}`">Ir a corregir</a>
        </div>
      </div>

      <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatsCard label="Total archivos" :value="summary.total_files" />
        <StatsCard label="A corregir" :value="summary.needs_correction" accent="warn" />
        <StatsCard label="Corruptos" :value="summary.corrupt" accent="bad" />
        <StatsCard label="Duplicados" :value="summary.duplicates_count" />
        <StatsCard label="Fotos" :value="summary.photos" />
        <StatsCard label="Vídeos" :value="summary.videos" />
        <StatsCard label="Con fecha EXIF" :value="summary.with_exif_date" accent="good" />
        <StatsCard label="Sin fecha EXIF" :value="summary.without_exif_date" />
      </div>

      <div class="grid gap-6 lg:grid-cols-2">
        <Chart title="Carpetas nivel 1 (por nº de archivos)" :items="l1Items" />
        <Chart title="Carpetas nivel 2 (por nº de archivos)" :items="l2Items" />
      </div>

      <ResultsTable :session-id="summary.id" />
    </template>

    <AlertBox v-else variant="error" :message="error || 'No se encontró la sesión.'" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { api } from '../api/client';
import type { FolderNode, SessionSummary } from '../types/api';
import AlertBox from './AlertBox.vue';
import Chart from './Chart.vue';
import LoadingSpinner from './LoadingSpinner.vue';
import ResultsTable from './ResultsTable.vue';
import StatsCard from './StatsCard.vue';

const props = defineProps<{ sessionId: number }>();

const summary = ref<SessionSummary | null>(null);
const tree = ref<FolderNode[]>([]);
const loading = ref(true);
const error = ref('');

const reportUrl = computed(() => api.reportUrl(props.sessionId));
const l1Items = computed(() => tree.value.map((n) => ({
  label: n.folder, value: n.total, secondary: n.needs || undefined,
})));
const l2Items = computed(() => tree.value.flatMap((n) => (n.children || []).map((c) => ({
  label: c.folder, value: c.total, secondary: c.needs || undefined,
}))).sort((a, b) => b.value - a.value).slice(0, 15));

onMounted(async () => {
  try {
    summary.value = await api.getSummary(props.sessionId);
    tree.value = (await api.getTree(props.sessionId)).tree;
  } catch (e) {
    error.value = String(e);
  } finally {
    loading.value = false;
  }
});
</script>
