/**
 * Menus and lists (Mantine Menu and Combobox): one highlight glides from item to item, with the
 * mouse and with the keyboard, instead of each item lighting up on its own. The highlight is drawn
 * by the list itself (CSS `[data-list-glide]::before`), placed here from the item's position.
 */
const ITEM = "[data-combobox-option], .mantine-Menu-item";

function place(item: HTMLElement) {
  const box = item.offsetParent as HTMLElement | null;
  if (!box || box === document.body || item.hasAttribute("data-disabled")) return;
  const first = !box.hasAttribute("data-list-glide") || box.hasAttribute("data-list-glide-off");
  if (first) box.setAttribute("data-list-glide-instant", "");
  box.setAttribute("data-list-glide", "");
  box.removeAttribute("data-list-glide-off");
  box.style.setProperty("--gl-x", `${item.offsetLeft}px`);
  box.style.setProperty("--gl-y", `${item.offsetTop}px`);
  box.style.setProperty("--gl-w", `${item.offsetWidth}px`);
  box.style.setProperty("--gl-h", `${item.offsetHeight}px`);
  if (first) requestAnimationFrame(() => box.removeAttribute("data-list-glide-instant"));
}

export function installMenuGlide(): () => void {
  const over = (event: PointerEvent) => {
    const item = (event.target as Element | null)?.closest?.<HTMLElement>(ITEM);
    if (item) place(item);
  };
  const out = (event: PointerEvent) => {
    const from = (event.target as Element | null)?.closest?.<HTMLElement>(ITEM);
    const to = (event.relatedTarget as Element | null)?.closest?.<HTMLElement>(ITEM);
    const box = from?.offsetParent as HTMLElement | null;
    // Leaving the list: the highlight fades where it was, unless the keyboard holds an item
    if (from && !to && box && !box.querySelector("[data-combobox-selected], [data-hovered]")) box.setAttribute("data-list-glide-off", "");
  };
  const marks = new MutationObserver((records) => {
    for (const record of records) {
      const item = record.target as HTMLElement;
      if (item.matches?.(ITEM) && (item.hasAttribute("data-combobox-selected") || item.hasAttribute("data-hovered"))) place(item);
    }
  });
  document.addEventListener("pointerover", over, true);
  document.addEventListener("pointerout", out, true);
  marks.observe(document.body, { subtree: true, attributes: true, attributeFilter: ["data-combobox-selected", "data-hovered"] });
  return () => {
    document.removeEventListener("pointerover", over, true);
    document.removeEventListener("pointerout", out, true);
    marks.disconnect();
  };
}
