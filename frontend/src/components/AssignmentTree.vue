<template>
  <div>
    <!-- ayuda -->
    <div class="mb-3 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
      Por carpeta hay dos decisiones independientes: <b>metadatos</b> (¿se corrige el
      EXIF?) y <b>estructura</b> (¿se mueve el archivo a una carpeta por fecha?). Una
      carpeta hija hereda de su padre hasta que la cambias explícitamente. Formatos
      recomendados (ISO): <code>AAAA-MM-DD</code>, <code>AAAA-MM</code>, <code>AAAA</code>.
      Tokens para patrón manual: <code>AAAA AA MM DD hh mm ss</code>.
    </div>

    <!-- barra de multiselección de archivos -->
    <div v-if="selectedFiles.size > 0"
         class="mb-2 flex flex-wrap items-center gap-2 rounded-lg border border-brand-200 bg-brand-50 px-3 py-2 text-sm">
      <span class="font-medium text-brand-700">{{ selectedFiles.size }} archivo(s):</span>
      <button class="btn-ghost py-1 text-xs" @click="bulkFilesAction('update')">Actualizar metadatos</button>
      <button class="btn-ghost py-1 text-xs" @click="bulkFilesAction('keep')">Mantener metadatos</button>
      <input v-model="bulkFilePattern" class="input w-40 py-1 text-xs font-mono" placeholder="patrón manual" />
      <button class="btn-ghost py-1 text-xs" :disabled="!bulkFilePattern"
              @click="bulkFilesAction('pattern')">Aplicar patrón</button>
      <button class="ml-auto text-xs text-slate-500 hover:underline" @click="selectedFiles.clear()">
        limpiar selección
      </button>
    </div>

    <!-- barra de multiselección de carpetas -->
    <div v-if="selectedFolders.size > 0"
         class="mb-2 flex flex-wrap items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm">
      <span class="font-medium text-amber-700">{{ selectedFolders.size }} carpeta(s):</span>
      <button class="btn-ghost py-1 text-xs" @click="bulkFoldersAction('update')">Actualizar estructura</button>
      <button class="btn-ghost py-1 text-xs" @click="bulkFoldersAction('keep')">Mantener estructura</button>
      <input v-model="bulkFolderLayout" class="input w-32 py-1 text-xs font-mono" placeholder="AAAA/MM" />
      <button class="btn-ghost py-1 text-xs" :disabled="!bulkFolderLayout"
              @click="bulkFoldersAction('layout')">Aplicar patrón</button>
      <button class="ml-auto text-xs text-slate-500 hover:underline" @click="selectedFolders.clear()">
        limpiar selección
      </button>
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
             class="flex flex-wrap items-center gap-2 py-1.5 text-sm"
             :style="{ paddingLeft: item.depth * 16 + 'px' }">
          <input type="checkbox" :checked="selectedFolders.has(item.path!)"
                 @change="toggleFolderSelect(item.path!)" class="rounded border-slate-300" />
          <button class="text-slate-400 w-4" @click="toggle(item.path!)">
            {{ collapsed.has(item.path!) ? '▸' : '▾' }}
          </button>
          <span>📁</span>
          <span class="font-medium text-slate-700">{{ item.name }}</span>
          <span class="text-xs text-slate-400">({{ item.count }})</span>

          <div class="ml-2 flex items-center gap-1 rounded-full bg-slate-100 p-0.5 text-[11px]">
            <button class="rounded-full px-2 py-0.5"
                    :class="effectiveFor(item.path!).metadata_mode === 'update' ? 'bg-white shadow text-brand-700' : 'text-slate-500'"
                    @click="setFolder(item.path!, { metadata_mode: 'update' })">Metadatos ✓</button>
            <button class="rounded-full px-2 py-0.5"
                    :class="effectiveFor(item.path!).metadata_mode === 'keep' ? 'bg-white shadow text-slate-700' : 'text-slate-500'"
                    @click="setFolder(item.path!, { metadata_mode: 'keep' })">Metadatos =</button>
          </div>
          <div class="flex items-center gap-1 rounded-full bg-slate-100 p-0.5 text-[11px]">
            <button class="rounded-full px-2 py-0.5"
                    :class="effectiveFor(item.path!).structure_mode === 'update' ? 'bg-white shadow text-brand-700' : 'text-slate-500'"
                    @click="setFolder(item.path!, { structure_mode: 'update' })">Estructura ✓</button>
            <button class="rounded-full px-2 py-0.5"
                    :class="effectiveFor(item.path!).structure_mode === 'keep' ? 'bg-white shadow text-slate-700' : 'text-slate-500'"
                    @click="setFolder(item.path!, { structure_mode: 'keep' })">Estructura =</button>
          </div>
          <input v-if="effectiveFor(item.path!).structure_mode === 'update'"
                 class="input w-28 py-0.5 text-xs font-mono"
                 :value="decisions[item.path!]?.structure_layout || ''"
                 placeholder="layout del run"
                 @change="setFolder(item.path!, { structure_layout: ($event.target as HTMLInputElement).value || undefined, clear_structure_layout: !($event.target as HTMLInputElement).value })" />
        </div>

        <!-- archivo -->
        <div v-else class="py-1.5" :style="{ paddingLeft: item.depth * 16 + 8 + 'px' }">
          <div class="flex flex-wrap items-center gap-2 text-sm">
            <input type="checkbox" :checked="selectedFiles.has(item.file!.path)"
                   @change="toggleFileSelect(item.file!.path)" class="rounded border-slate-300" />
            <span class="text-slate-400">🖼️</span>
            <span class="truncate text-slate-700" :title="item.file!.path">{{ fileName(item.file!.path) }}</span>
            <span class="text-xs text-slate-400 font-mono">{{ item.file!.exif_date || 'sin fecha' }}</span>
            <span class="text-slate-300">→</span>
            <span class="text-xs font-mono"
                  :class="decisionClass(item.file!.path)">{{ displayValue(item.file!) }}</span>
            <span v-if="fileDecisions[item.file!.path]"
                  class="rounded bg-brand-50 px-1.5 text-[10px] text-brand-700">
              {{ decisionLabel(item.file!.path) }}
            </span>
            <span v-if="effectiveFor(dirOf(item.file!.path)).structure_mode === 'update'"
                  class="rounded bg-amber-50 px-1.5 text-[10px] text-amber-700">se moverá</span>
            <button class="ml-auto text-xs text-brand-600 hover:underline"
                    @click="openAction(item.file!.path)">
              {{ activePath === item.file!.path ? 'cerrar' : 'acción' }}
            </button>
          </div>

          <!-- panel de acción de metadatos (por archivo) -->
          <div v-if="activePath === item.file!.path"
               class="mt-2 space-y-2 rounded-lg border border-slate-200 bg-white p-3 text-sm">
            <label class="flex items-center gap-2">
              <input type="radio" :name="'a-'+item.file!.path" :checked="!fileDecisions[item.file!.path]"
                     @change="keepRecommendation(item.file!.path)" />
              <span>Mantener recomendación
                <span class="font-mono text-xs text-slate-500">({{ item.file!.recommended_date || '—' }})</span></span>
            </label>

            <div v-if="loadingOptions" class="pl-6"><LoadingSpinner label="Cargando opciones…" /></div>
            <label v-for="o in options" :key="o.source" class="flex items-center gap-2">
              <input type="radio" :name="'a-'+item.file!.path"
                     :checked="isChosen(item.file!.path, o.value)"
                     @change="chooseValue(item.file!.path, o)" />
              <span>{{ o.label }}
                <span class="font-mono text-xs text-slate-700">{{ o.value }}</span>
                <span v-if="o.precision" class="text-[10px] text-slate-400">· {{ o.precision }}</span></span>
            </label>

            <label class="flex items-start gap-2">
              <input type="radio" :name="'a-'+item.file!.path"
                     :checked="fileDecisions[item.file!.path]?.kind === 'date_pattern'"
                     @change="manualMode[item.file!.path] = true" />
              <span class="flex-1">
                Entrada manual (patrón)
                <div class="mt-1 flex gap-2">
                  <input v-model="manualPattern" class="input font-mono py-1 text-xs" placeholder="DD-MM-AAAA" />
                  <button class="btn-ghost py-1 text-xs" @click="applyManual(item.file!.path)">Aplicar</button>
                </div>
                <span v-if="manualError" class="text-xs text-red-600">{{ manualError }}</span>
              </span>
            </label>

            <label class="flex items-center gap-2">
              <input type="radio" :name="'a-'+item.file!.path"
                     :checked="fileDecisions[item.file!.path]?.kind === 'skip'"
                     @change="chooseSkip(item.file!.path)" />
              <span>No cambiar este archivo</span>
            </label>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { api } from '../api/client';
import type { AnalyzedFile, FolderDecision, MetadataMode, StructureMode } from '../types/api';
import LoadingSpinner from './LoadingSpinner.vue';

const props = defineProps<{ sessionId: number; root?: string; files: AnalyzedFile[] }>();
const emit = defineEmits<{ (e: 'changed'): void }>();

// --- decisiones por carpeta ---
const decisions = reactive<Record<string, FolderDecision>>({});
const DEFAULT_DECISION = { metadata_mode: 'update' as MetadataMode,
                           structure_mode: 'keep' as StructureMode, structure_layout: null as string | null };

function isUnder(path: string, folder: string) {
  const f = folder.replace(/\/+$/, '');
  return path === f || path.startsWith(f + '/');
}
function effectiveFor(path: string) {
  let best: FolderDecision | undefined;
  let bestLen = -1;
  for (const folder in decisions) {
    if (isUnder(path, folder) && folder.length > bestLen) { best = decisions[folder]; bestLen = folder.length; }
  }
  return best ?? DEFAULT_DECISION;
}
function dirOf(path: string) { return path.slice(0, path.lastIndexOf('/')) || path; }

async function setFolder(folder: string, fields: { metadata_mode?: MetadataMode;
                         structure_mode?: StructureMode; structure_layout?: string;
                         clear_structure_layout?: boolean }) {
  const res = await api.setFolderDecision({ session_id: props.sessionId, folder, ...fields });
  decisions[folder] = res;
  emit('changed');
}

// --- decisiones por archivo (metadatos) ---
type Decision = { kind: string; value?: string; label: string };
const fileDecisions = reactive<Record<string, Decision>>({});
const collapsed = ref<Set<string>>(new Set());
const activePath = ref('');
const options = ref<Array<{ source: string; label: string; value: string; precision: string | null }>>([]);
const loadingOptions = ref(false);
const manualMode = reactive<Record<string, boolean>>({});
const manualPattern = ref('');
const manualError = ref('');
const selectedFiles = reactive<Set<string>>(new Set());
const selectedFolders = reactive<Set<string>>(new Set());
const bulkFilePattern = ref('');
const bulkFolderLayout = ref('');

// --- árbol carpeta → archivos ---
interface Node { name: string; path: string; folders: Map<string, Node>; files: AnalyzedFile[]; count: number }
function newNode(name: string, path: string): Node {
  return { name, path, folders: new Map(), files: [], count: 0 };
}
const tree = computed(() => {
  const rootPath = (props.root || '').replace(/\/+$/, '');
  const root = newNode(rootPath || '/', rootPath || '');
  for (const f of props.files) {
    let rel = f.path;
    if (rootPath && rel.startsWith(rootPath + '/')) rel = rel.slice(rootPath.length + 1);
    const parts = rel.split('/');
    const folders = parts.slice(0, -1);
    let node = root;
    let acc = rootPath;
    for (const seg of folders) {
      acc = acc ? acc + '/' + seg : seg;
      if (!node.folders.has(seg)) node.folders.set(seg, newNode(seg, acc));
      node = node.folders.get(seg)!;
    }
    node.files.push(f);
  }
  return root;
});

const allFolders = computed(() => {
  const acc: string[] = [];
  const walk = (n: Node) => { for (const c of n.folders.values()) { acc.push(c.path); walk(c); } };
  walk(tree.value);
  return acc;
});

function countNode(n: Node): number {
  n.count = n.files.length;
  for (const c of n.folders.values()) n.count += countNode(c);
  return n.count;
}

interface Item { type: 'folder' | 'file'; key: string; depth: number; name?: string;
                 path?: string; count?: number; file?: AnalyzedFile }
const visible = computed<Item[]>(() => {
  countNode(tree.value);
  const out: Item[] = [];
  const walk = (n: Node, depth: number) => {
    const folders = [...n.folders.values()].sort((a, b) => a.name.localeCompare(b.name));
    for (const f of folders) {
      out.push({ type: 'folder', key: 'd:' + f.path, depth, name: f.name, path: f.path, count: f.count });
      if (!collapsed.value.has(f.path)) walk(f, depth + 1);
    }
    for (const f of n.files) {
      out.push({ type: 'file', key: f.path, depth, file: f });
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
function toggleFileSelect(p: string) { selectedFiles.has(p) ? selectedFiles.delete(p) : selectedFiles.add(p); }
function toggleFolderSelect(p: string) { selectedFolders.has(p) ? selectedFolders.delete(p) : selectedFolders.add(p); }

function displayValue(f: AnalyzedFile) {
  const d = fileDecisions[f.path];
  if (d) return d.kind === 'skip' ? '(no cambiar)' : (d.value || '—');
  return f.recommended_date || '—';
}
function decisionClass(path: string) {
  const d = fileDecisions[path];
  if (d?.kind === 'skip') return 'text-slate-400 line-through';
  return d ? 'text-brand-700 font-semibold' : 'text-slate-800';
}
function decisionLabel(path: string) {
  const d = fileDecisions[path];
  return d?.kind === 'skip' ? 'sin cambios' : 'manual';
}
function isChosen(path: string, value: string) {
  const d = fileDecisions[path];
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
  delete fileDecisions[path];
  emit('changed');
}
async function chooseValue(path: string, o: { value: string; precision: string | null; label: string }) {
  await api.setFileOverride({ session_id: props.sessionId, path, kind: 'date_value',
    value: o.value, precision: o.precision || undefined });
  fileDecisions[path] = { kind: 'date_value', value: o.value, label: o.label };
  emit('changed');
}
async function chooseSkip(path: string) {
  await api.setFileOverride({ session_id: props.sessionId, path, kind: 'skip' });
  fileDecisions[path] = { kind: 'skip', label: 'no cambiar' };
  emit('changed');
}
async function applyManual(path: string) {
  manualError.value = '';
  try {
    const res = await api.setFileOverride({ session_id: props.sessionId, path,
      kind: 'date_pattern', value: manualPattern.value });
    fileDecisions[path] = { kind: 'date_pattern', value: res.new || undefined, label: 'patrón' };
    emit('changed');
  } catch (e: any) {
    manualError.value = e?.message || 'patrón inválido para este archivo';
  }
}

// --- bulk: archivos seleccionados (eje metadatos) ---
async function bulkFilesAction(kind: 'update' | 'keep' | 'pattern') {
  for (const path of selectedFiles) {
    if (kind === 'update') {
      await api.deleteFileOverride(props.sessionId, path);
      delete fileDecisions[path];
    } else if (kind === 'keep') {
      await api.setFileOverride({ session_id: props.sessionId, path, kind: 'skip' });
      fileDecisions[path] = { kind: 'skip', label: 'no cambiar' };
    } else if (kind === 'pattern' && bulkFilePattern.value) {
      try {
        const res = await api.setFileOverride({ session_id: props.sessionId, path,
          kind: 'date_pattern', value: bulkFilePattern.value });
        fileDecisions[path] = { kind: 'date_pattern', value: res.new || undefined, label: 'patrón' };
      } catch { /* archivo sin match para el patrón: se ignora */ }
    }
  }
  selectedFiles.clear();
  emit('changed');
}

// --- bulk: carpetas seleccionadas (eje estructura) ---
async function bulkFoldersAction(kind: 'update' | 'keep' | 'layout') {
  for (const folder of selectedFolders) {
    if (kind === 'update') await setFolder(folder, { structure_mode: 'update' });
    else if (kind === 'keep') await setFolder(folder, { structure_mode: 'keep' });
    else if (kind === 'layout' && bulkFolderLayout.value)
      await setFolder(folder, { structure_mode: 'update', structure_layout: bulkFolderLayout.value });
  }
  selectedFolders.clear();
}

onMounted(async () => {
  try {
    const [fd, fo] = await Promise.all([
      api.listFolderDecisions(props.sessionId), api.listFileOverrides(props.sessionId),
    ]);
    for (const d of fd.decisions) decisions[d.folder] = d;
    for (const o of fo.file_overrides) {
      fileDecisions[o.path] = { kind: o.kind, value: o.value || undefined,
        label: o.kind === 'skip' ? 'no cambiar' : 'manual' };
    }
  } catch { /* sesión nueva: sin decisiones previas */ }
});
</script>
