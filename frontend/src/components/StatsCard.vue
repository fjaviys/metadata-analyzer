<template>
  <div class="card">
    <p class="text-sm text-slate-500">{{ label }}</p>
    <p :class="['mt-1 text-2xl font-semibold', accentClass]">{{ value }}</p>
    <p v-if="hint" class="mt-1 text-xs text-slate-400">{{ hint }}</p>
  </div>
</template>

<script setup lang="ts">
const props = withDefaults(defineProps<{
  label: string;
  value: number | string;
  hint?: string;
  accent?: 'default' | 'good' | 'warn' | 'bad';
}>(), { accent: 'default' });

const accentClass = {
  default: 'text-slate-800',
  good: 'text-green-600',
  warn: 'text-amber-600',
  bad: 'text-red-600',
}[props.accent];
</script>
