<template>
  <div :class="['rounded-lg border px-4 py-3 text-sm', styles[variant]]" role="alert">
    <div class="flex items-start gap-2">
      <span>{{ icons[variant] }}</span>
      <div>
        <p v-if="title" class="font-semibold">{{ title }}</p>
        <p><slot>{{ message }}</slot></p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  variant?: 'info' | 'success' | 'warning' | 'error';
  title?: string;
  message?: string;
}>(), { variant: 'info' });

const styles: Record<string, string> = {
  info: 'border-blue-200 bg-blue-50 text-blue-800',
  success: 'border-green-200 bg-green-50 text-green-800',
  warning: 'border-amber-200 bg-amber-50 text-amber-800',
  error: 'border-red-200 bg-red-50 text-red-800',
};
const icons: Record<string, string> = {
  info: 'ℹ️', success: '✅', warning: '⚠️', error: '⛔',
};
</script>
