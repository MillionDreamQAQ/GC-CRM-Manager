<script setup>
import { computed } from "vue";

const props = defineProps({
  source: { type: Object, required: true },
});

const stateClass = computed(() => ({
  0: "open",
  1: "won",
  2: "lost",
})[props.source.opportunity_state] || "unknown");
</script>

<template>
  <span
    v-if="source.type === 'opportunity' && source.opportunity_status"
    class="opportunity-status"
    :class="stateClass"
  >{{ source.opportunity_status }}</span>
</template>
