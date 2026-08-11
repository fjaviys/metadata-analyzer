<template>
  <div class="card space-y-3">
    <div class="flex items-center justify-between">
      <p class="font-semibold text-slate-700">
        {{ phaseLabel }}
        <span v-if="ev?.dry_run" class="ml-2 rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-700">
          DRY-RUN
        </span>
      </p>
      <span class="text-sm text-slate-500">{{ ev?.percent ?? 0 }}%</span>
    </div>

    <div class="h-3 w-full overflow-hidden rounded-full bg-slate-100">
      <div class="h-full rounded-full transition-all duration-300"
           :class="done ? 'bg-green-500' : (aborted ? 'bg-red-500' : 'bg-brand-500')"
           :style="{ width: (ev?.percent ?? 0) + '%' }"></div>
    </div>

    <div class="grid grid-cols-2 gap-2 text-sm text-slate-600 sm:grid-cols-4">
      <div><span class="text-slate-400">Procesados:</span> {{ ev?.processed ?? 0 }}/{{ ev?.total ?? 0 }}</div>
      <div v-if="phase === 'analysis'">
        <span class="text-slate-400">Inconsistencias:</span> {{ ev?.inconsistencies ?? 0 }}
      </div>
      <div v-if="phase === 'analysis'">
        <span class="text-slate-400">A corregir:</span> {{ ev?.needs_correction ?? 0 }}
      </div>
      <div v-if="phase === 'correction' && ev?.dry_run">
        <span class="text-slate-400">Propuestos:</span> {{ ev?.applied ?? 0 }}
      </div>
      <div v-if="phase === 'correction' && !ev?.dry_run">
        <span class="text-slate-400">Verificados:</span> {{ ev?.verified ?? 0 }}
      </div>
      <div v-if="phase === 'correction'">
        <span class="text-slate-400">Fallidos:</span> {{ ev?.failed ?? 0 }}
      </div>
      <div v-if="phase === 'reorganize'">
        <span class="text-slate-400">{{ ev?.dry_run ? 'Propuestos' : 'Movidos' }}:</span>
        {{ ev?.moved ?? 0 }}
      </div>
      <div v-if="phase === 'reorganize'">
        <span class="text-slate-400">Fallidos:</span> {{ ev?.failed ?? 0 }}
      </div>
    </div>

    <p v-if="ev?.current_file" class="truncate text-xs text-slate-400" :title="ev.current_file">
      {{ ev.current_file }}
    </p>

    <AlertBox v-if="aborted" variant="error"
              :message="ev?.abort_reason || 'Ejecución abortada; se restauró desde backup.'" />
    <AlertBox v-else-if="ev?.status === 'failed'" variant="error"
              :message="ev?.error || 'Error en la ejecución.'" />
    <AlertBox v-else-if="done" variant="success" :message="doneMessage" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { subscribeProgress, type ProgressSocket } from '../api/client';
import type { ProgressEvent } from '../types/api';
import AlertBox from './AlertBox.vue';

const props = defineProps<{ kind: 'session' | 'run'; id: string | number }>();
const emit = defineEmits<{ (e: 'done', ev: ProgressEvent): void }>();

const ev = ref<ProgressEvent | null>(null);
let sock: ProgressSocket | null = null;

const phase = computed(() => ev.value?.phase ?? (props.kind === 'run' ? 'correction' : 'analysis'));
const phaseLabel = computed(() => {
  if (phase.value === 'correction') return 'Corrigiendo metadatos';
  if (phase.value === 'reorganize') return 'Reorganizando carpetas';
  return 'Analizando';
});
const done = computed(() => ev.value?.status === 'completed');
const aborted = computed(() => !!ev.value?.aborted);
const doneMessage = computed(() => {
  if (phase.value === 'correction') {
    return ev.value?.dry_run
      ? `Simulación completada: ${ev.value?.applied ?? 0} cambios propuestos, ${ev.value?.skipped ?? 0} sin cambios.`
      : `Corrección completada: ${ev.value?.verified ?? 0} verificados, ${ev.value?.failed ?? 0} fallidos.`;
  }
  if (phase.value === 'reorganize') {
    return ev.value?.dry_run
      ? `Simulación completada: ${ev.value?.moved ?? 0} movimientos propuestos, ${ev.value?.skipped ?? 0} sin cambios.`
      : `Reorganización completada: ${ev.value?.moved ?? 0} movidos, ${ev.value?.failed ?? 0} fallidos.`;
  }
  return `Análisis completado: ${ev.value?.needs_correction ?? 0} archivos a corregir.`;
});

onMounted(() => {
  sock = subscribeProgress(props.kind, props.id, (e) => {
    ev.value = e;
    if (e.status === 'completed' || e.status === 'failed') emit('done', e);
  });
});
onUnmounted(() => sock?.close());
</script>
