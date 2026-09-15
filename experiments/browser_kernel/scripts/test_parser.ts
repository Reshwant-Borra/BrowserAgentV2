// Regression test for adapters/mcp/snapshotParser.ts. Covers three real bugs
// found and fixed during the spike:
//   1. frame-path nesting via iframe boundaries;
//   2. value extraction confused by ']' characters appearing INSIDE typed
//      text (e.g. "...[]{}...") rather than in an attribute tag;
//   3. YAML double-quoting/escaping not being stripped from values.
import { parseSnapshot, parseTabList } from "../adapters/mcp/snapshotParser.js";

let failures = 0;
function assertEqual(actual: unknown, expected: unknown, label: string) {
  const a = JSON.stringify(actual);
  const e = JSON.stringify(expected);
  if (a !== e) {
    failures++;
    console.error(`FAIL ${label}\n  expected: ${e}\n  actual:   ${a}`);
  } else {
    console.log(`ok   ${label}`);
  }
}

const frameSample = `\`\`\`yaml
- generic [active] [ref=f2e1]:
  - link "index" [ref=f2e3] [cursor=pointer]:
    - /url: /
  - iframe [ref=f2e6]:
    - generic [ref=f3e1]:
      - button "Frame Button A" [ref=f3e3]
      - textbox [ref=f3e4]
  - iframe [ref=f2e10]:
    - generic [ref=f4e1]:
      - iframe [ref=f4e5]:
        - generic [ref=f5e1]:
          - button "Frame Button Nested" [ref=f5e3]
\`\`\``;
const frameEls = parseSnapshot(frameSample);
assertEqual(
  frameEls.find((e) => e.ref === "f3e3")?.framePath,
  ["main", "iframe:f2e6"],
  "single-level iframe path"
);
assertEqual(
  frameEls.find((e) => e.ref === "f5e3")?.framePath,
  ["main", "iframe:f2e10", "iframe:f4e5"],
  "doubly-nested iframe path"
);

const valueSample = `\`\`\`yaml
- textbox "Prefilled" [ref=e13]: old-value-123
- textbox "Special chars" [active] [ref=e16]: "!@#$%^&*()_+-=[]{}#5"
- textbox "unicode" [ref=e20]: "café ☃ 中文#6"
- textbox "Plain input" [ref=e7]
\`\`\``;
const valueEls = parseSnapshot(valueSample);
assertEqual(valueEls.find((e) => e.ref === "e13")?.value, "old-value-123", "unquoted value");
assertEqual(
  valueEls.find((e) => e.ref === "e16")?.value,
  "!@#$%^&*()_+-=[]{}#5",
  "value containing brackets is not mistaken for an attribute tag"
);
assertEqual(valueEls.find((e) => e.ref === "e20")?.value, "café ☃ 中文#6", "quoted unicode value is unescaped");
assertEqual(valueEls.find((e) => e.ref === "e7")?.value, undefined, "element with no value stays undefined");

const tabText = `### Result
- 0: (current) [Fixture E - Popups](http://localhost:4173/fixtures/e)
- 1: [Fixture A - Normal typing](http://localhost:4173/fixtures/a)
- 2: [Fixture A - Normal typing](http://localhost:4173/fixtures/a?via=delayed)`;
const rows = parseTabList(tabText);
assertEqual(rows.length, 3, "tab list row count");
assertEqual(rows[0], { index: 0, current: true, title: "Fixture E - Popups", url: "http://localhost:4173/fixtures/e" }, "tab row 0");
assertEqual(rows[2].url, "http://localhost:4173/fixtures/a?via=delayed", "duplicate-title tab row 2 url");

if (failures > 0) {
  console.error(`\n${failures} assertion(s) failed`);
  process.exit(1);
}
console.log("\nall parser assertions passed");
