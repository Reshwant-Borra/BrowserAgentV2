// Parses Playwright MCP's text/YAML-like accessibility snapshot format into
// structured elements with frame paths. This is the one place MCP's
// text-protocol specifics are allowed to leak, per experiment rules ("small
// adapter-specific translation is expected").
//
// Example input line shapes observed empirically (see scripts/explore_mcp*.ts):
//   - generic [active] [ref=e1]:
//   - link "index" [ref=e3] [cursor=pointer]:
//   - textbox "Prefilled (clear + replace)" [ref=e13]: old-value-123
//   - iframe [ref=f2e6]:
//   - text: Plain input          (no ref -> not a target candidate)

export interface ParsedElement {
  ref: string;
  role: string;
  name: string;
  value: string | undefined;
  framePath: string[];
}

export function extractYamlBlock(snapshotText: string): string {
  const match = snapshotText.match(/```yaml\n([\s\S]*?)\n```/);
  return match ? match[1] : snapshotText;
}

export function parseSnapshot(snapshotText: string): ParsedElement[] {
  const yaml = extractYamlBlock(snapshotText);
  const lines = yaml.split("\n");
  const out: ParsedElement[] = [];
  const stack: Array<{ indent: number; frameLabel: string }> = [{ indent: -1, frameLabel: "main" }];

  for (const rawLine of lines) {
    if (!rawLine.trim().startsWith("-")) continue;
    const indent = rawLine.length - rawLine.trimStart().length;

    while (stack.length > 1 && stack[stack.length - 1].indent >= indent) stack.pop();
    const framePath = stack.map((s) => s.frameLabel);

    const refMatch = rawLine.match(/\[ref=([a-zA-Z0-9]+)\]/);
    const trimmed = rawLine.trim();
    const roleMatch = trimmed.match(/^-\s+([a-zA-Z][a-zA-Z0-9_-]*)/);
    const role = roleMatch?.[1] ?? "";

    if (refMatch) {
      const nameMatch = trimmed.match(/"([^"]*)"/);
      const name = nameMatch?.[1] ?? "";

      // Attribute tags like [ref=e16], [active], [cursor=pointer] can
      // appear both before and after the quoted name, so "everything after
      // the last ']' on the line" (the original approach) breaks whenever
      // the VALUE ITSELF contains a ']' character (e.g. typed text
      // "...[]{}..." in fixture A's special-chars case). Strip every
      // well-formed attribute tag first — those never contain spaces/quotes
      // — so the raw value's own brackets, which don't match this pattern
      // in isolation, are left untouched.
      const withoutTags = trimmed.replace(/\s*\[[a-zA-Z][a-zA-Z0-9_=:.,-]*\]/g, "");
      const withoutName = nameMatch ? withoutTags.replace(`"${nameMatch[1]}"`, "") : withoutTags;
      const valMatch = withoutName.match(/:\s*(.*)$/);
      let value: string | undefined;
      if (valMatch && valMatch[1].trim() !== "") {
        const rawValue = valMatch[1].trim();
        // MCP double-quotes values needing escaping (whitespace-sensitive
        // strings, punctuation): unescape via JSON.parse, which uses the
        // same \" \\ \n \t \uXXXX grammar as YAML double-quoted scalars.
        if (rawValue.startsWith('"') && rawValue.endsWith('"')) {
          try {
            value = JSON.parse(rawValue);
          } catch {
            value = rawValue;
          }
        } else {
          value = rawValue;
        }
      }

      out.push({ ref: refMatch[1], role, name, value, framePath });
    }

    if (role === "iframe" && refMatch) {
      stack.push({ indent, frameLabel: `iframe:${refMatch[1]}` });
    }
  }

  return out;
}

export interface TabRow {
  index: number;
  current: boolean;
  title: string;
  url: string;
}

/** Parses `browser_tabs` list output, e.g.:
 *  ### Result
 *  - 0: (current) [Fixture E - Popups](http://localhost:4173/fixtures/e)
 *  - 1: [Fixture A - Normal typing](http://localhost:4173/fixtures/a)
 */
export function parseTabList(text: string): TabRow[] {
  const rows: TabRow[] = [];
  const lineRe = /^-\s+(\d+):\s*(\(current\)\s*)?\[([^\]]*)\]\(([^)]*)\)\s*$/;
  for (const line of text.split("\n")) {
    const m = line.trim().match(lineRe);
    if (!m) continue;
    rows.push({ index: Number(m[1]), current: !!m[2], title: m[3], url: m[4] });
  }
  return rows;
}
