/**
 * Icon tools above a map or a 3D view: square buttons sharing one gliding tooltip; toggles, choices
 * with a sliding highlight, and menus that open out of the bar itself.
 */
import { UnstyledButton } from "@mantine/core";
import { type Icon, IconCheck } from "@tabler/icons-react";
import { createContext, type CSSProperties, type FocusEvent, type KeyboardEvent, type PointerEvent, type ReactNode, useCallback, useContext, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { defineMessages, useT } from "../i18n";
import { prefersReducedMotion } from "../motion";

const messages = defineMessages({ en: { escape: "Esc" }, fr: { escape: "Échap" } });

const SIZE = 30;
const GAP = 2;
/** Width of a menu grown out of the bar, and the time it takes (ms). */
const MENU_WIDTH = 260, MORPH = 380;

interface Tip { label: string; hint?: string }
interface MenuOptions { label: string; value?: string | null; options: { value: string; label: string }[]; onChange: (value: string) => void }
interface Bar {
  tip: (target: HTMLElement | null, tip?: Tip) => void;
  open: (menu: MenuOptions, trigger: HTMLElement) => void;
  opened: string | null;
}

const BarContext = createContext<Bar | null>(null);

/** Name a tool on hover and on keyboard focus, in the bar's one tooltip. */
function useToolTip(label: string, hint?: string) {
  const bar = useContext(BarContext);
  return {
    onPointerEnter: (event: PointerEvent<HTMLElement>) => bar?.tip(event.currentTarget, { label, hint }),
    onFocus: (event: FocusEvent<HTMLElement>) => { if (event.currentTarget.matches(":focus-visible")) bar?.tip(event.currentTarget, { label, hint }); },
    onBlur: () => bar?.tip(null),
  };
}

/** The tooltip of a bar: one dark label that slides from tool to tool, its text changing in place. */
function useGlidingTip() {
  const element = useRef<HTMLDivElement>(null);
  const shown = useRef<HTMLElement | null>(null);
  const tip = useCallback((target: HTMLElement | null, info?: Tip) => {
    const el = element.current;
    if (!el) return;
    shown.current = target && info ? target : null;
    if (!target || !info) return void el.removeAttribute("data-on");
    const box = target.getBoundingClientRect();
    const above = box.top > 56;
    const was = el.hasAttribute("data-on");
    if (!was || prefersReducedMotion()) el.style.transition = "none";
    el.style.transform = `translate(${box.left + box.width / 2}px, ${above ? box.top - 8 : box.bottom + 8}px) translate(-50%, ${above ? "-100%" : "0"})`;
    if (el.dataset.label !== info.label) {
      el.dataset.label = info.label;
      const text = document.createElement("span");
      text.append(info.label);
      if (info.hint) {
        const hint = document.createElement("small");
        hint.textContent = info.hint;
        text.append(hint);
      }
      el.replaceChildren(text);
    }
    if (!was) {
      void el.offsetWidth;
      el.style.transition = "";
    }
    el.setAttribute("data-on", "");
  }, []);
  // A scroll moves the tools away from their name
  useEffect(() => {
    const hide = () => shown.current && tip(null);
    window.addEventListener("scroll", hide, true);
    return () => window.removeEventListener("scroll", hide, true);
  }, [tip]);
  return { element, tip };
}

/** A row of tools; groups are separated by a thin rule. */
export function ToolBar({ children, label }: { children: ReactNode; label: string }) {
  const t = useT(messages);
  const { element, tip } = useGlidingTip();
  const bar = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const [menu, setMenu] = useState<(MenuOptions & { trigger: HTMLElement; from: { w: number; h: number }; closing?: boolean; refocus?: boolean }) | null>(null);
  const current = useRef(menu);
  useLayoutEffect(() => {
    current.current = menu;
  });

  const open = useCallback((options: MenuOptions, trigger: HTMLElement) => {
    const box = bar.current;
    if (!box) return;
    tip(null);
    // Opened again while it shrinks back: the bar's own size is the one kept
    setMenu({ ...options, trigger, from: current.current?.from ?? { w: box.offsetWidth, h: box.offsetHeight } });
  }, [tip]);
  const close = useCallback((refocus: boolean) => {
    if (current.current && !current.current.closing) setMenu({ ...current.current, closing: true, refocus });
  }, []);

  // The bar grows from its own size into the list, and back
  useLayoutEffect(() => {
    const box = bar.current, panel = list.current;
    if (!box || !menu) return;
    const quick = prefersReducedMotion();
    if (menu.closing) {
      // The tools are back (no longer inert): the one that opened the list takes the focus again
      if (menu.refocus) menu.trigger.focus({ preventScroll: true });
      box.style.width = `${menu.from.w}px`;
      box.style.height = `${menu.from.h}px`;
      const done = window.setTimeout(() => {
        box.style.removeProperty("width");
        box.style.removeProperty("height");
        setMenu(null);
      }, quick ? 0 : MORPH);
      return () => window.clearTimeout(done);
    }
    if (!panel) return;
    box.style.transition = "none";
    box.style.width = `${menu.from.w}px`;
    box.style.height = `${menu.from.h}px`;
    void box.offsetWidth;
    box.style.transition = "";
    box.style.width = `${Math.max(menu.from.w, MENU_WIDTH)}px`;
    box.style.height = `${panel.offsetHeight}px`;
    const first = window.setTimeout(() => (panel.querySelector<HTMLElement>("[aria-checked='true']") ?? panel.querySelector<HTMLElement>("[role='menuitemradio']"))?.focus({ preventScroll: true }), quick ? 0 : 200);
    return () => window.clearTimeout(first);
  }, [menu]);

  // A press outside the bar closes the list
  useEffect(() => {
    if (!menu || menu.closing) return;
    const away = (event: globalThis.PointerEvent) => { if (!bar.current?.contains(event.target as Node)) close(false); };
    document.addEventListener("pointerdown", away, true);
    return () => document.removeEventListener("pointerdown", away, true);
  }, [menu, close]);

  const onMenuKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const items = Array.from(event.currentTarget.querySelectorAll<HTMLElement>("[role='menuitemradio']"));
    const at = items.indexOf(document.activeElement as HTMLElement);
    const next = ({ ArrowDown: (at + 1) % items.length, ArrowUp: (at - 1 + items.length) % items.length, Home: 0, End: items.length - 1 } as Record<string, number>)[event.key];
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      close(true);
    } else if (event.key === "Tab") close(false);
    else if (next !== undefined && items.length) {
      event.preventDefault();
      items[next].focus();
    }
  };

  const context: Bar = { tip, open, opened: menu && !menu.closing ? menu.label : null };
  return (
    <BarContext.Provider value={context}>
      <div ref={bar} className="ows-toolbar" data-open={(menu && !menu.closing) || undefined} data-morph={menu ? "" : undefined}>
        <div className="ows-toolbar-row" role="toolbar" aria-label={label} onPointerLeave={() => tip(null)} inert={(menu && !menu.closing) || undefined}>{children}</div>
        {menu && (
          <div ref={list} className="ows-toolbar-menu" role="menu" aria-label={menu.label} onKeyDown={onMenuKey}>
            <div className="ows-toolbar-menu-label">{menu.label}<span>{t("escape")}</span></div>
            <div className="ows-toolbar-menu-items">
              {menu.options.map((option, k) => (
                <button key={option.value} type="button" role="menuitemradio" aria-checked={option.value === menu.value} style={{ "--i": k } as CSSProperties}
                  onClick={() => { menu.onChange(option.value); close(true); }}>
                  <span>{option.label}</span>
                  {option.value === menu.value && <IconCheck size={14} aria-hidden="true" />}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
      {createPortal(<div ref={element} className="ows-tool-tip" aria-hidden="true" />, document.body)}
    </BarContext.Provider>
  );
}

export function ToolGroup({ children }: { children: ReactNode }) {
  return <div className="ows-tool-group">{children}</div>;
}

/** Something named by the bar's tooltip that is not a tool (a count). */
export function ToolText({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return <span className={className} {...useToolTip(label)}>{children}</span>;
}

export function ToolToggle({ icon: Glyph, label, hint, active, onChange }: { icon: Icon; label: string; hint?: string; active: boolean; onChange: (active: boolean) => void }) {
  return (
    <UnstyledButton className="ows-tool" data-active={active || undefined} aria-pressed={active} aria-label={label} aria-description={hint} onClick={() => onChange(!active)} style={{ width: SIZE, height: SIZE }} {...useToolTip(label, hint)}>
      <Glyph size={17} stroke={1.6} />
    </UnstyledButton>
  );
}

/** A plain action (remove, close); its key, if any, in the hint. */
export function ToolButton({ icon: Glyph, label, hint, danger, onClick }: { icon: Icon; label: string; hint?: string; danger?: boolean; onClick: () => void }) {
  return (
    <UnstyledButton className="ows-tool" data-danger={danger || undefined} aria-label={label} aria-description={hint} onClick={onClick} style={{ width: SIZE, height: SIZE }} {...useToolTip(label, hint)}>
      <Glyph size={17} stroke={1.6} />
    </UnstyledButton>
  );
}

/** A link drawn as a tool (to the Exporter tab, its choice made). */
export function ToolLink({ icon: Glyph, label, href }: { icon: Icon; label: string; href: string }) {
  return (
    <UnstyledButton component="a" href={href} className="ows-tool" aria-label={label} style={{ width: SIZE, height: SIZE }} {...useToolTip(label)}>
      <Glyph size={17} stroke={1.6} />
    </UnstyledButton>
  );
}

/** An icon that turns the bar into a short list to pick from (a model, a farm); the current one is ticked. */
export function ToolMenu({ icon: Glyph, label, value, options, onChange }: { icon: Icon; label: string; value?: string | null; options: { value: string; label: string }[]; onChange: (value: string) => void }) {
  const bar = useContext(BarContext);
  return (
    <UnstyledButton className="ows-tool" aria-label={label} aria-haspopup="menu" aria-expanded={bar?.opened === label} style={{ width: SIZE, height: SIZE }} {...useToolTip(label)}
      onClick={(event) => bar?.open({ label, value, options, onChange }, event.currentTarget)}>
      <Glyph size={17} stroke={1.6} />
    </UnstyledButton>
  );
}

/** One of a few: the highlight slides under the one chosen. */
export function ToolChoice<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: { value: T; icon: Icon; label: string; hint?: string }[]; onChange: (value: T) => void }) {
  const index = Math.max(0, options.findIndex((option) => option.value === value));
  return (
    <div className="ows-tool-choice" role="radiogroup" aria-label={label}>
      <span className="ows-tool-slider" style={{ width: SIZE, height: SIZE, transform: `translateX(${index * (SIZE + GAP)}px)` }} />
      {options.map((option) => <ChoiceTool key={option.value} option={option} active={option.value === value} onChange={onChange} />)}
    </div>
  );
}

function ChoiceTool<T extends string>({ option, active, onChange }: { option: { value: T; icon: Icon; label: string; hint?: string }; active: boolean; onChange: (value: T) => void }) {
  const Glyph = option.icon;
  return (
    <UnstyledButton className="ows-tool" role="radio" aria-checked={active} data-active={active || undefined} aria-label={option.label} aria-description={option.hint}
      onClick={() => onChange(option.value)} style={{ width: SIZE, height: SIZE }} {...useToolTip(option.label, option.hint)}>
      <Glyph size={17} stroke={1.6} />
    </UnstyledButton>
  );
}
