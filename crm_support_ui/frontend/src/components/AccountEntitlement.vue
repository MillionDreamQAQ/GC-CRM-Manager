<script setup>
import { computed } from "vue";

const props = defineProps({
  source: { type: Object, required: true },
});

const count = computed(() => Number(props.source.available_entitlement_count || 0));
</script>

<template>
  <span
    v-if="source.type === 'account'"
    class="account-entitlement"
    :class="{ available: count > 0, unavailable: count === 0 }"
    :title="count > 0 ? `该客户有 ${count} 条可用客户权利` : '该客户没有可用客户权利'"
  >{{ count > 0 ? `可用权利 ${count}` : "无可用权利" }}</span>
</template>
