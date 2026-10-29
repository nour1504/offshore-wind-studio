import { Accordion, Alert, Button, Group, List, Select, SimpleGrid, Stack, Text } from "@mantine/core";
import { IconAlertTriangle, IconCircleX, IconCurrentLocation, IconFocusCentered, IconWorld } from "@tabler/icons-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { useGeometry, useNamelistSchema } from "../../api/cases";
import type { Case, Issue, MapProj } from "../../api/types";
import { useLoadedDraft } from "../../app/CaseDraft";
import { sectionMessages } from "../../app/sections";
import { useFormat, useT } from "../../i18n";
import { FieldLabel, NumberField } from "../../ui/Inputs";
import { Page, Section } from "../../ui/Page";
import { Pills } from "../../ui/Pills";
import { ProjectMap } from "../../ui/map/ProjectMap";
import { Stat, StatGrid } from "../../ui/Stat";
import { ErrorState } from "../../ui/States";
import { Fold } from "../../ui/Fold";
import { HelpLink } from "../../ui/Help";
import { prefersReducedMotion } from "../../motion";
import { DomainCard } from "./domains/DomainCard";
import {
  centreInParent,
  centreOuter,
  descendants,
  domainDx,
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
  const f = useFormat();
  const { draft, update, issues } = useLoadedDraft();
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
  useEffect(() => { const stop = (event: KeyboardEvent) => { if (event.key === "Escape") setPicking(false); }; window.addEventListener("keydown", stop); return () => window.removeEventListener("keydown", stop); }, []);

  const grid = draft.grid;
  const count = grid.domains.length;
  const place = Math.min(target, count - 1);
  const drawable = PLACEABLE.includes(grid.projection.map_proj);
  const spacing = domainDx(grid);
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

  const what = t("placeNest", { name: domainName(place) });
  const totalPoints = grid.domains.reduce((n, d) => n + d.e_we * d.e_sn, 0);
  const finest = Math.min(...spacing);

  return (
    <Page title={ts("project.domains")} help="domains" fluid>
      <Accordion ref={mapSection} value={mapOpen ? "map" : null} onChange={(value) => { setMapOpen(value === "map"); if (value !== "map") setPicking(false); }} variant="contained" radius="lg" className="ows-disclosure" styles={{ control: { paddingBlock: 14 }, content: { paddingTop: 4, paddingBottom: 22 } }}>
      <Accordion.Item value="map"><Accordion.Control><Text fw={600} size="17px">{t("map")}</Text></Accordion.Control><Accordion.Panel>
      {mapOpen && <Section
        actions={
          drawable && (
            <Group gap="xs" align="center">
              <Text size="sm" c="dimmed">{t("place")}</Text>
              <Select
                size="xs"
                aria-label={t("place")}
                data={grid.domains.map((_, i) => ({ value: String(i), label: t("placeNest", { name: domainName(i) }) }))}
                value={String(place)}
                onChange={(v) => setTarget(Number(v ?? 0))}
                allowDeselect={false}
                w={260}
              />
              <Button
                size="xs"
                variant={picking ? "filled" : "light"}
                leftSection={<IconCurrentLocation size={16} />}
                onClick={() => setPicking((p) => !p)}
              >
                {picking ? t("stopPlacing") : t("startPlacing")}
              </Button>
            </Group>
          )
        }
        flush
      >
        <Stack gap={0}>
          {!drawable && <Text size="sm" c="dimmed" px="md" py="sm">{t("notDrawable")}</Text>}
          <Group gap={6} px="md" py="sm" wrap="wrap" className="ows-map-toolbar">
            <Group gap={6} mr={4} c="dimmed"><IconFocusCentered size={16} /><Text size="sm" fw={600}>{t("viewOn")}</Text></Group>
            <Pills
              label={t("viewOn")}
              value={view.target}
              onChange={(target) => setView((current) => ({ target, key: current.key + 1 }))}
              options={[
                ...grid.domains.map((_, i) => ({ value: `domain:${i + 1}`, label: domainName(i) })),
                ...(draft.farms.some((farm) => farm.turbines.length) ? [{ value: "all", label: t("viewFarms") }] : []),
              ]}
            />
          </Group>
          {geometry.error && <ErrorState error={geometry.error} onRetry={() => void geometry.refetch()} />}
          {(picking || notice) && (
            <Text size="sm" px="lg" pb="xs" c={notice ? "orange" : "dimmed"}>
              {notice ?? t("placing", { what })}
            </Text>
          )}
          <ProjectMap
            geometry={geometry.data}
            farmOrder={draft.farms.map((farm) => farm.id)}
            showProbes={false}
            picking={picking}
            onPick={(lat, lon) => onPick(lat, lon)}
            frame={view}
            height={460}
            ariaLabel={t("map")}
          />
        </Stack>
      </Section>}
      </Accordion.Panel></Accordion.Item></Accordion>

      <Fold title={t("domains")} aside={String(count)}>
      <Stack gap="xl">
      <StatGrid cols={4}>
        <Stat label={t("domains")} value={count} hint={grid.domains.map((_, i) => domainName(i)).join(" · ")} />
        <Stat
          label={t("finest")}
          value={finest >= 1000 ? f.number(finest / 1000, finest % 1000 ? 2 : 0) : f.number(finest, 0)}
          unit={finest >= 1000 ? "km" : "m"}
          hint={spacing.includes(finest) ? t("finestOn", { name: domainName(spacing.indexOf(finest)) }) : undefined}
        />
        <Stat label={t("points")} value={f.compact(totalPoints)} hint={t("pointsValue", { n: f.number(totalPoints, 0) })} />
        <Stat
          label={t("levels")}
          value={grid.e_vert}
        />
      </StatGrid>

        {schema.error && <ErrorState error={schema.error} onRetry={() => void schema.refetch()} />}
        <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="xl">
          {grid.domains.map((_, index) => (
            <DomainCard
              key={index}
              c={draft}
              index={index}
              update={update}
              problems={problems.filter((p) => p.domain === index)}
              holdsFarms={farmDomains.includes(index + 1)}
              schema={schema.data}
              onPlace={drawable ? () => { setTarget(index); setPicking(true); revealMap(); } : undefined}
              onAdded={(added) => {
                setTarget(added);
                setPicking(drawable);
                if (drawable) revealMap();
              }}
            />
          ))}
        </SimpleGrid>
      </Stack>
      </Fold>

      <TimeStep c={draft} update={update} issues={issues} />

        <Fold title={t("projection")} aside={grid.projection.map_proj}>
          <Stack gap="xl">
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
            <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="sm">
              <NumberField
                label={t("refLat")}
                info={t("refLatInfo")}
                unit="°"
                min={-89.9}
                max={89.9}
                decimalScale={4}
                commitOnBlur
                value={grid.projection.ref_lat}
                onValue={(lat) => update((c) => centreOuter(c.grid, lat, c.grid.projection.ref_lon))}
              />
              <NumberField
                label={t("refLon")}
                info={t("refLonInfo")}
                unit="°"
                min={-180}
                max={180}
                decimalScale={4}
                commitOnBlur
                value={grid.projection.ref_lon}
                onValue={(lon) => update((c) => centreOuter(c.grid, c.grid.projection.ref_lat, lon))}
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
            <Group justify="space-between">
              <Button
                size="xs"
                variant="light"
                leftSection={<IconWorld size={16} />}
                title={t("suggestInfo")}
                onClick={() => update((c) => editGrid(c.grid, (g) => Object.assign(g.projection, suggestedProjection(g))))}
              >
                {t("suggest")}
              </Button>
              <HelpLink topic="projection" />
            </Group>
          </Stack>
        </Fold>

        <VerticalLevels draft={draft} update={update} />
        <LevelsScene draft={draft} />

      {(problems.length > 0 || serverIssues.length > 0) && <Fold title={t("problems")} aside={String(problems.length + serverIssues.length)}>
        <Alert
          color={problems.some((p) => p.severity === "error") || serverIssues.some((i) => i.severity === "error") ? "red" : "orange"}
          variant="light"
          icon={<IconAlertTriangle size={18} />}
          title={t("problems")}
        >
          <List spacing={4} size="sm">
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
        </Alert>
      </Fold>}
    </Page>
  );
}
