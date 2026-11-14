/**
 * A technical sheet, as a panel: a title with its action on the right, then label/value rows that
 * come in one after the other; a soft light glides under the row the pointer is on. Used by the
 * Compute page.
 */
import { Group, Text, UnstyledButton } from "@mantine/core";
import { type PointerEvent, type ReactNode, useRef } from "react";


export function Sheet({ title, action, children }: { title: ReactNode; action?: ReactNode; children?: ReactNode }) {
  return (
    <section className="ows-sheet">
      <Group justify="space-between" align="baseline" wrap="nowrap" className="ows-sheet-head">
        <Text component="h2" className="ows-sheet-title">{title}</Text>
        {action}
      </Group>
      {children}
    </section>
  );
}

export function SheetRows({ children }: { children: ReactNode }) {
  const glow = useRef<HTMLSpanElement>(null);
  const hide = () => {
    if (glow.current) glow.current.style.opacity = "0";
  };
  const follow = (event: PointerEvent<HTMLDivElement>) => {
    const light = glow.current;
    const row = (event.target as HTMLElement).closest<HTMLElement>(".ows-sheet-row");
    if (!light || !row || !event.currentTarget.contains(row)) return hide();
    light.style.opacity = "1";
    light.style.transform = `translateY(${row.offsetTop}px)`;
    light.style.height = `${row.offsetHeight}px`;
  };
  return (
    <div className="ows-sheet-rows" onPointerMove={follow} onPointerLeave={hide}>
      <span ref={glow} className="ows-sheet-glow" aria-hidden="true" />
      {children}
    </div>
  );
}

export function SheetRow({ label, children }: { label: ReactNode; children: ReactNode }) {
  return (
    <div className="ows-sheet-row">
      <div className="ows-sheet-key">{label}</div>
      <div className="ows-sheet-value">{children}</div>
    </div>
  );
}

/** An action written as a green link. */
export function SheetLink({ children, onClick, disabled, danger }: { children: ReactNode; onClick?: () => void; disabled?: boolean; danger?: boolean }) {
  return (
    <UnstyledButton className="ows-sheet-link" data-danger={danger || undefined} onClick={onClick} disabled={disabled}>
      {children}
    </UnstyledButton>
  );
}

/** A small round state mark: green and beating when ready. */
export function SheetDot({ ok }: { ok: boolean }) {
  return <span className="ows-sheet-dot" data-ok={ok || undefined} />;
}
