import type { NamelistValue, OptionSchema, Scalar } from "../../../api/types";

/** Read scalar/list syntax without splitting a quoted string containing commas. */
export function parseNamelistValue(text: string, schema?: OptionSchema): NamelistValue | null {
  const parts: string[] = []; let current = ""; let quote = "";
  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (quote) { current += char; if (char === quote) { if (text[i + 1] === quote) current += text[++i]; else quote = ""; } }
    else if (char === "'" || char === '"') { quote = char; current += char; }
    else if (char === ",") { parts.push(current.trim()); current = ""; }
    else current += char;
  }
  if (quote) return null; parts.push(current.trim());
  const scalar = (value: string): Scalar | null => {
    const kind = schema?.type.toLowerCase() ?? "";
    if (!value && !kind.includes("char")) return null;
    if (/^(['"]).*\1$/s.test(value)) return kind && !kind.includes("char") ? null : value.slice(1, -1).replace(/''/g, "'").replace(/""/g, '"');
    if (kind.includes("char")) return value;
    if (/^\.?true\.?$/i.test(value)) return kind.includes("integer") || kind.includes("real") ? null : true;
    if (/^\.?false\.?$/i.test(value)) return kind.includes("integer") || kind.includes("real") ? null : false;
    if (kind.includes("logical")) return null;
    const n = Number(value.replace(/([\d.])[dD]([+-]?\d+)$/, "$1e$2"));
    if (value && Number.isFinite(n)) return kind.includes("integer") && !Number.isInteger(n) ? null : n;
    return kind.includes("integer") || kind.includes("real") ? null : value;
  };
  const values = parts.map((part) => !part && parts.length > 1 ? null : scalar(part));
  if (values.some((value, index) => value === null && parts[index] !== "")) return null;
  return values.length === 1 ? values[0]! : values;
}
export function formatNamelistValue(value: NamelistValue | undefined): string {
  if (value === undefined) return "";
  if (structuredNamelistValue(value)) return JSON.stringify(value, null, 2);
  const scalar = (item: NamelistValue) => item === null ? "" : typeof item === "boolean" ? item ? ".true." : ".false." : typeof item === "string" ? `'${item.replace(/'/g, "''")}'` : String(item);
  return Array.isArray(value) ? value.map(scalar).join(", ") : scalar(value);
}

export function structuredNamelistValue(value: NamelistValue): boolean {
  return typeof value === "object" && value !== null && (!Array.isArray(value) || value.some((item) => typeof item === "object" && item !== null));
}
export function validNamelistJson(value: unknown): value is NamelistValue {
  return value === null || typeof value === "string" || typeof value === "boolean" || typeof value === "number" && Number.isFinite(value) || Array.isArray(value) && value.every(validNamelistJson) || typeof value === "object" && value !== null && Object.values(value).every(validNamelistJson);
}

/** A schema description made readable. Some start with their default ("0, — minutes between…"),
    others repeat themselves after it ("activate ocean model (…) 0 — activate ocean model (…)"). */
export function cleanDescription(text: string): string {
  let clean = text.replace(/\s+/g, " ").trim().replace(/^(?:\.?(?:true|false)\.?|[-+\d.eE]+)?\s*,?\s*[\u2014\u2013\uFFFD]\s*/i, "");
  const repeated = /^(.+?)\s+(?:\.?(?:true|false)\.?|[-+\d.eE'"]*)\s*,?\s*[\u2014\u2013\uFFFD]\s*(.+)$/i.exec(clean);
  if (repeated) {
    const [, first, second] = repeated;
    const start = (value: string) => value.toLowerCase().replace(/[^a-z0-9]/g, "").slice(0, 24);
    if (start(first) && start(second).startsWith(start(first).slice(0, Math.min(24, start(first).length)))) clean = first;
  }
  return clean ? clean.charAt(0).toUpperCase() + clean.slice(1) : "";
}
