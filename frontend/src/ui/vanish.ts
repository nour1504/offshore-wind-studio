/**
 * Text erased in one go (a word, a selection, the whole field) leaves in drifting letters that
 * shrink, blur and fade where it stood. Typing and keys are untouched: only a picture of the
 * text that went.
 */
import { useCallback, useRef } from "react";

import { prefersReducedMotion } from "../motion";

let ruler: CanvasRenderingContext2D | null = null;

/** A ref for the field: listens while the field is there (a dialog may mount it later) */
export function useVanish(): (field: HTMLInputElement | null) => void {
  const detach = useRef<(() => void) | null>(null);
  return useCallback((field: HTMLInputElement | null) => {
    detach.current?.();
    detach.current = null;
    if (!field) return;
    let before = field.value;
    const hold = () => { before = field.value; };
    const erased = (event: Event) => {
      const now = field.value;
      const old = before;
      before = now;
      if ((event as InputEvent).isComposing || now.length > old.length - 2 || prefersReducedMotion()) return;
      // What went: between the start and the end the two texts share
      let start = 0;
      while (start < now.length && now[start] === old[start]) start++;
      let end = 0;
      while (end < now.length - start && now[now.length - 1 - end] === old[old.length - 1 - end]) end++;
      const gone = old.slice(start, old.length - end);
      if (gone.trim().length >= 2) scatter(field, old.slice(0, start), gone);
    };
    field.addEventListener("beforeinput", hold);
    field.addEventListener("input", erased);
    detach.current = () => {
      field.removeEventListener("beforeinput", hold);
      field.removeEventListener("input", erased);
    };
  }, []);
}

function scatter(field: HTMLInputElement, kept: string, gone: string) {
  ruler ??= document.createElement("canvas").getContext("2d");
  if (!ruler) return;
  const style = getComputedStyle(field);
  const font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
  ruler.font = font;
  const box = field.getBoundingClientRect();
  let x = box.left + parseFloat(style.borderLeftWidth) + parseFloat(style.paddingLeft) - field.scrollLeft + ruler.measureText(kept).width;
  const layer = document.createElement("div");
  layer.className = "ows-vanish";
  layer.setAttribute("aria-hidden", "true");
  [...gone].forEach((char, k) => {
    if (char.trim()) {
      const letter = document.createElement("span");
      letter.textContent = char;
      letter.style.cssText = `left:${x}px;top:${box.top + box.height / 2}px;font:${font};color:${style.color};--dx:${12 + ((k * 37) % 26)}px;--dy:${-(6 + ((k * 53) % 22))}px;--k:${k}`;
      layer.append(letter);
    }
    x += ruler!.measureText(char).width;
  });
  document.body.append(layer);
  window.setTimeout(() => layer.remove(), 1000);
}
