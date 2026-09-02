<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { Link, Refresh, Search } from "@element-plus/icons-vue";
import SourceBadge from "./SourceBadge.vue";
import { crmApi, sourceSubtitle } from "@/lib/crm";
import { matchesSourceQuery } from "@/lib/source-search";

const props = defineProps({
  selected: { type: Object, default: null },
  refreshKey: { type: Number, default: 0 },
});

const cases = ref([]);
const query = ref("");
const onlySelected = ref(false);
const loading = ref(false);
const loadError = ref("");
const lastUpdated = ref("");
let requestVersion = 0;

const filteredCases = computed(() => {
  return cases.value.filter((item) => {
    const matchesSelected = !onlySelected.value
      || (props.selected
        && item.source_entity === props.selected.entity
        && item.source_id === props.selected.id);
    return matchesSelected && matchesSourceQuery(item, query.value);
  });
});

function formatSourceType(item) {
  if (item.source_type === "account") return "客户";
  if (item.source_type === "opportunity") return "商机";
  return "未关联";
}

function sourceDetail(item) {
  return sourceSubtitle({
    type: item.source_type,
    customer: item.customer,
    opportunity: item.opportunity,
  });
}

async function loadCases() {
  const version = ++requestVersion;
  loading.value = true;
  loadError.value = "";
  try {
    const result = await crmApi.incidents();
    if (version !== requestVersion) return;
    cases.value = result.items || [];
    lastUpdated.value = new Date().toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch (error) {
    if (version !== requestVersion) return;
    loadError.value = error.message;
    ElMessage.error({ message: `历史案例读取失败：${error.message}`, duration: 8000, showClose: true });
  } finally {
    if (version === requestVersion) loading.value = false;
  }
}

watch(() => props.refreshKey, loadCases);
onMounted(loadCases);
</script>

<template>
  <section class="history-panel" aria-labelledby="history-heading">
    <div class="history-heading">
      <div class="history-title">
        <span class="history-mark" aria-hidden="true">◷</span>
        <div>
          <p class="eyebrow">Recent activity</p>
          <h2 id="history-heading">历史案例</h2>
        </div>
        <span class="history-count">{{ filteredCases.length }} 条</span>
      </div>
      <el-tooltip content="刷新历史案例" placement="bottom">
        <el-button
          class="icon-command"
          :icon="Refresh"
          circle
          text
          :loading="loading"
          aria-label="刷新历史案例"
          @click="loadCases"
        />
      </el-tooltip>
    </div>

    <div class="history-toolbar">
      <el-input v-model="query" :prefix-icon="Search" clearable placeholder="搜索主题、说明、客户或商机" />
      <el-checkbox v-model="onlySelected" :disabled="!selected">仅当前对象</el-checkbox>
      <span v-if="lastUpdated">更新于 {{ lastUpdated }}</span>
      <span v-else-if="loading">正在读取 CRM</span>
      <span v-else-if="loadError" class="history-error">读取失败</span>
    </div>

    <div v-loading="loading" class="history-table-shell">
      <el-table
        :data="filteredCases"
        height="100%"
        row-key="id"
        empty-text="没有找到匹配的历史案例"
      >
        <el-table-column label="主题" min-width="230">
          <template #default="{ row }">
            <strong class="history-subject">{{ row.subject || "（无主题）" }}</strong>
          </template>
        </el-table-column>
        <el-table-column label="关联对象" min-width="250">
          <template #default="{ row }">
            <div class="history-source">
              <SourceBadge v-if="row.source_type" :source="{ type: row.source_type }" compact />
              <div>
                <strong>{{ row.source_name || "未关联对象" }}</strong>
                <small>{{ formatSourceType(row) }} · {{ sourceDetail(row) }}</small>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="说明" min-width="330" show-overflow-tooltip />
        <el-table-column prop="actual_end" label="实际结束时间" width="150" />
        <el-table-column prop="created_on" label="创建时间" width="150" />
        <el-table-column label="操作" width="82" fixed="right" align="center">
          <template #default="{ row }">
            <el-tooltip content="在 CRM 中打开案例" placement="top">
              <el-button
                tag="a"
                :href="row.url"
                target="_blank"
                rel="noopener noreferrer"
                :icon="Link"
                circle
                text
                aria-label="在 CRM 中打开案例"
              />
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </section>
</template>
