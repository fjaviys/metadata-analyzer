<template>
  <div>
    <!-- ayuda -->
    <div class="mb-3 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
      Por archivo, decide si se mantiene su fecha actual o se corrige usando la
      fecha detectada en el <b>nombre de archivo</b> o en la <b>carpeta
      contenedora</b>. Sin decisión, no se toca nada.
    </div>

    <!-- barra de multiselección de archivos -->
    <div v-if="selectedFiles.size > 0"
         class="mb-2 flex flex-wrap items-center gap-2 rounded-lg border border-brand-200 bg-brand-50 px-3 py-2 text-sm">
      <span class="font-medium text-brand-700">{{ selectedFiles.size }} archivo(s):</span>
      <button class="btn-ghost py-1 text-xs" @click="bulkAction('keep')">Mantener</button>
      <button class="btn-ghost py-1 text-xs" @click="bulkAction('filename')">Nombre de archivo</button>
      <button class="btn-ghost py-1 text-xs" @click="bulkAction('folder')">Carpeta contenedora</button>
      <button class="ml-auto text-xs text-slate-500 hover:underline" @click="selectedFiles.clear()">
        limpiar selección
      </button>
    </div>

    <div class="mb-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
      <button class="hover:underline" @click="collapsed = new Set(allFolders)">Colapsar todo</button>
      <span>·</span>
      <button class="hover:underline" @click="collapsed = new Set()">Expandir todo</button>
      <span>·</span>
      <button class="hover:underline" @click="selectNeedsCorrection">
        Seleccionar los que necesitan corrección ({{ needsCorrectionCount }})
      </button>
    </div>

    <div class="divide-y divide-slate-100">
      <template v-for="item in visible" :key="item.key">
        <!-- carpeta -->
        <div v-if="item.type === 'folder'"
             class="flex items-center gap-2 py-1.5 text-sm"
             :style="{ paddingLeft: item.depth * 16 + 'px' }">
          <input type="checkbox" :checked="selectedFolders.has(item.path!)"
                 @change="toggleFolderCascade(item.path!)" class="rounded border-slate-300"
                 title="Selecciona/deselecciona esta carpeta y todo su contenido" />
          <button class="text-slate-400 w-4" @click="toggle(item.path!)">
            {{ collapsed.has(item.path!) ? '▸' : '▾' }}
          </button>
          <span>📁</span>
          <span class="font-medium text-slate-700">{{ item.name }}</span>
          <span class="text-xs text-slate-400">({{ item.count }})</span>
        </div>

        <!-- archivo -->
        <div v-else class="flex flex-wrap items-center gap-3 py-1.5 text-sm"
             :style="{ paddingLeft: item.depth * 16 + 8 + 'px' }">
          <input type="checkbox" :checked="selectedFiles.has(item.file!.path)"
                 @click="onFileCheckboxClick($event, item.file!.path)" class="rounded border-slate-300"
                 title="Clic: solo este · Ctrl/Cmd+clic: añadir/quitar · Shift+clic: rango" />
          <span class="text-slate-400">🖼️</span>
          <span class="truncate text-slate-700" :title="item.file!.path">{{ fileName(item.file!.path) }}</span>
          <span class="text-xs text-slate-400 font-mono">{{ item.file!.exif_date || 'sin fecha' }}</span>
          <span v-if="item.file!.needs_correction" class="rounded bg-amber-50 px-1.5 text-[10px] text-amber-700">
            necesita corrección
          </span>

          <div class="ml-auto flex flex-wrap items-center gap-3 text-xs">
            <label class="flex items-center gap-1">
              <input type="radio" :name="'k-'+item.file!.path"
                     :checked="decisionKind(item.file!.path) === 'keep'"
                     @change="setDecision(item.file!.path, 'keep')" />
              Mantener
            </label>
            <label class="flex items-center gap-1" :class="{ 'opacity-40': !item.file!.filename_date }">
              <input type="radio" :name="'k-'+item.file!.path" :disabled="!item.file!.filename_date"
                     :checked="decisionKind(item.file!.path) === 'filename'"
                     @change="setDecision(item.file!.path, 'filename')" />
              Nombre de archivo
              <span class="font-mono text-slate-400">{{ item.file!.filename_date || '—' }}</span>
            </label>
            <label class="flex items-center gap-1" :class="{ 'opacity-40': !item.file!.path_date }">
              <input type="radio" :name="'k-'+item.file!.path" :disabled="!item.file!.path_date"
                     :checked="decisionKind(item.file!.path) === 'folder'"
                     @change="setDecision(item.file!.path, 'folder')" />
              Carpeta contenedora
              <span class="font-mono text-slate-400">{{ item.file!.path_date || '—' }}</span>
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
import type { AnalyzedFile } from '../types/api';

const props = defineProps<{ sessionId: number; root?: string; files: AnalyzedFile[] }>();
const emit = defineEmits<{ (e: 'changed'): void }>();

const decisions = reactive<Record<string, string>>({});   // path -> kind
const collapsed = ref<Set<string>>(new Set());
const selectedFiles = reactive<Set<string>>(new Set());
const selectedFolders = reactive<Set<string>>(new Set());
const lastClickedFileIndex = ref<number | null>(null);

const needsCorrectionCount = computed(() => props.files.filter((f) => f.needs_correction).length);

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
  const { folders, files } = collectDescendants(node);
  const nowSelected = !selectedFolders.has(folderPath);
  const apply = (set: Set<string>, keys: string[]) => {
    for (const k of keys) { nowSelected ? set.add(k) : set.delete(k); }
  };
  apply(selectedFolders, [folderPath, ...folders]);
  apply(selectedFiles, files);
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

function onFileCheckboxClick(e: MouseEvent, path: string) {
  e.preventDefault();
  const fileItems = visible.value.filter((i) => i.type === 'file');
  const idx = fileItems.findIndex((i) => i.file!.path === path);

  if (e.shiftKey && lastClickedFileIndex.value !== null) {
    const [a, b] = [lastClickedFileIndex.value, idx].sort((x, y) => x - y);
    for (let i = a; i <= b; i++) selectedFiles.add(fileItems[i].file!.path);
  } else if (e.ctrlKey || e.metaKey) {
    selectedFiles.has(path) ? selectedFiles.delete(path) : selectedFiles.add(path);
    lastClickedFileIndex.value = idx;
  } else {
    selectedFiles.clear();
    selectedFiles.add(path);
    lastClickedFileIndex.value = idx;
  }
}

function selectNeedsCorrection() {
  selectedFiles.clear();
  for (const f of props.files) if (f.needs_correction) selectedFiles.add(f.path);
}

function decisionKind(path: string): string {
  return decisions[path] ?? 'keep';
}

async function setDecision(path: string, kind: 'keep' | 'filename' | 'folder') {
  await api.setFileOverride({ session_id: props.sessionId, path, kind });
  decisions[path] = kind;
  emit('changed');
}

async function bulkAction(kind: 'keep' | 'filename' | 'folder') {
  for (const path of selectedFiles) {
    const file = props.files.find((f) => f.path === path);
    if (kind === 'filename' && !file?.filename_date) continue;
    if (kind === 'folder' && !file?.path_date) continue;
    await api.setFileOverride({ session_id: props.sessionId, path, kind });
    decisions[path] = kind;
  }
  selectedFiles.clear();
  emit('changed');
}

onMounted(async () => {
  try {
    const fo = await api.listFileOverrides(props.sessionId);
    for (const o of fo.file_overrides) decisions[o.path] = o.kind;
  } catch { /* sesión nueva: sin decisiones previas */ }
});
</script>
