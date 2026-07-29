import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";


test("keeps the selected mode switcher text readable on hover", async () => {
  const styles = await readFile(new URL("../src/styles.css", import.meta.url), "utf8");

  assert.match(
    styles,
    /\.mode-switcher \.el-segmented__item\.is-selected:hover\s*\{\s*color:\s*var\(--el-segmented-item-selected-color\);\s*\}/,
  );
  assert.doesNotMatch(styles, /\.el-segmented__item-selected:hover/);
});
