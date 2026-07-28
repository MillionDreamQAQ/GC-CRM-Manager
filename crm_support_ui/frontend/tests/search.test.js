import test from "node:test";
import assert from "node:assert/strict";

import { matchesSourceQuery } from "../src/lib/source-search.js";


const source = {
  type: "account",
  name: "葡萄城软件",
  customer: "葡萄城软件",
  opportunity: "",
  opportunity_status: "",
  owner: "徐秦君豪",
};


test("matches a Chinese source name by full pinyin", () => {
  assert.equal(matchesSourceQuery(source, "putaocheng"), true);
});


test("matches a Chinese source name by pinyin initials", () => {
  assert.equal(matchesSourceQuery(source, "ptcrj"), true);
});


test("keeps the existing source text search behavior", () => {
  assert.equal(matchesSourceQuery(source, "葡萄"), true);
  assert.equal(matchesSourceQuery(source, "徐秦"), true);
  assert.equal(matchesSourceQuery(source, ""), true);
  assert.equal(matchesSourceQuery(source, "不存在"), false);
});
