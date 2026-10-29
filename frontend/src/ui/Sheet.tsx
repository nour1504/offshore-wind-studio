/**
 * A technical sheet: a rule, a title with its action on the right, then label/value rows. Used by
 * the Compute page.
 */
import { Group, Text, UnstyledButton } from "@mantine/core";
import type { ReactNode } from "react";

export function Sheet({ title, action, children }: { title: ReactNode; action?: ReactNode; children?: ReactNode }) {
  return (
    <section className="ows-sheet">
      <Group justify="space-between" align="baseline" wrap="nowrap">
        <Text component="h2" className="ows-sheet-title">{title}</Text>
        {action}
      </Group>
      {children}
    </section>
  );
}

export function SheetRows({ children }: { children: ReactNode }) {
  return <div className="ows-sheet-rows">{children}</div>;
}

export function SheetRow({ label, children }: { label: ReactNode; children: ReactNode }) {
  return (
    <>
      <div className="ows-sheet-key">{label}</div>
      <div className="ows-sheet-value">{children}</div>
    </>
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

/** A small round state mark: green when ready. */
export function SheetDot({ ok }: { ok: boolean }) {
  return <span className="ows-sheet-dot" data-ok={ok || undefined} />;
}
