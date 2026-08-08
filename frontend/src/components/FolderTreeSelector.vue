<template>
  <div class="card">
    <div class="mb-3 flex items-center justify-between">
      <p class="font-semibold text-slate-700">Selecciona carpetas a corregir</p>
      <div class="flex gap-2">
        <button class="text-xs text-brand-600 hover:underline" @click="selectAll">Todas</button>
        <button class="text-xs text-slate-500 hover:underline" @click="clear">Ninguna</button>
      </div>
    </div>

    <p v-if="tree.length === 0" class="text-sm text-slate-400">Sin carpetas.</p>

    <ul class="space-y-1">
      <li v-for="node in tree" :key="node.folder">
        <div class="flex items-center gap-2 rounded px-2 py-1 hover:bg-slate-50">
          <input type="checkbox" :checked="isSelected(node.folder)"
                 @change="toggle(node.folder)" class="rounded border-slate-300" />
          <button v-if="node.children?.length" class="text-slate-400"
                  @click="expanded[node.folder] = !expanded[node.folder]">
            {{ expanded[node.folder] ? '▾' : '▸' }}
          </button>
          <span v-else class="w-3"></span>
          <span class="flex-1 text-sm font-medium text-slate-700">{{ node.folder }}</span>
          <span class="text-xs text-slate-400">
            {{ node.total }} archivos
            <span v-if="node.needs" class="text-amber-600">· {{ node.needs }} a corregir</span>
          </span>
        </div>

        <ul v-if="expanded[node.folder] && node.children?.length" class="ml-6 space-y-1">
          <li v-for="child in node.children" :key="child.folder"
              class="flex items-center gap-2 rounded px-2 py-1 hover:bg-slate-50">
            <input type="checkbox" :checked="isSelected(child.folder)"
                   @change="toggle(child.folder)" class="rounded border-slate-300" />
            <span class="w-3"></span>
            <span class="flex-1 text-sm text-slate-600">{{ child.folder }}</span>
            <span class="text-xs text-slate-400">
              {{ child.total }}
              <span v-if="child.needs" class="text-amber-600">· {{ child.needs }}</span>
            </span>
          </li>
        </ul>
      </li>
    </ul>

    <p class="mt-3 text-xs text-slate-500">
      {{ selected.length === 0 ? 'Ninguna seleccionada → se aplicará a TODAS las carpetas.'
                               : `${selected.length} carpeta(s) seleccionada(s).` }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue';
import type { FolderNode } from '../types/api';

const props = defineProps<{ tree: FolderNode[] }>();
const emit = defineEmits<{ (e: 'update:selected', v: string[]): void }>();

const selected = ref<string[]>([]);
const expanded = reactive<Record<string, boolean>>({});

const isSelected = (f: string) => selected.value.includes(f);

function toggle(folder: string) {
  const i = selected.value.indexOf(folder);
  if (i >= 0) selected.value.splice(i, 1);
  else selected.value.push(folder);
}
function selectAll() {
  selected.value = props.tree.map((n) => n.folder);
}
function clear() {
  selected.value = [];
}

watch(selected, (v) => emit('update:selected', [...v]), { deep: true });
</script>
