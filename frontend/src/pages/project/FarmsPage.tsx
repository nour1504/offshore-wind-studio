import { Accordion, ActionIcon, Alert, Badge, Box, Button, Checkbox, Collapse, Grid, Group, List, Modal, MultiSelect, Paper, Select, SimpleGrid, Stack, Switch, Table, Text, TextInput, Tooltip, UnstyledButton } from "@mantine/core";
import { IconArrowRight, IconClick, IconFileImport, IconFocusCentered, IconGrid4x4, IconPlus, IconPropeller, IconTransfer, IconTrash, IconWind, IconWindmill, IconX } from "@tabler/icons-react";
import { ToolBar, ToolButton, ToolGroup, ToolMenu, ToolToggle } from "../../ui/ToolBar";
import { useEffect, useMemo, useState } from "react";
import { useGeometry } from "../../api/cases";
import { useWrfGenericTurbine } from "../../api/farms";
import type { Farm, FarmAppearance, FarmScheme, Turbine } from "../../api/types";
import { useLoadedDraft } from "../../app/CaseDraft";
import { sectionMessages } from "../../app/sections";
import { useFormat, useT } from "../../i18n";
import { href } from "../../router";
import { Confirm, FieldLabel, NumberField } from "../../ui/Inputs";
import { Page, Section } from "../../ui/Page";
import { EmptyState, ErrorState } from "../../ui/States";
import { Term } from "../../ui/Term";
import { Pills } from "../../ui/Pills";
import { ProjectMap } from "../../ui/map/ProjectMap";
import { FarmSymbolMark } from "../../ui/map/FarmSymbolMark";
import { farmAppearance } from "../../ui/map/farms";
import { domainDx, domainName } from "./domains/grid";
import { CellsSummary, cellMessages, useFarmCells } from "./farms/FarmCells";
import { AddTurbines } from "./farms/AddTurbines";
import { FarmAppearanceEditor, FarmCreate } from "./farms/FarmAppearanceEditor";
import { farmMessages } from "./farms/messages";
import { FARM_ID_PATTERN, farmColor, farmIssues, forMap, idFromName, innermostCentre, localProblems, newScheme, newTurbine, nextPosition, summarize, turbineLabel, turbineTypes, usualType, valueForDomain } from "./farms/model";

/** Whether (lon, lat) lies in the outline (ray casting). */
function inside(outline: [number, number][], lon: number, lat: number): boolean {
  let within = false;
  for (let i = 0, j = outline.length - 1; i < outline.length; j = i++) {
    const [xi, yi] = outline[i];
    const [xj, yj] = outline[j];
    if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) within = !within;
  }
  return within;
}

/**
 * Wind farms: a large map framed on the turbines, the farms beside it, three plain ways to add
 * turbines, then the list of turbines and the technical choices, folded until needed.
 */
export default function FarmsPage() {
  const t = useT(farmMessages); const ts = useT(sectionMessages); const f = useFormat();
  const { caseId, draft, update, issues } = useLoadedDraft();
  const generic = useWrfGenericTurbine();
  const types = useMemo(() => turbineTypes(draft, generic), [draft, generic]);
  const geometry = useGeometry(forMap(draft));
  const [farmId, setFarmId] = useState(draft.farms[0]?.id ?? "");
  // Selected turbines, in any farm: chosen on the map (click, Ctrl+click, lasso) or in the list
  const [picked, setPicked] = useState<{ farm: string; index: number }[]>([]);
  const [picking, setPicking] = useState(false); const [importing, setImporting] = useState(false);
  const [creating, setCreating] = useState(false);
  const [styling, setStyling] = useState(false);
  const [markerMode, setMarkerMode] = useState<"auto" | "all">("auto");
  const tc = useT(cellMessages);
  const farmCells = useFarmCells(draft);
  const [showCells, setShowCells] = useState(false);
  // What the map frames: every farm at first, then the farm chosen above the map or in the list
  const [view, setView] = useState({ target: "all", key: 0 });
  const centre = (target: string) => setView((current) => ({ target, key: current.key + 1 }));
  const [property, setProperty] = useState(""); const [propertyValue, setPropertyValue] = useState("");
  const farm = draft.farms.find((item) => item.id === farmId) ?? draft.farms[0];
  const actualId = farm?.id ?? "";
  // Only turbines that still exist (after an undo or a removal)
  const chosen = picked.filter((p) => (draft.farms.find((item) => item.id === p.farm)?.turbines.length ?? 0) > p.index);
  const chosenFarms = [...new Set(chosen.map((p) => p.farm))];
  const selected = chosen.filter((p) => p.farm === actualId).map((p) => p.index);
  const setSelected = (indices: number[]) => setPicked((now) => [...now.filter((p) => p.farm !== actualId), ...indices.map((index) => ({ farm: actualId, index }))]);
  const chosenIn = (id: string) => new Set(chosen.filter((p) => p.farm === id).map((p) => p.index));
  const chosenTurbines = chosen.map((p) => draft.farms.find((item) => item.id === p.farm)!.turbines[p.index]);
  const chosenType = chosenTurbines.length && chosenTurbines.every((tb) => tb.type === chosenTurbines[0].type) ? String(chosenTurbines[0].type) : null;
  const setChosenType = (value: string | null) => { if (value) update((c) => { for (const p of chosen) c.farms.find((item) => item.id === p.farm)!.turbines[p.index].type = Number(value); }); };
  const moveChosen = (target: string | null) => {
    if (!target) return;
    update((c) => {
      const moving: Turbine[] = [];
      for (const item of c.farms) {
        if (item.id === target) continue;
        const out = chosenIn(item.id);
        moving.push(...item.turbines.filter((_, index) => out.has(index)));
        item.turbines = item.turbines.filter((_, index) => !out.has(index));
      }
      c.farms.find((item) => item.id === target)?.turbines.push(...moving);
    });
    setPicked([]);
    setFarmId(target);
  };
  const removeChosen = () => { update((c) => { for (const item of c.farms) { const out = chosenIn(item.id); item.turbines = item.turbines.filter((_, index) => !out.has(index)); } }); setPicked([]); };
  useEffect(() => { setPicking(false); setImporting(false); }, [actualId]);
  useEffect(() => { const stop = (event: KeyboardEvent) => { if (event.key === "Escape") { setPicking(false); setPicked([]); } }; window.addEventListener("keydown", stop); return () => window.removeEventListener("keydown", stop); }, []);
  const editFarm = (change: (item: Farm) => void) => update((c) => { const item = c.farms.find((item) => item.id === actualId); if (item) change(item); });
  const addTurbine = (lat?: number, lon?: number) => {
    if (!farm) return;
    const pos = lat === undefined || lon === undefined ? nextPosition(farm, innermostCentre(draft, geometry.data), null) : { lat, lon };
    editFarm((item) => item.turbines.push(newTurbine(pos.lat, pos.lon, usualType(farm, types))));
  };
  const addFarm = (name: string, appearance: FarmAppearance) => {
    const id = idFromName(name, draft.farms.map((item) => item.id));
    update((c) => { c.farms.push({ id, name, appearance, enabled: true, properties: {}, turbines: [] }); if (!c.farm_scheme && c.grid.domains.length) c.farm_scheme = newScheme("fitch", c, null); }); setFarmId(id); setCreating(false);
  };
  const scheme = draft.farm_scheme;
  // Grid spacing of the scheme's domains in diameters of the largest rotor simulated (README.windturbine)
  const rotor = Math.max(0, ...draft.farms.filter((item) => item.enabled).flatMap((item) => item.turbines.map((tb) => types.get(tb.type)?.rotorM ?? 0)));
  const spacing = domainDx(draft.grid);
  const cells = scheme && rotor > 0 ? scheme.domains.filter((n) => n >= 1 && n <= spacing.length).map((n) => `${domainName(n - 1)} ${f.number(spacing[n - 1] / rotor, 1)} D`) : [];
  const typeOptions = [...types.values()].map((type) => ({ value: String(type.number), label: type.known ? `${type.number} · ${type.name}` : t("turbines.typeUndefined", { n: type.number }) }));
  const checks = farmIssues(issues);
  const problems: ReturnType<typeof localProblems> = localProblems(draft).filter((problem) => problem.kind !== "emptyFarm");
  const missing = !draft.grid.domains.length ? "domains" : !Object.keys(draft.turbine_types).length && !draft.farms.some((farm) => farm.turbines.length) ? "turbines" : null;
  const setScheme = (change: (value: FarmScheme) => void) => update((c) => { if (c.farm_scheme) change(c.farm_scheme); });
  const replaceTurbines = (turbines: Turbine[], replace: boolean) => { editFarm((item) => { item.turbines = replace ? turbines : [...item.turbines, ...turbines]; }); setSelected([]); setImporting(false); };
  const ways = [
    { key: "click", icon: IconClick, active: picking, onClick: () => setPicking((value) => !value) },
    { key: "import", icon: IconFileImport, active: importing, onClick: () => setImporting(true) },
    { key: "one", icon: IconPlus, active: false, onClick: () => addTurbine() },
  ] as const;

  return <Page title={ts("project.farms")} description={t("page.intro")} help="farms" fluid className="ows-farms">
    {(problems.length > 0 || checks.some((item) => item.severity === "error")) && <Alert color="orange" title={t("checks.title")}><List size="sm">{problems.map((problem, index) => <List.Item key={index}>{problem.kind === "emptyFarm" ? t("checks.emptyFarm", { name: problem.farm.name }) : problem.kind === "badId" ? t("checks.badId", { name: problem.farm.name, id: problem.farm.id }) : problem.kind === "duplicateId" ? t("checks.duplicateId", { id: problem.id }) : problem.kind === "noName" ? t("checks.noName", { id: problem.farm.id }) : t("checks.noDomain")}</List.Item>)}{checks.map((issue, index) => <List.Item key={`server-${index}`}>{issue.message}</List.Item>)}</List></Alert>}
    <Grid gap="xl" align="flex-start" className="ows-farms-workspace">
      <Grid.Col span={{ base: 12, lg: 7 }} style={{ position: "sticky", top: 76 }} className="ows-farms-map-column">
        <Paper withBorder p={0} style={{ overflow: "hidden" }} className="ows-farms-map-frame">
          {draft.farms.some((item) => item.turbines.length > 0) && <Group gap={6} px="md" py="sm" wrap="wrap" className="ows-map-toolbar">
            <Group gap={6} mr={4} c="dimmed"><IconFocusCentered size={16} /><Text size="sm" fw={600}>{t("map.centre")}</Text></Group>
            <Pills label={t("map.centre")} value={view.target} onChange={(target) => { centre(target); if (target.startsWith("farm:")) setFarmId(target.slice(5)); }} options={[{ value: "all", label: t("map.allFarms") }, ...draft.farms.map((item, index) => ({ value: `farm:${item.id}`, label: item.name, marker: <FarmSymbolMark {...farmAppearance(item, index)} />, disabled: !item.turbines.length })), { value: "domain", label: t("map.domain"), disabled: !draft.grid.domains.length }]} />
          </Group>}
          {picking && farm && <Group justify="space-between" px="md" py="sm" bg="var(--mantine-primary-color-light)"><Text size="sm" fw={600}>{t("page.placing", { name: farm.name })}</Text><Button size="xs" onClick={() => setPicking(false)}>{t("page.done")}</Button></Group>}
          {geometry.error && <ErrorState error={geometry.error} onRetry={() => void geometry.refetch()} />}
          <ProjectMap geometry={geometry.data} farmOrder={draft.farms.map((item) => item.id)} showProbes={false} markerMode={markerMode} onFarmClick={(id) => { setFarmId(id); centre(`farm:${id}`); }} height="100%" fit="turbines" frame={view} picking={picking} onPick={addTurbine} selected={chosen.map((p, n) => ({ farm: p.farm, number: p.index + 1, lat: chosenTurbines[n].lat, lon: chosenTurbines[n].lon }))} onMapClick={() => setPicked([])} onTurbineClick={(props, adding) => {
            const item = draft.farms.find((item) => item.id === props.farm); if (!item) return;
            const index = props.number !== undefined ? props.number - 1 : item.turbines.findIndex((_, index) => turbineLabel(item, index) === props.label);
            if (index < 0 || index >= item.turbines.length) return;
            setFarmId(item.id);
            const one = { farm: item.id, index };
            const has = chosen.some((p) => p.farm === one.farm && p.index === one.index);
            setPicked(adding ? (has ? chosen.filter((p) => !(p.farm === one.farm && p.index === one.index)) : [...chosen, one]) : [one]);
          }} cells={showCells ? farmCells.data?.geojson : undefined} litFarm={showCells ? farm?.id : null} cellSize={farmCells.data?.dx_m ?? undefined} ariaLabel={t("map.label")} onLasso={(outline, adding) => {
            // Every turbine inside the outline, whatever its farm
            const caught = draft.farms.flatMap((item) => item.turbines.flatMap((tb, index) => (inside(outline, tb.lon, tb.lat) ? [{ farm: item.id, index }] : [])));
            const fresh = caught.filter((p) => !chosen.some((q) => q.farm === p.farm && q.index === p.index));
            setPicked(adding ? [...chosen, ...fresh] : caught);
            if (caught.length && !adding) setFarmId(caught[0].farm);
          }} extraTools={<>
              <ToolToggle icon={IconGrid4x4} label={tc("grid")} active={showCells} onChange={setShowCells} />
              <ToolToggle icon={IconWindmill} label={t("map.everyTurbine")} active={markerMode === "all"} onChange={(on) => setMarkerMode(on ? "all" : "auto")} />
            </>} />
          {chosen.length > 0 && <div className="ows-selection-bar">
            <ToolBar label={t("turbines.selected", { n: chosen.length })}>
              <Tooltip label={chosenFarms.length > 1 ? `${t("turbines.selected", { n: chosen.length })} · ${t("turbines.selectedFarms", { n: chosenFarms.length })}` : t("turbines.selected", { n: chosen.length })} withArrow openDelay={250}>
                <span className="ows-selection-count">{f.number(chosen.length, 0)}</span>
              </Tooltip>
              <ToolGroup>
                <ToolMenu icon={IconPropeller} label={t("turbines.setType")} value={chosenType} options={typeOptions} onChange={setChosenType} />
                {draft.farms.length > 1 && <ToolMenu icon={IconTransfer} label={t("turbines.moveTo")} options={draft.farms.filter((item) => !(chosenFarms.length === 1 && chosenFarms[0] === item.id)).map((item) => ({ value: item.id, label: item.name }))} onChange={moveChosen} />}
                <Confirm title={t("turbines.removeTitle", { n: chosen.length })} text={t("turbines.removeText", { name: chosenFarms.map((id) => draft.farms.find((item) => item.id === id)?.name ?? id).join(", ") })} onConfirm={removeChosen}>
                  {(open) => <ToolButton icon={IconTrash} label={t("turbines.removeSelected")} danger onClick={open} />}
                </Confirm>
              </ToolGroup>
              <ToolButton icon={IconX} label={t("turbines.deselect")} onClick={() => setPicked([])} />
            </ToolBar>
          </div>}
        </Paper>
      </Grid.Col>
      <Grid.Col span={{ base: 12, lg: 5 }} className="ows-farms-inspector">
        <Stack gap="lg">
          <Stack gap="sm" className="ows-stagger">
            <Group justify="space-between"><Text fw={600} size="lg">{t("page.farms")}</Text><Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={() => setCreating(true)}>{t("page.newFarm")}</Button></Group>
            {!draft.farms.length ? <EmptyState icon={<IconWindmill size={26} stroke={1.5} />} title={t("list.emptyTitle")}>{t("page.noFarm")}</EmptyState> : draft.farms.map((item, index) => {
              const info = summarize(item, types); const active = item.id === actualId;
              return <Paper key={item.id} className="ows-farm-item" data-selected={active || undefined} style={{ borderLeftColor: farmColor(index, item) }}>
                <Group justify="space-between" wrap="nowrap" gap="sm">
                  <UnstyledButton className="ows-farm-head" aria-expanded={active && styling} onClick={() => { if (active) setStyling((open) => !open); else { setFarmId(item.id); setStyling(true); if (item.turbines.length) centre(`farm:${item.id}`); } }}>
                    <Stack gap={2}><Group gap="xs" wrap="nowrap"><FarmSymbolMark {...farmAppearance(item, index)} /><Text fw={600} truncate>{item.name}</Text></Group><Text size="sm" c="dimmed">{t("list.turbines", { n: info.turbines })} · {f.number(info.installedMw, 1)} MW</Text></Stack>
                  </UnstyledButton>
                  <Switch aria-label={t("list.simulate", { name: item.name })} label={t("page.simulated")} checked={item.enabled} onChange={(event) => { const enabled = event.currentTarget.checked; update((c) => { c.farms[index].enabled = enabled; }); }} />
                </Group>
                <Collapse expanded={active && styling} transitionDuration={220}>
                  <Box pt="sm" mt="sm" style={{ borderTop: "1px solid var(--ows-border)" }}>
                    <FarmAppearanceEditor value={item.appearance} index={index} onChange={(appearance) => update((c) => { c.farms[index].appearance = appearance; })} />
                  </Box>
                </Collapse>
              </Paper>;
            })}
          </Stack>
          {farm && <Stack gap="sm" className="ows-farm-tools">
            <Text fw={600} size="lg">{t("page.add", { name: farm.name })}</Text>
            {missing ? <Paper withBorder p="lg"><Stack gap="sm" align="flex-start"><Text size="sm">{t(missing === "domains" ? "page.needDomains" : "page.needTurbines")}</Text><Button component="a" href={href(`projects/${encodeURIComponent(caseId)}/${missing}`)} rightSection={<IconArrowRight size={16} />}>{t(missing === "domains" ? "page.goDomains" : "page.goTurbines")}</Button></Stack></Paper> : <Button.Group className="ows-farm-ways">
              {ways.map((way) => <Button key={way.key} variant={way.active ? "light" : "default"} aria-pressed={way.active} leftSection={<way.icon size={18} />} onClick={way.onClick}>{t(`page.ways.${way.key}`)}</Button>)}
            </Button.Group>}
            <Accordion variant="contained" radius="lg">
              <Accordion.Item value="more"><Accordion.Control><Text size="sm" fw={600}>{t("page.more")}</Text></Accordion.Control><Accordion.Panel><Stack gap="sm">
                <TextInput label={t("dialog.name")} maxLength={80} value={farm.name} error={!farm.name.trim() ? t("dialog.nameRequired") : undefined} onChange={(event) => { const value = event.currentTarget.value; editFarm((item) => { item.name = value; }); }} />
                <TextInput label={<FieldLabel label={t("dialog.id")} info={t("dialog.idInfo")} />} value={farm.id} error={!FARM_ID_PATTERN.test(farm.id) ? t("dialog.idInvalid") : draft.farms.filter((item) => item.id === farm.id).length > 1 ? t("dialog.idTaken") : undefined} onChange={(event) => { const value = event.currentTarget.value; editFarm((item) => { item.id = value; }); setFarmId(value); }} />
                <Text size="sm" fw={600} mt="xs">{t("details.properties")}</Text>
                <Text size="xs" c="dimmed">{t("details.propertiesInfo")}</Text>
                {Object.entries(farm.properties).map(([key, value]) => <Group key={key} wrap="nowrap"><Text w={140} size="sm">{key}</Text><TextInput aria-label={t("details.value")} value={value} style={{ flex: 1 }} onChange={(event) => { const v = event.currentTarget.value; editFarm((item) => { item.properties[key] = v; }); }} /><ActionIcon color="red" variant="subtle" aria-label={t("details.removeProperty", { key })} onClick={() => editFarm((item) => { delete item.properties[key]; })}><IconTrash size={16} /></ActionIcon></Group>)}
                <Group align="flex-end"><TextInput label={t("details.key")} placeholder={t("details.keyExample")} value={property} onChange={(event) => setProperty(event.currentTarget.value)} style={{ flex: 1 }} /><TextInput label={t("details.value")} placeholder={t("details.valueExample")} value={propertyValue} onChange={(event) => setPropertyValue(event.currentTarget.value)} style={{ flex: 1 }} /><Button variant="default" disabled={!property.trim() || property.trim() in farm.properties} onClick={() => { editFarm((item) => { item.properties[property.trim()] = propertyValue; }); setProperty(""); setPropertyValue(""); }}>{t("details.addProperty")}</Button></Group>
                <Confirm title={t("list.delete")} text={t("list.deleteText", { n: farm.turbines.length })} onConfirm={() => update((c) => { c.farms = c.farms.filter((entry) => entry.id !== farm.id); })}>{(open) => <Group><Button size="xs" variant="subtle" color="red" leftSection={<IconTrash size={14} />} onClick={open}>{t("list.delete")}</Button></Group>}</Confirm>
              </Stack></Accordion.Panel></Accordion.Item>
            </Accordion>
          </Stack>}
        </Stack>
      </Grid.Col>
    </Grid>
    {farm && <Section title={t("page.list", { name: farm.name, n: farm.turbines.length })} className="ows-farm-table">
      {!farm.turbines.length ? <EmptyState icon={<IconClick size={26} stroke={1.5} />} title={t("turbines.emptyTitle")}>{t("page.emptyTurbines")}</EmptyState> : <Accordion variant="default"><Accordion.Item value="list"><Accordion.Control><Text size="sm" fw={600}>{t("page.showList", { n: farm.turbines.length })}</Text></Accordion.Control><Accordion.Panel>
        <Table.ScrollContainer minWidth={650}><Table aria-label={t("turbines.title", { name: farm.name })}><Table.Thead><Table.Tr><Table.Th><Checkbox aria-label={t("turbines.selectAll")} checked={selected.length === farm.turbines.length} indeterminate={selected.length > 0 && selected.length < farm.turbines.length} onChange={(event) => setSelected(event.currentTarget.checked ? farm.turbines.map((_, index) => index) : [])} /></Table.Th><Table.Th>{t("turbines.label")}</Table.Th><Table.Th>{t("turbines.lat")}</Table.Th><Table.Th>{t("turbines.lon")}</Table.Th><Table.Th>{t("turbines.type")}</Table.Th></Table.Tr></Table.Thead><Table.Tbody>{farm.turbines.map((tb, index) => {
          const label = turbineLabel(farm, index); const edit = (change: (item: Turbine) => void) => editFarm((item) => change(item.turbines[index])); return <Table.Tr key={index}><Table.Td><Checkbox aria-label={t("turbines.selectRow", { label })} checked={selected.includes(index)} onChange={(event) => setSelected(event.currentTarget.checked ? [...selected, index] : selected.filter((n) => n !== index))} /></Table.Td><Table.Td><TextInput aria-label={t("turbines.labelOf", { label })} size="xs" value={tb.id ?? ""} placeholder={label} maxLength={32} onChange={(event) => { const value = event.currentTarget.value; edit((item) => { item.id = value || null; }); }} /></Table.Td><Table.Td><NumberField aria-label={t("turbines.latOf", { label })} size="xs" min={-90} max={90} decimalScale={6} commitOnBlur value={tb.lat} onValue={(value) => edit((item) => { item.lat = value; })} /></Table.Td><Table.Td><NumberField aria-label={t("turbines.lonOf", { label })} size="xs" min={-180} max={180} decimalScale={6} commitOnBlur value={tb.lon} onValue={(value) => edit((item) => { item.lon = value; })} /></Table.Td><Table.Td><Select aria-label={t("turbines.typeOf", { label })} size="xs" data={typeOptions} value={String(tb.type)} allowDeselect={false} onChange={(value) => value && edit((item) => { item.type = Number(value); })} /></Table.Td></Table.Tr>;
        })}</Table.Tbody></Table></Table.ScrollContainer>
      </Accordion.Panel></Accordion.Item></Accordion>}
    </Section>}
    {farmCells.data && <CellsSummary cells={farmCells.data.cells} domain={farmCells.data.domain} />}
    <Accordion variant="contained" radius="lg"><Accordion.Item value="parameterization"><Accordion.Control icon={<IconWind size={18} />}>
      <Group justify="space-between" pr="md"><Text fw={600}>{t("page.scheme")}</Text><Badge size="lg">{scheme?.scheme === "fitch" ? "Fitch" : scheme?.scheme === "mav" ? "MAV" : t("scheme.none")}</Badge></Group>
    </Accordion.Control><Accordion.Panel>
      <Stack gap="md">
        <Select label={<>{t("scheme.choice")} (<Term id="fitch" />, <Term id="mav" />)</>} value={scheme?.scheme ?? "none"} allowDeselect={false} data={[{ value: "none", label: t("scheme.none") }, { value: "fitch", label: "Fitch" }, { value: "mav", label: "MAV" }]} onChange={(value) => update((c) => { c.farm_scheme = value === "none" ? null : newScheme(value as "fitch" | "mav", c, c.farm_scheme); })} />
        {!scheme && <Text size="sm" c="dimmed">{t("scheme.noneText")}</Text>}
        {scheme && <>
          <MultiSelect label={<FieldLabel label={t("scheme.domains")} info={t("scheme.domainsInfo")} />} value={scheme.domains.map(String)} data={draft.grid.domains.map((_, index) => ({ value: String(index + 1), label: `d${String(index + 1).padStart(2, "0")}` }))} onChange={(values) => setScheme((s) => { s.domains = values.map(Number); })} error={!scheme.domains.length ? t("scheme.noDomain") : undefined} />
          {cells.length > 0 && <Text size="sm" c="dimmed" className="ows-num">{t("scheme.cells", { list: cells.join(" · ") })}</Text>}
          {scheme.domains.some((domain) => Number(valueForDomain(draft.physics.bl_pbl_physics, domain)) !== 5) && <Alert color="orange">{t("scheme.pblMissing", { domains: scheme.domains.map((domain) => `d${String(domain).padStart(2, "0")}`).join(", "), value: String(draft.physics.bl_pbl_physics ?? t("scheme.pblUnset")) })}</Alert>}
          <Box><Text size="sm" fw={600} mb="xs">{t("page.schemeAdvanced")}</Text><SimpleGrid cols={{ base: 1, sm: 2 }}>
            <NumberField label={t("scheme.tke")} info={t("scheme.tkeInfo")} min={0} value={scheme.tke_factor} onValue={(value) => setScheme((s) => { s.tke_factor = value; })} />
            {scheme.scheme === "fitch" ? <Switch mt="xl" label={<FieldLabel label={t("scheme.induction")} info={t("scheme.inductionInfo")} />} checked={scheme.induction} onChange={(event) => { const value = event.currentTarget.checked; setScheme((s) => { s.induction = value; }); }} /> : <>
              <Select label={<FieldLabel label={t("scheme.wakeModel")} info={t("scheme.wakeModelInfo")} />} value={String(scheme.wake_model)} allowDeselect={false} data={([1, 2, 3, 4, 5] as const).map((value) => ({ value: String(value), label: `${value} · ${t(`scheme.wake.${value}`)}` }))} onChange={(value) => setScheme((s) => { s.wake_model = Number(value) as FarmScheme["wake_model"]; })} />
              <Select label={<FieldLabel label={t("scheme.overlap")} info={t("scheme.overlapInfo")} />} disabled={scheme.wake_model === 3} description={scheme.wake_model === 3 ? t("scheme.overlapGm") : undefined} value={String(scheme.overlap_method)} allowDeselect={false} data={([1, 2, 3, 4] as const).map((value) => ({ value: String(value), label: `${value} · ${t(`scheme.overlapMethod.${value}`)}` }))} onChange={(value) => setScheme((s) => { s.overlap_method = Number(value) as FarmScheme["overlap_method"]; })} />
            </>}
          </SimpleGrid></Box>
        </>}
      </Stack>
    </Accordion.Panel></Accordion.Item></Accordion>
    <Modal opened={importing && Boolean(farm)} onClose={() => setImporting(false)} title={<Text fw={600}>{farm ? t("page.importTitle", { name: farm.name }) : ""}</Text>} size="min(1180px, 94vw)">
      {farm && <AddTurbines draft={draft} farm={farm} types={typeOptions} info={types} geometry={geometry.data} onApply={replaceTurbines} />}
    </Modal>
    {creating && <FarmCreate opened index={draft.farms.length} defaultName={`${t("page.farm")} ${draft.farms.length + 1}`} onClose={() => setCreating(false)} onCreate={addFarm} />}
  </Page>;
}
