import { Accordion, ActionIcon, Autocomplete, Badge, Button, Group, NumberInput, Paper, SegmentedControl, Select, SimpleGrid, Stack, Text, Title, Tooltip } from "@mantine/core";
import { IconCurrentLocation, IconFocusCentered, IconPlus, IconTrash } from "@tabler/icons-react";
import { useEffect, useState } from "react";

import type { Case, NamelistSchema } from "../../../api/types";
import { useFieldIssue } from "../../../app/CaseDraft";
import { useFormat, useT } from "../../../i18n";
import { common } from "../../../i18n/common";
import { Confirm, FieldLabel, UnitInput, NumberField } from "../../../ui/Inputs";
import { addNest, removeDomains } from "./edit";
import { centreInParent, descendants, domainDx, domainName, editGrid, MAX_DOMAINS, nestMargins, snapPoints, type Problem } from "./grid";
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
  holdsFarms: boolean;
  onAdded: (index: number) => void;
  onPlace?: () => void;
  schema?: NamelistSchema;
}

/** One domain: spacing, size, position in its parent and static data, with its actions. */
export function DomainCard({ c, index, update, problems, holdsFarms, onAdded, onPlace, schema }: Props) {
  const t = useT(domainMessages);
  const geogIssue = useFieldIssue(`grid.domains.${index}.geog_data_res`);
  const geogValue = c.grid.domains[index].geog_data_res;
  const [otherGeog, setOtherGeog] = useState(geogValue !== "default" && geogValue !== "lowres");
  const geogChoice = otherGeog ? "other" : geogValue;
  const setGeog = (value: string) => update((next) => void (next.grid.domains[index].geog_data_res = value));
  const tc = useT(common);
  const f = useFormat();
  const grid = c.grid;
  const d = grid.domains[index];
  const [ratioInput, setRatioInput] = useState<string | number>(d.parent_grid_ratio);
  useEffect(() => setRatioInput(d.parent_grid_ratio), [d.parent_grid_ratio]);
  const dx = domainDx(grid)[index];
  const name = domainName(index);
  const parentName = index > 0 ? domainName(d.parent_id - 1) : "";
  const margins = nestMargins(grid, index);
  const children = descendants(grid, index);
  const severity = problems.some((p) => p.severity === "error") ? "red" : problems.length ? "orange" : undefined;

  // Changes that move or resize a domain keep every nest over the same place on Earth
  const edit = (change: (c: Case) => void, moved: number[] = []) =>
    update((next) => {
      editGrid(next.grid, () => change(next), moved);
    });

  return (
    <Paper withBorder radius="md" p="md" style={severity ? { borderColor: `var(--mantine-color-${severity}-5)` } : undefined}>
      <Stack gap="sm">
        <Group justify="space-between" gap="xs" wrap="nowrap">
          <Group gap="xs" wrap="nowrap">
            <Title order={4}>{name}</Title>
            <Text size="sm" c="dimmed" className="ows-num">
              {dx >= 1000 ? `${f.number(dx / 1000, dx % 1000 ? 2 : 0)} km` : `${f.number(dx, 0)} m`}
            </Text>
          </Group>
          <Group gap={2} wrap="nowrap">
            {index > 0 && (
              <Tooltip label={t("centre", { parent: parentName })}>
                <ActionIcon variant="subtle" aria-label={t("centre", { parent: parentName })} onClick={() => update((next) => centreInParent(next.grid, index))}>
                  <IconFocusCentered size={18} />
                </ActionIcon>
              </Tooltip>
            )}
            {grid.domains.length < MAX_DOMAINS && (
              <Tooltip label={t("addNest", { name })}>
                <ActionIcon
                  variant="subtle"
                  aria-label={t("addNest", { name })}
                  disabled={!schema}
                  onClick={() => {
                    // The new nest comes last
                    update((next) => void addNest(next, index, 3, schema));
                    onAdded(grid.domains.length);
                  }}
                >
                  <IconPlus size={18} />
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
                    <ActionIcon disabled={!schema} variant="subtle" color="red" aria-label={t("deleteNest", { name })} onClick={open}>
                      <IconTrash size={18} />
                    </ActionIcon>
                  </Tooltip>
                )}
              </Confirm>
            )}
          </Group>
        </Group>

        {holdsFarms && (
          <Badge size="sm" color="teal" variant="light" w="fit-content">
            {t("farms")}
          </Badge>
        )}
        <Text size="sm" className="ows-num">
          {t("sizeValue", {
            we: d.e_we,
            sn: d.e_sn,
            width: f.number(((d.e_we - 1) * dx) / 1000, 0),
            height: f.number(((d.e_sn - 1) * dx) / 1000, 0),
          })}
        </Text>

        <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="sm">
          {index === 0 ? (
            <NumberField
              label={t("spacing")}
              unit="km"
              min={0.1}
              decimalScale={3}
              commitOnBlur
              value={grid.dx / 1000}
              onValue={(km) => edit((next) => void (next.grid.dx = Math.round(km * 1000)))}
            />
          ) : (
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
          )}
          {index > 0 && (
            <Select
              label={t("parent")}
              data={grid.domains.slice(0, index).map((_, i) => ({ value: String(i + 1), label: domainName(i) }))}
              value={String(d.parent_id)}
              allowDeselect={false}
              onChange={(v) => v && edit((next) => void (next.grid.domains[index].parent_id = Number(v)))}
            />
          )}
        </SimpleGrid>
        <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="sm">
          {(["we", "sn"] as const).map((axis) => <ExtentInput key={axis}
            label={t(axis === "we" ? "width" : "height")} info={t("dimensionsInfo")} minimum={dx * 9 / 1000}
            km={((axis === "we" ? d.e_we : d.e_sn) - 1) * dx / 1000}
            commit={(value) => {
              const points = snapPoints(grid, index, axis, Math.round(value * 1000 / dx) + 1);
              edit((next) => { next.grid.domains[index][axis === "we" ? "e_we" : "e_sn"] = points; });
              return (points - 1) * dx / 1000;
            }} />)}
        </SimpleGrid>
        {onPlace && <Button variant="light" leftSection={<IconCurrentLocation size={16} />} onClick={onPlace}>{t("startPlacing")}</Button>}
        <Accordion variant="default"><Accordion.Item value="details"><Accordion.Control>{t("advanced")}</Accordion.Control><Accordion.Panel>
        <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="sm">
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
          {index > 0 && (
            <>
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
        </SimpleGrid>
        <Stack gap={6} mt="sm">
          <FieldLabel label={t("geog")} info={t("geogInfo")} />
          <SegmentedControl
            fullWidth
            value={geogChoice}
            onChange={(choice) => {
              setOtherGeog(choice === "other");
              if (choice !== "other") setGeog(choice);
            }}
            data={[
              { value: "default", label: t("geogLabels.default") },
              { value: "lowres", label: t("geogLabels.lowres") },
              { value: "other", label: t("geogOther") },
            ]}
          />
        </Stack>
        {otherGeog && <Autocomplete
          mt="xs"
          aria-label={t("geog")}
          data={(Object.keys(GEOG_RESOLUTIONS) as (keyof typeof GEOG_RESOLUTIONS)[]).map((group) => ({ group: t(`geogGroups.${group}`), items: [...GEOG_RESOLUTIONS[group]] }))}
          renderOption={({ option }) => (
            <Group justify="space-between" wrap="nowrap" w="100%" gap="md">
              <Text size="sm" ff="monospace">{option.value}</Text>
              <Text size="xs" c="dimmed">{t(`geogLabels.${option.value as GeogKeyword}`)}</Text>
            </Group>
          )}
          filter={({ options }) => options}
          value={d.geog_data_res}
          error={geogIssue?.text}
          onChange={setGeog}
          styles={{ input: { fontFamily: "var(--mantine-font-family-monospace)" } }}
        />}
        {!otherGeog && geogIssue && <Text size="xs" c={geogIssue.severity === "error" ? "red" : "orange"}>{geogIssue.text}</Text>}
        </Accordion.Panel></Accordion.Item></Accordion>
        {margins && (
          <Text size="xs" c="dimmed" style={{ fontVariantNumeric: "tabular-nums" }}>
            {t("margins", margins)}
          </Text>
        )}
        {index === 0 && grid.domains.length === 1 && (
          <Group>
            <Button
              size="xs"
              variant="light"
              leftSection={<IconPlus size={14} />}
              disabled={!schema}
              onClick={() => {
                update((next) => void addNest(next, 0, 3, schema));
                onAdded(1);
              }}
            >
              {t("addNest", { name })}
            </Button>
          </Group>
        )}
      </Stack>
    </Paper>
  );
}
