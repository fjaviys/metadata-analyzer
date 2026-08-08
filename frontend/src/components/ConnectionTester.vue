<template>
  <div class="space-y-2">
    <button class="btn-ghost" :disabled="testing" @click="test">
      <LoadingSpinner v-if="testing" label="Probando…" />
      <span v-else>Probar conexión</span>
    </button>
    <AlertBox v-if="result" :variant="result.ok ? 'success' : 'error'"
              :message="result.message" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { api, ApiError } from '../api/client';
import type { ConnectionTestRequest, ConnectionTestResult } from '../types/api';
import AlertBox from './AlertBox.vue';
import LoadingSpinner from './LoadingSpinner.vue';

const props = defineProps<{ payload: ConnectionTestRequest }>();
const emit = defineEmits<{ (e: 'result', r: ConnectionTestResult): void }>();

const testing = ref(false);
const result = ref<ConnectionTestResult | null>(null);

async function test() {
  testing.value = true;
  result.value = null;
  try {
    result.value = await api.testConnection(props.payload);
  } catch (e) {
    result.value = { ok: false, message: e instanceof ApiError ? e.message : String(e) };
  } finally {
    testing.value = false;
    if (result.value) emit('result', result.value);
  }
}
</script>
