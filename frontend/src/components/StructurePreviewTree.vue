<template>
  <div>
    <div class="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
      <span class="font-semibold text-slate-700">Resultado con este patrón</span>
      <span class="text-xs text-slate-600">
        <b class="text-brand-700">{{ totalMove }}</b> a mover ·
        <b>{{ totalSkip }}</b> sin mover
      </span>
      <label class="flex items-center gap-1.5 text-xs text-slate-600">
        <input type="checkbox" v-model="onlyMoves" class="rounded border-slate-300" />
        Solo los que se mueven
      </label>
      <span class="ml-auto text-xs text-slate-400">Vista de solo lectura · aún no se ha movido nada</span>
    </div>

    <p v-if="!roots.length" class="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-500">
      Ningún archivo se movería con este patrón.
    </p>

    <div v-for="root in roots" :key="root.dir" class="mb-3 rounded-lg border border-slate-200">
      <button class="flex w-full flex-wrap items-center gap-2 px-3 py-2 text-left text-sm hover:bg-slate-50"
              @click="toggle(root.dir)">
        <span class="w-4 text-slate-400">{{ collapsed.has(root.dir) ? '▸' : '▾' }}</span>
        <span>📁</span>
        <span class="font-medium text-slate-700">{{ shortRoot(root.dir) }}</span>
        <span class="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500">raíz detectada</span>
        <span class="ml-auto text-xs text-slate-500">
          {{ root.items.length }} archivos ·
          <b class="text-brand-700">{{ root.moves }}</b> a mover
        </span>
      </button>

      <div v-if="!collapsed.has(root.dir)" class="divide-y divide-slate-100 border-t border-slate-100">
        <div v-for="it in shown(root)" :key="it.path"
             class="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-1.5 text-sm">
          <span class="text-slate-400">🖼️</span>
          <span class="truncate text-slate-700" :title="it.path">{{ fileName(it.path) }}</span>

          <span class="font-mono text-xs text-slate-400">{{ it.before }}</span>
          <span class="text-xs text-slate-300">→</span>
          <span class="font-mono text-xs" :class="it.after ? 'text-brand-700' : 'text-slate-300'">
            {{ it.after || '—' }}
          </span>

          <span class="ml-auto rounded px-2 py-0.5 text-[11px]"
                :class="it.after ? 'bg-brand-100 text-brand-800' : 'bg-slate-100 text-slate-600'"
                :title="it.reason">
            {{ it.after ? 'mover' : `sin mover · ${it.reason}` }}
          </span>
        </div>

        <p v-if="!shown(root).length" class="px-3 py-1.5 text-xs text-slate-400">
          Ningún archivo de esta carpeta se mueve.
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import type { ReorganizePreviewResult } from '../types/api';

const props = defineProps<{ root?: string; preview: ReorganizePreviewResult }>();

const collapsed = ref<Set<string>>(new Set());
const onlyMoves = ref(false);

interface Item { path: string; before: string; after: string | null; reason: string }
interface Root { dir: string; items: Item[]; moves: number }

/** Ruta relativa a `base` (o a la raíz de la sesión), con '/' final; '.' si coincide. */
function relTo(dir: string | undefined, base: string): string {
  if (!dir) return '—';
  const b = base.replace(/\/+$/, '');
  if (dir === b) return './';
  return (dir.startsWith(b + '/') ? dir.slice(b.length + 1) : dir) + '/';
}

const roots = computed<Root[]>(() => {
  const sessionRoot = (props.root || '').replace(/\/+$/, '');
  const byRoot = new Map<string, Root>();

  for (const mv of props.preview.moves) {
    const dir = mv.base_dir || sessionRoot;
    let entry = byRoot.get(dir);
    if (!entry) { entry = { dir, items: [], moves: 0 }; byRoot.set(dir, entry); }
    const after = mv.after_dir ? relTo(mv.after_dir, dir) : null;
    if (after) entry.moves++;
    entry.items.push({
      path: mv.path,
      before: relTo(mv.before_dir, dir),
      after,
      reason: mv.skip_reason || mv.reason || '',
    });
  }

  return [...byRoot.values()].sort((a, b) => a.dir.localeCompare(b.dir));
});

const totalMove = computed(() => roots.value.reduce((n, r) => n + r.moves, 0));
const totalSkip = computed(() =>
  roots.value.reduce((n, r) => n + r.items.length - r.moves, 0));

function shown(root: Root): Item[] {
  return onlyMoves.value ? root.items.filter((i) => i.after) : root.items;
}
function shortRoot(dir: string): string {
  const r = (props.root || '').replace(/\/+$/, '');
  if (dir === r) return dir;
  return dir.startsWith(r + '/') ? dir.slice(r.length + 1) : dir;
}
function fileName(p: string) { return p.split('/').pop(); }
function toggle(dir: string) {
  const s = new Set(collapsed.value);
  s.has(dir) ? s.delete(dir) : s.add(dir);
  collapsed.value = s;
}
</script>
