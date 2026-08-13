<template>
  <div class="relative" ref="rootEl">
    <label v-if="label" class="label">{{ label }}</label>
    <div class="flex gap-2">
      <input
        ref="inputEl"
        :value="modelValue"
        class="input font-mono"
        :placeholder="placeholder"
        autocomplete="off"
        @input="onInput(($event.target as HTMLInputElement).value)"
        @focus="onFocus"
        @keydown.escape="open = false"
      />
      <button class="btn-ghost" type="button" @click="goUp" :disabled="!current.parent"
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
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
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
const rootEl = ref<HTMLElement | null>(null);
// Texto de filtro SOLO mientras se escribe (independiente del valor
// seleccionado); '' significa "sin filtro, listar todo lo que devolvió browsePath".
const filterText = ref('');
let timer: ReturnType<typeof setTimeout> | null = null;

const filtered = computed(() => {
  const f = filterText.value.toLowerCase();
  if (!f) return current.value.dirs;
  return current.value.dirs.filter((d) => d.name.toLowerCase().includes(f));
});

async function browsePath(path: string) {
  loading.value = true;
  try {
    current.value = await api.browse(path);
  } catch {
    current.value = { path, parent: null, dirs: [] };
  } finally {
    loading.value = false;
  }
}

// Al enfocar: muestra el contenido de la carpeta YA seleccionada (el valor
// exacto actual), no de un supuesto "padre" calculado a partir del texto.
function onFocus() {
  filterText.value = '';
  open.value = true;
  browsePath(props.modelValue);
}

function onInput(v: string) {
  emit('update:modelValue', v);
  open.value = true;
  const i = v.lastIndexOf('/');
  const dir = i > 0 ? v.slice(0, i) : '';
  filterText.value = i >= 0 ? v.slice(i + 1) : v;
  debounceRefresh(dir);
}

function debounceRefresh(dir: string) {
  if (timer) clearTimeout(timer);
  // mientras se escribe, se filtra dentro del padre del texto tecleado
  timer = setTimeout(() => browsePath(dir), 250);
}

function choose(d: BrowseEntry) {
  filterText.value = '';
  emit('update:modelValue', d.path);
  open.value = false;
}

function useCurrent() {
  if (current.value.path) emit('update:modelValue', current.value.path);
  open.value = false;
}

function goUp() {
  const target = current.value.parent;
  if (target) {
    filterText.value = '';
    emit('update:modelValue', target);
    browsePath(target);
  }
}

function onDocClick(e: MouseEvent) {
  if (open.value && rootEl.value && !rootEl.value.contains(e.target as Node)) {
    open.value = false;
  }
}

onMounted(() => document.addEventListener('click', onDocClick));
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick);
  if (timer) clearTimeout(timer);
});
</script>
