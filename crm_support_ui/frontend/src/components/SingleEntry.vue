<script setup>
import { computed, h, nextTick, reactive, ref, watch } from "vue";
import { ElAutoResizer, ElMessage, ElNotification, FixedSizeList } from "element-plus";
import { Link, Refresh, Search } from "@element-plus/icons-vue";
import SourceBadge from "./SourceBadge.vue";
import OpportunityStatus from "./OpportunityStatus.vue";
import AccountEntitlement from "./AccountEntitlement.vue";
import HistoryCases from "./HistoryCases.vue";
import { crmApi, localDateValue, sourceKey, sourceName, sourceSubtitle } from "@/lib/crm";
import { buildForumContent, FORUM_TITLE_MAX_LENGTH } from "@/lib/forum";
import { matchesSourceQuery } from "@/lib/source-search";

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
const createStage = ref("");
const pending = ref(null);
const forumCookieInput = ref(null);
const forumCookie = ref("");
const forumTitleInput = ref(null);
const forumContentInput = ref(null);
const forumTitle = ref("");
const forumContent = ref("");
const form = reactive({
  subject: "",
  description: "",
  actual_end: localDateValue(),
  create_forum_post: false,
});
const historyRefreshKey = ref(0);

const filteredSources = computed(() => {
  return props.sources.filter((item) => {
    const matchesType = type.value === "all" || item.type === type.value;
    return matchesType && matchesSourceQuery(item, query.value);
  });
});

watch(
  () => props.sources,
  (items) => {
    if (!selected.value) return;
    selected.value = items.find((item) => sourceKey(item) === sourceKey(selected.value)) || null;
  },
);

watch(
  () => form.create_forum_post,
  (enabled) => {
    if (!enabled) {
      forumCookie.value = "";
      forumTitle.value = "";
      forumContent.value = "";
      return;
    }
    if (!forumTitle.value.trim()) forumTitle.value = form.subject.trim();
    if (!forumContent.value.trim()) forumContent.value = form.description.trim();
  },
);

function selectSource(source) {
  selected.value = source;
  nextTick(() => subjectInput.value?.focus());
}

function openConfirmation() {
  if (!selected.value || !form.subject.trim() || !form.actual_end) return;
  const subject = form.subject.trim();
  let forumTitleValue = "";
  let forumContentValue = "";
  if (form.create_forum_post) {
    forumTitleValue = forumTitle.value.trim();
    forumContentValue = forumContent.value.trim();
    if (!forumTitleValue) {
      ElMessage.warning("请填写论坛帖子主题");
      nextTick(() => forumTitleInput.value?.focus());
      return;
    }
    if (Array.from(forumTitleValue).length > FORUM_TITLE_MAX_LENGTH) {
      ElMessage.warning(`论坛帖子主题不能超过 ${FORUM_TITLE_MAX_LENGTH} 个字符，请缩短主题`);
      nextTick(() => forumTitleInput.value?.focus());
      return;
    }
    if (!forumContentValue) {
      ElMessage.warning("请填写论坛帖子内容");
      nextTick(() => forumContentInput.value?.focus());
      return;
    }
    if (!forumCookie.value.trim()) {
      ElMessage.warning("请先输入 GCDN 论坛 Cookie");
      nextTick(() => forumCookieInput.value?.focus());
      return;
    }
    if (/[\r\n]/.test(forumCookie.value)) {
      ElMessage.warning("Cookie 必须是一行请求头内容，请删除换行后重试");
      nextTick(() => forumCookieInput.value?.focus());
      return;
    }
    if (forumCookie.value.length > 16000) {
      ElMessage.warning("Cookie 内容过长，请确认只粘贴 Cookie 请求头");
      nextTick(() => forumCookieInput.value?.focus());
      return;
    }
  }
  pending.value = {
    source_entity: selected.value.entity,
    source_id: selected.value.id,
    subject,
    description: form.description.trim(),
    actual_end: form.actual_end,
    create_forum_post: form.create_forum_post,
    forum_title: forumTitleValue,
    forum_content: forumContentValue,
  };
  confirmVisible.value = true;
}

async function createIncident() {
  if (!pending.value || creating.value) return;
  creating.value = true;
  createStage.value = "正在创建 CRM 案例…";
  const values = { ...pending.value };
  const forumRequested = Boolean(values.create_forum_post);
  const forumCookieValue = forumRequested ? forumCookie.value.trim() : "";
  const forumTitleValue = forumRequested ? String(values.forum_title || "").trim() : "";
  const forumContentValue = forumRequested ? String(values.forum_content || "").trim() : "";
  const forumSourceName = sourceName(selected.value);
  delete values.create_forum_post;
  delete values.forum_title;
  delete values.forum_content;

  try {
    const result = await crmApi.createIncident(values);
    let forumResult = null;
    let forumError = null;
    if (forumRequested) {
      createStage.value = "CRM 案例已创建，正在发布论坛帖子…";
      try {
        forumResult = await crmApi.createForumPost({
          cookie: forumCookieValue,
          title: forumTitleValue,
          content: buildForumContent({
            description: forumContentValue,
            sourceName: forumSourceName,
            actualEnd: values.actual_end,
            crmUrl: result.url,
          }),
        });
      } catch (error) {
        forumError = error;
      }
    }

    confirmVisible.value = false;
    const notificationLinks = [
      h(
        "a",
        { href: result.url, target: "_blank", rel: "noopener noreferrer", class: "notification-link" },
        "在 CRM 中打开",
      ),
    ];
    if (forumResult?.url) {
      notificationLinks.push(
        h(
          "a",
          {
            href: forumResult.url,
            target: "_blank",
            rel: "noopener noreferrer",
            class: "notification-link",
          },
          "打开论坛帖子",
        ),
      );
    }
    if (forumError) {
      notificationLinks.push(
        h("span", { class: "notification-error" }, `论坛发帖失败：${forumError.message}`),
      );
    }
    const notification = {
      title: "技术支持案例已创建",
      type: "success",
      duration: 8000,
      message: h("div", notificationLinks),
    };
    if (forumError) {
      notification.title = "CRM 案例已创建，论坛发帖失败";
      notification.type = "warning";
      notification.duration = 12000;
    } else if (forumResult) {
      notification.title = "案例和论坛帖子已创建";
    }
    ElNotification(notification);
    form.subject = "";
    form.description = "";
    form.actual_end = localDateValue();
    form.create_forum_post = false;
    forumCookie.value = "";
    forumTitle.value = "";
    forumContent.value = "";
    historyRefreshKey.value += 1;
    nextTick(() => subjectInput.value?.focus());
  } catch (error) {
    ElMessage.error({ message: `创建失败：${error.message}`, duration: 8000, showClose: true });
  } finally {
    creating.value = false;
    createStage.value = "";
  }
}
</script>

<template>
  <div class="single-view">
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
        <el-input v-model="query" :prefix-icon="Search" clearable placeholder="搜索名称、拼音或首字母" />
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
          <el-form-item class="forum-option-item">
            <el-checkbox v-model="form.create_forum_post">同时创建对应论坛帖子</el-checkbox>
            <span class="forum-option-hint">使用下方 Cookie 直发到 GCDN；论坛字段默认带入 CRM 内容，可单独修改</span>
          </el-form-item>
          <el-form-item v-if="form.create_forum_post" label="GCDN 论坛 Cookie" required class="forum-cookie-item">
            <el-input
              ref="forumCookieInput"
              v-model="forumCookie"
              type="password"
              show-password
              clearable
              autocomplete="new-password"
              maxlength="16000"
              placeholder="粘贴浏览器请求头中的 Cookie 值"
            />
          </el-form-item>
          <el-form-item v-if="form.create_forum_post" label="论坛帖子主题" required class="forum-title-item">
            <el-input
              ref="forumTitleInput"
              v-model="forumTitle"
              maxlength="80"
              show-word-limit
              placeholder="填写论坛帖子主题"
            />
          </el-form-item>
          <el-form-item v-if="form.create_forum_post" label="论坛帖子内容" required class="forum-content-item">
            <el-input
              ref="forumContentInput"
              v-model="forumContent"
              type="textarea"
              :rows="7"
              resize="vertical"
              maxlength="200000"
              show-word-limit
              placeholder="填写论坛帖子内容"
            />
          </el-form-item>
          <el-button
            native-type="submit"
            type="primary"
            :disabled="!form.subject.trim() || !form.actual_end"
          >核对并创建</el-button>
      </el-form>
    </section>
    </main>
    <HistoryCases :selected="selected" :refresh-key="historyRefreshKey" />
  </div>

  <el-dialog v-model="confirmVisible" title="确认创建技术支持案例？" width="min(560px, calc(100% - 30px))">
    <el-descriptions v-if="pending" :column="1" border>
      <el-descriptions-item label="关联对象">{{ sourceName(selected) }}</el-descriptions-item>
      <el-descriptions-item label="类型">{{ selected.type === "account" ? "客户" : "商机" }}</el-descriptions-item>
      <el-descriptions-item label="主题">{{ pending.subject }}</el-descriptions-item>
      <el-descriptions-item label="实际结束时间">{{ pending.actual_end }}</el-descriptions-item>
      <el-descriptions-item label="说明"><span class="pre-wrap">{{ pending.description || "（未填写）" }}</span></el-descriptions-item>
      <el-descriptions-item label="论坛帖子">{{ pending.create_forum_post ? "创建（提交后由论坛返回结果）" : "不创建" }}</el-descriptions-item>
      <template v-if="pending.create_forum_post">
        <el-descriptions-item label="论坛主题">{{ pending.forum_title }}</el-descriptions-item>
        <el-descriptions-item label="论坛内容"><span class="pre-wrap">{{ pending.forum_content }}</span></el-descriptions-item>
      </template>
    </el-descriptions>
    <template #footer>
      <el-button @click="confirmVisible = false">返回修改</el-button>
      <el-button class="confirm-create-button" type="primary" :loading="creating" @click="createIncident">{{ creating ? createStage : "确认创建" }}</el-button>
    </template>
  </el-dialog>
</template>
