<template>
  <div>
    <!-- ayuda -->
    <div class="mb-3 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
      Por carpeta, decide si se mantiene su estructura o se agrupan sus
      archivos por fecha en subcarpetas. La carpeta raíz analizada nunca se
      mueve. Una carpeta hija hereda de su padre hasta que la cambias
      explícitamente. Formatos recomendados: <code>AAAA/MM</code>,
      <code>AAAA/MM/DD</code>, <code>AAAA-MM</code>.
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
                 @change="toggleFolderCascade(item.path!)" class="rounded border-slate-300"
                 title="Selecciona/deselecciona esta carpeta y sus subcarpetas" />
          <button class="text-slate-400 w-4" @click="toggle(item.path!)">
            {{ collapsed.has(item.path!) ? '▸' : '▾' }}
          </button>
          <span>📁</span>
          <span class="font-medium text-slate-700">{{ item.name }}</span>
          <span class="text-xs text-slate-400">({{ item.count }})</span>

          <div class="ml-2 flex items-center gap-1 rounded-full bg-slate-100 p-0.5 text-[11px]">
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
          <span v-if="effectiveFor(item.path!).structure_mode === 'update' && folderDestinations(item.path!).length"
                class="text-xs text-amber-700">
            → {{ folderDestinations(item.path!).slice(0, 4).map(relTo(item.path!)).join(', ') }}<template
              v-if="folderDestinations(item.path!).length > 4">, +{{ folderDestinations(item.path!).length - 4 }} más</template>
          </span>
        </div>

        <!-- archivo (solo lectura) -->
        <div v-else class="flex flex-wrap items-center gap-2 py-1.5 text-sm"
             :style="{ paddingLeft: item.depth * 16 + 8 + 'px' }">
          <span class="text-slate-400">🖼️</span>
          <span class="truncate text-slate-700" :title="item.file!.path">{{ fileName(item.file!.path) }}</span>
          <span class="text-xs text-slate-400 font-mono">{{ item.file!.exif_date || 'sin fecha' }}</span>
          <span v-if="moveDestination(item.file!.path)"
                class="rounded bg-amber-50 px-1.5 text-[10px] text-amber-700 font-mono">
            → {{ moveDestination(item.file!.path) }}
          </span>
          <span v-else-if="skipReason(item.file!.path)"
                class="rounded bg-slate-100 px-1.5 text-[10px] text-slate-500"
                :title="skipReason(item.file!.path)">sin mover</span>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { api } from '../api/client';
import type { AnalyzedFile, FolderDecision, ReorganizePreviewResult, StructureMode } from '../types/api';

const props = defineProps<{ sessionId: number; root?: string; files: AnalyzedFile[];
                            preview?: ReorganizePreviewResult | null }>();
const emit = defineEmits<{ (e: 'changed'): void }>();

// --- previsualización ---
const movesByPath = computed(() => {
  const m = new Map<string, { after_dir?: string; skip_reason?: string }>();
  for (const mv of props.preview?.moves ?? []) m.set(mv.path, mv);
  return m;
});
function rawDestination(path: string): string | null {
  return movesByPath.value.get(path)?.after_dir ?? null;
}
function moveDestination(path: string): string | null {
  const dir = rawDestination(path);
  if (!dir) return null;
  const r = (props.root || '').replace(/\/+$/, '');
  return (r && dir.startsWith(r + '/') ? dir.slice(r.length + 1) : dir) + '/';
}
function skipReason(path: string): string | null {
  return movesByPath.value.get(path)?.skip_reason ?? null;
}
function relTo(base: string) {
  const b = base.replace(/\/+$/, '');
  return (dir: string) => (dir.startsWith(b + '/') ? dir.slice(b.length + 1) : dir) + '/';
}
function folderDestinations(folderPath: string): string[] {
  const { files } = collectDescendants(nodeByPath.value.get(folderPath)!);
  const dirs = new Set<string>();
  for (const p of files) {
    const d = rawDestination(p);
    if (d) dirs.add(d);
  }
  return [...dirs].sort();
}

// --- decisiones por carpeta ---
const decisions = reactive<Record<string, FolderDecision>>({});
const DEFAULT_DECISION = { structure_mode: 'keep' as StructureMode, structure_layout: null as string | null };

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

async function setFolder(folder: string, fields: { structure_mode?: StructureMode;
                         structure_layout?: string; clear_structure_layout?: boolean }) {
  const res = await api.setStructureFolderDecision({ session_id: props.sessionId, folder, ...fields });
  decisions[folder] = res;
  emit('changed');
}

const collapsed = ref<Set<string>>(new Set());
const selectedFolders = reactive<Set<string>>(new Set());
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

const nodeByPath = computed(() => {
  const m = new Map<string, Node>();
  const walk = (n: Node) => { m.set(n.path, n); for (const c of n.folders.values()) walk(c); };
  walk(tree.value);
  return m;
});

function collectDescendants(node: Node): { folders: string[]; files: string[] } {
  const folders: string[] = [];
  const files: string[] = [];
  const walk = (n: Node) => {
    for (const c of n.folders.values()) { folders.push(c.path); walk(c); }
    files.push(...n.files.map((f) => f.path));
  };
  walk(node);
  return { folders, files };
}

function toggleFolderCascade(folderPath: string) {
  const node = nodeByPath.value.get(folderPath);
  if (!node) return;
  const { folders } = collectDescendants(node);
  const nowSelected = !selectedFolders.has(folderPath);
  const apply = (set: Set<string>, keys: string[]) => {
    for (const k of keys) { nowSelected ? set.add(k) : set.delete(k); }
  };
  apply(selectedFolders, [folderPath, ...folders]);
}

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

// --- bulk: carpetas seleccionadas ---
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
    const fd = await api.listStructureFolderDecisions(props.sessionId);
    for (const d of fd.decisions) decisions[d.folder] = d;
  } catch { /* sesión nueva: sin decisiones previas */ }
});
</script>
