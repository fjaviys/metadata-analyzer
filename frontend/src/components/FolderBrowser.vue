<template>
  <div class="relative">
    <label v-if="label" class="label">{{ label }}</label>
    <div class="flex gap-2">
      <input
        ref="inputEl"
        :value="modelValue"
        class="input font-mono"
        :placeholder="placeholder"
        autocomplete="off"
        @input="onInput(($event.target as HTMLInputElement).value)"
        @focus="open = true; refresh()"
        @keydown.escape="open = false"
      />
      <button class="btn-ghost" type="button" @click="goUp" :disabled="!current.parent && !hasSlash"
              title="Subir un nivel">↑</button>
    </div>

    <!-- desplegable de subcarpetas -->
    <div v-if="open"
         class="absolute z-20 mt-1 w-full overflow-hidden rounded-lg border border-slate-200 bg-white shadow-lg">
      <div class="flex items-center justify-between border-b border-slate-100 px-3 py-1.5 text-xs text-slate-500">
        <span class="truncate font-mono" :title="current.path || 'raíces permitidas'">
          {{ current.path || 'raíces permitidas' }}
        </span>
        <button class="text-slate-400 hover:text-slate-700" @click="open = false">✕</button>
      </div>
      <div v-if="loading" class="px-3 py-2"><LoadingSpinner label="Cargando…" /></div>
      <ul v-else class="max-h-64 overflow-y-auto">
        <li v-if="filtered.length === 0" class="px-3 py-2 text-sm text-slate-400">
          Sin subcarpetas.
        </li>
        <li v-for="d in filtered" :key="d.path">
          <button type="button"
                  class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-brand-50"
                  @click="choose(d)">
            <span>📁</span>
            <span class="truncate">{{ d.name }}</span>
          </button>
        </li>
      </ul>
      <div class="border-t border-slate-100 px-3 py-1.5 text-right">
        <button type="button" class="text-xs text-brand-600 hover:underline" @click="useCurrent">
          Usar esta carpeta
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue';
import { api } from '../api/client';
import type { BrowseEntry, BrowseResult } from '../types/api';
import LoadingSpinner from './LoadingSpinner.vue';

const props = withDefaults(defineProps<{
  modelValue: string;
  label?: string;
  placeholder?: string;
}>(), { placeholder: '/media' });

const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>();

const open = ref(false);
const loading = ref(false);
const current = ref<BrowseResult>({ path: '', parent: null, dirs: [] });
let timer: ReturnType<typeof setTimeout> | null = null;

const hasSlash = computed(() => props.modelValue.includes('/'));

// Fragmento tras la última barra (para autocompletar) y directorio a listar.
const frag = computed(() => {
  const v = props.modelValue;
  const i = v.lastIndexOf('/');
  return i >= 0 ? v.slice(i + 1) : v;
});
const dirPart = computed(() => {
  const v = props.modelValue;
  const i = v.lastIndexOf('/');
  return i > 0 ? v.slice(0, i) : (i === 0 ? '/' : '');
});

const filtered = computed(() => {
  const f = frag.value.toLowerCase();
  if (!f) return current.value.dirs;
  return current.value.dirs.filter((d) => d.name.toLowerCase().includes(f));
});

function onInput(v: string) {
  emit('update:modelValue', v);
  open.value = true;
  debounceRefresh();
}

function debounceRefresh() {
  if (timer) clearTimeout(timer);
  timer = setTimeout(refresh, 250);
}

async function refresh() {
  loading.value = true;
  try {
    current.value = await api.browse(dirPart.value);
  } catch {
    current.value = { path: dirPart.value, parent: null, dirs: [] };
  } finally {
    loading.value = false;
  }
}

function choose(d: BrowseEntry) {
  emit('update:modelValue', d.path + '/');
  open.value = true;
  refresh();
}

function useCurrent() {
  if (current.value.path) emit('update:modelValue', current.value.path);
  open.value = false;
}

function goUp() {
  const target = current.value.parent ?? dirPart.value;
  if (target) {
    emit('update:modelValue', target + '/');
    refresh();
  }
}

onBeforeUnmount(() => { if (timer) clearTimeout(timer); });
</script>
