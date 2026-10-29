import { Alert, Button, Group, SimpleGrid, Stack, Text, TextInput } from "@mantine/core";
import { IconArrowRight, IconCheck, IconPropeller, IconX } from "@tabler/icons-react";
import { useState } from "react";
import { useBuiltInTurbine, useTurbineCatalog } from "../../api/turbines";
import type { TurbineType } from "../../api/types";
import { useLoadedDraft } from "../../app/CaseDraft";
import { sectionMessages } from "../../app/sections";
import { useFormat, useT } from "../../i18n";
import { Confirm, NumberField } from "../../ui/Inputs";
import { href } from "../../router";
import { Page, Section } from "../../ui/Page";
import { EmptyState, LoadingState } from "../../ui/States";
import { Stat, StatGrid } from "../../ui/Stat";
import { CatalogPicker } from "./turbines/CatalogPicker";
import { TurbineCurve } from "./turbines/TurbineCurve";
import { BETZ_LIMIT, blankTurbine, farmGrid, metrics, nextTypeNumber, typeUsage } from "./turbines/curve";
import { messages } from "./turbines/messages";

export default function TurbinesPage() {
  const t = useT(messages); const ts = useT(sectionMessages); const f = useFormat();
  const { caseId, draft, update } = useLoadedDraft();
  const catalog = useTurbineCatalog(); const builtIn = useBuiltInTurbine();
  const [number, setNumber] = useState<string | null>(null);
  const [catalogOpen, setCatalogOpen] = useState(false);
  const stored = number === null ? undefined : draft.turbine_types[number];
  // Model 1 without its own definition is WRF's built-in turbine: shown like any model, and
  // copied into the project on its first change
  const builtInShown = Number(number) === 1 && !stored ? builtIn.data?.turbine : undefined;
  const model = stored ?? builtInShown;
  const usage = typeUsage(draft); const used = usage.get(Number(number)) ?? [];
  const count = used.reduce((sum, row) => sum + row.count, 0);
  // Without its definition, model 1 in use falls back to WRF's built-in table
  const fallsBack = Number(number) === 1 && count > 0;
  const edit = (change: (value: TurbineType) => void) => update((c) => {
    if (number === null) return;
    if (!c.turbine_types[number] && builtInShown) c.turbine_types[number] = structuredClone(builtInShown);
    const value = c.turbine_types[number];
    if (value) change(value);
  });
  const add = (value: TurbineType, explicit?: number) => {
    const n = explicit ?? nextTypeNumber(draft); update((c) => { c.turbine_types[String(n)] = structuredClone(value); }); setNumber(String(n)); setCatalogOpen(false);
  };
  const m = model ? metrics(model) : null;
  const grid = farmGrid(draft);
  const keys = [...new Set([...Object.keys(draft.turbine_types).map(Number), ...usage.keys()])].sort((a, b) => a - b);
  return <Page title={ts("project.turbines")} description={t("description")} help="turbines" fluid actions={<><Button variant="light" onClick={() => setCatalogOpen(true)}>{t("addCatalog")}</Button><Button onClick={() => { const n = nextTypeNumber(draft); add(blankTurbine(t("blankName", { n })), n); }}>{t("addBlank")}</Button></>}>
    <Section title={t("list.title")}>
      {!keys.length ? <EmptyState icon={<IconPropeller size={26} stroke={1.5} />} title={t("list.emptyTitle")}>{t("list.emptyText")}</EmptyState> : <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>{keys.map((key) => {
        const value = draft.turbine_types[String(key)] ?? (key === 1 ? builtIn.data?.turbine : undefined);
        return <Button key={key} h="auto" p="md" variant={number === String(key) ? "light" : "default"} onClick={() => setNumber(number === String(key) ? null : String(key))} justify="flex-start"><Stack gap={3} align="flex-start"><Text fw={600}>{t("typeN", { n: key })} · {value?.name || (key === 1 ? t("builtIn.fallbackName") : t("list.notDefined"))}</Text><Text size="xs">{value ? `${f.number(value.rated_power_mw, 2)} MW · ${f.number(value.rotor_diameter_m, 0)} m` : "—"}</Text><Text size="xs">{(usage.get(key) ?? []).map((row) => t("list.farmCount", { name: row.farm.name, n: row.count })).join(" · ") || t("list.unused")}</Text></Stack></Button>;
      })}</SimpleGrid>}
    </Section>
    {number === null ? null : !model ? Number(number) === 1 ? <LoadingState rows={4} /> : <Alert color="orange" title={t("missing.title", { n: Number(number) })}><Stack><Text size="sm">{t("missing.text", { n: Number(number), count })}</Text><Button onClick={() => add(blankTurbine(t("blankName", { n: Number(number) })), Number(number))}>{t("missing.blank")}</Button></Stack></Alert> : <>
      <Section title={model.name || t("unnamed")} description={t("editor.characteristicsHelp")} actions={<><Button size="xs" variant="default" leftSection={<IconX size={14} />} onClick={() => setNumber(null)}>{t("close")}</Button><Button size="xs" variant="light" onClick={() => add({ ...structuredClone(model), name: t("copyName", { name: model.name }) })}>{t("editor.duplicate")}</Button>{stored && <Confirm title={t(fallsBack ? "editor.restoreTitle" : "editor.deleteTitle", { n: Number(number), name: model.name })} text={t(fallsBack ? "editor.restoreText" : "editor.deleteText")} onConfirm={() => { update((c) => { delete c.turbine_types[number]; }); setNumber(null); }}>{(open) => <Button size="xs" color="red" variant="light" disabled={count > 0 && !fallsBack} onClick={open}>{t(fallsBack ? "editor.restore" : "editor.delete")}</Button>}</Confirm>}</>}>
        <Stack><TextInput label={t("editor.name")} value={model.name} onChange={(event) => { const value = event.currentTarget.value; edit((item) => { item.name = value; }); }} /><SimpleGrid cols={{ base: 1, sm: 2, xl: 4 }}>{(["rated_power_mw", "rotor_diameter_m", "hub_height_m", "standing_thrust_coefficient"] as const).map((key) => {
          const label = key === "rated_power_mw" ? "rated" : key === "rotor_diameter_m" ? "rotor" : key === "hub_height_m" ? "hub" : "standing";
          return <NumberField key={key} label={t(`editor.${label}`)} info={t(`editor.${label}Info`)} value={model[key]} unit={key === "rated_power_mw" ? "MW" : key === "standing_thrust_coefficient" ? undefined : "m"} min={key === "standing_thrust_coefficient" ? 0 : 0.001} onValue={(value) => edit((item) => { item[key] = value; })} />;
        })}</SimpleGrid></Stack>
      </Section>
      <Section title={t("use.title")}>{!draft.farms.length ? <Group justify="space-between" wrap="wrap"><Text size="sm">{t("use.ready")}</Text><Button component="a" href={href(`projects/${encodeURIComponent(caseId)}/farms`)} rightSection={<IconArrowRight size={16} />}>{t("use.goFarms")}</Button></Group> : <Stack gap="sm">{draft.farms.map((farm) => {
        const used = farm.turbines.filter((tb) => tb.type === Number(number)).length; const all = farm.turbines.length > 0 && used === farm.turbines.length;
        return <Group key={farm.id} justify="space-between" wrap="wrap"><Group gap={6}>{all && <IconCheck size={16} />}<Text size="sm">{all ? t("use.inUse", { n: used, farm: farm.name }) : t("use.partly", { farm: farm.name, used, total: farm.turbines.length })}</Text></Group>{!all && farm.turbines.length > 0 && <Button size="sm" leftSection={<IconCheck size={16} />} aria-label={t("use.label", { n: Number(number), farm: farm.name })} onClick={() => update((c) => { c.farms.find((item) => item.id === farm.id)?.turbines.forEach((tb) => { tb.type = Number(number); }); })}>{t("use.forFarm", { farm: farm.name })}</Button>}</Group>;
      })}</Stack>}</Section>
      {m && <StatGrid cols={4}><Stat label={t("metrics.specific")} value={m.specificPower === null ? "—" : f.number(m.specificPower, 0)} unit="W/m²" info={t("metrics.specificInfo")} /><Stat label={t("metrics.maxCp")} value={m.maxCp === null ? "—" : f.number(m.maxCp, 3)} tone={m.maxCp !== null && m.maxCp > BETZ_LIMIT ? "bad" : "default"} hint={t("metrics.maxCpHint", { ws: m.maxCpSpeed ?? "—", betz: f.number(BETZ_LIMIT, 3) })} info={t("metrics.maxCpInfo")} /><Stat label={t("metrics.rated")} value={m.rated ?? "—"} unit="m/s" hint={t("metrics.ratedHint", { cutIn: m.cutIn ?? "—", cutOut: m.cutOut ?? "—" })} info={t("metrics.ratedInfo")} /><Stat label={t("metrics.grid")} value={grid ? f.number(grid.dx / model.rotor_diameter_m, 1) : "—"} unit="D" tone={grid && grid.dx / model.rotor_diameter_m < 5 ? "bad" : "default"} hint={grid ? t("metrics.gridHint", { dx: f.number(grid.dx / 1000, 2), domain: grid.domain, min: 5 }) : t("metrics.gridNone")} info={t("metrics.gridInfo")} /></StatGrid>}
      <TurbineCurve key={number ?? ""} turbine={model} number={Number(number)} onChange={(patch) => edit((item) => Object.assign(item, patch))} />
    </>}
    <CatalogPicker opened={catalogOpen} onClose={() => setCatalogOpen(false)} catalog={catalog} onPick={(entry) => add(entry.turbine)} />
  </Page>;
}
