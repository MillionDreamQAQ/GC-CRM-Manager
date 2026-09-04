export const FORUM_TITLE_MAX_LENGTH = 80;

function normalizedText(value) {
  return String(value || "").replace(/\r\n/g, "\n").trim();
}

export function buildForumContent({
  description = "",
  sourceName = "",
  actualEnd = "",
  crmUrl = "",
} = {}) {
  const body = normalizedText(description);
  const context = [
    sourceName && `关联对象：${normalizedText(sourceName)}`,
    actualEnd && `实际结束时间：${normalizedText(actualEnd)}`,
    crmUrl && `CRM 案例：${normalizedText(crmUrl)}`,
  ].filter(Boolean);

  if (!context.length) return body;
  return [body, body ? "" : null, "---", ...context].filter((line) => line !== null).join("\n");
}
