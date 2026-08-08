<template>
  <div class="card space-y-4">
    <div>
      <label class="label">Tipo de conexión</label>
      <div class="flex gap-2">
        <button v-for="t in types" :key="t.key"
                :class="form.type === t.key ? 'btn-primary' : 'btn-ghost'"
                @click="form.type = t.key">{{ t.label }}</button>
      </div>
    </div>

    <!-- LOCAL -->
    <template v-if="form.type === 'local'">
      <div>
        <label class="label">Ruta de la carpeta de medios</label>
        <input v-model="form.root_path" class="input" placeholder="/media/fotos" />
        <p v-if="roots.length" class="mt-1 text-xs text-slate-400">
          Raíces permitidas: {{ roots.join(', ') }}
        </p>
      </div>
    </template>

    <!-- IMMICH -->
    <template v-else-if="form.type === 'immich'">
      <div>
        <label class="label">URL de Immich</label>
        <input v-model="form.base_url" class="input" placeholder="http://immich:2283" />
      </div>
      <div>
        <label class="label">API Key</label>
        <input v-model="form.api_key" type="password" class="input" placeholder="••••••••" />
      </div>
    </template>

    <!-- OMV -->
    <template v-else>
      <div>
        <label class="label">URL de OpenMediaVault</label>
        <input v-model="form.base_url" class="input" placeholder="http://omv.local" />
      </div>
      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="label">Usuario</label>
          <input v-model="form.username" class="input" />
        </div>
        <div>
          <label class="label">Contraseña</label>
          <input v-model="form.password" type="password" class="input" />
        </div>
      </div>
    </template>

    <div class="flex items-center justify-between border-t border-slate-100 pt-4">
      <ConnectionTester :payload="payload" @result="onResult" />
      <button class="btn-primary" @click="save">Guardar configuración</button>
    </div>

    <AlertBox v-if="saved" variant="success"
              message="Configuración guardada en este navegador. Ya puedes ir a Análisis." />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { api } from '../api/client';
import type { ConnectionTestRequest, ConnectionType } from '../types/api';
import AlertBox from './AlertBox.vue';
import ConnectionTester from './ConnectionTester.vue';

const types: { key: ConnectionType; label: string }[] = [
  { key: 'local', label: 'Sistema de archivos' },
  { key: 'immich', label: 'Immich' },
  { key: 'omv', label: 'OpenMediaVault' },
];

const form = reactive<ConnectionTestRequest>({
  type: 'local', root_path: '', base_url: '', api_key: '', username: '', password: '',
});
const roots = ref<string[]>([]);
const saved = ref(false);

const payload = computed<ConnectionTestRequest>(() => ({ ...form }));

onMounted(async () => {
  try {
    const r = await api.getRoots();
    roots.value = r.allowed_media_roots;
    if (!form.root_path && roots.value.length) form.root_path = roots.value[0];
  } catch { /* ignore */ }
  const stored = localStorage.getItem('ma_config');
  if (stored) Object.assign(form, JSON.parse(stored));
});

function onResult() { saved.value = false; }

function save() {
  localStorage.setItem('ma_config', JSON.stringify(form));
  saved.value = true;
}
</script>
