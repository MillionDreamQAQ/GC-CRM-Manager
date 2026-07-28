<script setup>
defineProps({
  source: { type: Object, required: true },
  compact: { type: Boolean, default: false },
});
</script>

<template>
  <span
    class="source-badge"
    :class="[source.type, { compact }]"
    :aria-label="source.type === 'account' ? '客户' : '商机'"
  >
    <span aria-hidden="true">{{ source.type === "account" ? "🏆" : "💼" }}</span>
  </span>
</template>
