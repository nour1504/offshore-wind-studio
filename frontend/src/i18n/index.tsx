/**
 * English and French texts, kept next to the pages that use them.
 *
 *   const messages = defineMessages({ en: { title: "Farms", count: "{n} turbines" },
 *                                     fr: { title: "Parcs", count: "{n} éoliennes" } });
 *   const t = useT(messages);  t("count", { n: 80 })
 *
 * The French texts must have exactly the keys of the English ones (checked by TypeScript).
 */
import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";

export type Lang = "en" | "fr";

type Tree = { readonly [key: string]: string | Tree };

// The same keys as T, with string leaves
export type Shape<T> = { readonly [K in keyof T]: T[K] extends string ? string : Shape<T[K]> };

// "a" | "b.c" ... for every leaf of T
type Leaves<T, P extends string = ""> = {
  [K in keyof T & string]: T[K] extends string ? `${P}${K}` : Leaves<T[K], `${P}${K}.`>;
}[keyof T & string];

export interface Messages<T extends Tree> {
  en: T;
  fr: Shape<T>;
}

export function defineMessages<const T extends Tree>(messages: { en: T; fr: Shape<T> }): Messages<T> {
  return messages;
}

export type Vars = Record<string, string | number>;

function lookup(tree: Tree, key: string): string | undefined {
  let node: string | Tree | undefined = tree;
  for (const part of key.split(".")) {
    if (node === undefined || typeof node === "string") return undefined;
    node = node[part];
  }
  return typeof node === "string" ? node : undefined;
}

/**
 * Replaces {name} by its value, and {name|one|other} by the singular or plural form, where #
 * stands for the number ("{n|# farm|# farms}"). French uses the singular for 0 and 1.
 */
export function format(text: string, vars?: Vars, lang: Lang = "en"): string {
  if (!vars) return text;
  return text.replace(/\{(\w+)(?:\|([^|}]*)\|([^}]*))?\}/g, (whole, name: string, one?: string, other?: string) => {
    if (!(name in vars)) return whole;
    const value = vars[name];
    if (one === undefined || other === undefined) return String(value);
    const n = Number(value);
    const singular = lang === "fr" ? Math.abs(n) < 2 : n === 1;
    return (singular ? one : other).replace(/#/g, String(value));
  });
}

interface LangContext {
  lang: Lang;
  setLang: (lang: Lang) => void;
}

const Context = createContext<LangContext>({ lang: "en", setLang: () => undefined });

export function I18nProvider({ lang, setLang, children }: LangContext & { children: ReactNode }) {
  const value = useMemo(() => ({ lang, setLang }), [lang, setLang]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useLang(): LangContext {
  return useContext(Context);
}

export type Translate<T extends Tree> = (key: Leaves<T>, vars?: Vars) => string;

export function useT<T extends Tree>(messages: Messages<T>): Translate<T> {
  const { lang } = useLang();
  return useCallback(
    (key: Leaves<T>, vars?: Vars) => {
      const text = lookup(messages[lang] as Tree, key) ?? lookup(messages.en, key) ?? key;
      return format(text, vars, lang);
    },
    [lang, messages],
  );
}

/** Times from the server are UTC; those written without a zone ("2025-10-01T00:00:00") too. */
export function parseUtc(iso: string): Date {
  // Date-only strings are already read as UTC by JavaScript
  const zoned = /^\d{4}-\d{2}-\d{2}$/.test(iso) || /([zZ]|[+-]\d\d:?\d\d)$/.test(iso);
  return new Date(zoned ? iso : `${iso}Z`);
}

/** Locale-aware formatting of numbers and UTC dates. */
export function useFormat() {
  const { lang } = useLang();
  return useMemo(() => {
    const locale = lang === "fr" ? "fr-FR" : "en-GB";
    const numbers = new Map<string, Intl.NumberFormat>();
    const numberFormat = (digits: number, compact = false) => {
      const key = `${digits}-${compact}`;
      let f = numbers.get(key);
      if (!f) {
        f = new Intl.NumberFormat(locale, {
          maximumFractionDigits: digits,
          minimumFractionDigits: compact ? 0 : digits,
          notation: compact ? "compact" : "standard",
        });
        numbers.set(key, f);
      }
      return f;
    };
    const dateTime = new Intl.DateTimeFormat(locale, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "UTC",
    });
    const date = new Intl.DateTimeFormat(locale, { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" });
    const relative = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
    return {
      locale,
      /** A number with a fixed count of decimals; "–" when missing. */
      number: (value: number | null | undefined, digits = 1) =>
        value === null || value === undefined || !Number.isFinite(value) ? "–" : numberFormat(digits).format(value),
      compact: (value: number) => numberFormat(1, true).format(value),
      percent: (fraction: number | null | undefined, digits = 1) =>
        fraction === null || fraction === undefined || !Number.isFinite(fraction)
          ? "–"
          : `${numberFormat(digits).format(fraction * 100)} %`,
      /** Date and time in UTC, the reference time of the application. */
      dateTime: (iso: string | null | undefined) => (iso ? `${dateTime.format(parseUtc(iso))} UTC` : "–"),
      date: (iso: string | null | undefined) => (iso ? date.format(parseUtc(iso)) : "–"),
      ago: (iso: string | null | undefined) => {
        if (!iso) return "–";
        const seconds = (parseUtc(iso).getTime() - Date.now()) / 1000;
        const steps: [number, Intl.RelativeTimeFormatUnit][] = [
          [60, "second"],
          [3600, "minute"],
          [86400, "hour"],
          [Infinity, "day"],
        ];
        const divisors: Record<string, number> = { second: 1, minute: 60, hour: 3600, day: 86400 };
        for (const [limit, unit] of steps) {
          if (Math.abs(seconds) < limit) return relative.format(Math.round(seconds / divisors[unit]), unit);
        }
        return "–";
      },
      duration: (seconds: number | null | undefined) => {
        if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return "–";
        const minutes = Math.round(seconds / 60);
        const h = Math.floor(minutes / 60);
        const m = minutes % 60;
        if (h >= 48) return `${numberFormat(1).format(seconds / 86400)} ${lang === "fr" ? "j" : "d"}`;
        return h > 0 ? `${h} h ${String(m).padStart(2, "0")}` : `${m} min`;
      },
      bytes: (value: number | null | undefined) => {
        if (value === null || value === undefined) return "–";
        const units = lang === "fr" ? ["o", "Ko", "Mo", "Go", "To"] : ["B", "KB", "MB", "GB", "TB"];
        let v = value;
        let i = 0;
        while (v >= 1000 && i < units.length - 1) {
          v /= 1000;
          i += 1;
        }
        return `${numberFormat(i === 0 ? 0 : 1).format(v)} ${units[i]}`;
      },
    };
  }, [lang]);
}
