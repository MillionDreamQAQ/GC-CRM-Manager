import { pinyin } from "pinyin-pro";


const SEARCH_FIELDS = [
  "name",
  "customer",
  "opportunity",
  "opportunity_status",
  "owner",
  "subject",
  "description",
  "source_name",
];
const searchIndexCache = new WeakMap();


function normalize(value) {
  return String(value ?? "").normalize("NFKC").toLocaleLowerCase("zh-CN");
}


function buildSearchIndex(source) {
  const original = SEARCH_FIELDS.map((field) => normalize(source[field])).join(" ");
  const syllables = pinyin(original, { toneType: "none", type: "array" });
  const fullPinyin = syllables.join("");
  const initials = syllables.map((syllable) => syllable[0] ?? "").join("");
  return `${original} ${fullPinyin} ${initials}`;
}


export function matchesSourceQuery(source, query) {
  const needle = normalize(query).trim();
  if (!needle) return true;

  let searchIndex = searchIndexCache.get(source);
  if (!searchIndex) {
    searchIndex = buildSearchIndex(source);
    searchIndexCache.set(source, searchIndex);
  }
  return searchIndex.includes(needle.replaceAll(" ", "")) || searchIndex.includes(needle);
}
