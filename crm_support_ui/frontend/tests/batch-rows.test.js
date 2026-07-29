import test from "node:test";
import assert from "node:assert/strict";

import { removeSucceededRows, rowIsRemovable } from "../src/lib/crm.js";


test("removes only successfully created batch rows", () => {
  const rows = [
    { key: "draft", status: "draft" },
    { key: "success-1", status: "succeeded" },
    { key: "failed", status: "failed" },
    { key: "success-2", status: "succeeded" },
  ];

  assert.deepEqual(removeSucceededRows(rows), [rows[0], rows[2]]);
});


test("allows removing completed rows but not active job rows", () => {
  assert.equal(rowIsRemovable({ status: "draft" }), true);
  assert.equal(rowIsRemovable({ status: "failed" }), true);
  assert.equal(rowIsRemovable({ status: "succeeded" }), true);
  assert.equal(rowIsRemovable({ status: "queued" }), false);
  assert.equal(rowIsRemovable({ status: "running" }), false);
});
