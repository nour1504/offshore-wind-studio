import { Alert, Button, Grid, List, Paper, Text } from "@mantine/core";
import { IconGrid4x4, IconPropeller, IconTransfer, IconTrash, IconWindmill, IconX } from "@tabler/icons-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { useGeometry } from "../../api/cases";
import { useWrfGenericTurbine } from "../../api/farms";
import type { Farm, FarmAppearance, Turbine } from "../../api/types";
import { useLoadedDraft } from "../../app/CaseDraft";
import { prefersReducedMotion } from "../../motion";
import { sectionMessages } from "../../app/sections";
import { useFormat, useT } from "../../i18n";
import { Confirm } from "../../ui/Inputs";
import { Page } from "../../ui/Page";
import { ErrorState } from "../../ui/States";
import { Window } from "../../ui/Window";
import { ToolBar, ToolButton, ToolGroup, ToolMenu, ToolText, ToolToggle } from "../../ui/ToolBar";
import { MapChoice } from "../../ui/map/MapChoice";
import { ProjectMap } from "../../ui/map/ProjectMap";
import { AddTurbines } from "./farms/AddTurbines";
import { FarmCreate } from "./farms/FarmAppearanceEditor";
import { CellsSummary, cellMessages, mixedCells, useFarmCells } from "./farms/FarmCells";
import { FarmPanel } from "./farms/FarmPanel";
import { farmMessages } from "./farms/messages";
import { farmIssues, forMap, idFromName, innermostCentre, localProblems, newScheme, newTurbine, nextPosition, turbineLabel, turbineTypes, usualType } from "./farms/model";
import { SchemeFold } from "./farms/SchemeFold";
import { TurbineList } from "./farms/TurbineList";

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
 * Wind farms: a large map framed on the turbines, the farms beside it behind tabs with three plain
 * ways to add turbines, then the list of turbines and the farm scheme, folded until needed.
 */
export default function FarmsPage() {
  const t = useT(farmMessages); const ts = useT(sectionMessages); const tc = useT(cellMessages); const f = useFormat();
  const { caseId, draft, update, issues } = useLoadedDraft();
  const generic = useWrfGenericTurbine();
  const types = useMemo(() => turbineTypes(draft, generic), [draft, generic]);
  const geometry = useGeometry(forMap(draft));
  const [farmId, setFarmId] = useState(draft.farms[0]?.id ?? "");
  // Selected turbines, in any farm: chosen on the map (click, Ctrl+click, lasso) or in the list
  const [picked, setPicked] = useState<{ farm: string; index: number }[]>([]);
  const mapFrame = useRef<HTMLDivElement>(null);
  const [picking, setPicking] = useState(false);
  const [importing, setImporting] = useState(false);
  const [creating, setCreating] = useState(false);
  const [markerMode, setMarkerMode] = useState<"auto" | "all">("auto");
  const farmCells = useFarmCells(draft);
  const [showCells, setShowCells] = useState(false);
  // What the map frames: every farm at first, then the farm chosen beside the map or in the list
  const [view, setView] = useState({ target: "all", key: 0 });
  const centre = (target: string) => setView((current) => ({ target, key: current.key + 1 }));
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
  const editFarm = (change: (item: Farm) => void) => update((c) => { const item = c.farms.find((entry) => entry.id === actualId); if (item) change(item); });
  const addTurbine = (lat?: number, lon?: number) => {
    if (!farm) return;
    const pos = lat === undefined || lon === undefined ? nextPosition(farm, innermostCentre(draft, geometry.data), null) : { lat, lon };
    editFarm((item) => item.turbines.push(newTurbine(pos.lat, pos.lon, usualType(farm, types))));
  };
  const addFarm = (name: string, appearance: FarmAppearance) => {
    const id = idFromName(name, draft.farms.map((item) => item.id));
    update((c) => { c.farms.push({ id, name, appearance, enabled: true, properties: {}, turbines: [] }); if (!c.farm_scheme && c.grid.domains.length) c.farm_scheme = newScheme("fitch", c, null); });
    setFarmId(id);
    setCreating(false);
  };
  const choose = (id: string) => {
    setFarmId(id);
    if (draft.farms.find((item) => item.id === id)?.turbines.length) centre(`farm:${id}`);
  };
  const typeOptions = [...types.values()].map((type) => ({ value: String(type.number), label: type.known ? `${type.number} · ${type.name}` : t("turbines.typeUndefined", { n: type.number }) }));
  const checks = farmIssues(issues);
  const problems: ReturnType<typeof localProblems> = localProblems(draft).filter((problem) => problem.kind !== "emptyFarm");
  const missing = !draft.grid.domains.length ? "domains" : !Object.keys(draft.turbine_types).length && !draft.farms.some((item) => item.turbines.length) ? "turbines" : null;
  const replaceTurbines = (turbines: Turbine[], replace: boolean) => { editFarm((item) => { item.turbines = replace ? turbines : [...item.turbines, ...turbines]; }); setSelected([]); setImporting(false); };
  const locate = (index: number) => {
    const tb = farm?.turbines[index];
    if (!tb) return;
    setPicked([{ farm: actualId, index }]);
    centre(`point:${tb.lat},${tb.lon}`);
    // The list sits under the map: the map comes back into view
    mapFrame.current?.scrollIntoView({ block: "nearest", behavior: prefersReducedMotion() ? "auto" : "smooth" });
  };

  return <Page title={ts("project.farms")} help="farms" fluid className="ows-farms">
    {(problems.length > 0 || checks.some((item) => item.severity === "error")) && <Alert color="orange" title={t("checks.title")}><List size="sm">{problems.map((problem, index) => <List.Item key={index}>{problem.kind === "emptyFarm" ? t("checks.emptyFarm", { name: problem.farm.name }) : problem.kind === "badId" ? t("checks.badId", { name: problem.farm.name, id: problem.farm.id }) : problem.kind === "duplicateId" ? t("checks.duplicateId", { id: problem.id }) : problem.kind === "noName" ? t("checks.noName", { id: problem.farm.id }) : t("checks.noDomain")}</List.Item>)}{checks.map((issue, index) => <List.Item key={`server-${index}`}>{issue.message}</List.Item>)}</List></Alert>}
    <Grid gap="xl" align="flex-start" className="ows-farms-workspace">
      <Grid.Col span={{ base: 12, lg: 7 }} className="ows-farms-map-column">
        <Paper ref={mapFrame} withBorder p={0} className="ows-farms-map-frame">
          {geometry.error && <ErrorState error={geometry.error} onRetry={() => void geometry.refetch()} />}
          {picking && farm && <div className="ows-map-banner" role="status"><Text size="sm" fw={600}>{t("page.placing", { name: farm.name })}</Text><Button size="compact-sm" onClick={() => setPicking(false)}>{t("page.done")}</Button></div>}
          <ProjectMap geometry={geometry.data} farmOrder={draft.farms.map((item) => item.id)} showProbes={false} markerMode={markerMode} onFarmClick={(id) => { setFarmId(id); centre(`farm:${id}`); }} height="100%" fit="turbines" frame={view} picking={picking} onPick={addTurbine}
            selected={chosen.map((p, n) => ({ farm: p.farm, number: p.index + 1, lat: chosenTurbines[n].lat, lon: chosenTurbines[n].lon }))} onMapClick={() => setPicked([])}
            onTurbineClick={(props, adding) => {
              const item = draft.farms.find((entry) => entry.id === props.farm); if (!item) return;
              const index = props.number !== undefined ? props.number - 1 : item.turbines.findIndex((_, i) => turbineLabel(item, i) === props.label);
              if (index < 0 || index >= item.turbines.length) return;
              setFarmId(item.id);
              const one = { farm: item.id, index };
              const has = chosen.some((p) => p.farm === one.farm && p.index === one.index);
              setPicked(adding ? (has ? chosen.filter((p) => !(p.farm === one.farm && p.index === one.index)) : [...chosen, one]) : [one]);
            }}
            cells={showCells ? farmCells.data?.geojson : mixedCells(farmCells.data?.geojson)} litFarm={showCells ? farm?.id : null} cellSize={farmCells.data?.dx_m ?? undefined} ariaLabel={t("map.label")}
            onLasso={(outline, adding) => {
              // Every turbine inside the outline, whatever its farm
              const caught = draft.farms.flatMap((item) => item.turbines.flatMap((tb, index) => (inside(outline, tb.lon, tb.lat) ? [{ farm: item.id, index }] : [])));
              const fresh = caught.filter((p) => !chosen.some((q) => q.farm === p.farm && q.index === p.index));
              setPicked(adding ? [...chosen, ...fresh] : caught);
              if (caught.length && !adding) setFarmId(caught[0].farm);
            }}
            lead={draft.farms.some((item) => item.turbines.length > 0) && <MapChoice label={t("map.centre")} value={view.target} onChange={centre} options={[{ value: "all", label: t("map.allFarms") }, { value: "domain", label: t("map.domain"), disabled: !draft.grid.domains.length }]} />}
            extraTools={<>
              <ToolToggle icon={IconGrid4x4} label={tc("grid")} active={showCells} onChange={setShowCells} />
              <ToolToggle icon={IconWindmill} label={t("map.everyTurbine")} active={markerMode === "all"} onChange={(on) => setMarkerMode(on ? "all" : "auto")} />
            </>} />
          {chosen.length > 0 && <div className="ows-selection-bar">
            <ToolBar label={t("turbines.selected", { n: chosen.length })}>
              <ToolText className="ows-selection-count" label={chosenFarms.length > 1 ? `${t("turbines.selected", { n: chosen.length })} · ${t("turbines.selectedFarms", { n: chosenFarms.length })}` : t("turbines.selected", { n: chosen.length })}>
                {f.number(chosen.length, 0)}
              </ToolText>
              <ToolGroup>
                <ToolMenu icon={IconPropeller} label={t("turbines.setType")} value={chosenType} options={typeOptions} onChange={setChosenType} />
                {draft.farms.length > 1 && <ToolMenu icon={IconTransfer} label={t("turbines.moveTo")} options={draft.farms.filter((item) => !(chosenFarms.length === 1 && chosenFarms[0] === item.id)).map((item) => ({ value: item.id, label: item.name }))} onChange={moveChosen} />}
                <Confirm title={t("turbines.removeTitle", { n: chosen.length })} text={t("turbines.removeText", { name: chosenFarms.map((id) => draft.farms.find((item) => item.id === id)?.name ?? id).join(", ") })} onConfirm={removeChosen}>
                  {(open) => <ToolButton icon={IconTrash} label={t("turbines.removeSelected")} danger onClick={open} />}
                </Confirm>
              </ToolGroup>
              <ToolButton icon={IconX} label={t("turbines.deselect")} hint={t("turbines.deselectHint")} onClick={() => setPicked([])} />
            </ToolBar>
          </div>}
        </Paper>
      </Grid.Col>
      <Grid.Col span={{ base: 12, lg: 5 }} className="ows-farms-inspector">
        <FarmPanel caseId={caseId} draft={draft} farm={farm} types={types} missing={missing} picking={picking} onPicking={setPicking}
          onImport={() => setImporting(true)} onAddOne={() => addTurbine()} onChoose={choose} onCreate={() => setCreating(true)} update={update} />
      </Grid.Col>
    </Grid>
    {farm && <TurbineList farm={farm} types={types} typeOptions={typeOptions} selected={selected} onSelect={setSelected} onLocate={locate}
      onEdit={(index, change) => editFarm((item) => change(item.turbines[index]))} />}
    {farmCells.data && <CellsSummary cells={farmCells.data.cells} domain={farmCells.data.domain} />}
    <SchemeFold draft={draft} types={types} update={update} />
    <Window opened={importing && Boolean(farm)} onClose={() => setImporting(false)} title={<Text fw={600}>{farm ? t("page.importTitle", { name: farm.name }) : ""}</Text>} size="min(1240px, 94vw)" className="ows-add-turbines">
      {farm && <AddTurbines draft={draft} farm={farm} types={typeOptions} info={types} geometry={geometry.data} onApply={replaceTurbines} />}
    </Window>
    {creating && <FarmCreate opened index={draft.farms.length} defaultName={`${t("page.farm")} ${draft.farms.length + 1}`} onClose={() => setCreating(false)} onCreate={addFarm} />}
  </Page>;
}
