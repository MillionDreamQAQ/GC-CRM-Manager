<script setup>
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { crmApi } from "@/lib/crm";

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  editableCount: { type: Number, required: true },
});
const emit = defineEmits(["update:modelValue", "apply"]);

const HEADER_FIELDS = {
  "主题": "subject",
  subject: "subject",
  "说明": "description",
  description: "description",
  "实际结束时间": "actual_end",
  actualend: "actual_end",
  actual_end: "actual_end",
  "日期": "actual_end",
};
const FIELD_OPTIONS = [
  { value: "", label: "忽略" },
  { value: "subject", label: "主题" },
  { value: "description", label: "说明" },
  { value: "actual_end", label: "实际结束时间" },
];

const text = ref("");
const rows = ref([]);
const mappings = ref([]);
const columnCount = ref(0);
const parsing = ref(false);
let parseTimer = 0;
let parseVersion = 0;

const mappedFields = computed(() => mappings.value.filter(Boolean));
const duplicateMapping = computed(() => new Set(mappedFields.value).size !== mappedFields.value.length);
const warning = computed(() => {
  if (duplicateMapping.value) return "同一个字段不能映射到多列。";
  if (rows.value.length > props.editableCount) {
    return `粘贴内容有 ${rows.value.length} 行，但表格只有 ${props.editableCount} 条可编辑记录。`;
  }
  if (rows.value.length && rows.value.length < props.editableCount) {
    return `将应用到前 ${rows.value.length} 条可编辑记录，其余记录保持不变。`;
  }
  return "";
});
const canApply = computed(() => (
  rows.value.length > 0
  && mappedFields.value.length > 0
  && !duplicateMapping.value
  && rows.value.length <= props.editableCount
));

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return;
    text.value = "";
    rows.value = [];
    mappings.value = [];
    columnCount.value = 0;
    parseVersion += 1;
  },
);

watch(text, () => {
  clearTimeout(parseTimer);
  parseTimer = setTimeout(parseText, 250);
});

function defaultMappings(count) {
  if (count === 1) return ["description"];
  if (count === 2) return ["subject", "description"];
  if (count >= 3) return ["subject", "description", "actual_end", ...Array(count - 3).fill("")];
  return [];
}

async function parseText() {
  const value = text.value;
  const version = ++parseVersion;
  if (!value.trim()) {
    rows.value = [];
    mappings.value = [];
    columnCount.value = 0;
    return;
  }
  parsing.value = true;
  try {
    const result = await crmApi.parsePaste(value);
    if (version !== parseVersion) return;
    let parsedRows = result.rows || [];
    const count = result.column_count || 0;
    let nextMappings = defaultMappings(count);
    if (parsedRows.length) {
      const headerMappings = Array.from({ length: count }, (_, index) => (
        HEADER_FIELDS[String(parsedRows[0][index] || "").trim().toLocaleLowerCase("zh-CN")] || ""
      ));
      const recognizedHeader = headerMappings.some(Boolean)
        && parsedRows[0].every((cell, index) => !String(cell || "").trim() || Boolean(headerMappings[index]));
      if (recognizedHeader) {
        nextMappings = headerMappings;
        parsedRows = parsedRows.slice(1);
      }
    }
    rows.value = parsedRows;
    mappings.value = nextMappings;
    columnCount.value = count;
  } catch (error) {
    if (version === parseVersion) {
      ElMessage.error({ message: `无法解析粘贴内容：${error.message}`, duration: 8000, showClose: true });
    }
  } finally {
    if (version === parseVersion) parsing.value = false;
  }
}

function applyPaste() {
  emit("apply", { rows: rows.value, mappings: mappings.value });
  emit("update:modelValue", false);
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    class="paste-dialog"
    title="粘贴并映射数据"
    width="min(900px, calc(100% - 30px))"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <label class="paste-input-label">
      <span>在此粘贴 Excel 单元格</span>
      <el-input
        v-model="text"
        type="textarea"
        :rows="5"
        placeholder="一列默认作为说明；也支持主题、说明、实际结束时间三列"
      />
    </label>

    <div class="paste-summary">
      <span>{{ rows.length ? `识别到 ${rows.length} 行、${columnCount} 列` : "等待粘贴内容" }}</span>
      <span v-if="parsing">正在解析</span>
    </div>

    <div v-if="columnCount" class="paste-mapping">
      <label v-for="index in columnCount" :key="index">
        <span>第 {{ index }} 列</span>
        <el-select v-model="mappings[index - 1]">
          <el-option v-for="option in FIELD_OPTIONS" :key="option.value" :label="option.label" :value="option.value" />
        </el-select>
      </label>
    </div>

    <div class="paste-preview-shell">
      <el-table v-if="rows.length" :data="rows.slice(0, 5)" height="100%" border size="small">
        <el-table-column v-for="index in columnCount" :key="index" :label="`第 ${index} 列`" min-width="150">
          <template #default="scope">{{ scope.row[index - 1] || "" }}</template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="暂无预览数据" :image-size="54" />
    </div>

    <div class="paste-warning">{{ warning }}</div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :disabled="!canApply" @click="applyPaste">应用到批量表格</el-button>
    </template>
  </el-dialog>
</template>
