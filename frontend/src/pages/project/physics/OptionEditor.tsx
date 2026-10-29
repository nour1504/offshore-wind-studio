import { Button, Group, SegmentedControl, Select, SimpleGrid, Stack, Text, Textarea, TextInput } from "@mantine/core";
import { IconArrowBackUp } from "@tabler/icons-react";
import { type ReactNode, useEffect, useState } from "react";
import type { NamelistValue, OptionSchema, Scalar } from "../../../api/types";
import { useT } from "../../../i18n";
import { FieldLabel, NumberField } from "../../../ui/Inputs";
import { useChoiceData } from "./ChoiceEditor";
import { messages } from "./messages";
import { cleanDescription, formatNamelistValue, parseNamelistValue, structuredNamelistValue, validNamelistJson } from "./values";

/** What kind of field suits an option: a yes/no, a list of named choices, a number or text. */
export function fieldKind(schema: OptionSchema | undefined, value: NamelistValue | undefined, named: boolean): "logical" | "choice" | "integer" | "real" | "character" | "text" {
  const type = schema?.type.toLowerCase() ?? "";
  if (type.includes("logical") || (!type && typeof value === "boolean")) return "logical";
  if (named) return "choice";
  if (type.includes("integer")) return "integer";
  if (type.includes("real")) return "real";
  if (type.includes("char")) return "character";
  if (!type && typeof value === "number") return "real";
  return "text";
}

/**
 * One value of a namelist option, with the field its type calls for. `onChange(null)` leaves a
 * domain unset (WRF then takes the default), when `clearable`.
 */
export function NamelistField({ name, value, schema, label, onChange, readOnly, clearable }: { name: string; value: Scalar | null; schema?: OptionSchema; label?: string; onChange: (value: Scalar | null) => void; readOnly?: boolean; clearable?: boolean }) {
  const t = useT(messages);
  const choices = useChoiceData(name, [value]);
  const kind = fieldKind(schema, value ?? undefined, Boolean(choices));
  const [text, setText] = useState(formatNamelistValue(value));
  const [error, setError] = useState(false);
  useEffect(() => { setText(formatNamelistValue(value)); setError(false); }, [value]);
  if (kind === "logical") {
    return <Stack gap={4}>{label && <Text size="xs" c="dimmed">{label}</Text>}<SegmentedControl size="xs" fullWidth disabled={readOnly} aria-label={label ?? name} value={value === true ? "true" : value === false ? "false" : ""} onChange={(next) => onChange(next === "true")} data={[{ value: "true", label: t("yes") }, { value: "false", label: t("no") }]} /></Stack>;
  }
  if (kind === "choice" && choices) {
    return <Select size="xs" label={label} aria-label={label ?? name} data={choices} value={value === null ? null : String(value)} allowDeselect={false} disabled={readOnly} onChange={(next) => next !== null && onChange(Number(next))} />;
  }
  if (kind === "integer" || kind === "real") {
    return <NumberField size="xs" label={label} aria-label={label ?? name} readOnly={readOnly} allowDecimal={kind === "real"} unit={schema?.units || undefined} value={typeof value === "number" ? value : null} onValue={onChange} onClear={clearable ? () => onChange(null) : undefined} />;
  }
  const commit = () => {
    if (readOnly) return;
    if (clearable && !text.trim()) { setError(false); onChange(null); return; }
    const parsed = kind === "character" ? text : parseNamelistValue(text, schema);
    const invalid = parsed === null || Array.isArray(parsed) || (typeof parsed === "object" && parsed !== null);
    setError(invalid); if (!invalid) onChange(parsed as Scalar);
  };
  return <TextInput size="xs" label={label} aria-label={label ?? name} readOnly={readOnly} value={text} error={error ? t("invalid") : undefined} onChange={(event) => setText(event.currentTarget.value)} onBlur={commit} onKeyDown={(event) => { if (event.key === "Enter") commit(); }} styles={kind === "character" ? undefined : { input: { fontFamily: "var(--mantine-font-family-monospace)" } }} />;
}

/** A whole value typed as text: lists ("1, 2, 3") or structured values (JSON). */
function TextValue({ value, schema, label, onChange, readOnly }: { value: NamelistValue; schema?: OptionSchema; label: string; onChange: (value: NamelistValue) => void; readOnly?: boolean }) {
  const t = useT(messages); const [text, setText] = useState(formatNamelistValue(value)); const [error, setError] = useState(false);
  useEffect(() => { setText(formatNamelistValue(value)); setError(false); }, [value]);
  const structured = structuredNamelistValue(value);
  const commit = () => {
    if (readOnly) return;
    if (structured) { try { const parsed: unknown = JSON.parse(text); if (!validNamelistJson(parsed)) { setError(true); return; } setError(false); onChange(parsed); } catch { setError(true); } return; }
    const parsed = parseNamelistValue(text, schema); setError(parsed === null); if (parsed !== null) onChange(parsed);
  };
  if (structured) return <Textarea readOnly={readOnly} size="xs" aria-label={label} value={text} minRows={3} autosize maxRows={12} error={error ? t("invalid") : undefined} onChange={(event) => setText(event.currentTarget.value)} onBlur={commit} styles={{ input: { fontFamily: "var(--mantine-font-family-monospace)" } }} />;
  return <TextInput readOnly={readOnly} size="xs" aria-label={label} value={text} error={error ? t("invalid") : undefined} onChange={(event) => setText(event.currentTarget.value)} onBlur={commit} onKeyDown={(event) => { if (event.key === "Enter") commit(); }} styles={{ input: { fontFamily: "var(--mantine-font-family-monospace)" } }} />;
}

/**
 * One namelist option: its name, what it does, and its value for each domain. An option another
 * page controls (dates, domains, outputs, farms) is locked here and says where to change it; a
 * value typed here by hand can always be undone.
 */
export function OptionEditor({ name, value, schema, domains, label, overridden, managedBy, onChange, onReset, readOnly }: { name: string; value: NamelistValue; schema?: OptionSchema; domains: number; label?: string; generated?: NamelistValue; overridden?: boolean; managedBy?: ReactNode; onChange: (value: NamelistValue) => void; onReset: () => void; readOnly?: boolean }) {
  const t = useT(messages);
  // A project without a domain yet still shows one field, which applies to every domain
  const count = Math.max(1, domains);
  const locked = readOnly || Boolean(managedBy);
  const description = cleanDescription(schema?.description ?? "");
  const perDomain = schema?.per_domain && !structuredNamelistValue(value) && (!Array.isArray(value) || value.every((item) => item === null || typeof item !== "object"));
  const values: (Scalar | null)[] = Array.from({ length: count }, (_, index) => {
    const item = Array.isArray(value) ? (index < value.length ? value[index] : schema?.default ?? value[0] ?? null) : value;
    return item === undefined || (typeof item === "object" && item !== null) ? null : item as Scalar | null;
  });
  const scalar = !Array.isArray(value) && !structuredNamelistValue(value);
  return <Stack gap={8} className="ows-option" data-locked={locked || undefined}>
    <Group justify="space-between" wrap="nowrap" gap="xs" align="flex-start">
      <Stack gap={2} style={{ minWidth: 0 }}>
        <Text size="sm" fw={600} className={label ? undefined : "ows-option-code"}><FieldLabel label={label ?? name} info={description || schema ? `${name}${schema?.units ? ` (${schema.units})` : ""}${description ? ` — ${description}` : ""}${schema ? ` · ${t("wrfDefault", { value: formatNamelistValue(schema.default) })}` : ""}` : undefined} /></Text>
        {label && <Text ff="monospace" size="xs" c="dimmed">{name}</Text>}
      </Stack>
      {overridden && <Button size="compact-xs" variant="subtle" color="gray" leftSection={<IconArrowBackUp size={14} />} onClick={onReset} style={{ flexShrink: 0 }}>{t("undoMine")}</Button>}
    </Group>
    {perDomain
      ? <SimpleGrid cols={{ base: 1, xs: Math.min(count, 2), lg: Math.min(count, 3) }} spacing="xs">{values.map((item, index) => <NamelistField key={index} name={name} schema={schema} readOnly={locked} clearable={domains > 0} value={item} label={domains > 1 ? t("domainShort", { n: String(index + 1).padStart(2, "0") }) : undefined} onChange={(next) => { const updated = [...values]; updated[index] = next; onChange(domains > 0 ? updated : next); }} />)}</SimpleGrid>
      : scalar ? <NamelistField name={name} schema={schema} readOnly={locked} value={value as Scalar | null} onChange={(next) => next !== null && onChange(next)} />
      : <TextValue readOnly={locked} value={value} schema={schema} label={structuredNamelistValue(value) ? `${t("value")} (JSON)` : t("value")} onChange={onChange} />}
    {managedBy ? <Text size="xs" c="dimmed">{managedBy}</Text>
      : null}
  </Stack>;
}
