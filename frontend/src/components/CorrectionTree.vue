<template>
  <div>
    <!-- ayuda de formatos -->
    <div class="mb-3 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
      <b>Formatos recomendados (ISO):</b> <code>AAAA-MM-DD</code>, <code>AAAA-MM</code>, <code>AAAA</code>.
      Para entrada manual usa tokens: <code>AAAA</code> (año), <code>AA</code> (año 2 cifras),
      <code>MM</code> (mes), <code>DD</code> (día), <code>hh mm ss</code> (hora). Los separadores
      son opcionales: <code>DDMMAAAA</code> reconoce <code>02102009</code>.
    </div>

    <div class="mb-2 flex items-center gap-2 text-xs text-slate-500">
      <button class="hover:underline" @click="collapsed = new Set(allFolders)">Colapsar todo</button>
      <span>·</span>
      <button class="hover:underline" @click="collapsed = new Set()">Expandir todo</button>
    </div>

    <div class="divide-y divide-slate-100">
      <template v-for="item in visible" :key="item.key">
        <!-- carpeta -->
        <div v-if="item.type === 'folder'"
             class="flex items-center gap-1 py-1 text-sm"
             :style="{ paddingLeft: item.depth * 16 + 'px' }">
          <button class="text-slate-400 w-4" @click="toggle(item.path)">
            {{ collapsed.has(item.path) ? '▸' : '▾' }}
          </button>
          <span>📁</span>
          <span class="font-medium text-slate-700">{{ item.name }}</span>
          <span class="text-xs text-slate-400">({{ item.count }})</span>
        </div>

        <!-- archivo -->
        <div v-else class="py-1.5" :style="{ paddingLeft: item.depth * 16 + 8 + 'px' }">
          <div class="flex flex-wrap items-center gap-2 text-sm">
            <span class="text-slate-400">🖼️</span>
            <span class="truncate text-slate-700" :title="item.row.path">{{ fileName(item.row.path) }}</span>
            <span class="text-xs text-slate-400 font-mono">{{ item.row.original_value || 'sin fecha' }}</span>
            <span class="text-slate-300">→</span>
            <span class="text-xs font-mono"
                  :class="decisionClass(item.row.path)">{{ displayValue(item.row) }}</span>
            <span v-if="decisions[item.row.path]"
                  class="rounded bg-brand-50 px-1.5 text-[10px] text-brand-700">
              {{ decisionLabel(item.row.path) }}
            </span>
            <button class="ml-auto text-xs text-brand-600 hover:underline"
                    @click="openAction(item.row.path)">
              {{ activePath === item.row.path ? 'cerrar' : 'acción' }}
            </button>
          </div>

          <!-- panel de acción -->
          <div v-if="activePath === item.row.path"
               class="mt-2 space-y-2 rounded-lg border border-slate-200 bg-white p-3 text-sm">
            <label class="flex items-center gap-2">
              <input type="radio" :name="'a-'+item.row.path" :checked="!decisions[item.row.path]"
                     @change="keepRecommendation(item.row.path)" />
              <span>Mantener recomendación
                <span class="font-mono text-xs text-slate-500">({{ item.row.new_value || '—' }})</span></span>
            </label>

            <div v-if="loadingOptions" class="pl-6"><LoadingSpinner label="Cargando opciones…" /></div>
            <label v-for="o in options" :key="o.source" class="flex items-center gap-2">
              <input type="radio" :name="'a-'+item.row.path"
                     :checked="isChosen(item.row.path, o.value)"
                     @change="chooseValue(item.row.path, o)" />
              <span>{{ o.label }}
                <span class="font-mono text-xs text-slate-700">{{ o.value }}</span>
                <span v-if="o.precision" class="text-[10px] text-slate-400">· {{ o.precision }}</span></span>
            </label>

            <label class="flex items-start gap-2">
              <input type="radio" :name="'a-'+item.row.path"
                     :checked="decisions[item.row.path]?.kind === 'date_pattern'"
                     @change="manualMode[item.row.path] = true" />
              <span class="flex-1">
                Entrada manual (patrón)
                <div class="mt-1 flex gap-2">
                  <input v-model="manualPattern" class="input font-mono py-1 text-xs" placeholder="DD-MM-AAAA" />
                  <button class="btn-ghost py-1 text-xs" @click="applyManual(item.row.path)">Aplicar</button>
                </div>
                <span v-if="manualError" class="text-xs text-red-600">{{ manualError }}</span>
              </span>
            </label>

            <label class="flex items-center gap-2">
              <input type="radio" :name="'a-'+item.row.path"
                     :checked="decisions[item.row.path]?.kind === 'skip'"
                     @change="chooseSkip(item.row.path)" />
              <span>No cambiar este archivo</span>
            </label>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import { api } from '../api/client';
import type { CorrectionRow } from '../types/api';
import LoadingSpinner from './LoadingSpinner.vue';

const props = defineProps<{ sessionId: number; root?: string; rows: CorrectionRow[] }>();
const emit = defineEmits<{ (e: 'changed'): void }>();

type Decision = { kind: string; value?: string; label: string };
const decisions = reactive<Record<string, Decision>>({});
const collapsed = ref<Set<string>>(new Set());
const activePath = ref('');
const options = ref<Array<{ source: string; label: string; value: string; precision: string | null }>>([]);
const loadingOptions = ref(false);
const manualMode = reactive<Record<string, boolean>>({});
const manualPattern = ref('');
const manualError = ref('');

// --- construir árbol carpeta→archivos a partir de las rutas ---
interface Node { name: string; path: string; folders: Map<string, Node>; files: CorrectionRow[]; count: number }
function newNode(name: string, path: string): Node {
  return { name, path, folders: new Map(), files: [], count: 0 };
}
const tree = computed(() => {
  const rootPath = (props.root || '').replace(/\/+$/, '');
  const root = newNode(rootPath || '/', rootPath || '');
  for (const row of props.rows) {
    let rel = row.path;
    if (rootPath && rel.startsWith(rootPath + '/')) rel = rel.slice(rootPath.length + 1);
    const parts = rel.split('/');
    const folders = parts.slice(0, -1);
    let node = root;
    let acc = rootPath;
    for (const f of folders) {
      acc = acc ? acc + '/' + f : f;
      if (!node.folders.has(f)) node.folders.set(f, newNode(f, acc));
      node = node.folders.get(f)!;
    }
    node.files.push(row);
  }
  return root;
});

const allFolders = computed(() => {
  const acc: string[] = [];
  const walk = (n: Node) => { for (const c of n.folders.values()) { acc.push(c.path); walk(c); } };
  walk(tree.value);
  return acc;
});

// recuento por carpeta
function countNode(n: Node): number {
  n.count = n.files.length;
  for (const c of n.folders.values()) n.count += countNode(c);
  return n.count;
}

interface Item { type: 'folder' | 'file'; key: string; depth: number; name?: string;
                 path?: string; count?: number; row?: CorrectionRow }
const visible = computed<Item[]>(() => {
  countNode(tree.value);
  const out: Item[] = [];
  const walk = (n: Node, depth: number) => {
    const folders = [...n.folders.values()].sort((a, b) => a.name.localeCompare(b.name));
    for (const f of folders) {
      out.push({ type: 'folder', key: 'd:' + f.path, depth, name: f.name, path: f.path, count: f.count });
      if (!collapsed.value.has(f.path)) walk(f, depth + 1);
    }
    for (const row of n.files) {
      out.push({ type: 'file', key: row.path, depth, row });
    }
  };
  walk(tree.value, 0);
  return out;
});

function toggle(path: string) {
  const s = new Set(collapsed.value);
  s.has(path) ? s.delete(path) : s.add(path);
  collapsed.value = s;
}
function fileName(p: string) { return p.split('/').pop(); }

function displayValue(row: CorrectionRow) {
  const d = decisions[row.path];
  if (d) return d.kind === 'skip' ? '(no cambiar)' : (d.value || '—');
  return row.new_value || '—';
}
function decisionClass(path: string) {
  const d = decisions[path];
  if (d?.kind === 'skip') return 'text-slate-400 line-through';
  return d ? 'text-brand-700 font-semibold' : 'text-slate-800';
}
function decisionLabel(path: string) {
  const d = decisions[path];
  return d?.kind === 'skip' ? 'sin cambios' : 'manual';
}
function isChosen(path: string, value: string) {
  const d = decisions[path];
  return d?.kind === 'date_value' && d.value === value;
}

async function openAction(path: string) {
  if (activePath.value === path) { activePath.value = ''; return; }
  activePath.value = path;
  manualError.value = '';
  loadingOptions.value = true;
  try {
    options.value = (await api.getDateOptions(props.sessionId, path)).options;
  } catch { options.value = []; } finally { loadingOptions.value = false; }
}

async function keepRecommendation(path: string) {
  await api.deleteFileOverride(props.sessionId, path);
  delete decisions[path];
  emit('changed');
}
async function chooseValue(path: string, o: { value: string; precision: string | null; label: string }) {
  await api.setFileOverride({ session_id: props.sessionId, path, kind: 'date_value',
    value: o.value, precision: o.precision || undefined });
  decisions[path] = { kind: 'date_value', value: o.value, label: o.label };
  emit('changed');
}
async function chooseSkip(path: string) {
  await api.setFileOverride({ session_id: props.sessionId, path, kind: 'skip' });
  decisions[path] = { kind: 'skip', label: 'no cambiar' };
  emit('changed');
}
async function applyManual(path: string) {
  manualError.value = '';
  try {
    const res = await api.setFileOverride({ session_id: props.sessionId, path,
      kind: 'date_pattern', value: manualPattern.value });
    decisions[path] = { kind: 'date_pattern', value: res.new || undefined, label: 'patrón' };
    emit('changed');
  } catch (e: any) {
    manualError.value = e?.message || 'patrón inválido para este archivo';
  }
}
</script>
