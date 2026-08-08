<template>
  <div class="card">
    <p v-if="title" class="mb-3 text-sm font-semibold text-slate-700">{{ title }}</p>
    <div v-if="items.length === 0" class="text-sm text-slate-400">Sin datos.</div>
    <div v-else class="space-y-2">
      <div v-for="item in items" :key="item.label" class="flex items-center gap-2">
        <span class="w-40 shrink-0 truncate text-xs text-slate-600" :title="item.label">
          {{ item.label }}
        </span>
        <div class="h-5 flex-1 overflow-hidden rounded bg-slate-100">
          <div class="h-full rounded bg-brand-500 transition-all"
               :style="{ width: pct(item.value) + '%' }"></div>
        </div>
        <span class="w-14 shrink-0 text-right text-xs tabular-nums text-slate-700">
          {{ item.value }}
          <span v-if="item.secondary !== undefined" class="text-red-500">
            /{{ item.secondary }}</span>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

interface Item { label: string; value: number; secondary?: number }
const props = defineProps<{ title?: string; items: Item[] }>();

const max = computed(() => Math.max(1, ...props.items.map((i) => i.value)));
const pct = (v: number) => Math.round((v / max.value) * 100);
</script>
