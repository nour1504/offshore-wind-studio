import { Alert, Anchor, Box, Group, List, SegmentedControl, Select, SimpleGrid, Stack, Switch, Text, TextInput, UnstyledButton } from "@mantine/core";
import { IconAlertTriangle, IconArrowRight, IconCircleX, IconInfoCircle, IconKey, IconLink, IconUnlink } from "@tabler/icons-react";

import { useSettings } from "../../api/system";
import { useWindowPlan } from "../../api/method";
import type { Grouping, GribInput, InputSource } from "../../api/types";
import { useFieldIssue, useLoadedDraft } from "../../app/CaseDraft";
import { sectionMessages } from "../../app/sections";
import { defineMessages, parseUtc, useFormat, useT } from "../../i18n";
import { href } from "../../router";
import { FieldLabel, NumberField } from "../../ui/Inputs";
import { Page } from "../../ui/Page";
import { Fold } from "../../ui/Fold";
import { QueryView } from "../../ui/States";
import { ToolBar, ToolChoice } from "../../ui/ToolBar";
import { Examination } from "./data/Examination";
import { OwnFiles } from "./data/OwnFiles";
import { WindowStairs } from "./data/stairs/WindowStairs";

const messages = defineMessages({
  en: {
    description:
      "When to simulate, and the weather data that feed the simulation.",
    period: "Period",
    start: "Start (UTC)",
    end: "End (UTC)",
    interval: "Boundary data every",
    intervalInfo: "Interval between two data times: 6 h for GFS, down to 1 h for ERA5.",
    spinUpInfo: "Hours simulated before the start of the period. Not kept.",
    source: "Weather data",
    gfs: "GFS (NOAA)",
    era5: "ERA5 (Copernicus)",
    grib: "My own files",
    automatic: "Missing weather data are downloaded at launch.",
    cache: "Local download cache",
    copied: "Copied",
    cdsMissing: "Your Copernicus (CDS) access token is not set yet.",
    cdsOk: "Copernicus (CDS) access token set.",
    settings: "Settings",
    sst: "Sea temperature (SST)",
    fromInput: "The one in the weather data",
    separate: "A dedicated SST file",
    update: "Let the sea temperature change during the calculation",
    updateInfo:
      "Without update, WRF keeps the initial SST. Recommended beyond a few days.",
    updateEvery: "Update every",
    updateEveryInfo: "Empty: same interval as the weather data.",
    issues: "To check",
    windowsTitle: "Calculation windows",
    length: "Length of a window",
    lengthInfo: "72 h maximum. A shorter period is simulated in one run.",
    chain: "Windows",
    independent: "Independent",
    chained: "Chained",
    spinUp: "Spin-up",
    storeBy: "Store the outputs by",
    weekFit: "{best} h advised",
    independentHint: "Each with its own spin-up, from the last to the first",
    chainedHint: "One spin-up, each carries on the previous one (WRF restart)",
    storeByInfo: "Outputs are stored by block, then assembled over the period. A window stays within one block.",
    month: "Month",
    quarter: "3 months",
    week: "Week",
    window: "Window",
    count: "{n|# calculation|# calculations}",
    other: "Other",
    land: "Land surface (soil)",
    landNone: "The one in the weather data",
    landOwn: "A dedicated source (e.g. ERA5-Land)",
    landPrefix: "Name of the source in WPS",
    landPrefixInfo: "Prefix of the intermediate files (fg_name). Read after the weather data: its fields replace theirs.",
  },
  fr: {
    description:
      "Quand simuler, et les données météo qui alimentent la simulation.",
    period: "Période",
    start: "Début (UTC)",
    end: "Fin (UTC)",
    interval: "Données aux frontières toutes les",
    intervalInfo:
      "Intervalle entre deux échéances des données : 6 h pour GFS, jusqu'à 1 h pour ERA5.",
    spinUpInfo: "Heures simulées avant le début de la période. Non conservées.",
    source: "Données météo",
    gfs: "GFS (NOAA)",
    era5: "ERA5 (Copernicus)",
    grib: "Mes propres fichiers",
    automatic: "Les données météo manquantes sont téléchargées au lancement.",
    cache: "Cache local des téléchargements",
    copied: "Copié",
    cdsMissing: "Votre jeton d'accès Copernicus (CDS) n'est pas encore réglé.",
    cdsOk: "Jeton d'accès Copernicus (CDS) réglé.",
    settings: "Paramètres",
    sst: "Température de la mer (SST)",
    fromInput: "Celle des données météo",
    separate: "Un fichier SST dédié",
    update: "Faire évoluer la température de la mer pendant le calcul",
    updateInfo:
      "Sans mise à jour, WRF garde la SST initiale. Recommandé au-delà de quelques jours.",
    updateEvery: "Mise à jour toutes les",
    updateEveryInfo: "Vide : même intervalle que les données météo.",
    issues: "À vérifier",
    windowsTitle: "Fenêtres de calcul",
    length: "Durée d'une fenêtre",
    lengthInfo: "72 h maximum. Une période plus courte est simulée en une seule fois.",
    chain: "Fenêtres",
    independent: "Indépendantes",
    chained: "Enchaînées",
    spinUp: "Mise en route",
    storeBy: "Ranger les sorties par",
    weekFit: "{best} h conseillées",
    independentHint: "Chacune sa mise en route, de la dernière à la première",
    chainedHint: "Une mise en route, chacune reprend la précédente (restart de WRF)",
    storeByInfo: "Les sorties sont rangées par bloc puis assemblées sur la période. Une fenêtre reste dans un seul bloc.",
    month: "Mois",
    quarter: "3 mois",
    week: "Semaine",
    window: "Fenêtre",
    count: "{n|# calcul|# calculs}",
    other: "Autre",
    land: "Surface terrestre (sol)",
    landNone: "Celle des données météo",
    landOwn: "Une source dédiée (ex. ERA5-Land)",
    landPrefix: "Nom de la source dans WPS",
    landPrefixInfo: "Préfixe des fichiers intermédiaires (fg_name). Lu après les données météo : ses champs remplacent les leurs.",
  },
});

const toInput = (iso: string) => Number.isFinite(parseUtc(iso).getTime()) ? parseUtc(iso).toISOString().slice(0, 16) : iso.slice(0, 16);
const fromInput = (value: string) => (value.length === 16 ? `${value}:00` : value);
const emptyGrib = (vtable: string): GribInput => ({ folder: "", pattern: "*", vtable, custom_vtable: "" });

const INPUT_WORDS = ["Input", "SST", "sea surface", "ERA5", "GFS", "usemonalb"];
// Window lengths that cut a week (168 h) evenly and stay within 72 h
const WEEK_FITS = [24, 42, 56];

/** The calculation windows: the drawing of the plan, then its three settings only. */
function WindowsFold() {
  const t = useT(messages);
  const { draft, update } = useLoadedDraft();
  const plan = useWindowPlan(draft);
  const presets = [6, 12, 24];
  const count = plan.data?.windows.length;
  // By week, a window length that cuts a week evenly (else one short run a week)
  const length = draft.windows.useful_hours;
  const weekAdvice = count !== undefined && count > 1 && draft.windows.grouping === "week" && 168 % length !== 0
    ? WEEK_FITS.reduce((best, h) => (Math.abs(h - length) < Math.abs(best - length) ? h : best), WEEK_FITS[0])
    : null;
  return (
    <Fold title={t("windowsTitle")} aside={count ? t("count", { n: count }) : undefined} lazy>
      <Stack gap="xl">
        <QueryView query={plan}>{(windows) => <WindowStairs plan={windows} />}</QueryView>
        <Group align="flex-end" gap="xl" pb={weekAdvice !== null ? 22 : 0}>
          <Box pos="relative">
            <NumberField label={t("length")} info={t("lengthInfo")} unit="h" min={1} allowDecimal={false} w={180} field="windows.useful_hours" value={draft.windows.useful_hours} onValue={(h) => update((c) => { c.windows.useful_hours = h; })} />
            {weekAdvice !== null && (
              <UnstyledButton className="ows-advice" onClick={() => update((c) => { c.windows.useful_hours = weekAdvice; })}>
                <IconArrowRight size={12} /> {t("weekFit", { best: weekAdvice })}
              </UnstyledButton>
            )}
          </Box>
          <Stack gap={6}>
            <Text size="sm" fw={500}><FieldLabel label={t("spinUp")} info={t("spinUpInfo")} /></Text>
            <Group gap="sm" align="center" wrap="nowrap">
              <SegmentedControl aria-label={t("spinUp")} data={[...presets.map((h) => ({ value: String(h), label: `${h} h` })), { value: "other", label: t("other") }]} value={presets.includes(draft.spin_up_hours) ? String(draft.spin_up_hours) : "other"} onChange={(value) => update((c) => { c.spin_up_hours = value === "other" ? (presets.includes(c.spin_up_hours) ? 18 : c.spin_up_hours) : Number(value); })} />
              {!presets.includes(draft.spin_up_hours) && <NumberField aria-label={t("spinUp")} unit="h" min={1} allowDecimal={false} w={110} value={draft.spin_up_hours} onValue={(h) => update((c) => { c.spin_up_hours = h; })} />}
            </Group>
          </Stack>
          {count !== undefined && count > 1 && (
            <Stack gap={6}>
              <Text size="sm" fw={500}>{t("chain")}</Text>
              <ToolBar label={t("chain")}>
                <ToolChoice label={t("chain")} value={draft.windows.restart ? "chained" : "independent"} onChange={(value) => update((c) => { c.windows.restart = value === "chained"; })}
                  options={[{ value: "independent", icon: IconUnlink, label: t("independent"), hint: t("independentHint") }, { value: "chained", icon: IconLink, label: t("chained"), hint: t("chainedHint") }]} />
              </ToolBar>
            </Stack>
          )}
          {count !== undefined && count > 1 && (
            <Select label={<FieldLabel label={t("storeBy")} info={t("storeByInfo")} />} w={210} allowDeselect={false} value={draft.windows.grouping} onChange={(value) => value && update((c) => { c.windows.grouping = value as Grouping; })} data={(["month", "quarter", "week", "window"] as const).map((g) => ({ value: g, label: t(g) }))} />
          )}
        </Group>
      </Stack>
    </Fold>
  );
}

export default function DataPage() {
  const t = useT(messages);
  const ts = useT(sectionMessages);
  const f = useFormat();
  const { draft, update, issues } = useLoadedDraft();
  const settings = useSettings();

  const hours = (parseUtc(draft.period.end).getTime() - parseUtc(draft.period.start).getTime()) / 3.6e6;
  const boundaryHours = draft.period.interval_seconds / 3600;
  const relevant = issues.filter((i) => !i.field && INPUT_WORDS.some((w) => i.message.includes(w)));
  const periodIssue = useFieldIssue("period");
  const sourceIssue = useFieldIssue("input_source");

  return (
    <Page title={ts("project.data")} help="input-data">
      <Fold title={t("period")} aside={Number.isFinite(hours) && hours > 0 ? `${f.number(hours, 0)} h · UTC` : "UTC"} help="period">
        <Stack gap="xl">
          <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="xl">
            <TextInput
              type="datetime-local"
              label={t("start")}
              value={toInput(draft.period.start)}
              onChange={(e) => {
                const value = fromInput(e.currentTarget.value);
                update((c) => {
                  c.period.start = value;
                });
              }}
            />
            <TextInput
              type="datetime-local"
              label={t("end")}
              error={periodIssue?.text}
              value={toInput(draft.period.end)}
              onChange={(e) => {
                const value = fromInput(e.currentTarget.value);
                update((c) => {
                  c.period.end = value;
                });
              }}
            />
            <NumberField
              label={t("interval")}
              info={t("intervalInfo")}
              unit="h"
              min={1}
              value={boundaryHours}
              onValue={(v) => update((c) => { c.period.interval_seconds = Math.round(v * 3600); })}
            />
          </SimpleGrid>
        </Stack>
      </Fold>

      <WindowsFold />

      <Fold title={t("source")} aside={`${t(draft.input_source)} · SST`}>
        <Stack gap="lg">
          <SegmentedControl
            value={draft.input_source}
            onChange={(value) =>
              update((c) => {
                c.input_source = value as InputSource;
                if (value === "grib" && !c.grib) c.grib = emptyGrib("Vtable.ECMWF");
              })
            }
            data={[
              { value: "gfs", label: t("gfs") },
              { value: "era5", label: t("era5") },
              { value: "grib", label: t("grib") },
            ]}
            fullWidth
            maw={560}
          />
          {sourceIssue && <Text size="xs" c={sourceIssue.severity === "error" ? "red" : "orange"} mt={-8}>{sourceIssue.text}</Text>}
          {draft.input_source === "era5" && (
            <Stack gap="xs">
              {settings.data && (
                <Group gap={6}>
                  <IconKey size={16} color={settings.data.cds_key_configured ? "var(--mantine-color-teal-6)" : "var(--mantine-color-orange-6)"} />
                  <Text size="sm">{settings.data.cds_key_configured ? t("cdsOk") : t("cdsMissing")}</Text>
                  {!settings.data.cds_key_configured && (
                    <Anchor href={href("settings")} size="sm">
                      {t("settings")}
                    </Anchor>
                  )}
                </Group>
              )}
            </Stack>
          )}
          {draft.input_source === "grib" && draft.grib && (
            <Stack>
              <OwnFiles
                value={draft.grib}
                defaultVtable="Vtable.ECMWF"
                onChange={(value) =>
                  update((c) => {
                    c.grib = value;
                  })
                }
              />
              <Examination
                role="atmosphere"
                onUseVtable={(name) =>
                  update((c) => {
                    if (c.grib) c.grib.vtable = name;
                  })
                }
              />
            </Stack>
          )}
          <Text fw={600} mt="md">{t("sst")}</Text>
          <SegmentedControl
            value={draft.sea_surface.source}
            onChange={(value) =>
              update((c) => {
                c.sea_surface.source = value as "input" | "grib";
                if (value === "grib" && !c.sea_surface.grib) c.sea_surface.grib = emptyGrib("Vtable.SST");
              })
            }
            data={[
              { value: "input", label: t("fromInput") },
              { value: "grib", label: t("separate") },
            ]}
            maw={480}
          />
          {draft.sea_surface.source === "grib" && draft.sea_surface.grib && (
            <Box py="md" style={{ borderTop: "1px solid var(--ows-border)" }}>
              <Stack>
                <OwnFiles
                  value={draft.sea_surface.grib}
                  defaultVtable="Vtable.SST"
                  onChange={(value) =>
                    update((c) => {
                      c.sea_surface.grib = value;
                    })
                  }
                />
                <Examination
                  role="sst"
                  onUseVtable={(name) =>
                    update((c) => {
                      if (c.sea_surface.grib) c.sea_surface.grib.vtable = name;
                    })
                  }
                />
              </Stack>
            </Box>
          )}
          <Group align="flex-end" gap="lg">
            <Switch
              label={<FieldLabel label={t("update")} info={t("updateInfo")} />}
              checked={draft.sea_surface.update}
              onChange={(e) => {
                const on = e.currentTarget.checked;
                update((c) => {
                  c.sea_surface.update = on;
                });
              }}
            />
            {draft.sea_surface.update && (
              <NumberField
                label={t("updateEvery")}
                info={t("updateEveryInfo")}
                unit="min"
                placeholder={String(draft.period.interval_seconds / 60)}
                min={1}
                w={200}
                field="sea_surface.update_interval_minutes"
                value={draft.sea_surface.update_interval_minutes}
                onValue={(v) => update((c) => { c.sea_surface.update_interval_minutes = v; })}
                onClear={() => update((c) => { c.sea_surface.update_interval_minutes = null; })}
              />
            )}
          </Group>
        </Stack>
      </Fold>

      <Fold title={t("land")} aside={draft.land ? draft.land.prefix : undefined}>
        <Stack>
          <SegmentedControl
            value={draft.land ? "own" : "none"}
            onChange={(value) => update((c) => { c.land = value === "own" ? { ...emptyGrib("Vtable.ECMWF"), prefix: "ERA5LAND" } : null; })}
            data={[{ value: "none", label: t("landNone") }, { value: "own", label: t("landOwn") }]}
            maw={480}
          />
          {draft.land && (
            <Stack>
              <TextInput label={<FieldLabel label={t("landPrefix")} info={t("landPrefixInfo")} />} value={draft.land.prefix} maw={240} onChange={(e) => { const prefix = e.currentTarget.value.replace(/[^A-Za-z0-9_]/g, "").slice(0, 16); update((c) => { if (c.land) c.land.prefix = prefix; }); }} />
              <OwnFiles value={draft.land} defaultVtable="Vtable.ECMWF" onChange={(value) => update((c) => { if (c.land) c.land = { ...value, prefix: c.land.prefix }; })} />
            </Stack>
          )}
        </Stack>
      </Fold>

      {relevant.length > 0 && <Fold title={t("issues")} aside={String(relevant.length)}>
        <Alert
          color={relevant.some((i) => i.severity === "error") ? "red" : "orange"}
          variant="light"
          icon={<IconInfoCircle size={18} />}
          title={t("issues")}
        >
          <List spacing={4} size="sm">
            {relevant.map((issue, i) => (
              <List.Item
                key={i}
                icon={
                  issue.severity === "error" ? (
                    <IconCircleX size={16} color="var(--mantine-color-red-6)" />
                  ) : issue.severity === "warning" ? (
                    <IconAlertTriangle size={16} color="var(--mantine-color-orange-6)" />
                  ) : (
                    <IconInfoCircle size={16} color="var(--mantine-color-blue-6)" />
                  )
                }
              >
                {issue.message}
              </List.Item>
            ))}
          </List>
        </Alert>
      </Fold>}
    </Page>
  );
}
