// Executed inside the page/frame via Frame.evaluate(). Stamps every
// candidate interactive element with observation-scoped attributes so it can
// be re-resolved later ONLY if the exact same DOM node still exists. A
// rerender/replace that creates a new node (even with identical text/id)
// will not carry these attributes forward, which is what makes stale-target
// rejection possible without retained ElementHandles.
export function snapshotInPage(observationId: string): Array<{
  refToken: string;
  role: string;
  name: string;
  value: string | undefined;
  id: string | null;
}> {
  const SELECTOR = 'input, textarea, select, button, a[href], [role], [contenteditable="true"]';
  const nodes = Array.from(document.querySelectorAll(SELECTOR)) as HTMLElement[];
  const out: Array<{ refToken: string; role: string; name: string; value: string | undefined; id: string | null }> =
    [];
  let i = 0;
  for (const el of nodes) {
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") continue;
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) continue;

    const refToken = "r" + i++;
    el.setAttribute("data-bk-obs", observationId);
    el.setAttribute("data-bk-ref", refToken);

    const tag = el.tagName.toLowerCase();
    let role = el.getAttribute("role") || "";
    if (!role) {
      const TEXTLIKE_INPUT_TYPES = new Set(["text", "search", "email", "tel", "url", "password", ""]);
      if (tag === "a") role = "link";
      else if (tag === "button") role = "button";
      else if (tag === "input") {
        const type = (el as HTMLInputElement).type || "text";
        if (type === "checkbox") role = "checkbox";
        else if (type === "radio") role = "radio";
        else if (type === "submit" || type === "button") role = "button";
        else if (TEXTLIKE_INPUT_TYPES.has(type)) role = "textbox";
        else role = type; // e.g. "file", "range", "color" keep their own identity
      } else if (tag === "select") role = "combobox";
      else if (tag === "textarea") role = "textbox";
      else role = "generic";
    }

    const labelText = (el as HTMLInputElement).labels?.[0]?.textContent?.trim();
    const name =
      el.getAttribute("aria-label") ||
      labelText ||
      el.getAttribute("placeholder") ||
      (el.textContent || "").trim().slice(0, 120) ||
      el.id ||
      "";

    let value: string | undefined;
    if ("value" in el) value = (el as HTMLInputElement).value;
    else if ((el as HTMLElement).isContentEditable) value = el.textContent || "";

    out.push({ refToken, role, name, value, id: el.id || null });
  }
  return out;
}
