export const FORUM_TITLE_MAX_LENGTH = 80;
export const FORUM_COOKIE_STORAGE_KEY = "crm-support-ui.forum-cookie";

function getBrowserStorage() {
  try {
    return globalThis.localStorage;
  } catch {
    return null;
  }
}

export function loadStoredForumCookie(storage = getBrowserStorage()) {
  try {
    return String(storage?.getItem(FORUM_COOKIE_STORAGE_KEY) || "").trim();
  } catch {
    return "";
  }
}

export function saveStoredForumCookie(cookie, storage = getBrowserStorage()) {
  const value = String(cookie || "").trim();
  try {
    if (!storage) return false;
    if (value) {
      storage.setItem(FORUM_COOKIE_STORAGE_KEY, value);
    } else {
      storage.removeItem(FORUM_COOKIE_STORAGE_KEY);
    }
    return true;
  } catch {
    return false;
  }
}

export function clearStoredForumCookie(storage = getBrowserStorage()) {
  try {
    if (!storage) return false;
    storage.removeItem(FORUM_COOKIE_STORAGE_KEY);
    return true;
  } catch {
    return false;
  }
}

function normalizedText(value) {
  return String(value || "").replace(/\r\n/g, "\n").trim();
}

export function buildForumContent({ description = "" } = {}) {
  // Forum posts intentionally contain only the text entered for the post.
  // CRM association metadata must never be copied into the public topic.
  return normalizedText(description);
}
