<template>
  <div class="card space-y-4">
    <p class="font-semibold text-slate-700">Formatos a analizar</p>

    <!-- Grupos a incluir -->
    <div class="space-y-3">
      <div v-for="g in groups" :key="g.key">
        <div class="flex items-center justify-between">
          <label class="flex items-center gap-2 text-sm font-medium text-slate-700">
            <input type="checkbox" :checked="g.on.value" class="rounded border-slate-300"
                   @change="toggleGroup(g.key)" />
            <span>{{ g.icon }} {{ g.label }}</span>
            <span class="text-xs text-slate-400">({{ g.exts.length }})</span>
          </label>
          <button type="button" class="text-xs text-slate-400 hover:underline"
                  @click="g.open.value = !g.open.value">
            {{ g.open.value ? 'ocultar' : 'ver extensiones' }}
          </button>
        </div>
        <div v-if="g.open.value" class="mt-2 flex flex-wrap gap-1 pl-6">
          <button v-for="ext in g.exts" :key="ext" type="button"
                  :class="chipClass(ext)" @click="toggleExt(ext)">{{ ext }}</button>
        </div>
      </div>
    </div>

    <!-- Omitir extensiones -->
    <div class="border-t border-slate-100 pt-3">
      <label class="label">Omitir extensiones (imagen/vídeo)</label>
      <div class="flex gap-2">
        <input v-model="omitInput" class="input font-mono" placeholder=".png, .gif, .wmv"
               @keydown.enter.prevent="addOmit" />
        <button type="button" class="btn-ghost" @click="addOmit">Añadir</button>
      </div>
      <div v-if="excluded.size" class="mt-2 flex flex-wrap gap-1">
        <span v-for="ext in [...excluded]" :key="ext"
              class="inline-flex items-center gap-1 rounded bg-red-50 px-2 py-0.5 text-xs text-red-700">
          {{ ext }}
          <button type="button" class="hover:text-red-900" @click="removeOmit(ext)">✕</button>
        </span>
      </div>
    </div>

    <p class="text-xs text-slate-500">
      Se analizarán <b>{{ effectiveCount }}</b> extensiones.
      <span v-if="effectiveCount === 0" class="text-red-600">Selecciona al menos un formato.</span>
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { api } from '../api/client';
import type { FormatCatalog } from '../types/api';

const emit = defineEmits<{
  (e: 'update:include', v: string[]): void;
  (e: 'update:exclude', v: string[]): void;
}>();

const catalog = reactive<FormatCatalog>({ image: [], raw: [], video: [] });
const selected = ref<Set<string>>(new Set());   // extensiones incluidas
const excluded = ref<Set<string>>(new Set());
const omitInput = ref('');

const groups = [
  { key: 'image' as const, label: 'Imagen', icon: '🖼️', exts: [] as string[],
    on: ref(true), open: ref(false) },
  { key: 'raw' as const, label: 'RAW', icon: '🎞️', exts: [] as string[],
    on: ref(true), open: ref(false) },
  { key: 'video' as const, label: 'Vídeo', icon: '🎬', exts: [] as string[],
    on: ref(true), open: ref(false) },
];

const allExts = computed(() => [...catalog.image, ...catalog.raw, ...catalog.video]);
const effectiveCount = computed(() =>
  [...selected.value].filter((e) => !excluded.value.has(e)).length);

function chipClass(ext: string) {
  return selected.value.has(ext)
    ? 'rounded bg-brand-500 px-2 py-0.5 text-xs text-white'
    : 'rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-500';
}

function toggleExt(ext: string) {
  const s = new Set(selected.value);
  s.has(ext) ? s.delete(ext) : s.add(ext);
  selected.value = s;
  syncGroupFlags();
}

function toggleGroup(key: 'image' | 'raw' | 'video') {
  const exts = catalog[key];
  const s = new Set(selected.value);
  const allOn = exts.every((e) => s.has(e));
  exts.forEach((e) => (allOn ? s.delete(e) : s.add(e)));
  selected.value = s;
  syncGroupFlags();
}

function syncGroupFlags() {
  for (const g of groups) {
    g.exts = catalog[g.key];
    g.on.value = g.exts.length > 0 && g.exts.every((e) => selected.value.has(e));
  }
}

function addOmit() {
  const parts = omitInput.value.split(',').map((s) => s.trim().toLowerCase()).filter(Boolean);
  const s = new Set(excluded.value);
  for (let p of parts) {
    if (!p.startsWith('.')) p = '.' + p;
    s.add(p);
  }
  excluded.value = s;
  omitInput.value = '';
}
function removeOmit(ext: string) {
  const s = new Set(excluded.value);
  s.delete(ext);
  excluded.value = s;
}

// Emite include/exclude. include = [] cuando están TODAS (equivale a "todas").
watch([selected, excluded], () => {
  const all = allExts.value;
  const inc = [...selected.value];
  const includeOut = inc.length === all.length ? [] : inc;
  emit('update:include', includeOut);
  emit('update:exclude', [...excluded.value]);
}, { deep: true });

onMounted(async () => {
  try {
    const cat = await api.getFormats();
    Object.assign(catalog, cat);
    selected.value = new Set(allExts.value);   // por defecto, todas
    syncGroupFlags();
  } catch { /* ignore */ }
});
</script>
