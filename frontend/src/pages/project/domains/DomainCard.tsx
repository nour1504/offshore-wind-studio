import { ActionIcon, Autocomplete, Group, NumberInput, Select, SimpleGrid, Text, Tooltip } from "@mantine/core";
import { IconCurrentLocation, IconFocusCentered, IconPlus, IconTrash } from "@tabler/icons-react";
import { useEffect, useState } from "react";

import type { Case, NamelistSchema } from "../../../api/types";
import { useFieldIssue } from "../../../app/CaseDraft";
import { useFormat, useT } from "../../../i18n";
import { common } from "../../../i18n/common";
import { Spec } from "../../../ui/Fold";
import { Confirm, FieldLabel, UnitInput, NumberField } from "../../../ui/Inputs";
import { addNest, removeDomains } from "./edit";
import { centreInParent, centreOuter, descendants, domainDx, domainName, editGrid, MAX_DOMAINS, nestMargins, snapPoints, type Problem } from "./grid";
import { domainMessages } from "./messages";

// Keywords of geogrid's GEOGRID.TBL.ARW (WPS 4.7), grouped as offered; any other value can be typed
const GEOG_RESOLUTIONS = {
  set: ["default", "lowres"],
  res: ["30s", "2m", "5m", "10m"],
  data: ["modis_15s+default", "modis_30s+default", "usgs_30s+default", "gmted2010_30s+default", "nlcd2011_9s+default", "bnu_soil_30s+default"],
} as const;
type GeogKeyword = (typeof GEOG_RESOLUTIONS)[keyof typeof GEOG_RESOLUTIONS][number];

/** Keep incomplete typing local: resizing a grid also repositions its nests. */
function ExtentInput({ label, info, km, minimum, commit }: { label: string; info: string; km: number; minimum: number; commit: (value: number) => number }) {
  const [value, setValue] = useState<string | number>(km);
  useEffect(() => setValue(km), [km]);
  return <UnitInput label={label} info={info} unit="km" min={minimum} decimalScale={2}
    value={value} onChange={setValue}
    onBlur={() => setValue(value !== "" && Number(value) > 0 ? commit(Number(value)) : km)}
    onKeyDown={(event) => { if (event.key === "Enter") event.currentTarget.blur(); }} />;
}

interface Props {
  c: Case;
  index: number;
  update: (change: (c: Case) => void) => void;
  problems: Problem[];
  onAdded: (index: number) => void;
  onPlace?: () => void;
  schema?: NamelistSchema;
}

/**
 * One domain in two columns: on the left its name, its grid spacing in large type, its parent and
 * margins, and its tools; on the right every setting written to the namelists for it (spacing or
 * refinement, centre or start in the parent, static data, size in km and in points).
 */
export function DomainCard({ c, index, update, problems, onAdded, onPlace, schema }: Props) {
  const t = useT(domainMessages);
  const tc = useT(common);
  const f = useFormat();
  const geogIssue = useFieldIssue(`grid.domains.${index}.geog_data_res`);
  const grid = c.grid;
  const d = grid.domains[index];
  const [ratioInput, setRatioInput] = useState<string | number>(d.parent_grid_ratio);
  useEffect(() => setRatioInput(d.parent_grid_ratio), [d.parent_grid_ratio]);
  const dx = domainDx(grid)[index];
  const name = domainName(index);
  const parentName = index > 0 ? domainName(d.parent_id - 1) : "";
  const margins = nestMargins(grid, index);
  const children = descendants(grid, index);
  const holdsFarms = (c.farm_scheme?.domains ?? []).includes(index + 1);
  const severity = problems.some((p) => p.severity === "error") ? "error" : problems.length ? "warning" : undefined;

  // Changes that move or resize a domain keep every nest over the same place on Earth
  const edit = (change: (c: Case) => void, moved: number[] = []) =>
    update((next) => {
      editGrid(next.grid, () => change(next), moved);
    });

  const tools = (
    <>
      {onPlace && (
        <Tooltip label={t("startPlacing")}>
          <ActionIcon variant="default" aria-label={`${t("startPlacing")} · ${name}`} onClick={onPlace}><IconCurrentLocation size={16} /></ActionIcon>
        </Tooltip>
      )}
      {index > 0 && (
        <Tooltip label={t("centre", { parent: parentName })}>
          <ActionIcon variant="default" aria-label={t("centre", { parent: parentName })} onClick={() => update((next) => centreInParent(next.grid, index))}><IconFocusCentered size={16} /></ActionIcon>
        </Tooltip>
      )}
      {grid.domains.length < MAX_DOMAINS && (
        <Tooltip label={t("addNest", { name })}>
          <ActionIcon
            variant="default"
            aria-label={t("addNest", { name })}
            disabled={!schema}
            onClick={() => {
              // The new nest comes last
              update((next) => void addNest(next, index, 3, schema));
              onAdded(grid.domains.length);
            }}
          >
            <IconPlus size={16} />
          </ActionIcon>
        </Tooltip>
      )}
      {index > 0 && (
        <Confirm
          title={t("deleteNest", { name })}
          text={children.length ? t("deleteWithChildren", { name, names: children.map(domainName).join(", ") }) : undefined}
          confirmLabel={tc("delete")}
          onConfirm={() => update((next) => void removeDomains(next, index, schema))}
        >
          {(open) => (
            <Tooltip label={t("deleteNest", { name })}>
              <ActionIcon disabled={!schema} variant="default" c="red.6" aria-label={t("deleteNest", { name })} onClick={open}><IconTrash size={16} /></ActionIcon>
            </Tooltip>
          )}
        </Confirm>
      )}
    </>
  );

  // A nest sits in a parent listed before it; with a single choice, the parent is only named
  const parents = grid.domains.slice(0, index).map((_, i) => ({ value: String(i + 1), label: domainName(i) }));
  const detail = (index > 0 || holdsFarms) && (
    <>
      {index > 0 && <Group gap={8} wrap="nowrap" className="ows-domain-parent">
        <span>{t("parent")}</span>
        {parents.length > 1 ? (
          <Select size="xs" w={84} aria-label={t("parent")} data={parents} value={String(d.parent_id)} allowDeselect={false}
            onChange={(v) => v && edit((next) => void (next.grid.domains[index].parent_id = Number(v)))} />
        ) : <span className="ows-domain-parent-name">{parentName}</span>}
      </Group>}
      {index > 0 && margins && <span title={t("margins", margins)}>{t("marginsShort", margins)}</span>}
      {holdsFarms && <span>{t("farms")}</span>}
    </>
  );

  const geog = (
    <Autocomplete
      label={<FieldLabel label={t("geog")} info={t("geogInfo")} />}
      data={(Object.keys(GEOG_RESOLUTIONS) as (keyof typeof GEOG_RESOLUTIONS)[]).map((group) => ({ group: t(`geogGroups.${group}`), items: [...GEOG_RESOLUTIONS[group]] }))}
      renderOption={({ option }) => (
        <Group justify="space-between" wrap="nowrap" w="100%" gap="md">
          <Text size="sm" ff="monospace">{option.value}</Text>
          <Text size="xs" c="dimmed">{t(`geogLabels.${option.value as GeogKeyword}`)}</Text>
        </Group>
      )}
      filter={({ options }) => options}
      value={d.geog_data_res}
      error={geogIssue?.severity === "error" ? geogIssue.text : undefined}
      description={geogIssue?.severity === "warning" ? <span className="ows-field-warning">{geogIssue.text}</span> : undefined}
      inputWrapperOrder={["label", "input", "description", "error"]}
      onChange={(value) => update((next) => void (next.grid.domains[index].geog_data_res = value))}
      styles={{ input: { fontFamily: "var(--mantine-font-family-monospace)" } }}
    />
  );

  return (
    <Spec
      label={<span className="ows-domain-name" data-severity={severity}>{name}</span>}
      value={dx >= 1000 ? f.number(dx / 1000, dx % 1000 ? 2 : 0) : f.number(dx, 0)}
      unit={dx >= 1000 ? "km" : "m"}
      detail={detail || undefined}
      tools={tools}
    >
      <SimpleGrid cols={{ base: 1, xs: 2, lg: 4 }} spacing="md" verticalSpacing="lg" className="ows-domain-fields">
        {index === 0 ? (
          <>
            <NumberField
              label={t("spacing")}
              unit="km"
              min={0.1}
              decimalScale={3}
              commitOnBlur
              value={grid.dx / 1000}
              onValue={(km) => edit((next) => void (next.grid.dx = Math.round(km * 1000)))}
            />
            <NumberField
              label={t("refLat")}
              info={t("refLatInfo")}
              unit="°"
              min={-89.9}
              max={89.9}
              decimalScale={4}
              commitOnBlur
              value={grid.projection.ref_lat}
              onValue={(lat) => update((next) => centreOuter(next.grid, lat, next.grid.projection.ref_lon))}
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
              onValue={(lon) => update((next) => centreOuter(next.grid, next.grid.projection.ref_lat, lon))}
            />
          </>
        ) : (
          <>
            <NumberInput
              label={<FieldLabel label={t("ratio")} info={t("ratioInfo")} />}
              min={1}
              allowDecimal={false}
              value={ratioInput}
              onChange={setRatioInput}
              onKeyDown={(event) => { if (event.key === "Enter") event.currentTarget.blur(); }}
              onBlur={() => {
                const ratio = Number(ratioInput);
                if (!Number.isSafeInteger(ratio) || ratio < 1) { setRatioInput(d.parent_grid_ratio); return; }
                if (ratio === d.parent_grid_ratio) return;
                edit((next) => {
                  const nest = next.grid.domains[index];
                  // Keep about the same area: the same number of parent cells
                  const cellsWe = Math.max(1, Math.round((nest.e_we - 1) / nest.parent_grid_ratio));
                  const cellsSn = Math.max(1, Math.round((nest.e_sn - 1) / nest.parent_grid_ratio));
                  nest.parent_grid_ratio = ratio;
                  nest.e_we = cellsWe * ratio + 1;
                  nest.e_sn = cellsSn * ratio + 1;
                });
              }}
            />
            <NumberField
              label={t("startI")}
              info={t("startInfo")}
              min={1}
              allowDecimal={false}
              commitOnBlur
              value={d.i_parent_start}
              onValue={(v) => edit((next) => void (next.grid.domains[index].i_parent_start = v), [index, ...children])}
            />
            <NumberField
              label={t("startJ")}
              info={t("startInfo")}
              min={1}
              allowDecimal={false}
              commitOnBlur
              value={d.j_parent_start}
              onValue={(v) => edit((next) => void (next.grid.domains[index].j_parent_start = v), [index, ...children])}
            />
          </>
        )}
        {geog}
        {(["we", "sn"] as const).map((axis) => <ExtentInput key={axis}
          label={t(axis === "we" ? "width" : "height")} info={t("dimensionsInfo")} minimum={dx * 9 / 1000}
          km={((axis === "we" ? d.e_we : d.e_sn) - 1) * dx / 1000}
          commit={(value) => {
            const points = snapPoints(grid, index, axis, Math.round(value * 1000 / dx) + 1);
            edit((next) => { next.grid.domains[index][axis === "we" ? "e_we" : "e_sn"] = points; });
            return (points - 1) * dx / 1000;
          }} />)}
        <NumberField
          label={t("pointsWe")}
          info={t("pointsInfo")}
          min={10}
          allowDecimal={false}
          step={index > 0 ? d.parent_grid_ratio : 1}
          commitOnBlur
          value={d.e_we}
          onValue={(v) => edit((next) => void (next.grid.domains[index].e_we = snapPoints(next.grid, index, "we", v)))}
        />
        <NumberField
          label={t("pointsSn")}
          info={t("pointsInfo")}
          min={10}
          allowDecimal={false}
          step={index > 0 ? d.parent_grid_ratio : 1}
          commitOnBlur
          value={d.e_sn}
          onValue={(v) => edit((next) => void (next.grid.domains[index].e_sn = snapPoints(next.grid, index, "sn", v)))}
        />
      </SimpleGrid>
    </Spec>
  );
}
