/**
 * The main physics choices as menus of named options instead of WRF's numbers. One choice
 * applies to every domain; options set differently per domain keep the detailed editor.
 */
import { Group, Select, SimpleGrid, Stack, Switch, Text } from "@mantine/core";

import type { NamelistValue } from "../../../api/types";
import { defineMessages, useLang, useT } from "../../../i18n";
import { FieldLabel } from "../../../ui/Inputs";
import { Term, type TermId } from "../../../ui/Term";

/** The usual WRF 4.8 values of each option, in the order shown. */
export const CHOICES: Record<string, number[]> = {
  mp_physics: [0, 3, 4, 6, 8, 10, 16, 28],
  ra_lw_physics: [0, 1, 4, 5],
  ra_sw_physics: [0, 1, 2, 4, 5],
  sf_sfclay_physics: [1, 2, 5, 91],
  sf_surface_physics: [0, 1, 2, 3, 4, 5, 7, 8],
  bl_pbl_physics: [0, 1, 2, 5, 7, 8, 11],
  cu_physics: [0, 1, 2, 3, 5, 6, 11, 16],
  diff_opt: [0, 1, 2],
  km_opt: [1, 2, 3, 4],
  damp_opt: [0, 1, 2, 3],
  w_damping: [0, 1],
};

export const TERMS: Record<string, TermId> = {
  mp_physics: "microphysics",
  ra_lw_physics: "radiation",
  ra_sw_physics: "radiation",
  sf_surface_physics: "landSurface",
  bl_pbl_physics: "pbl",
  cu_physics: "cumulus",
};

export const choiceMessages = defineMessages({
  en: {
    differs: "Different per domain",
    domain: "Domain {n}",
    recommended: "recommended",
    farmsNeed: "needed by the wind farms",
    forced: "Priority value from the namelist editor.",
    enabled: "On",
    disabled: "Off",
    names: {
      mp_physics: { 0: "None (no clouds)", 3: "WSM3 (simple)", 4: "WSM5", 6: "WSM6", 8: "Thompson", 10: "Morrison", 16: "WDM6", 28: "Thompson with aerosols" },
      ra_lw_physics: { 0: "None", 1: "RRTM", 4: "RRTMG", 5: "Goddard" },
      ra_sw_physics: { 0: "None", 1: "Dudhia (simple)", 2: "Goddard", 4: "RRTMG", 5: "Goddard (new)" },
      sf_sfclay_physics: { 1: "Revised MM5", 2: "Eta (Janjić)", 5: "MYNN", 91: "Old MM5" },
      sf_surface_physics: { 0: "None", 1: "Thermal diffusion (simple)", 2: "Noah", 3: "RUC", 4: "Noah-MP", 5: "CLM4", 7: "Pleim-Xiu", 8: "SSiB" },
      bl_pbl_physics: { 0: "None", 1: "YSU", 2: "MYJ", 5: "MYNN", 7: "ACM2", 8: "BouLac", 11: "Shin-Hong" },
      cu_physics: { 0: "Off (cells under ~4 km)", 1: "Kain-Fritsch", 2: "Betts-Miller-Janjić", 3: "Grell-Freitas", 5: "Grell 3D", 6: "Tiedtke", 11: "Multi-scale Kain-Fritsch", 16: "New Tiedtke" },
      diff_opt: { 0: "None", 1: "Along model levels (simple)", 2: "In physical space (full)" },
      km_opt: { 1: "Constant", 2: "1.5-order TKE (3D)", 3: "Smagorinsky 3D", 4: "Smagorinsky horizontal" },
      damp_opt: { 0: "None", 1: "Diffusive layer", 2: "Rayleigh (idealised cases)", 3: "Implicit Rayleigh on vertical wind" },
      w_damping: { 0: "Off", 1: "On" },
    },
  },
  fr: {
    differs: "Différent selon les domaines",
    domain: "Domaine {n}",
    recommended: "conseillé",
    farmsNeed: "nécessaire aux parcs éoliens",
    forced: "Valeur prioritaire de l'éditeur des namelists.",
    enabled: "Activée",
    disabled: "Désactivée",
    names: {
      mp_physics: { 0: "Aucune (pas de nuages)", 3: "WSM3 (simple)", 4: "WSM5", 6: "WSM6", 8: "Thompson", 10: "Morrison", 16: "WDM6", 28: "Thompson avec aérosols" },
      ra_lw_physics: { 0: "Aucun", 1: "RRTM", 4: "RRTMG", 5: "Goddard" },
      ra_sw_physics: { 0: "Aucun", 1: "Dudhia (simple)", 2: "Goddard", 4: "RRTMG", 5: "Goddard (nouveau)" },
      sf_sfclay_physics: { 1: "MM5 révisé", 2: "Eta (Janjić)", 5: "MYNN", 91: "Ancien MM5" },
      sf_surface_physics: { 0: "Aucun", 1: "Diffusion thermique (simple)", 2: "Noah", 3: "RUC", 4: "Noah-MP", 5: "CLM4", 7: "Pleim-Xiu", 8: "SSiB" },
      bl_pbl_physics: { 0: "Aucune", 1: "YSU", 2: "MYJ", 5: "MYNN", 7: "ACM2", 8: "BouLac", 11: "Shin-Hong" },
      cu_physics: { 0: "Désactivé (mailles < 4 km)", 1: "Kain-Fritsch", 2: "Betts-Miller-Janjić", 3: "Grell-Freitas", 5: "Grell 3D", 6: "Tiedtke", 11: "Kain-Fritsch multi-échelle", 16: "Nouveau Tiedtke" },
      diff_opt: { 0: "Aucune", 1: "Le long des niveaux du modèle (simple)", 2: "Dans l'espace physique (complète)" },
      km_opt: { 1: "Constant", 2: "TKE d'ordre 1,5 (3D)", 3: "Smagorinsky 3D", 4: "Smagorinsky horizontal" },
      damp_opt: { 0: "Aucun", 1: "Couche diffusive", 2: "Rayleigh (cas idéalisés)", 3: "Rayleigh implicite sur le vent vertical" },
      w_damping: { 0: "Désactivé", 1: "Activé" },
    },
  },
});

const NOTES: Record<string, Record<number, "recommended" | "farmsNeed">> = {
  bl_pbl_physics: { 5: "farmsNeed" },
  sf_sfclay_physics: { 5: "recommended" },
  ra_lw_physics: { 4: "recommended" },
  ra_sw_physics: { 4: "recommended" },
  damp_opt: { 3: "recommended" },
  w_damping: { 1: "recommended" },
};

/** Named choices of an option ("8 · Thompson"), or undefined when it has none. */
export function useChoiceData(name: string, present: (number | boolean | string | null)[] = []) {
  const t = useT(choiceMessages); const { lang } = useLang();
  const values = CHOICES[name.toLowerCase()];
  if (!values) return undefined;
  const names = (choiceMessages[lang].names as unknown as Record<string, Record<string, string>>)[name.toLowerCase()];
  const label = (v: number) => { const text = names?.[String(v)] ?? String(v); const note = NOTES[name.toLowerCase()]?.[v]; return `${note ? `${text} — ${t(note)}` : text}  (${v})`; };
  return [...new Set([...values, ...present.filter((v): v is number => typeof v === "number")])].map((v) => ({ value: String(v), label: label(v) }));
}

/** The single value of an option when every domain has the same, else undefined. */
export function sameEverywhere(value: NamelistValue, domains: number): number | boolean | undefined {
  const values = Array.isArray(value) ? value.slice(0, domains) : [value];
  const first = values[0];
  if (typeof first !== "number" && typeof first !== "boolean") return undefined;
  return values.every((item) => item === first) ? first : undefined;
}

/** Read-only summary of a closed topic, using the same labels as the actual selector. */
export function ChoiceValue({ name, value, domains }: { name: string; value: NamelistValue; domains: number }) {
  const t = useT(choiceMessages); const { lang } = useLang();
  const current = sameEverywhere(value, Math.max(1, domains));
  const names = (choiceMessages[lang].names as unknown as Record<string, Record<string, string>>)[name];
  return <Text size="sm" c="dimmed">{current === undefined ? t("differs") : typeof current === "boolean" ? t(current ? "enabled" : "disabled") : names?.[String(current)] ?? String(current)}</Text>;
}

export function ChoiceEditor({ name, label, info, value, domains, forced, onChange }: { name: string; label: string; info?: string; value: NamelistValue; domains: number; forced: boolean; onChange: (value: NamelistValue) => void }) {
  const t = useT(choiceMessages);
  const { lang } = useLang();
  // A project without a domain yet: one choice, kept for every domain added later
  const count = Math.max(1, domains);
  const current = sameEverywhere(value, count);
  const perDomain = Array.isArray(value) && domains > 0;
  const spread = (next: number | boolean): NamelistValue => (perDomain ? Array.from({ length: domains }, () => next) : next);
  const term = TERMS[name];
  const title = (
    <Group gap={6} wrap="nowrap">
      <Text size="sm" fw={600}>
        {term ? <Term id={term}>{label}</Term> : <FieldLabel label={label} info={info ?? name} />}
      </Text>
    </Group>
  );
  if (typeof current === "boolean") {
    return <Stack gap={6} py={4}><Switch label={title} checked={current} disabled={forced} onChange={(event) => onChange(spread(event.currentTarget.checked))} />{forced && <Text size="xs" c="dimmed">{t("forced")}</Text>}</Stack>;
  }
  const values = CHOICES[name] ?? [];
  const names = (choiceMessages[lang].names as unknown as Record<string, Record<string, string>>)[name];
  const label_ = (v: number) => {
    const text = names?.[String(v)] ?? String(v);
    const note = NOTES[name]?.[v];
    return note ? `${text} — ${t(note)}` : text;
  };
  const present = (Array.isArray(value) ? value.slice(0, count) : [value]).filter((v): v is number => typeof v === "number");
  const data = [...new Set([...values, ...present])].map((v) => ({ value: String(v), label: `${label_(v)}  (${v})` }));
  const perDomainValues = Array.from({ length: count }, (_, i) => (Array.isArray(value) ? (value[i] ?? value[value.length - 1]) : value));
  return (
    <Stack gap={10}>
      {title}
      {current === undefined ? (
        <SimpleGrid cols={{ base: 1, xs: Math.min(count, 2), md: Math.min(count, 3) }} spacing="sm">
          {perDomainValues.map((v, i) => (
            <Select key={i} size="sm" label={t("domain", { n: i + 1 })} aria-label={`${label} · ${t("domain", { n: i + 1 })}`} data={data} value={String(v)} allowDeselect={false} disabled={forced} onChange={(next) => { if (next === null) return; const updated = [...perDomainValues]; updated[i] = Number(next); onChange(updated); }} />
          ))}
        </SimpleGrid>
      ) : (
        <Select data={data} value={String(current)} allowDeselect={false} disabled={forced} aria-label={label} onChange={(next) => next !== null && onChange(spread(Number(next)))} />
      )}
      {forced && (
        <Text size="xs" c="dimmed">
          {t("forced")}
        </Text>
      )}
    </Stack>
  );
}
