<template>
  <div>
    <!-- ayuda -->
    <div class="mb-3 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
      <b>1.</b> Selecciona: clic en una carpeta marca todos sus archivos; en la lista,
      clic selecciona uno, <b>Ctrl+clic</b> añade o quita y <b>Mayús+clic</b> marca un rango.
      <b>2.</b> Pulsa el patrón que quieres aplicar a la selección. Verás al instante
      la fecha resultante y la acción de cada archivo. Sin decisión, no se toca nada.
    </div>

    <!-- resumen -->
    <div class="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-600">
      <span><b>{{ files.length }}</b> archivos</span>
      <span class="text-brand-700"><b>{{ willCorrectCount }}</b> se corregirán</span>
      <span><b>{{ files.length - willCorrectCount }}</b> se mantienen</span>
      <span v-if="notApplicableCount" class="text-amber-700">
        <b>{{ notApplicableCount }}</b> sin fecha en la fuente elegida
      </span>
    </div>

    <!-- barra de acciones sobre la selección -->
    <div v-if="selectedFiles.size > 0"
         class="sticky top-0 z-10 mb-2 flex flex-wrap items-center gap-2 rounded-lg border border-brand-200 bg-brand-50 px-3 py-2 text-sm">
      <span class="font-medium text-brand-700">{{ selectedFiles.size }} seleccionado(s) →</span>
      <button class="btn-ghost py-1 text-xs" :disabled="applying" @click="applyToSelection('keep')">
        Mantener
      </button>
      <button class="btn-ghost py-1 text-xs" :disabled="applying" @click="applyToSelection('filename')">
        Nombre de archivo
      </button>
      <button class="btn-ghost py-1 text-xs" :disabled="applying" @click="applyToSelection('folder')">
        Carpeta contenedora
      </button>
      <span v-if="lastApply" class="text-xs" :class="lastApply.skipped ? 'text-amber-700' : 'text-slate-500'">
        {{ lastApply.text }}
      </span>
      <button class="ml-auto text-xs text-slate-500 hover:underline" @click="clearSelection">
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
      <span>·</span>
      <button class="hover:underline" @click="selectAll">Seleccionar todo</button>
    </div>

    <div class="divide-y divide-slate-100">
      <template v-for="item in visible" :key="item.key">
        <!-- carpeta -->
        <div v-if="item.type === 'folder'"
             class="flex items-center gap-2 py-1.5 text-sm"
             :style="{ paddingLeft: item.depth * 16 + 'px' }">
          <input type="checkbox" class="rounded border-slate-300"
                 :checked="folderState(item.path!) === 'all'"
                 :indeterminate.prop="folderState(item.path!) === 'some'"
                 @change="toggleFolderCascade(item.path!)"
                 title="Selecciona/deselecciona todos los archivos de esta carpeta" />
          <button class="w-4 text-slate-400" @click="toggle(item.path!)">
            {{ collapsed.has(item.path!) ? '▸' : '▾' }}
          </button>
          <span>📁</span>
          <span class="font-medium text-slate-700">{{ item.name }}</span>
          <span class="text-xs text-slate-400">({{ item.count }})</span>
        </div>

        <!-- archivo -->
        <div v-else
             class="flex cursor-pointer select-none flex-wrap items-center gap-3 py-1.5 text-sm"
             :class="selectedFiles.has(item.file!.path) ? 'bg-brand-50' : 'hover:bg-slate-50'"
             :style="{ paddingLeft: item.depth * 16 + 8 + 'px' }"
             @click="onFileClick($event, item.file!.path)">
          <input type="checkbox" class="pointer-events-none rounded border-slate-300"
                 :checked="selectedFiles.has(item.file!.path)" tabindex="-1" />
          <span class="text-slate-400">🖼️</span>
          <span class="truncate text-slate-700" :title="item.file!.path">
            {{ fileName(item.file!.path) }}
          </span>

          <!-- origen → resultado -->
          <span class="font-mono text-xs text-slate-400">{{ item.file!.exif_date || 'sin fecha' }}</span>
          <span class="text-xs text-slate-300">→</span>
          <span class="font-mono text-xs"
                :class="resultOf(item.file!) ? 'text-brand-700' : 'text-slate-300'">
            {{ resultOf(item.file!) || '—' }}
          </span>

          <!-- acción -->
          <span class="ml-auto flex items-center gap-2 text-xs">
            <span v-if="item.file!.needs_correction && decisionKind(item.file!.path) === 'keep'"
                  class="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-700">
              necesita corrección
            </span>
            <span v-if="notApplicable(item.file!)"
                  class="rounded bg-amber-100 px-2 py-0.5 text-[11px] text-amber-800">
              no aplicable · {{ notApplicable(item.file!) }}
            </span>
            <span v-else class="rounded px-2 py-0.5 text-[11px]"
                  :class="decisionKind(item.file!.path) === 'keep'
                    ? 'bg-slate-100 text-slate-600' : 'bg-brand-100 text-brand-800'">
              {{ ACTION_LABELS[decisionKind(item.file!.path)] }}
            </span>
          </span>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { api } from '../api/client';
import type { AnalyzedFile } from '../types/api';

type Kind = 'keep' | 'filename' | 'folder';

const props = defineProps<{ sessionId: number; root?: string; files: AnalyzedFile[] }>();
const emit = defineEmits<{ (e: 'changed'): void }>();

const ACTION_LABELS: Record<string, string> = {
  keep: 'Mantener',
  filename: 'Nombre de archivo',
  folder: 'Carpeta contenedora',
};

const decisions = reactive<Record<string, Kind>>({});   // path -> kind
const collapsed = ref<Set<string>>(new Set());
// selectedFiles es la ÚNICA fuente de verdad de la selección: el estado del
// checkbox de carpeta se deriva de ella (nunca se desincronizan).
const selectedFiles = reactive<Set<string>>(new Set());
const anchorPath = ref<string | null>(null);            // ancla del rango Mayús+clic
const applying = ref(false);
const lastApply = ref<{ text: string; skipped: boolean } | null>(null);
// archivos que se quedaron fuera del último patrón aplicado (su fuente no
// tenía fecha): se marcan en la fila, no se omiten en silencio.
const skipped = reactive<Set<string>>(new Set());
const skippedKind = ref<Kind | null>(null);

const fileByPath = computed(() => {
  const m = new Map<string, AnalyzedFile>();
  for (const f of props.files) m.set(f.path, f);
  return m;
});

function decisionKind(path: string): Kind {
  return decisions[path] ?? 'keep';
}
/** Fecha de la fuente elegida (ya calculada en el análisis), o null. */
function sourceDate(file: AnalyzedFile, kind: Kind): string | null {
  if (kind === 'filename') return file.filename_date || null;
  if (kind === 'folder') return file.path_date || null;
  return null;
}
/** Resultado que se escribiría; null si se mantiene o si la fuente no tiene fecha. */
function resultOf(file: AnalyzedFile): string | null {
  return sourceDate(file, decisionKind(file.path));
}
const SOURCE_LABELS: Record<string, string> = {
  filename: 'sin fecha en el nombre',
  folder: 'sin fecha en la carpeta',
};
/**
 * Motivo por el que este archivo NO se va a corregir pese a que se le pidió:
 * o bien tiene una decisión guardada cuya fuente no tiene fecha, o bien se
 * quedó fuera del último patrón aplicado. Se avisa en la fila en vez de
 * omitirlo en silencio.
 */
function notApplicable(file: AnalyzedFile): string | null {
  const kind = decisionKind(file.path);
  if (kind !== 'keep' && !resultOf(file)) return SOURCE_LABELS[kind];
  if (skippedKind.value && skipped.has(file.path)) return SOURCE_LABELS[skippedKind.value];
  return null;
}

const needsCorrectionCount = computed(() => props.files.filter((f) => f.needs_correction).length);
const willCorrectCount = computed(() => props.files.filter((f) => !!resultOf(f)).length);
const notApplicableCount = computed(() => props.files.filter(notApplicable).length);

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

/** Estado del checkbox de carpeta, derivado de sus archivos descendientes. */
function folderState(folderPath: string): 'none' | 'some' | 'all' {
  const node = nodeByPath.value.get(folderPath);
  if (!node) return 'none';
  const { files } = collectDescendants(node);
  if (!files.length) return 'none';
  let sel = 0;
  for (const p of files) if (selectedFiles.has(p)) sel++;
  return sel === 0 ? 'none' : sel === files.length ? 'all' : 'some';
}

function toggleFolderCascade(folderPath: string) {
  const node = nodeByPath.value.get(folderPath);
  if (!node) return;
  const { files } = collectDescendants(node);
  const select = folderState(folderPath) !== 'all';   // parcial o vacía -> seleccionar todo
  for (const p of files) select ? selectedFiles.add(p) : selectedFiles.delete(p);
  anchorPath.value = select && files.length ? files[0] : null;
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
    for (const f of n.files) out.push({ type: 'file', key: f.path, depth, file: f });
  };
  walk(tree.value, 0);
  return out;
});

const visibleFilePaths = computed(() =>
  visible.value.filter((i) => i.type === 'file').map((i) => i.file!.path));

function toggle(path: string) {
  const s = new Set(collapsed.value);
  s.has(path) ? s.delete(path) : s.add(path);
  collapsed.value = s;
}
function fileName(p: string) { return p.split('/').pop(); }

function onFileClick(e: MouseEvent, path: string) {
  const paths = visibleFilePaths.value;
  const ctrl = e.ctrlKey || e.metaKey;

  // El ancla se guarda como PATH (no como índice): plegar/desplegar carpetas
  // entre dos clics ya no descuadra el rango.
  if (e.shiftKey && anchorPath.value !== null) {
    const from = paths.indexOf(anchorPath.value);
    const to = paths.indexOf(path);
    if (from !== -1 && to !== -1) {
      if (!ctrl) selectedFiles.clear();                 // Mayús reemplaza; Ctrl+Mayús amplía
      const [a, b] = from <= to ? [from, to] : [to, from];
      for (let i = a; i <= b; i++) selectedFiles.add(paths[i]);
      return;
    }
  }
  if (ctrl) {
    selectedFiles.has(path) ? selectedFiles.delete(path) : selectedFiles.add(path);
  } else {
    selectedFiles.clear();
    selectedFiles.add(path);
  }
  anchorPath.value = path;
}

function selectNeedsCorrection() {
  selectedFiles.clear();
  for (const f of props.files) if (f.needs_correction) selectedFiles.add(f.path);
  anchorPath.value = null;
}
function selectAll() {
  for (const p of visibleFilePaths.value) selectedFiles.add(p);
}
function clearSelection() {
  selectedFiles.clear();
  anchorPath.value = null;
  lastApply.value = null;
  skipped.clear();
  skippedKind.value = null;
}

async function applyToSelection(kind: Kind) {
  const paths = [...selectedFiles];
  const applicable: string[] = [];
  skipped.clear();
  skippedKind.value = kind === 'keep' ? null : kind;
  for (const p of paths) {
    const file = fileByPath.value.get(p);
    if (kind !== 'keep' && (!file || !sourceDate(file, kind))) { skipped.add(p); continue; }
    applicable.push(p);
  }

  // 1) pintado inmediato (los datos ya están en cada fila: no hace falta esperar al backend)
  for (const p of applicable) decisions[p] = kind;
  const source = kind === 'filename' ? 'el nombre' : 'la carpeta';
  lastApply.value = {
    text: skipped.size
      ? `aplicado a ${applicable.length} · ${skipped.size} omitidos (sin fecha en ${source})`
      : `aplicado a ${applicable.length}`,
    skipped: skipped.size > 0,
  };
  if (!applicable.length) return;

  // 2) una sola petición para toda la selección (no se limpia: el usuario ve lo que cambió)
  applying.value = true;
  try {
    await api.setFileOverridesBulk({ session_id: props.sessionId, paths: applicable, kind });
    emit('changed');
  } catch (e) {
    lastApply.value = { text: `error al guardar: ${String(e)}`, skipped: true };
  } finally {
    applying.value = false;
  }
}

onMounted(async () => {
  try {
    const fo = await api.listFileOverrides(props.sessionId);
    for (const o of fo.file_overrides) decisions[o.path] = o.kind as Kind;
  } catch { /* sesión nueva: sin decisiones previas */ }
});
</script>
