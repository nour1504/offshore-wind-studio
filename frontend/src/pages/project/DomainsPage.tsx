import { Button, Group, List, Select, SimpleGrid, Text } from "@mantine/core";
import { IconAlertTriangle, IconCircleX, IconCurrentLocation, IconWorld } from "@tabler/icons-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useGeometry, useNamelistSchema } from "../../api/cases";
import type { Case, Issue, MapProj } from "../../api/types";
import { useLoadedDraft } from "../../app/CaseDraft";
import { sectionMessages } from "../../app/sections";
import { useT } from "../../i18n";
import { FieldLabel, NumberField } from "../../ui/Inputs";
import { Page } from "../../ui/Page";
import { MapChoice } from "../../ui/map/MapChoice";
import { ProjectMap } from "../../ui/map/ProjectMap";
import { ErrorState } from "../../ui/States";
import { Fold } from "../../ui/Fold";
import { prefersReducedMotion } from "../../motion";
import { DomainCard } from "./domains/DomainCard";
import { followingTurbines } from "./domains/edit";
import {
  centreInParent,
  centreOuter,
  descendants,
  domainName,
  editGrid,
  gridProblems,
  NEST_MARGIN,
  newNest,
  PLACEABLE,
  type Placement,
  placeCentre,
  suggestedProjection,
} from "./domains/grid";
import { domainMessages } from "./domains/messages";
import { isTimeStepIssue, TimeStep } from "./domains/TimeStep";
import { LevelsStack } from "./domains/LevelsStack";
import { VerticalLevels } from "./domains/VerticalLevels";
import { LevelsScene } from "./domains/VerticalScene";

const PROJECTIONS: MapProj[] = ["lambert", "mercator", "polar", "lat-lon"];
const SERVER_WORDS = ["domain", "grid", "Domain", "nest"];
// Server checks listed at the bottom: the time step has its own block, and the grid spacing in
// rotor diameters belongs with the wind farms (this page comes before the turbine models)
const listedHere = (issue: Issue) =>
  SERVER_WORDS.some((w) => issue.message.includes(w)) && !isTimeStepIssue(issue) && !issue.message.includes("rotor");

export default function DomainsPage() {
  const t = useT(domainMessages);
  const ts = useT(sectionMessages);
  const { draft, update: updateDraft, issues } = useLoadedDraft();
  // Every change made here keeps the wind farm scheme over the turbines
  const update = useCallback((change: (c: Case) => void) => updateDraft(followingTurbines(change)), [updateDraft]);
  const geometry = useGeometry(draft);
  const schema = useNamelistSchema();
  const [target, setTarget] = useState(0);
  const [picking, setPicking] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [mapOpen, setMapOpen] = useState(false);
  const mapSection = useRef<HTMLDivElement>(null);
  const revealMap = () => {
    setMapOpen(true);
    requestAnimationFrame(() => mapSection.current?.scrollIntoView({ block: "start", behavior: prefersReducedMotion() ? "auto" : "smooth" }));
  };
  // What the camera frames (only the view: nothing moves)
  const [view, setView] = useState({ target: "domain:1", key: 0 });
  const stopPlacing = () => { setPicking(false); setNotice(null); };
  const startPlacing = (index: number) => { setTarget(index); setPicking(true); setNotice(null); };
  useEffect(() => { const stop = (event: KeyboardEvent) => { if (event.key === "Escape") { setPicking(false); setNotice(null); } }; window.addEventListener("keydown", stop); return () => window.removeEventListener("keydown", stop); }, []);

  const grid = draft.grid;
  const count = grid.domains.length;
  const place = Math.min(target, count - 1);
  const drawable = PLACEABLE.includes(grid.projection.map_proj);
  const farmDomains = draft.farm_scheme?.domains ?? [];
  const problems = useMemo(() => (count ? gridProblems(grid, farmDomains) : []), [grid, farmDomains, count]);
  const serverIssues = issues.filter(listedHere);

  const onPick = (lat: number, lon: number) => {
    const next: Case = structuredClone(draft);
    let placed: Placement | null = null;
    if (place === 0) {
      centreOuter(next.grid, lat, lon);
    } else {
      // The nest moves with the nests inside it; the others stay over the same places
      editGrid(
        next.grid,
        (g) => {
          placed = placeCentre(g, place, lat, lon, NEST_MARGIN);
          if (placed && !placed.inside) centreInParent(g, place);
        },
        [place, ...descendants(grid, place)],
      );
    }
    update((c) => {
      c.grid = next.grid;
    });
    const result = placed as Placement | null;
    const name = domainName(place);
    const parent = place > 0 ? domainName(grid.domains[place].parent_id - 1) : "";
    setNotice(result && !result.inside ? t("outside", { name, parent }) : result?.clamped ? t("clamped", { name, parent }) : null);
  };

  // A new project has no domain yet: one click on the map places the usual pair, an outer
  // domain and a finer one around the study area, which the page then lets you adjust
  if (count === 0) {
    const start = (lat: number, lon: number) => {
      update((c) => {
        c.grid.domains = [{ e_we: 100, e_sn: 100, parent_id: 1, parent_grid_ratio: 1, i_parent_start: 1, j_parent_start: 1, geog_data_res: "default" }];
        c.grid.domains.push(newNest(c.grid, 0, 3));
        centreOuter(c.grid, lat, lon);
      });
      setMapOpen(true);
    };
    return (
      <Page title={ts("project.domains")} help="domains" fluid>
        <Fold title={<FieldLabel label={t("firstTitle")} info={t("firstText")} />} lazy>
          <ProjectMap geometry={geometry.data} farmOrder={[]} picking onPick={start} height="min(68vh, 640px)" ariaLabel={t("map")} />
        </Fold>
      </Page>
    );
  }

  return (
    <Page title={ts("project.domains")} help="domains" fluid>
      <div ref={mapSection}>
        <Fold title={t("map")} open={mapOpen} onOpenChange={(open) => { setMapOpen(open); if (!open) stopPlacing(); }} lazy>
          {!drawable && <Text size="sm" c="dimmed" mb="sm">{t("notDrawable")}</Text>}
          {geometry.error && <ErrorState error={geometry.error} onRetry={() => void geometry.refetch()} />}
          <div className="ows-map-frame">
            {picking && (
              <div className="ows-map-banner" role="status" data-tone={notice ? "warning" : undefined}>
                <Text size="sm" fw={600}>{notice ?? t("placing", { name: domainName(place) })}</Text>
                <Button size="compact-sm" onClick={stopPlacing}>{t("done")}</Button>
              </div>
            )}
            <ProjectMap
              geometry={geometry.data}
              farmOrder={draft.farms.map((farm) => farm.id)}
              showProbes={false}
              picking={picking}
              onPick={(lat, lon) => onPick(lat, lon)}
              frame={view}
              height={520}
              ariaLabel={t("map")}
              lead={<>
                <MapChoice
                  label={t("viewOn")}
                  value={view.target}
                  onChange={(target) => setView((current) => ({ target, key: current.key + 1 }))}
                  options={[
                    ...grid.domains.map((_, i) => ({ value: `domain:${i + 1}`, label: domainName(i) })),
                    ...(draft.farms.some((farm) => farm.turbines.length) ? [{ value: "all", label: t("viewFarms") }] : []),
                  ]}
                />
                {drawable && (
                  <MapChoice
                    icon={IconCurrentLocation}
                    label={t("place")}
                    value={picking ? String(place) : ""}
                    onChange={(value) => (picking && Number(value) === place ? stopPlacing() : startPlacing(Number(value)))}
                    options={grid.domains.map((_, i) => ({ value: String(i), label: domainName(i) }))}
                  />
                )}
              </>}
            />
          </div>
        </Fold>
      </div>

      <Fold title={t("domains")} aside={String(count)}>
        {schema.error && <ErrorState error={schema.error} onRetry={() => void schema.refetch()} />}
        {grid.domains.map((_, index) => (
          <DomainCard
            key={index}
            c={draft}
            index={index}
            update={update}
            problems={problems.filter((p) => p.domain === index)}
            schema={schema.data}
            onPlace={drawable ? () => { startPlacing(index); revealMap(); } : undefined}
            onAdded={(added) => {
              if (!drawable) return;
              startPlacing(added);
              revealMap();
            }}
          />
        ))}
      </Fold>

      <TimeStep c={draft} update={update} issues={issues} />

        <Fold title={t("projection")} value={t(`projShort.${grid.projection.map_proj}`)} help="projection">
          {/* Four columns from 1408 px only: narrower, the longest projection name would not fit */}
          <SimpleGrid cols={{ base: 1, xs: 2, xl: 4 }} spacing="md" verticalSpacing="lg">
            <Select
              label={<FieldLabel label={t("mapProj")} info={t("mapProjInfo")} />}
              data={PROJECTIONS.map((p) => ({
                value: p,
                label: t(p === "lat-lon" ? "latlon" : p),
              }))}
              value={grid.projection.map_proj}
              allowDeselect={false}
              onChange={(v) =>
                v &&
                update((c) => {
                  c.grid.projection.map_proj = v as MapProj;
                  Object.assign(c.grid.projection, suggestedProjection(c.grid));
                })
              }
            />
            {grid.projection.map_proj !== "lat-lon" && (
              <NumberField
                label={t("truelat1")}
                info={t("truelatInfo")}
                unit="°"
                min={-90}
                max={90}
                decimalScale={2}
                commitOnBlur
                value={grid.projection.truelat1}
                onValue={(v) => update((c) => editGrid(c.grid, (g) => { g.projection.truelat1 = v; }))}
                onClear={() => update((c) => editGrid(c.grid, (g) => { g.projection.truelat1 = null; }))}
              />
            )}
            {grid.projection.map_proj === "lambert" && (
              <NumberField
                label={t("truelat2")}
                info={t("truelatInfo")}
                unit="°"
                min={-90}
                max={90}
                decimalScale={2}
                commitOnBlur
                value={grid.projection.truelat2}
                onValue={(v) => update((c) => editGrid(c.grid, (g) => { g.projection.truelat2 = v; }))}
                onClear={() => update((c) => editGrid(c.grid, (g) => { g.projection.truelat2 = null; }))}
              />
            )}
            {(grid.projection.map_proj === "lambert" || grid.projection.map_proj === "polar") && (
              <NumberField
                label={t("standLon")}
                info={t("standLonInfo")}
                unit="°"
                min={-180}
                max={180}
                decimalScale={2}
                commitOnBlur
                value={grid.projection.stand_lon}
                onValue={(v) => update((c) => editGrid(c.grid, (g) => { g.projection.stand_lon = v; }))}
                onClear={() => update((c) => editGrid(c.grid, (g) => { g.projection.stand_lon = null; }))}
              />
            )}
          </SimpleGrid>
          <Group>
            <Button
              size="xs"
              variant="default"
              leftSection={<IconWorld size={16} />}
              title={t("suggestInfo")}
              onClick={() => update((c) => editGrid(c.grid, (g) => Object.assign(g.projection, suggestedProjection(g))))}
            >
              {t("suggest")}
            </Button>
          </Group>
        </Fold>

        <VerticalLevels draft={draft} update={update} />
        <LevelsStack draft={draft} />
        <LevelsScene draft={draft} />

      {(problems.length > 0 || serverIssues.length > 0) && <Fold title={t("problems")} value={problems.length + serverIssues.length}>
          <List spacing={6} size="sm">
            {problems.map((p, i) => (
              <List.Item
                key={`p${i}`}
                icon={
                  p.severity === "error" ? (
                    <IconCircleX size={16} color="var(--mantine-color-red-6)" />
                  ) : (
                    <IconAlertTriangle size={16} color="var(--mantine-color-orange-6)" />
                  )
                }
              >
                {t(`problem.${p.key}`, {
                  ...p.vars,
                  axis: p.vars.axis === "we" || p.vars.axis === "sn" ? t(`axis.${p.vars.axis}`) : (p.vars.axis ?? ""),
                })}
              </List.Item>
            ))}
            {serverIssues.map((issue, i) => (
              <List.Item
                key={`s${i}`}
                icon={
                  issue.severity === "error" ? (
                    <IconCircleX size={16} color="var(--mantine-color-red-6)" />
                  ) : (
                    <IconAlertTriangle size={16} color="var(--mantine-color-orange-6)" />
                  )
                }
              >
                {issue.message}
              </List.Item>
            ))}
          </List>
      </Fold>}
    </Page>
  );
}
