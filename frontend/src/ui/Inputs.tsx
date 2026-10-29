import { Button, Group, Modal, NumberInput, type NumberInputProps, Stack, Text, Tooltip } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { IconInfoCircle } from "@tabler/icons-react";
import { type ReactNode, useEffect, useRef, useState } from "react";

import { common } from "../i18n/common";
import { defineMessages, useFormat, useLang, useT } from "../i18n";
import { useFieldIssue } from "../app/CaseDraft";

/** A field label with an optional explanation in a tooltip. */
export function FieldLabel({ label, info }: { label: ReactNode; info?: ReactNode }) {
  if (!info) return <>{label}</>;
  return (
    <Group gap={4} wrap="nowrap" component="span">
      {label}
      <Tooltip label={info}>
        <IconInfoCircle size={14} style={{ color: "var(--ows-muted)", verticalAlign: "middle" }} aria-hidden />
      </Tooltip>
    </Group>
  );
}

/** A number with its unit shown inside the field. */
export function UnitInput({ unit, info, label, ...props }: NumberInputProps & { unit?: ReactNode; info?: ReactNode }) {
  const { lang } = useLang();
  return (
    <NumberInput
      // A decimal comma in French (a point typed is taken as one)
      decimalSeparator={lang === "fr" ? "," : "."}
      allowedDecimalSeparators={[".", ","]}
      label={label ? <FieldLabel label={label} info={info} /> : undefined}
      rightSection={
        unit ? (
          <Text size="xs" c="dimmed" pr={6}>
            {unit}
          </Text>
        ) : undefined
      }
      rightSectionWidth={unit ? 48 : undefined}
      {...props}
    />
  );
}

interface NumberFieldProps extends Omit<NumberInputProps, "value" | "onChange" | "defaultValue"> {
  value: number | null | undefined;
  /** A finite number within min and max */
  onValue: (value: number) => void;
  /** Called when the field is left empty; without it, an empty field goes back to the value */
  onClear?: () => void;
  /** Report the value once, on leaving the field or pressing Enter: for changes that move other
      things (a domain's size or centre), which half-typed numbers would scramble */
  commitOnBlur?: boolean;
  unit?: ReactNode;
  info?: ReactNode;
  /** The field as the server's checks name it ("windows.useful_hours"): their verdict shows here */
  field?: string;
}

const numberMessages = defineMessages({
  en: { number: "Number expected", atLeast: "≥ {v}", atMost: "≤ {v}" },
  fr: { number: "Nombre attendu", atLeast: "≥ {v}", atMost: "≤ {v}" },
});

/**
 * A number field pleasant to type in: "-", "0.", "49.50" or an empty field stay as typed, only
 * finite numbers within min and max are reported, and leaving the field while it is empty or
 * invalid puts the last value back (out-of-range numbers are brought to the nearest limit).
 */
export function NumberField({ value, onValue, onClear, commitOnBlur = false, min, max, onFocus, onBlur, onKeyDown, field, error, ...props }: NumberFieldProps) {
  const t = useT(numberMessages);
  const f = useFormat();
  const [text, setText] = useState<string | number>(value ?? "");
  const editing = useRef(false);
  // Changes from elsewhere (a click on the map, Discard changes) show up when not typing
  useEffect(() => {
    if (!editing.current) setText(value ?? "");
  }, [value]);
  const inRange = (n: number) => (min === undefined || n >= min) && (max === undefined || n <= max);
  // What is wrong, at once and next to the field: what is typed, then the server's checks
  const typed = typeof text === "number" ? text : text === "" || text === "-" ? null : Number(String(text).replace(",", "."));
  const problem = typed === null ? null
    : !Number.isFinite(typed) ? t("number")
    : min !== undefined && typed < min ? t("atLeast", { v: f.number(min, Number.isInteger(min) ? 0 : 2) })
    : max !== undefined && typed > max ? t("atMost", { v: f.number(max, Number.isInteger(max) ? 0 : 2) })
    : null;
  const issue = useFieldIssue(field);
  const shown = error ?? problem ?? (issue?.severity === "error" ? issue.text : undefined);
  const warning = !shown && issue?.severity === "warning" ? issue.text : undefined;
  return (
    <UnitInput
      {...props}
      error={shown}
      description={warning ? <span className="ows-field-warning">{warning}</span> : props.description}
      inputWrapperOrder={warning ? ["label", "input", "description", "error"] : props.inputWrapperOrder}
      min={min}
      max={max}
      clampBehavior="none"
      value={text}
      onFocus={(event) => {
        editing.current = true;
        onFocus?.(event);
      }}
      onChange={(next) => {
        setText(next);
        if (commitOnBlur) return;
        if (typeof next === "number" && Number.isFinite(next) && inRange(next)) onValue(next);
        else if (next === "" && onClear) onClear();
      }}
      onBlur={(event) => {
        editing.current = false;
        const parsed = typeof text === "number" ? text : Number(String(text).replace(",", "."));
        if (text === "" && onClear) {
          if (commitOnBlur) onClear();
        } else if (text !== "" && Number.isFinite(parsed)) {
          const kept = Math.min(max ?? Infinity, Math.max(min ?? -Infinity, parsed));
          setText(kept);
          if (kept !== value) onValue(kept);
        } else {
          setText(value ?? "");
        }
        onBlur?.(event);
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter") event.currentTarget.blur();
        onKeyDown?.(event);
      }}
    />
  );
}

interface ConfirmProps {
  title: ReactNode;
  text?: ReactNode;
  onConfirm: () => void;
  confirmLabel?: ReactNode;
  loading?: boolean;
  children: (open: () => void) => ReactNode;
  color?: string;
}

/** Asks before a destructive or irreversible action. */
export function Confirm({ title, text, onConfirm, confirmLabel, loading, children, color = "red" }: ConfirmProps) {
  const [opened, { open, close }] = useDisclosure(false);
  const t = useT(common);
  return (
    <>
      {children(open)}
      <Modal opened={opened} onClose={close} title={<Text fw={600}>{title}</Text>} size="sm">
        <Stack>
          {text && <Text size="sm">{text}</Text>}
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>
              {t("cancel")}
            </Button>
            <Button
              color={color}
              loading={loading}
              onClick={() => {
                onConfirm();
                close();
              }}
              data-autofocus
            >
              {confirmLabel ?? t("confirm")}
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}
