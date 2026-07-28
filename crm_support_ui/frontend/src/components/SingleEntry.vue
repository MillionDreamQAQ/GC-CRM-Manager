<script setup>
import { computed, h, nextTick, reactive, ref, watch } from "vue";
import { ElAutoResizer, ElMessage, ElNotification, FixedSizeList } from "element-plus";
import { Link, Refresh, Search } from "@element-plus/icons-vue";
import SourceBadge from "./SourceBadge.vue";
import OpportunityStatus from "./OpportunityStatus.vue";
import AccountEntitlement from "./AccountEntitlement.vue";
import { crmApi, localDateValue, sourceKey, sourceName, sourceSubtitle } from "@/lib/crm";

const props = defineProps({
  sources: { type: Array, required: true },
  loading: { type: Boolean, required: true },
  connectionError: { type: Boolean, required: true },
  lastUpdated: { type: String, default: "" },
  scope: { type: String, required: true },
});
const emit = defineEmits(["update:scope", "refresh"]);

const query = ref("");
const type = ref("all");
const selected = ref(null);
const subjectInput = ref(null);
const confirmVisible = ref(false);
const creating = ref(false);
const pending = ref(null);
const form = reactive({ subject: "", description: "", actual_end: localDateValue() });

const filteredSources = computed(() => {
  const needle = query.value.trim().toLocaleLowerCase("zh-CN");
  return props.sources.filter((item) => {
    const matchesType = type.value === "all" || item.type === type.value;
    const haystack = [item.name, item.customer, item.opportunity, item.opportunity_status, item.owner]
      .join(" ")
      .toLocaleLowerCase("zh-CN");
    return matchesType && (!needle || haystack.includes(needle));
  });
});

watch(
  () => props.sources,
  (items) => {
    if (!selected.value) return;
    selected.value = items.find((item) => sourceKey(item) === sourceKey(selected.value)) || null;
  },
);

function selectSource(source) {
  selected.value = source;
  nextTick(() => subjectInput.value?.focus());
}

function openConfirmation() {
  if (!selected.value || !form.subject.trim() || !form.actual_end) return;
  pending.value = {
    source_entity: selected.value.entity,
    source_id: selected.value.id,
    subject: form.subject.trim(),
    description: form.description.trim(),
    actual_end: form.actual_end,
  };
  confirmVisible.value = true;
}

async function createIncident() {
  if (!pending.value || creating.value) return;
  creating.value = true;
  try {
    const result = await crmApi.createIncident(pending.value);
    confirmVisible.value = false;
    ElNotification({
      title: "技术支持案例已创建",
      type: "success",
      duration: 8000,
      message: h(
        "a",
        { href: result.url, target: "_blank", rel: "noopener noreferrer", class: "notification-link" },
        "在 CRM 中打开",
      ),
    });
    form.subject = "";
    form.description = "";
    form.actual_end = localDateValue();
    nextTick(() => subjectInput.value?.focus());
  } catch (error) {
    ElMessage.error({ message: `创建失败：${error.message}`, duration: 8000, showClose: true });
  } finally {
    creating.value = false;
  }
}
</script>

<template>
  <main class="single-workspace">
    <section class="source-panel" aria-labelledby="source-heading">
      <div class="panel-heading">
        <div><span class="step">1</span><h2 id="source-heading">选择客户或商机</h2></div>
        <el-tooltip content="刷新 CRM 数据" placement="bottom">
          <el-button
            class="icon-command"
            :icon="Refresh"
            circle
            text
            :loading="loading"
            aria-label="刷新 CRM 数据"
            @click="emit('refresh')"
          />
        </el-tooltip>
      </div>

      <div class="source-tools">
        <el-input v-model="query" :prefix-icon="Search" clearable placeholder="搜索名称、客户或商机" />
        <div class="filter-row">
          <label>类型
            <el-select v-model="type">
              <el-option label="全部" value="all" />
              <el-option label="客户" value="account" />
              <el-option label="商机" value="opportunity" />
            </el-select>
          </label>
          <label>范围
            <el-select :model-value="scope" @update:model-value="emit('update:scope', $event)">
              <el-option label="与我相关" value="related" />
              <el-option label="全部记录" value="all" />
            </el-select>
          </label>
        </div>
      </div>

      <div class="list-meta">
        <span>{{ connectionError ? "读取失败" : `${filteredSources.length} 条记录` }}</span>
        <span v-if="lastUpdated">更新于 {{ lastUpdated }}</span>
      </div>

      <div v-loading="loading" class="source-list">
        <ElAutoResizer v-if="filteredSources.length">
          <template #default="{ height, width }">
            <FixedSizeList
              :data="filteredSources"
              :height="height"
              :width="width"
              :total="filteredSources.length"
              :item-size="65"
            >
              <template #default="{ data, index, style }">
                <button
                  :key="sourceKey(data[index])"
                  :style="style"
                  class="source-item"
                  :class="[data[index].type, { selected: sourceKey(data[index]) === sourceKey(selected) }]"
                  type="button"
                  @click="selectSource(data[index])"
                >
                  <SourceBadge :source="data[index]" />
                  <span class="source-main">
                    <span class="source-title-row"><strong>{{ sourceName(data[index]) }}</strong><OpportunityStatus :source="data[index]" /><AccountEntitlement :source="data[index]" /></span>
                    <small>{{ sourceSubtitle(data[index]) }}</small>
                  </span>
                  <span class="source-owner">{{ data[index].owner }}</span>
                </button>
              </template>
            </FixedSizeList>
          </template>
        </ElAutoResizer>
        <el-empty
          v-if="!loading && !filteredSources.length"
          :description="connectionError ? '暂时无法读取 CRM 数据' : '没有找到匹配的记录'"
          :image-size="64"
        />
      </div>
    </section>

    <section class="form-panel" aria-labelledby="form-heading">
      <div class="panel-heading"><div><span class="step">2</span><h2 id="form-heading">填写案例内容</h2></div></div>

      <div class="selection-summary" :class="selected?.type || 'empty'">
        <template v-if="selected">
          <SourceBadge :source="selected" />
          <div>
            <span class="source-title-row"><strong>{{ sourceName(selected) }}</strong><OpportunityStatus :source="selected" /><AccountEntitlement :source="selected" /></span>
            <small>{{ sourceSubtitle(selected) }}</small>
          </div>
          <el-tooltip content="在 CRM 中打开" placement="bottom">
            <el-button
              tag="a"
              :href="selected.url"
              target="_blank"
              rel="noopener noreferrer"
              :icon="Link"
              circle
              plain
              aria-label="在 CRM 中打开"
            />
          </el-tooltip>
        </template>
        <template v-else>
          <span class="selection-arrow" aria-hidden="true">←</span>
          <div><strong>请先从左侧选择一条记录</strong><small>选中后将在这里显示关联对象</small></div>
        </template>
      </div>

      <el-form
        class="incident-form"
        :model="form"
        label-position="top"
        :disabled="!selected"
        @submit.prevent="openConfirmation"
      >
          <el-form-item label="主题" required>
            <el-input ref="subjectInput" v-model="form.subject" maxlength="200" placeholder="例如：线下技术交流会" />
          </el-form-item>
          <el-form-item label="说明">
            <el-input
              v-model="form.description"
              type="textarea"
              :rows="7"
              resize="vertical"
              placeholder="记录交流内容、客户需求和后续计划"
            />
          </el-form-item>
          <el-form-item label="实际结束时间" required class="single-date-field">
            <el-date-picker v-model="form.actual_end" type="date" value-format="YYYY-MM-DD" />
          </el-form-item>
          <el-button
            native-type="submit"
            type="primary"
            :disabled="!form.subject.trim() || !form.actual_end"
          >核对并创建</el-button>
      </el-form>
    </section>
  </main>

  <el-dialog v-model="confirmVisible" title="确认创建技术支持案例？" width="min(560px, calc(100% - 30px))">
    <el-descriptions v-if="pending" :column="1" border>
      <el-descriptions-item label="关联对象">{{ sourceName(selected) }}</el-descriptions-item>
      <el-descriptions-item label="类型">{{ selected.type === "account" ? "客户" : "商机" }}</el-descriptions-item>
      <el-descriptions-item label="主题">{{ pending.subject }}</el-descriptions-item>
      <el-descriptions-item label="实际结束时间">{{ pending.actual_end }}</el-descriptions-item>
      <el-descriptions-item label="说明"><span class="pre-wrap">{{ pending.description || "（未填写）" }}</span></el-descriptions-item>
    </el-descriptions>
    <template #footer>
      <el-button @click="confirmVisible = false">返回修改</el-button>
      <el-button type="primary" :loading="creating" @click="createIncident">确认创建</el-button>
    </template>
  </el-dialog>
</template>
