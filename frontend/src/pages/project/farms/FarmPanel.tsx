/**
 * The farms beside the map, one at a time behind tabs: its figures (turbines, power, simulated or
 * not), the three ways to add turbines, then what names and marks it.
 */
import { ActionIcon, Button, Combobox, Group, InputBase, Paper, Popover, SimpleGrid, Stack, Switch, Text, TextInput, Tooltip, UnstyledButton } from "@mantine/core";
import { IconArrowRight, IconClick, IconClipboardText, IconPlus, IconTrash, IconWindmill } from "@tabler/icons-react";
import { useEffect, useState } from "react";

import type { Case, Farm, FarmAppearance, FarmSymbol } from "../../../api/types";
import { useFormat, useT } from "../../../i18n";
import { href } from "../../../router";
import { Confirm, FieldLabel } from "../../../ui/Inputs";
import { FarmSymbolMark } from "../../../ui/map/FarmSymbolMark";
import { farmAppearance } from "../../../ui/map/farms";
import { Stat, StatGrid } from "../../../ui/Stat";
import { EmptyState } from "../../../ui/States";
import { appearanceMessages, FarmAppearanceEditor } from "./FarmAppearanceEditor";
import { farmMessages } from "./messages";
import { FARM_ID_PATTERN, summarize, type TypeInfo } from "./model";

interface Props {
  caseId: string;
  draft: Case;
  farm: Farm | undefined;
  types: Map<number, TypeInfo>;
  /** What the farms still need before turbines can be placed */
  missing: "domains" | "turbines" | null;
  picking: boolean;
  onPicking: (on: boolean) => void;
  onImport: () => void;
  onAddOne: () => void;
  onChoose: (id: string) => void;
  onCreate: () => void;
  update: (change: (c: Case) => void) => void;
}

export function FarmPanel({ caseId, draft, farm, types, missing, picking, onPicking, onImport, onAddOne, onChoose, onCreate, update }: Props) {
  const t = useT(farmMessages);
  const ta = useT(appearanceMessages);
  const f = useFormat();
  const index = farm ? draft.farms.findIndex((item) => item.id === farm.id) : -1;
  const editFarm = (change: (item: Farm) => void) => update((c) => { const item = c.farms[index]; if (item) change(item); });

  return (
    <div className="ows-farm-panel">
      <div className="ows-farm-tabs" role="tablist" aria-label={t("page.farms")}>
        {draft.farms.map((item, i) => (
          <UnstyledButton key={item.id} role="tab" aria-selected={item.id === farm?.id} className="ows-farm-tab" onClick={() => onChoose(item.id)}>
            <FarmSymbolMark {...farmAppearance(item, i)} size={14} />
            <span className="ows-farm-tab-name">{item.name || item.id}</span>
          </UnstyledButton>
        ))}
        <Tooltip label={t("page.newFarm")}>
          <ActionIcon variant="subtle" color="gray" size={34} className="ows-farm-new" aria-label={t("page.newFarm")} onClick={onCreate}><IconPlus size={18} /></ActionIcon>
        </Tooltip>
      </div>
      {!farm ? <EmptyState icon={<IconWindmill size={26} stroke={1.5} />} title={t("list.emptyTitle")}>{t("page.noFarm")}</EmptyState> : (
        <div className="ows-farm-sheet" role="tabpanel" key={farm.id}>
          <StatGrid cols={{ base: 3 }}>
            <Stat label={t("panel.turbines")} value={f.number(farm.turbines.length, 0)} filled={farm.turbines.length > 0} />
            <Stat label={t("panel.power")} value={f.number(summarize(farm, types).installedMw, 1)} unit="MW" filled={farm.turbines.length > 0} order={1} />
            <Stat label={t("page.simulated")} filled={farm.enabled} order={2} value={
              <Switch aria-label={t("list.simulate", { name: farm.name })} checked={farm.enabled} onChange={(event) => { const enabled = event.currentTarget.checked; editFarm((item) => { item.enabled = enabled; }); }} />
            } />
          </StatGrid>
          {missing ? (
            <Paper withBorder p="lg">
              <Stack gap="sm" align="flex-start">
                <Text size="sm">{t(missing === "domains" ? "page.needDomains" : "page.needTurbines")}</Text>
                <Button variant="default" component="a" href={href(`projects/${encodeURIComponent(caseId)}/${missing}`)} rightSection={<IconArrowRight size={16} />}>{t(missing === "domains" ? "page.goDomains" : "page.goTurbines")}</Button>
              </Stack>
            </Paper>
          ) : (
            <div className="ows-farm-ways" role="group" aria-label={t("page.add", { name: farm.name })}>
              <UnstyledButton className="ows-farm-way" aria-pressed={picking} data-active={picking || undefined} onClick={() => onPicking(!picking)}><IconClick size={18} stroke={1.6} />{t("page.ways.click")}</UnstyledButton>
              <UnstyledButton className="ows-farm-way" onClick={onImport}><IconClipboardText size={18} stroke={1.6} />{t("page.ways.import")}</UnstyledButton>
              <UnstyledButton className="ows-farm-way" onClick={onAddOne}><IconPlus size={18} stroke={1.6} />{t("page.ways.one")}</UnstyledButton>
            </div>
          )}
          <SimpleGrid cols={2} spacing="md" verticalSpacing="md">
            <TextInput label={t("dialog.name")} maxLength={80} value={farm.name} error={!farm.name.trim() ? t("dialog.nameRequired") : undefined} onChange={(event) => { const value = event.currentTarget.value; editFarm((item) => { item.name = value; }); }} />
            <IdField farm={farm} farms={draft.farms} onCommit={(value) => { editFarm((item) => { item.id = value; }); onChoose(value); }} />
            <MarkField label={t("panel.marker")} farm={farm} index={index} name={(symbol) => ta(symbol)} onChange={(appearance) => editFarm((item) => { item.appearance = appearance; })} />
            <NotesField farm={farm} onChange={editFarm} />
          </SimpleGrid>
          <Group justify="flex-end" className="ows-farm-end">
            <Confirm title={t("list.delete")} text={t("list.deleteText", { n: farm.turbines.length })} onConfirm={() => update((c) => { c.farms = c.farms.filter((entry) => entry.id !== farm.id); })}>
              {(open) => <Button size="xs" variant="subtle" color="red" leftSection={<IconTrash size={14} />} onClick={open}>{t("list.delete")}</Button>}
            </Confirm>
          </Group>
        </div>
      )}
    </div>
  );
}

/** The farm's id, kept while typed and given to the farm once valid and free (Enter or leaving the field). */
function IdField({ farm, farms, onCommit }: { farm: Farm; farms: Farm[]; onCommit: (id: string) => void }) {
  const t = useT(farmMessages);
  const [value, setValue] = useState(farm.id);
  useEffect(() => setValue(farm.id), [farm.id]);
  const taken = farms.filter((item) => item.id === value).length > (value === farm.id ? 1 : 0);
  const error = !FARM_ID_PATTERN.test(value) ? t("dialog.idInvalid") : taken ? t("dialog.idTaken") : undefined;
  return (
    <TextInput label={<FieldLabel label={t("dialog.id")} info={t("dialog.idInfo")} />} value={value} error={error}
      onChange={(event) => setValue(event.currentTarget.value)}
      onKeyDown={(event) => { if (event.key === "Enter") event.currentTarget.blur(); }}
      onBlur={() => { if (value === farm.id) return; if (error) setValue(farm.id); else onCommit(value); }} />
  );
}

/** The farm's mark on the maps, shown as a field; its colours and symbols open under it. */
function MarkField({ label, farm, index, name, onChange }: { label: string; farm: Farm; index: number; name: (symbol: FarmSymbol) => string; onChange: (appearance: FarmAppearance) => void }) {
  const look = farmAppearance(farm, index);
  return (
    <Popover position="bottom-start" shadow="md" width={300} trapFocus>
      <Popover.Target>
        <InputBase component="button" type="button" label={label} pointer rightSection={<Combobox.Chevron />} rightSectionPointerEvents="none">
          <Group gap={8} wrap="nowrap"><FarmSymbolMark {...look} size={15} /><span>{name(look.symbol)}</span></Group>
        </InputBase>
      </Popover.Target>
      <Popover.Dropdown p="md"><FarmAppearanceEditor value={farm.appearance} index={index} onChange={onChange} /></Popover.Dropdown>
    </Popover>
  );
}

/** Free notes about the farm (operator, phase…), shown as a field with their count. */
function NotesField({ farm, onChange }: { farm: Farm; onChange: (change: (item: Farm) => void) => void }) {
  const t = useT(farmMessages);
  const [key, setKey] = useState("");
  const [value, setValue] = useState("");
  const entries = Object.entries(farm.properties);
  const add = () => { const name = key.trim(); onChange((item) => { item.properties[name] = value; }); setKey(""); setValue(""); };
  return (
    <Popover position="bottom-end" shadow="md" width={420} trapFocus>
      <Popover.Target>
        <InputBase component="button" type="button" label={t("details.properties")} pointer rightSection={<Combobox.Chevron />} rightSectionPointerEvents="none">
          <Text span c={entries.length ? undefined : "dimmed"} inherit>{entries.length ? t("panel.notes", { n: entries.length }) : t("panel.noNote")}</Text>
        </InputBase>
      </Popover.Target>
      <Popover.Dropdown p="md">
        <Stack gap="sm">
          {entries.map(([name, text]) => (
            <Group key={name} gap="xs" wrap="nowrap">
              <Text size="sm" w={120} truncate>{name}</Text>
              <TextInput aria-label={t("details.value")} value={text} style={{ flex: 1 }} onChange={(event) => { const next = event.currentTarget.value; onChange((item) => { item.properties[name] = next; }); }} />
              <ActionIcon color="red" variant="subtle" aria-label={t("details.removeProperty", { key: name })} onClick={() => onChange((item) => { delete item.properties[name]; })}><IconTrash size={16} /></ActionIcon>
            </Group>
          ))}
          <SimpleGrid cols={2} spacing="xs">
            <TextInput label={t("details.key")} placeholder={t("details.keyExample")} value={key} onChange={(event) => setKey(event.currentTarget.value)} />
            <TextInput label={t("details.value")} placeholder={t("details.valueExample")} value={value} onChange={(event) => setValue(event.currentTarget.value)} />
          </SimpleGrid>
          <Group justify="flex-end">
            <Button size="xs" variant="default" disabled={!key.trim() || key.trim() in farm.properties} onClick={add}>{t("details.addProperty")}</Button>
          </Group>
        </Stack>
      </Popover.Dropdown>
    </Popover>
  );
}
