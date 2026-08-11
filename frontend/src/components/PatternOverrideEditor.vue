<template>
  <div class="card space-y-4">
    <div>
      <p class="font-semibold text-slate-700">Patrón manual por carpeta</p>
      <p class="text-xs text-slate-500">
        Aplica un patrón de fecha a una carpeta y <b>todos sus archivos</b> (recursivo)
        cuando la detección automática no acierta. Vuelve a simular para verlo aplicado.
      </p>
    </div>

    <FolderBrowser v-model="folder" label="Carpeta" :placeholder="rootHint" />

    <div class="grid gap-3 sm:grid-cols-2">
      <div>
        <label class="label">Patrón predefinido</label>
        <select v-model="presetKey" class="input" @change="onPreset">
          <option value="">— elige —</option>
          <option v-for="p in presets" :key="p.key" :value="p.key">{{ p.label }}</option>
          <option value="__custom__">Personalizado (texto libre)…</option>
        </select>
      </div>
      <div v-if="presetKey === '__custom__'">
        <label class="label">Patrón (tokens)</label>
        <input v-model="customPattern" class="input font-mono" placeholder="DD-MM-AAAA" />
        <p class="mt-1 text-xs text-slate-400">Tokens: AAAA, AA, MM, DD, hh, mm, ss</p>
      </div>
    </div>

    <div class="flex items-center gap-3">
      <button class="btn-primary" :disabled="!canApply || loading" @click="apply">
        <LoadingSpinner v-if="loading" label="Aplicando…" />
        <span v-else>Aplicar patrón</span>
      </button>
      <span v-if="lastAffected !== null" class="text-sm text-slate-600">
        {{ lastAffected }} archivo(s) afectado(s)<template v-if="lastRescued"> ·
          <span class="text-amber-600">{{ lastRescued }} rescatado(s)</span> (no marcados por el análisis)</template>
      </span>
    </div>

    <AlertBox v-if="error" variant="error" :message="error" />

    <!-- previsualización -->
    <div v-if="preview.length" class="overflow-x-auto">
      <p class="mb-1 text-xs font-medium text-slate-500">Previsualización (máx. 20):</p>
      <table class="w-full text-left text-xs">
        <thead class="text-slate-400">
          <tr><th class="pr-3 py-1">Archivo</th><th class="pr-3">Antes</th><th></th><th>Después</th></tr>
        </thead>
        <tbody>
          <tr v-for="p in preview" :key="p.path" class="border-t border-slate-100">
            <td class="max-w-xs truncate pr-3 py-1" :title="p.path">
              {{ short(p.path) }}
              <span v-if="p.rescued" class="ml-1 rounded bg-amber-100 px-1 text-[10px] text-amber-700">rescatado</span>
            </td>
            <td class="pr-3 font-mono text-slate-400">{{ p.old || '—' }}</td>
            <td class="px-1 text-slate-300">→</td>
            <td class="font-mono text-slate-800">{{ p.new }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- overrides activos -->
    <div v-if="overrides.length" class="border-t border-slate-100 pt-3">
      <p class="mb-2 text-xs font-medium text-slate-500">Patrones activos en esta sesión:</p>
      <ul class="space-y-1">
        <li v-for="o in overrides" :key="o.id"
            class="flex items-center justify-between rounded bg-slate-50 px-2 py-1 text-xs">
          <span class="truncate"><b class="font-mono">{{ o.pattern }}</b> · {{ short(o.folder) }}</span>
          <button class="text-red-500 hover:underline" @click="remove(o.id)">quitar</button>
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { api, ApiError } from '../api/client';
import AlertBox from './AlertBox.vue';
import FolderBrowser from './FolderBrowser.vue';
import LoadingSpinner from './LoadingSpinner.vue';

const props = defineProps<{ sessionId: number; root?: string }>();
const emit = defineEmits<{ (e: 'changed'): void }>();

const presets = ref<Array<{ key: string; label: string; pattern: string }>>([]);
const overrides = ref<Array<{ id: number; folder: string; pattern: string; source: string }>>([]);
const folder = ref(props.root || '');
const presetKey = ref('');
const customPattern = ref('');
const loading = ref(false);
const error = ref('');
const lastAffected = ref<number | null>(null);
const lastRescued = ref(0);
const preview = ref<Array<{ path: string; old: string | null; new: string; rescued?: boolean }>>([]);

const rootHint = computed(() => props.root || '/media');
const effectivePattern = computed(() =>
  presetKey.value === '__custom__' ? customPattern.value.trim() : presetKey.value);
const canApply = computed(() => !!folder.value && !!effectivePattern.value);

function short(p: string) { return p.split('/').slice(-3).join('/'); }
function onPreset() { preview.value = []; lastAffected.value = null; }

async function apply() {
  loading.value = true;
  error.value = '';
  try {
    const res = await api.createOverride({
      session_id: props.sessionId, folder: folder.value,
      pattern: effectivePattern.value, source: 'auto',
    });
    lastAffected.value = res.affected;
    lastRescued.value = res.rescued;
    preview.value = res.preview;
    await loadOverrides();
    emit('changed');
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

async function remove(id: number) {
  await api.deleteOverride(id);
  await loadOverrides();
  emit('changed');
}

async function loadOverrides() {
  try { overrides.value = (await api.listOverrides(props.sessionId)).overrides; } catch { /* ignore */ }
}

watch(() => props.sessionId, loadOverrides);
onMounted(async () => {
  try { presets.value = (await api.getPatternPresets()).presets; } catch { /* ignore */ }
  await loadOverrides();
});
</script>
