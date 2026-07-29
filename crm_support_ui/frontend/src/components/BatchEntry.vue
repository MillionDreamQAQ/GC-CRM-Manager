<script setup>
import { computed, h, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { ElMessage, ElMessageBox, ElNotification } from "element-plus";
import { CopyDocument, Delete, Link, Plus, Rank, RefreshLeft, Upload } from "@element-plus/icons-vue";
import Sortable from "sortablejs";
import SourceBadge from "./SourceBadge.vue";
import OpportunityStatus from "./OpportunityStatus.vue";
import AccountEntitlement from "./AccountEntitlement.vue";
import SourcePickerDialog from "./SourcePickerDialog.vue";
import PasteDialog from "./PasteDialog.vue";
import {
  ACTIVE_JOB_KEY,
  ApiError,
  DRAFT_KEY,
  crmApi,
  isValidDateValue,
  localDateValue,
  newRowKey,
  normalizeDate,
  removeSucceededRows,
  rowIsEditable,
  rowIsRemovable,
  sourceKey,
  sourceName,
  sourceSubtitle,
} from "@/lib/crm";

const props = defineProps({
  sources: { type: Array, required: true },
  loadingSources: { type: Boolean, default: false },
  scope: { type: String, required: true },
});
const emit = defineEmits(["refresh-sources", "update:scope"]);

function loadStoredRows() {
  try {
    const stored = JSON.parse(localStorage.getItem(DRAFT_KEY) || "[]");
    if (!Array.isArray(stored)) return [];
    return stored
      .filter((row) => row?.source?.entity && row?.source?.id)
      .map((row) => ({
        key: row.key || newRowKey(),
        source: row.source,
        subject: String(row.subject || ""),
        description: String(row.description || ""),
        actual_end: String(row.actual_end || ""),
        status: row.status || "draft",
        error: String(row.error || ""),
        record_id: String(row.record_id || ""),
        record_url: String(row.record_url || ""),
      }));
  } catch {
    return [];
  }
}

const batchRows = ref(loadStoredRows());
const defaultDate = ref(localDateValue());
const draftState = ref("草稿已保存");
const sourcePickerVisible = ref(false);
const pasteVisible = ref(false);
const descriptionVisible = ref(false);
const descriptionKey = ref("");
const descriptionValue = ref("");
const confirmVisible = ref(false);
const confirmRows = ref([]);
const lastPasteSnapshot = ref(null);
const activeBatchJob = ref(localStorage.getItem(ACTIVE_JOB_KEY) || "");
const jobProgress = ref(null);
const startingBatch = ref(false);
const tableRef = ref(null);
let persistTimer = 0;
let pollTimer = 0;
let tableSortable = null;

const editableRows = computed(() => batchRows.value.filter(rowIsEditable));
const validRows = computed(() => editableRows.value.filter((row) => row.subject.trim() && isValidDateValue(row.actual_end)));
const incompleteCount = computed(() => editableRows.value.length - validRows.value.length);
const failedRows = computed(() => batchRows.value.filter((row) => row.status === "failed"));
const succeededRows = computed(() => batchRows.value.filter((row) => row.status === "succeeded"));
const existingSourceKeys = computed(() => [...new Set(batchRows.value.map((row) => sourceKey(row.source)))]);
const createLabel = computed(() => (
  validRows.value.length ? `创建 ${validRows.value.length} 条有效记录` : "创建批量记录"
));
const validationText = computed(() => {
  if (activeBatchJob.value) return "批量任务正在执行";
  if (failedRows.value.length) return `${failedRows.value.length} 条记录创建失败，可单独重试`;
  if (incompleteCount.value) return `${incompleteCount.value} 条记录需要补充主题或日期`;
  if (validRows.value.length) return "所有待创建记录已通过校验";
  return "选择记录后即可开始编辑";
});

watch(
  batchRows,
  () => {
    draftState.value = "正在保存";
    clearTimeout(persistTimer);
    persistTimer = setTimeout(() => {
      localStorage.setItem(DRAFT_KEY, JSON.stringify(batchRows.value));
      draftState.value = "草稿已保存";
    }, 120);
  },
  { deep: true },
);

watch(
  () => props.sources,
  (sources) => {
    const current = new Map(sources.map((source) => [sourceKey(source), source]));
    for (const row of batchRows.value) {
      row.source = current.get(sourceKey(row.source)) || row.source;
    }
  },
);

function addSources(sources) {
  for (const source of sources) {
    batchRows.value.push({
      key: newRowKey(),
      source,
      subject: "",
      description: "",
      actual_end: defaultDate.value || localDateValue(),
      status: "draft",
      error: "",
      record_id: "",
      record_url: "",
    });
  }
}

function openSourcePicker() {
  if (!props.sources.length) {
    ElMessage.warning("CRM 数据尚未加载完成");
    return;
  }
  sourcePickerVisible.value = true;
}

function applyDefaultDate() {
  const value = defaultDate.value || localDateValue();
  defaultDate.value = value;
  for (const row of editableRows.value) row.actual_end = value;
}

function duplicateRow(row) {
  const copy = {
    ...row,
    key: newRowKey(),
    status: "draft",
    error: "",
    record_id: "",
    record_url: "",
  };
  batchRows.value.splice(batchRows.value.indexOf(row) + 1, 0, copy);
}

function removeRow(row) {
  if (!rowIsRemovable(row)) return;
  batchRows.value.splice(batchRows.value.indexOf(row), 1);
}

async function clearSucceededRows() {
  if (!succeededRows.value.length || activeBatchJob.value) return;
  try {
    await ElMessageBox.confirm(
      `将从本地列表移除 ${succeededRows.value.length} 条已创建记录，不会删除 CRM 中的案例。`,
      "清理已创建记录？",
      { confirmButtonText: "确认清理", cancelButtonText: "取消", type: "warning" },
    );
  } catch {
    return;
  }
  batchRows.value = removeSucceededRows(batchRows.value);
  lastPasteSnapshot.value = null;
  ElMessage.success("已从列表移除成功记录");
}

function openDescription(row) {
  if (!rowIsEditable(row)) return;
  descriptionKey.value = row.key;
  descriptionValue.value = row.description;
  descriptionVisible.value = true;
}

function saveDescription() {
  const row = batchRows.value.find((item) => item.key === descriptionKey.value);
  if (row) row.description = descriptionValue.value.trim();
  descriptionVisible.value = false;
}

function applyPaste({ rows, mappings }) {
  lastPasteSnapshot.value = JSON.parse(JSON.stringify(batchRows.value));
  const targets = editableRows.value;
  rows.forEach((cells, rowIndex) => {
    const target = targets[rowIndex];
    if (!target) return;
    mappings.forEach((field, columnIndex) => {
      if (!field) return;
      const value = String(cells[columnIndex] || "").trim();
      target[field] = field === "actual_end" ? normalizeDate(value) : value;
    });
  });
}

function undoPaste() {
  if (!lastPasteSnapshot.value) return;
  batchRows.value = lastPasteSnapshot.value;
  lastPasteSnapshot.value = null;
}

function statusFor(row) {
  if (row.status === "succeeded") return { label: "已创建", type: "success" };
  if (row.status === "failed") return { label: "失败", type: "danger" };
  if (row.status === "running") return { label: "创建中", type: "primary" };
  if (row.status === "queued") return { label: "等待中", type: "info" };
  if (!row.subject.trim()) return { label: "缺少主题", type: "warning" };
  if (!row.actual_end) return { label: "缺少日期", type: "warning" };
  if (!isValidDateValue(row.actual_end)) return { label: "日期无效", type: "warning" };
  return { label: "待创建", type: "success" };
}

function rowClassName({ row }) {
  return `batch-row-${row.status || "draft"}`;
}

function initializeRowSorting() {
  tableSortable?.destroy();
  tableSortable = null;
  nextTick(() => {
    const body = tableRef.value?.$el?.querySelector(".el-table__body-wrapper tbody");
    if (!body) return;
    tableSortable = Sortable.create(body, {
      animation: 160,
      disabled: Boolean(activeBatchJob.value),
      forceFallback: true,
      fallbackOnBody: true,
      fallbackTolerance: 3,
      handle: ".drag-handle",
      ghostClass: "batch-row-ghost",
      chosenClass: "batch-row-chosen",
      dragClass: "batch-row-dragging",
      onEnd({ oldIndex, newIndex }) {
        if (oldIndex == null || newIndex == null || oldIndex === newIndex) return;
        const [movedRow] = batchRows.value.splice(oldIndex, 1);
        batchRows.value.splice(newIndex, 0, movedRow);
      },
    });
  });
}

function openConfirmation() {
  if (!validRows.value.length) return;
  confirmRows.value = [...validRows.value];
  confirmVisible.value = true;
}

async function startBatch(rows) {
  if (!rows.length || activeBatchJob.value || startingBatch.value) return;
  startingBatch.value = true;
  try {
    const result = await crmApi.createBatch(rows.map((row) => ({
      client_key: row.key,
      source_entity: row.source.entity,
      source_id: row.source.id,
      source_name: sourceName(row.source),
      subject: row.subject.trim(),
      description: row.description.trim(),
      actual_end: row.actual_end,
    })));
    activeBatchJob.value = result.id;
    localStorage.setItem(ACTIVE_JOB_KEY, result.id);
    rows.forEach((row) => {
      row.status = "queued";
      row.error = "";
    });
    confirmVisible.value = false;
    await nextTick();
    pollBatchJob();
  } catch (error) {
    ElMessage.error({ message: `无法启动批量任务：${error.message}`, duration: 8000, showClose: true });
  } finally {
    startingBatch.value = false;
  }
}

function applyJobProgress(job) {
  for (const item of job.items || []) {
    const row = batchRows.value.find((candidate) => candidate.key === item.client_key);
    if (!row) continue;
    row.status = item.status;
    row.error = item.error || "";
    row.record_id = item.record_id || "";
    row.record_url = item.record_url || "";
  }
  jobProgress.value = job;
}

function completedNotification(job) {
  const firstSuccess = (job.items || []).find((item) => item.status === "succeeded");
  const children = [h("span", `成功 ${job.succeeded || 0} 条，失败 ${job.failed || 0} 条。`)];
  if (firstSuccess?.record_url) {
    children.push(h(
      "a",
      {
        href: firstSuccess.record_url,
        target: "_blank",
        rel: "noopener noreferrer",
        class: "notification-link batch-notification-link",
      },
      "打开第一条成功记录",
    ));
  }
  ElNotification({ title: "批量创建已完成", type: job.failed ? "warning" : "success", duration: 10000, message: h("div", children) });
}

async function pollBatchJob() {
  clearTimeout(pollTimer);
  if (!activeBatchJob.value) return;
  try {
    const job = await crmApi.batch(activeBatchJob.value);
    applyJobProgress(job);
    if (job.status === "completed") {
      activeBatchJob.value = "";
      localStorage.removeItem(ACTIVE_JOB_KEY);
      completedNotification(job);
      return;
    }
    pollTimer = setTimeout(pollBatchJob, 1000);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      activeBatchJob.value = "";
      localStorage.removeItem(ACTIVE_JOB_KEY);
      ElMessage.error("未找到之前的批量任务，已停止恢复进度");
      return;
    }
    ElMessage.error({ message: `读取批量进度失败：${error.message}`, duration: 5000, showClose: true });
    pollTimer = setTimeout(pollBatchJob, 3000);
  }
}

function retryFailed() {
  const rows = failedRows.value.filter((row) => row.subject.trim() && isValidDateValue(row.actual_end));
  startBatch(rows);
}

onMounted(() => {
  initializeRowSorting();
  if (activeBatchJob.value) pollBatchJob();
});
watch(activeBatchJob, (jobId) => {
  tableSortable?.option("disabled", Boolean(jobId));
});
watch(
  () => batchRows.value.length,
  initializeRowSorting,
);
onBeforeUnmount(() => {
  clearTimeout(persistTimer);
  clearTimeout(pollTimer);
  tableSortable?.destroy();
  localStorage.setItem(DRAFT_KEY, JSON.stringify(batchRows.value));
});
</script>

<template>
  <main class="batch-workspace">
    <section class="batch-editor" aria-labelledby="batch-heading">
      <header class="batch-header">
        <div><p class="eyebrow">Batch workspace</p><h2 id="batch-heading">批量案例工作台</h2></div>
        <div class="batch-actions">
          <el-button type="primary" :icon="Plus" @click="openSourcePicker">选择客户/商机</el-button>
          <el-button :icon="Upload" :disabled="!editableRows.length" @click="pasteVisible = true">从 Excel 粘贴</el-button>
          <el-tooltip content="撤销上次粘贴" placement="bottom">
            <el-button
              v-if="lastPasteSnapshot"
              :icon="RefreshLeft"
              circle
              aria-label="撤销上次粘贴"
              @click="undoPaste"
            />
          </el-tooltip>
        </div>
      </header>

      <div class="batch-toolbar">
        <label><span>默认日期</span><el-date-picker v-model="defaultDate" type="date" value-format="YYYY-MM-DD" /></label>
        <el-button link type="primary" @click="applyDefaultDate">应用到未创建项</el-button>
        <el-button
          v-if="succeededRows.length && !activeBatchJob"
          link
          type="danger"
          :icon="Delete"
          @click="clearSucceededRows"
        >清理已创建（{{ succeededRows.length }}）</el-button>
        <span class="batch-count">{{ batchRows.length ? `${batchRows.length} 条记录` : "尚未选择记录" }}</span>
        <span class="draft-state">{{ draftState }}</span>
      </div>

      <div class="batch-table-shell">
        <el-table
          ref="tableRef"
          :data="batchRows"
          height="100%"
          row-key="key"
          :row-class-name="rowClassName"
          empty-text="选择客户或商机后，可逐条编辑或粘贴 Excel 内容"
        >
          <el-table-column label="#" width="64" align="center">
            <template #default="scope">
              <div class="order-cell">
                <span class="row-order">{{ scope.$index + 1 }}</span>
                <el-tooltip :content="activeBatchJob ? '批量任务执行期间不可排序' : '拖拽排序'" placement="right">
                  <button
                    type="button"
                    class="drag-handle"
                    :disabled="Boolean(activeBatchJob)"
                    aria-label="拖拽排序"
                  ><el-icon><Rank /></el-icon></button>
                </el-tooltip>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="客户/商机" width="260">
            <template #default="scope">
              <div class="table-source">
                <SourceBadge :source="scope.row.source" compact />
                <span><span class="source-title-row"><strong>{{ sourceName(scope.row.source) }}</strong><OpportunityStatus :source="scope.row.source" /><AccountEntitlement :source="scope.row.source" /></span><small>{{ sourceSubtitle(scope.row.source) }}</small></span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="主题 *" width="250">
            <template #default="scope">
              <el-input
                v-model="scope.row.subject"
                maxlength="200"
                placeholder="填写主题"
                :disabled="!rowIsEditable(scope.row)"
                :class="{ 'is-invalid': rowIsEditable(scope.row) && !scope.row.subject.trim() }"
              />
            </template>
          </el-table-column>
          <el-table-column label="说明" min-width="250">
            <template #default="scope">
              <el-button
                class="description-button"
                :class="{ empty: !scope.row.description.trim() }"
                :disabled="!rowIsEditable(scope.row)"
                @click="openDescription(scope.row)"
              >{{ scope.row.description.trim() || "填写说明" }}</el-button>
            </template>
          </el-table-column>
          <el-table-column label="实际结束时间 *" width="175">
            <template #default="scope">
              <el-date-picker
                v-model="scope.row.actual_end"
                type="date"
                value-format="YYYY-MM-DD"
                :disabled="!rowIsEditable(scope.row)"
              />
            </template>
          </el-table-column>
          <el-table-column label="状态" width="128">
            <template #default="scope">
              <div class="row-status-cell">
                <el-tooltip :content="scope.row.error" :disabled="!scope.row.error" placement="top">
                  <el-tag :type="statusFor(scope.row).type" size="small" effect="light">{{ statusFor(scope.row).label }}</el-tag>
                </el-tooltip>
                <el-tooltip v-if="scope.row.record_url" content="打开 CRM 记录" placement="top">
                  <el-button
                    tag="a"
                    :href="scope.row.record_url"
                    target="_blank"
                    rel="noopener noreferrer"
                    :icon="Link"
                    link
                    type="primary"
                    aria-label="打开 CRM 记录"
                  />
                </el-tooltip>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="92" fixed="right" align="center">
            <template #default="scope">
              <div class="row-actions">
                <el-tooltip content="复制此行" placement="top">
                  <el-button :icon="CopyDocument" circle text aria-label="复制此行" @click="duplicateRow(scope.row)" />
                </el-tooltip>
                <el-tooltip content="移除此行" placement="top">
                  <el-button
                    :icon="Delete"
                    circle
                    text
                    type="danger"
                    :disabled="!rowIsRemovable(scope.row)"
                    aria-label="移除此行"
                    @click="removeRow(scope.row)"
                  />
                </el-tooltip>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <footer class="batch-footer">
        <div v-if="jobProgress" class="batch-progress">
          <el-progress
            :percentage="jobProgress.total ? Math.round((jobProgress.completed / jobProgress.total) * 100) : 0"
            :stroke-width="7"
            :show-text="false"
          />
          <span>{{ jobProgress.completed }}/{{ jobProgress.total }}，成功 {{ jobProgress.succeeded }}，失败 {{ jobProgress.failed }}</span>
        </div>
        <span class="batch-validation">{{ validationText }}</span>
        <el-button
          v-if="failedRows.length && !activeBatchJob"
          :loading="startingBatch"
          @click="retryFailed"
        >重试失败项</el-button>
        <el-button
          class="create-batch-button"
          type="primary"
          :disabled="!validRows.length || Boolean(activeBatchJob)"
          @click="openConfirmation"
        >{{ createLabel }}</el-button>
      </footer>
    </section>
  </main>

  <SourcePickerDialog
    v-model="sourcePickerVisible"
    :scope="scope"
    :sources="sources"
    :existing-keys="existingSourceKeys"
    :loading="loadingSources"
    @add="addSources"
    @refresh="emit('refresh-sources')"
    @update:scope="emit('update:scope', $event)"
  />
  <PasteDialog v-model="pasteVisible" :editable-count="editableRows.length" @apply="applyPaste" />

  <el-dialog
    v-model="descriptionVisible"
    class="description-dialog"
    title="编辑说明"
    width="min(680px, calc(100% - 30px))"
  >
    <el-input
      v-model="descriptionValue"
      type="textarea"
      :rows="14"
      resize="none"
      placeholder="填写交流内容、客户需求和后续计划"
    />
    <template #footer>
      <el-button @click="descriptionVisible = false">取消</el-button>
      <el-button type="primary" @click="saveDescription">保存说明</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="confirmVisible" title="确认创建批量案例？" width="min(520px, calc(100% - 30px))">
    <p class="batch-confirm-text">
      将创建 {{ confirmRows.length }} 条技术支持案例，其中客户
      {{ confirmRows.filter((row) => row.source.type === "account").length }} 条、商机
      {{ confirmRows.filter((row) => row.source.type === "opportunity").length }} 条。
    </p>
    <template #footer>
      <el-button @click="confirmVisible = false">返回检查</el-button>
      <el-button type="primary" :loading="startingBatch" @click="startBatch(confirmRows)">确认创建</el-button>
    </template>
  </el-dialog>
</template>
