<script setup>
import { onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import SingleEntry from "@/components/SingleEntry.vue";
import BatchEntry from "@/components/BatchEntry.vue";
import { crmApi } from "@/lib/crm";

const mode = ref("single");
const scope = ref("related");
const sources = ref([]);
const loading = ref(false);
const connectionError = ref(false);
const lastUpdated = ref("");
const user = reactive({ name: "正在连接 CRM", login: "请稍候" });
let sourceRequestVersion = 0;

async function loadSources() {
  const requestVersion = ++sourceRequestVersion;
  loading.value = true;
  try {
    const result = await crmApi.sources(scope.value);
    if (requestVersion !== sourceRequestVersion) return;
    sources.value = result.items || [];
    user.name = result.user?.name || "已登录 CRM";
    user.login = result.user?.login || "Azure CLI 登录";
    connectionError.value = false;
    lastUpdated.value = new Date().toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch (error) {
    if (requestVersion !== sourceRequestVersion) return;
    connectionError.value = true;
    user.name = "CRM 连接失败";
    user.login = "请检查 Azure CLI 登录";
    ElMessage.error({ message: error.message, duration: 8000, showClose: true });
  } finally {
    if (requestVersion === sourceRequestVersion) loading.value = false;
  }
}

watch(scope, loadSources);
onMounted(loadSources);
</script>

<template>
  <div class="app-shell">
    <header class="app-header">
      <div class="brand-block">
        <p class="eyebrow">Dynamics 365</p>
        <h1>技术支持案例录入</h1>
      </div>

      <el-segmented
        v-model="mode"
        class="mode-switcher"
        :options="[
          { label: '单条录入', value: 'single' },
          { label: '批量录入', value: 'batch' },
        ]"
      />

      <div class="session" aria-live="polite">
        <span class="status-dot" :class="connectionError ? 'error' : (!loading && 'ready')" />
        <div>
          <strong>{{ user.name }}</strong>
          <small>{{ user.login }}</small>
        </div>
      </div>
    </header>

    <SingleEntry
      v-if="mode === 'single'"
      v-model:scope="scope"
      :sources="sources"
      :loading="loading"
      :connection-error="connectionError"
      :last-updated="lastUpdated"
      @refresh="loadSources"
    />
    <BatchEntry
      v-else
      v-model:scope="scope"
      :sources="sources"
      :loading-sources="loading"
      @refresh-sources="loadSources"
    />
  </div>
</template>
