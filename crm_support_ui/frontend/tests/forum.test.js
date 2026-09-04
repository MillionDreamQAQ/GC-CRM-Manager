import test from "node:test";
import assert from "node:assert/strict";

import { buildForumContent } from "../src/lib/forum.js";


test("builds a forum body with CRM context without losing line breaks", () => {
  assert.equal(
    buildForumContent({
      description: "第一行\r\n第二行",
      sourceName: "Acme",
      actualEnd: "2026-09-04",
      crmUrl: "https://crm.example/case/1",
    }),
    "第一行\n第二行\n\n---\n关联对象：Acme\n实际结束时间：2026-09-04\nCRM 案例：https://crm.example/case/1",
  );
});
