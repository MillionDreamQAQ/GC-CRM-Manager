import test from "node:test";
import assert from "node:assert/strict";

import {
  buildForumContent,
  clearStoredForumCookie,
  loadStoredForumCookie,
  saveStoredForumCookie,
} from "../src/lib/forum.js";


test("keeps forum body line breaks without adding CRM association metadata", () => {
  assert.equal(
    buildForumContent({
      description: "第一行\r\n第二行",
      sourceName: "Acme",
      actualEnd: "2026-09-04",
      crmUrl: "https://crm.example/case/1",
    }),
    "第一行\n第二行",
  );
});

test("stores and clears a forum cookie through the browser storage helpers", () => {
  const values = new Map();
  const storage = {
    getItem(key) {
      return values.get(key) ?? null;
    },
    setItem(key, value) {
      values.set(key, String(value));
    },
    removeItem(key) {
      values.delete(key);
    },
  };

  assert.equal(loadStoredForumCookie(storage), "");
  assert.equal(saveStoredForumCookie("  sid=abc; token=xyz  ", storage), true);
  assert.equal(loadStoredForumCookie(storage), "sid=abc; token=xyz");
  assert.equal(clearStoredForumCookie(storage), true);
  assert.equal(loadStoredForumCookie(storage), "");
});
