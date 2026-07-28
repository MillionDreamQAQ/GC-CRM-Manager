export const DRAFT_KEY = "crm-support-batch-draft-v1";
export const ACTIVE_JOB_KEY = "crm-support-active-batch-v1";

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  let body = {};
  try {
    body = await response.json();
  } catch {
    // Some successful Dataverse proxy responses have no body.
  }
  if (!response.ok) {
    throw new ApiError(body.detail || `请求失败（HTTP ${response.status}）`, response.status);
  }
  return body;
}

export const crmApi = {
  sources(scope) {
    return request(`/api/sources?scope=${encodeURIComponent(scope)}`);
  },
  createIncident(values) {
    return request("/api/incidents", { method: "POST", body: JSON.stringify(values) });
  },
  parsePaste(text) {
    return request("/api/parse-paste", { method: "POST", body: JSON.stringify({ text }) });
  },
  createBatch(items) {
    return request("/api/batches", { method: "POST", body: JSON.stringify({ items }) });
  },
  batch(jobId) {
    return request(`/api/batches/${encodeURIComponent(jobId)}`);
  },
};

export function localDateValue(date = new Date()) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function normalizeDate(value) {
  const text = String(value || "").trim();
  const match = text.match(/^(\d{4})[\/-](\d{1,2})[\/-](\d{1,2})$/);
  if (!match) return text;
  return `${match[1]}-${match[2].padStart(2, "0")}-${match[3].padStart(2, "0")}`;
}

export function isValidDateValue(value) {
  const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return false;
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return date.getFullYear() === Number(match[1])
    && date.getMonth() === Number(match[2]) - 1
    && date.getDate() === Number(match[3]);
}

export function sourceKey(source) {
  return `${source?.entity || ""}:${source?.id || ""}`;
}

export function sourceSubtitle(source) {
  if (source?.type === "opportunity") {
    return [source.customer, source.opportunity].filter(Boolean).join(" · ") || "商机技术支持";
  }
  return source?.customer || "客户技术支持";
}

export function sourceName(source) {
  return source?.name || sourceSubtitle(source);
}

export function newRowKey() {
  return globalThis.crypto?.randomUUID?.() || `row-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function rowIsEditable(row) {
  return !["queued", "running", "succeeded"].includes(row.status);
}
