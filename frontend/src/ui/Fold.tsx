import { Accordion, Group, Text } from "@mantine/core";
import { IconPlus } from "@tabler/icons-react";
import { type ReactNode, type Ref, useLayoutEffect, useRef, useState } from "react";

import { EASE_GROW, prefersReducedMotion } from "../motion";
import { HelpLink } from "./Help";

/**
 * A section that opens and closes; its title and summary stay visible. Closed at first unless
 * `defaultOpen`; with `lazy`, the content is created when first opened. With `value`, the open
 * section shows that value under its title (a `Spec`); `open` and `onOpenChange` let a page drive it.
 */
export function Fold({ title, aside, value, unit, detail, children, defaultOpen = false, open, onOpenChange, lazy = false, className, help, actions }: {
  title: ReactNode;
  aside?: ReactNode;
  /** The section's value, large on the left once open (the summary while closed) */
  value?: ReactNode;
  unit?: ReactNode;
  /** A second figure under the value */
  detail?: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  lazy?: boolean;
  className?: string;
  help?: string;
  actions?: ReactNode;
}) {
  const [own, setOwn] = useState(defaultOpen);
  const opened = open ?? own;
  const [seen, setSeen] = useState(opened);
  if (opened && !seen) setSeen(true);
  const summary = useRef<HTMLSpanElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  // Where the summary stood when the section was opened, for the value to leave from there
  const from = useRef<DOMRect | null>(null);
  const spec = value !== undefined;

  useLayoutEffect(() => {
    const start = from.current;
    from.current = null;
    if (opened && start) travel(start, panel.current?.querySelector<HTMLElement>(".ows-spec-value") ?? null);
  }, [opened]);

  const shown = aside ?? (spec ? <>{value}{unit ? <> {unit}</> : null}</> : undefined);
  const body = spec ? <Spec value={value} unit={unit} detail={detail}>{actions && <Group justify="flex-end">{actions}</Group>}{children}</Spec>
    : <>{actions && <Group justify="flex-end" mb="lg">{actions}</Group>}{children}</>;
  return (
    <Accordion
      variant="contained"
      radius="lg"
      value={opened ? "content" : null}
      onChange={(next) => {
        const open = next === "content";
        if (open && summary.current && !prefersReducedMotion()) from.current = summary.current.getBoundingClientRect();
        setOwn(open);
        onOpenChange?.(open);
      }}
      className={["ows-disclosure", className].filter(Boolean).join(" ")}
      chevron={<IconPlus size={16} stroke={1.8} />}
      styles={{ control: { paddingBlock: 18 }, content: { paddingTop: 12, paddingBottom: 24 } }}
    >
      <Accordion.Item value="content">
        <div className="ows-disclosure-bar">
          <Accordion.Control>
            <Group justify="space-between" gap="sm" pr="sm" className="ows-disclosure-heading">
              <Text fw={600} fz={17} className="ows-disclosure-title">{title}</Text>
              {shown !== undefined && <Text ref={summary} size="sm" c="dimmed" component="span" className="ows-disclosure-summary">{shown}</Text>}
            </Group>
          </Accordion.Control>
          {help && opened && <span className="ows-disclosure-help"><HelpLink topic={help} /></span>}
        </div>
        <Accordion.Panel ref={panel}>{!lazy || seen ? body : null}</Accordion.Panel>
      </Accordion.Item>
    </Accordion>
  );
}

/**
 * One row of an open section in two columns: on the left what it is (a small label, the value in
 * large type, a second figure, its own tools), on the right what sets it. Rows follow one another
 * with a rule between them.
 */
export function Spec({ label, value, unit, detail, tools, children, valueRef }: {
  label?: ReactNode;
  value: ReactNode;
  unit?: ReactNode;
  detail?: ReactNode;
  tools?: ReactNode;
  children?: ReactNode;
  valueRef?: Ref<HTMLDivElement>;
}) {
  return (
    <div className="ows-spec">
      <div className="ows-spec-side">
        {label !== undefined && <div className="ows-spec-label">{label}</div>}
        <div ref={valueRef} className="ows-spec-value ows-num">{value}{unit !== undefined && unit !== null && unit !== "" && <small>{unit}</small>}</div>
        {detail !== undefined && detail !== null && <div className="ows-spec-detail">{detail}</div>}
        {tools && <div className="ows-spec-tools">{tools}</div>}
      </div>
      <div className="ows-spec-body">{children}</div>
    </div>
  );
}

/** The value leaves the summary's place and grows into its own, above the opening section. */
function travel(start: DOMRect, target: HTMLElement | null) {
  if (!target || !start.width) return;
  const end = target.getBoundingClientRect();
  if (!end.width || !end.height) return;
  const scale = Math.min(1, start.height / end.height);
  const ghost = target.cloneNode(true) as HTMLElement;
  Object.assign(ghost.style, {
    position: "fixed", left: `${end.left}px`, top: `${end.top}px`, width: `${end.width}px`, height: `${end.height}px`,
    margin: "0", zIndex: "300", pointerEvents: "none", transformOrigin: "0 0", animation: "none",
  });
  ghost.setAttribute("aria-hidden", "true");
  document.body.append(ghost);
  target.style.visibility = "hidden";
  const flight = ghost.animate([
    { transform: `translate(${start.left - end.left}px, ${start.top - end.top}px) scale(${scale})`, opacity: 0.55 },
    { transform: "none", opacity: 1 },
  ], { duration: 460, easing: EASE_GROW });
  const land = () => { ghost.remove(); target.style.visibility = ""; };
  flight.onfinish = land;
  flight.oncancel = land;
}
