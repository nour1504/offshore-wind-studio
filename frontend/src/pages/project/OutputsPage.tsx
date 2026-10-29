import { Accordion, ActionIcon, Alert, Box, Button, Code, Group, List, Modal, Select, SimpleGrid, Stack, Switch, Tabs, Text } from "@mantine/core";
import { IconTrash } from "@tabler/icons-react";
import { useState } from "react";

import { useGeometry } from "../../api/cases";
import type { TimeSeries, TimeSeriesPoint } from "../../api/types";
import { useLoadedDraft } from "../../app/CaseDraft";
import { sectionMessages } from "../../app/sections";
import { useFormat, useT } from "../../i18n";
import { GlideTabsList } from "../../ui/GlideTabs";
import { Confirm, FieldLabel, NumberField } from "../../ui/Inputs";
import { Page } from "../../ui/Page";
import { Fold } from "../../ui/Fold";
import { HelpLink } from "../../ui/Help";
import { QueryView } from "../../ui/States";
import { ProjectMap } from "../../ui/map/ProjectMap";
import { PointEditor, PointsImport } from "./outputs/PointsEditor";
import { VariableList } from "./outputs/VariableLists";
import { messages } from "./outputs/messages";
import { useTslistPreview } from "./outputs/queries";
import { defaultTimeSeries, duplicatePrefixes, hasName, historyTimes, iofieldsText, parseTslist, prefixFor, READ_BY_RESULTS, roundCoordinate, simulatedHours, turbineCount } from "./outputs/rules";
import styles from "./outputs/OutputsPage.module.css";

export default function OutputsPage() {
  const t = useT(messages); const ts = useT(sectionMessages); const f = useFormat();
  const { draft, update, issues } = useLoadedDraft();
  const [picking, setPicking] = useState(false);
  const [importing, setImporting] = useState(false);
  const [editing, setEditing] = useState<{ index: number | null; point: TimeSeriesPoint } | null>(null);
  const preview = useTslistPreview(draft); const geometry = useGeometry(draft);
  const locations = parseTslist(preview.data);
  const duplicates = duplicatePrefixes(locations.map((point) => point.prefix));
  const config = draft.time_series;
  const required = draft.outputs.remove.filter((name) => hasName(READ_BY_RESULTS, name));
  const setConfig = (change: (value: TimeSeries) => void) => update((c) => { if (c.time_series) change(c.time_series); });
  const begin = (lat = draft.grid.projection.ref_lat, lon = draft.grid.projection.ref_lon) => {
    const name = t("editor.defaultName", { n: (config?.points.length ?? 0) + 1 });
    const taken = new Set((config?.points ?? []).map((point) => point.prefix.toLowerCase()));
    setEditing({ index: null, point: { name, prefix: prefixFor(name, taken), lat: roundCoordinate(lat), lon: roundCoordinate(lon) } });
    setPicking(false);
  };
  // The note on repeated turbine names only informs: nothing to act on, so not shown
  const tsIssues = issues.filter((issue) => /time series|tslist|max_ts|prefix/i.test(issue.message) && !issue.message.startsWith("Repeated turbine labels"));
  const enableSwitch = config && config.points.length ? <Confirm title={t("ts.disableTitle")} text={t("ts.disableText", { n: config.points.length })} onConfirm={() => update((c) => { c.time_series = null; })}>{(open) => <Switch label={<FieldLabel label={t("ts.enable")} info={t("ts.enableInfo")} />} checked onChange={open} />}</Confirm> : <Switch label={<FieldLabel label={t("ts.enable")} info={t("ts.enableInfo")} />} checked={Boolean(config)} onChange={(event) => { const enabled = event.currentTarget.checked; update((c) => { c.time_series = enabled ? { ...defaultTimeSeries(c), max_levels: Math.min(15, c.grid.e_vert - 1) } : null; }); }} />;

  return <Page title={ts("project.outputs")} help="outputs" fluid>
    <Tabs defaultValue="points" keepMounted={false} onChange={() => setPicking(false)}>
      <GlideTabsList mb="xl" style={{ flexWrap: "nowrap", overflowX: "auto" }}>
        <Tabs.Tab value="points">{t("page.pointsTab")}</Tabs.Tab>
        <Tabs.Tab value="maps">{t("page.mapsTab")}</Tabs.Tab>
      </GlideTabsList>
      <Tabs.Panel value="points">
        <Stack gap={32}>
          <Fold title={t("ts.title")}>
            <Stack gap="xl"><Group justify="space-between">{enableSwitch}<HelpLink topic="tslist" /></Group>
            {!config ? <Text size="sm" c="dimmed">{t("ts.off")}</Text> : <Stack gap="lg">
              <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="xl" maw={850}>
                <Select label={<FieldLabel label={t("ts.turbines")} info={t("ts.turbinesInfo")} />} value={config.turbines} data={[{ value: "none", label: t("ts.none") }, { value: "cells", label: t("ts.cells") }, { value: "each", label: t("ts.each", { n: turbineCount(draft) }) }]} allowDeselect={false} onChange={(value) => setConfig((s) => { s.turbines = value as TimeSeries["turbines"]; })} />
                <NumberField label={t("ts.levels")} info={t("ts.levelsInfo", { max: draft.grid.e_vert - 1 })} unit={t("ts.levelsUnit")} min={1} max={draft.grid.e_vert - 1} allowDecimal={false} value={config.max_levels} onValue={(value) => setConfig((s) => { s.max_levels = value; })} />
              </SimpleGrid>
            </Stack>}
            </Stack>
          </Fold>
          {config && <>
            <Fold title={t("ts.points")} aside={String(config.points.length)} lazy>
              <Stack gap="lg">
                <Group gap="xs"><Button size="sm" variant={picking ? "filled" : "light"} onClick={() => setPicking((current) => !current)}>{t(picking ? "ts.stopPlacing" : "ts.place")}</Button><Button size="sm" variant="default" onClick={() => begin()}>{t("ts.add")}</Button><Button size="sm" variant="subtle" onClick={() => setImporting(true)}>{t("ts.paste")}</Button></Group>
                {picking && <Text size="sm" c="dimmed" role="status">{t("ts.placing")}</Text>}
                <div className={styles.workspace}>
                  <Box className={styles.map}>
                    <ProjectMap geometry={geometry.data} farmOrder={draft.farms.map((farm) => farm.id)} showProbes={false} points={config.points.map((point) => ({ lat: point.lat, lon: point.lon, label: point.name }))} height={380} picking={picking} onPick={begin} ariaLabel={t("ts.map")} />
                  </Box>
                  <Stack gap={0} className={styles.points}>
                    <Group justify="space-between" px="md" py="sm"><Text size="sm" fw={600}>{t("ts.pointsList")}</Text><Text size="xs" c="dimmed">{t("ts.count", { n: config.points.length })}</Text></Group>
                    {config.points.length === 0 ? <Stack gap="xs" p="md"><Text size="sm" fw={500}>{t("ts.empty")}</Text><Text size="sm" c="dimmed">{t("ts.emptyText")}</Text></Stack> : <Box className={styles.pointList}>{config.points.map((point, index) => <Group key={index} className={styles.point} justify="space-between" align="flex-start" wrap="nowrap">
                      <Stack gap={4} style={{ minWidth: 0 }}><Text size="sm" fw={600}>{point.name}</Text><Text size="xs" c="dimmed">{f.number(point.lat, 5)} · {f.number(point.lon, 5)}</Text><Code c={duplicates.has(point.prefix.toLowerCase()) ? "red" : undefined}>{point.prefix}</Code></Stack>
                      <Group gap={0} wrap="nowrap"><Button size="compact-xs" variant="subtle" onClick={() => setEditing({ index, point: structuredClone(point) })} aria-label={t("ts.edit", { name: point.name })}>{t("ts.editShort")}</Button><Confirm title={t("ts.remove", { name: point.name })} onConfirm={() => setConfig((s) => { s.points.splice(index, 1); })}>{(open) => <ActionIcon color="red" variant="subtle" aria-label={t("ts.remove", { name: point.name })} onClick={open}><IconTrash size={16} /></ActionIcon>}</Confirm></Group>
                    </Group>)}</Box>}
                  </Stack>
                </div>
              </Stack>
            </Fold>
            <Fold title={t("ts.summary")} aside={String(locations.length)}>
              <Stack gap="md">
                {tsIssues.length > 0 && <Alert color="orange" title={t("ts.checks")}><List size="sm">{tsIssues.map((issue, index) => <List.Item key={index}>{issue.message === "Repeated turbine labels are qualified by their farm in energy results. Generated tslist prefixes remain unique; truncated display names are not used for lookup." ? t("ts.repeatedLabels") : issue.message}</List.Item>)}</List></Alert>}
                <QueryView query={preview}>{(text) => <Stack gap="md">
                  <Group gap="xl"><Text size="sm" fw={600}>{t("ts.count", { n: locations.length })}</Text><Text size="sm" c="dimmed">{t("ts.countDetail", { generated: Math.max(0, locations.length - config.points.length), extra: config.points.length })}</Text></Group>
                  {locations.length === 0 && <Text size="sm" c="dimmed">{t("ts.noLocation")}</Text>}
                  <Accordion multiple>
                    <Accordion.Item value="tslist"><Accordion.Control>{t("ts.tslistFile")}</Accordion.Control><Accordion.Panel><Stack gap="sm"><Text size="sm" c="dimmed">{t("ts.tslistHelp")}</Text><Code block style={{ maxHeight: 300, overflow: "auto" }}>{text}</Code></Stack></Accordion.Panel></Accordion.Item>
                  </Accordion>
                </Stack>}</QueryView>
              </Stack>
            </Fold>
          </>}
        </Stack>
      </Tabs.Panel>
      <Tabs.Panel value="maps">
        <Stack gap={32}>
          <Fold title={t("history.title")} aside={`${draft.history_interval_minutes} min`} help="iofields">
            <Stack gap="lg">
              <Group align="flex-end" gap="xl"><NumberField label={t("history.interval")} info={t("history.intervalInfo")} field="history_interval_minutes" unit="min" min={1} allowDecimal={false} value={draft.history_interval_minutes} onValue={(value) => update((c) => { c.history_interval_minutes = value; })} maw={260} /><Text size="sm" c="dimmed" pb={8}>{t("history.times", { n: historyTimes(draft), hours: f.number(simulatedHours(draft), 1) })}</Text></Group>
              {draft.history_interval_minutes < 10 && <Alert color="orange">{t("history.frequent")}</Alert>}
            </Stack>
          </Fold>
          <Fold title={t("history.variables")} aside={`+${draft.outputs.add.length} / −${draft.outputs.remove.length}`} lazy>
            <Stack gap="md">
              <SimpleGrid cols={{ base: 1, md: 2 }} spacing={32}>{(["add", "remove"] as const).map((kind) => <VariableList key={kind} kind={kind} outputs={draft.outputs} onChange={(values, other) => update((c) => { c.outputs[kind] = values; c.outputs[kind === "add" ? "remove" : "add"] = other; })} />)}</SimpleGrid>
              {required.length > 0 && <Alert color="orange">{t("history.needed", { names: required.join(", ") })}</Alert>}
              <Accordion>
                <Accordion.Item value="iofields"><Accordion.Control>{t("history.iofields")}</Accordion.Control><Accordion.Panel>{iofieldsText(draft.outputs) ? <Code block>{iofieldsText(draft.outputs)}</Code> : <Text size="sm" c="dimmed">{t("history.noIofields")}</Text>}</Accordion.Panel></Accordion.Item>
              </Accordion>
            </Stack>
          </Fold>
        </Stack>
      </Tabs.Panel>
    </Tabs>
    <Modal opened={importing && Boolean(config)} onClose={() => setImporting(false)} title={t("paste.title")} size="lg"><PointsImport draft={draft} onAdd={(points) => { setConfig((s) => { s.points.push(...points); }); setImporting(false); }} /></Modal>
    {editing && config && <PointEditor key={String(editing.index) + "-" + editing.point.lat + "-" + editing.point.lon} initial={editing.point} index={editing.index} others={config.points.filter((_, index) => index !== editing.index).map((point) => point.prefix)} onClose={() => setEditing(null)} onApply={(point) => { setConfig((s) => { if (editing.index === null) s.points.push(point); else s.points[editing.index] = point; }); setEditing(null); }} />}
  </Page>;
}
