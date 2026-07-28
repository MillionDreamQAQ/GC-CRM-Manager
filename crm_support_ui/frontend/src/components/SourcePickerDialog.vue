<script setup>
import { computed, ref, watch } from "vue";
import { ElAutoResizer, FixedSizeList } from "element-plus";
import { Refresh, Search } from "@element-plus/icons-vue";
import SourceBadge from "./SourceBadge.vue";
import OpportunityStatus from "./OpportunityStatus.vue";
import AccountEntitlement from "./AccountEntitlement.vue";
import { sourceKey, sourceName, sourceSubtitle } from "@/lib/crm";
import { matchesSourceQuery } from "@/lib/source-search";

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  sources: { type: Array, required: true },
  existingKeys: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  scope: { type: String, required: true },
});
const emit = defineEmits(["update:modelValue", "update:scope", "add", "refresh"]);

const query = ref("");
const type = ref("all");
const selectedKeys = ref([]);
const existing = computed(() => new Set(props.existingKeys));

const filteredSources = computed(() => {
  return props.sources.filter((source) => {
    const matchesType = type.value === "all" || source.type === type.value;
    return matchesType && matchesSourceQuery(source, query.value);
  });
});

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return;
    query.value = "";
    type.value = "all";
    selectedKeys.value = [];
  },
);

watch(
  () => props.sources,
  (sources) => {
    const currentKeys = new Set(sources.map(sourceKey));
    selectedKeys.value = selectedKeys.value.filter((key) => currentKeys.has(key));
  },
);

function addSelected() {
  const selected = selectedKeys.value
    .map((key) => props.sources.find((source) => sourceKey(source) === key))
    .filter(Boolean);
  emit("add", selected);
  emit("update:modelValue", false);
}

function updateSelection(key, checked) {
  if (checked && !selectedKeys.value.includes(key)) selectedKeys.value.push(key);
  if (!checked) selectedKeys.value = selectedKeys.value.filter((item) => item !== key);
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    class="source-picker-dialog"
    title="选择客户或商机"
    width="min(820px, calc(100% - 30px))"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="picker-tools">
      <el-input v-model="query" :prefix-icon="Search" clearable placeholder="搜索名称、拼音或首字母" />
      <label class="picker-filter type-filter">
        <span>类型</span>
        <el-select v-model="type">
          <el-option label="全部类型" value="all" />
          <el-option label="客户" value="account" />
          <el-option label="商机" value="opportunity" />
        </el-select>
      </label>
      <label class="picker-filter scope-filter">
        <span>范围</span>
        <el-select :model-value="scope" @update:model-value="emit('update:scope', $event)">
          <el-option label="与我相关" value="related" />
          <el-option label="全部记录" value="all" />
        </el-select>
      </label>
      <el-tooltip content="刷新 CRM 数据" placement="bottom">
        <el-button class="picker-refresh" :icon="Refresh" circle :loading="loading" aria-label="刷新 CRM 数据" @click="emit('refresh')" />
      </el-tooltip>
    </div>

    <div class="picker-meta">
      <span>{{ filteredSources.length }} 条记录</span>
      <span>已选择 {{ selectedKeys.length }} 条</span>
    </div>

    <div v-loading="loading" class="picker-list">
      <ElAutoResizer v-if="filteredSources.length">
        <template #default="{ height, width }">
          <FixedSizeList
            :data="filteredSources"
            :height="height"
            :width="width"
            :total="filteredSources.length"
            :item-size="58"
          >
            <template #default="{ data, index, style }">
              <el-checkbox
                :key="sourceKey(data[index])"
                :style="style"
                :model-value="selectedKeys.includes(sourceKey(data[index]))"
                :disabled="existing.has(sourceKey(data[index]))"
                class="picker-item"
                @change="updateSelection(sourceKey(data[index]), $event)"
              >
                <SourceBadge :source="data[index]" compact />
                <span class="picker-item-main">
                  <span class="source-title-row"><strong>{{ sourceName(data[index]) }}</strong><OpportunityStatus :source="data[index]" /><AccountEntitlement :source="data[index]" /></span>
                  <small>{{ sourceSubtitle(data[index]) }}</small>
                </span>
                <span class="picker-state">{{ existing.has(sourceKey(data[index])) ? "已加入" : "" }}</span>
              </el-checkbox>
            </template>
          </FixedSizeList>
        </template>
      </ElAutoResizer>
      <el-empty v-if="!loading && !filteredSources.length" description="没有找到匹配的记录" :image-size="64" />
    </div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :disabled="!selectedKeys.length" @click="addSelected">
        {{ selectedKeys.length ? `加入 ${selectedKeys.length} 条记录` : "加入批量表格" }}
      </el-button>
    </template>
  </el-dialog>
</template>
