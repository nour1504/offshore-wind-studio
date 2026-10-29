/**
 * Icon tools above a map or a 3D view, as in drawing and mapping software: a group of square
 * buttons, each named in a tooltip. A toggle shows or hides one thing; a choice picks one of a
 * few, with a highlight that slides from one to the other.
 */
import { Menu, Tooltip, UnstyledButton } from "@mantine/core";
import { type Icon, IconCheck } from "@tabler/icons-react";
import type { ReactNode } from "react";

const SIZE = 30;
const GAP = 2;

function Tip({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <Tooltip
      label={hint ? <><strong>{label}</strong><br /><span className="ows-tool-hint">{hint}</span></> : label}
      multiline={Boolean(hint)}
      w={hint ? 240 : undefined}
      openDelay={250}
      transitionProps={{ transition: "pop", duration: 140 }}
      withArrow
    >
      {children}
    </Tooltip>
  );
}

/** A row of tools; groups are separated by a thin rule. */
export function ToolBar({ children, label }: { children: ReactNode; label: string }) {
  return <div className="ows-toolbar" role="toolbar" aria-label={label}>{children}</div>;
}

export function ToolGroup({ children }: { children: ReactNode }) {
  return <div className="ows-tool-group">{children}</div>;
}

export function ToolToggle({ icon: Glyph, label, hint, active, onChange }: { icon: Icon; label: string; hint?: string; active: boolean; onChange: (active: boolean) => void }) {
  return (
    <Tip label={label} hint={hint}>
      <UnstyledButton className="ows-tool" data-active={active || undefined} aria-pressed={active} aria-label={label} onClick={() => onChange(!active)} style={{ width: SIZE, height: SIZE }}>
        <Glyph size={17} stroke={1.6} />
      </UnstyledButton>
    </Tip>
  );
}

/** A plain action (remove, close). */
export function ToolButton({ icon: Glyph, label, danger, onClick }: { icon: Icon; label: string; danger?: boolean; onClick: () => void }) {
  return (
    <Tip label={label}>
      <UnstyledButton className="ows-tool" data-danger={danger || undefined} aria-label={label} onClick={onClick} style={{ width: SIZE, height: SIZE }}>
        <Glyph size={17} stroke={1.6} />
      </UnstyledButton>
    </Tip>
  );
}

/** A file to download (a CSV table): a link drawn as a tool. */
export function ToolLink({ icon: Glyph, label, href }: { icon: Icon; label: string; href: string }) {
  return (
    <Tip label={label}>
      <UnstyledButton component="a" href={href} download className="ows-tool" aria-label={label} style={{ width: SIZE, height: SIZE }}>
        <Glyph size={17} stroke={1.6} />
      </UnstyledButton>
    </Tip>
  );
}

/** An icon that opens a short list to pick from (a model, a farm); the current one is ticked. */
export function ToolMenu({ icon: Glyph, label, value, options, onChange }: { icon: Icon; label: string; value?: string | null; options: { value: string; label: string }[]; onChange: (value: string) => void }) {
  return (
    <Menu position="top" offset={8} withinPortal shadow="md" transitionProps={{ transition: "pop", duration: 140 }}>
      <Menu.Target>
        <span>
          <Tip label={label}>
            <UnstyledButton className="ows-tool" aria-label={label} style={{ width: SIZE, height: SIZE }}>
              <Glyph size={17} stroke={1.6} />
            </UnstyledButton>
          </Tip>
        </span>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Label>{label}</Menu.Label>
        {options.map((option) => (
          <Menu.Item key={option.value} onClick={() => onChange(option.value)} rightSection={option.value === value ? <IconCheck size={14} /> : null}>
            {option.label}
          </Menu.Item>
        ))}
      </Menu.Dropdown>
    </Menu>
  );
}

/** One of a few: the highlight slides under the one chosen. */
export function ToolChoice<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: { value: T; icon: Icon; label: string; hint?: string }[]; onChange: (value: T) => void }) {
  const index = Math.max(0, options.findIndex((option) => option.value === value));
  return (
    <div className="ows-tool-choice" role="radiogroup" aria-label={label}>
      <span className="ows-tool-slider" style={{ width: SIZE, height: SIZE, transform: `translateX(${index * (SIZE + GAP)}px)` }} />
      {options.map(({ value: option, icon: Glyph, label: name, hint }) => (
        <Tip key={option} label={name} hint={hint}>
          <UnstyledButton className="ows-tool" role="radio" aria-checked={option === value} data-active={option === value || undefined} aria-label={name} onClick={() => onChange(option)} style={{ width: SIZE, height: SIZE }}>
            <Glyph size={17} stroke={1.6} />
          </UnstyledButton>
        </Tip>
      ))}
    </div>
  );
}
