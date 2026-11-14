/**
 * The turbines of the farm shown, in two columns: their number and power on the left, the table
 * on the right. Only the rows in view are drawn, so a farm of a thousand turbines scrolls freely.
 */
import { ActionIcon, Checkbox, Select, Table, TextInput, Tooltip } from "@mantine/core";
import { IconClick, IconCurrentLocation } from "@tabler/icons-react";

import type { Farm, Turbine } from "../../../api/types";
import { useFormat, useT } from "../../../i18n";
import { Fold } from "../../../ui/Fold";
import { NumberField } from "../../../ui/Inputs";
import { useRowsInView } from "../../../ui/rows";
import { EmptyState } from "../../../ui/States";
import { farmMessages } from "./messages";
import { summarize, turbineLabel, type TypeInfo } from "./model";

const ROW = 44;
const VIEW = 528;
const MARGIN = 6;

export function TurbineList({ farm, types, typeOptions, selected, onSelect, onLocate, onEdit }: {
  farm: Farm;
  types: Map<number, TypeInfo>;
  typeOptions: { value: string; label: string }[];
  selected: number[];
  onSelect: (indices: number[]) => void;
  onLocate: (index: number) => void;
  onEdit: (index: number, change: (item: Turbine) => void) => void;
}) {
  const t = useT(farmMessages);
  const f = useFormat();
  const count = farm.turbines.length;
  const { first, last, before, after, onScroll } = useRowsInView(count, ROW, VIEW, MARGIN);
  const chosen = new Set(selected);

  return (
    <Fold title={t("turbines.title", { name: farm.name })} value={f.number(count, 0)} detail={`${f.number(summarize(farm, types).installedMw, 1)} MW`} lazy className="ows-farm-table">
      {!count ? <EmptyState icon={<IconClick size={26} stroke={1.5} />} title={t("turbines.emptyTitle")}>{t("page.emptyTurbines")}</EmptyState> : (
        <div className="ows-turbine-scroll" style={{ maxHeight: VIEW }} onScroll={onScroll}>
          <Table stickyHeader layout="fixed" aria-label={t("turbines.title", { name: farm.name })} aria-rowcount={count + 1}>
            <colgroup><col style={{ width: 44 }} /><col style={{ width: 56 }} /><col /><col /><col /><col /><col style={{ width: 48 }} /></colgroup>
            <Table.Thead>
              <Table.Tr>
                <Table.Th><Checkbox aria-label={t("turbines.selectAll")} checked={selected.length === count} indeterminate={selected.length > 0 && selected.length < count} onChange={(event) => onSelect(event.currentTarget.checked ? farm.turbines.map((_, index) => index) : [])} /></Table.Th>
                <Table.Th>#</Table.Th>
                <Table.Th>{t("turbines.label")}</Table.Th>
                <Table.Th>{t("turbines.lat")}</Table.Th>
                <Table.Th>{t("turbines.lon")}</Table.Th>
                <Table.Th>{t("turbines.type")}</Table.Th>
                <Table.Th aria-label={t("turbines.locate")} />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {before > 0 && <tr aria-hidden="true" style={{ height: before }} />}
              {farm.turbines.slice(first, last).map((tb, k) => {
                const index = first + k;
                const label = turbineLabel(farm, index);
                const edit = (change: (item: Turbine) => void) => onEdit(index, change);
                return (
                  <Table.Tr key={index} aria-rowindex={index + 2} data-selected={chosen.has(index) || undefined}>
                    <Table.Td><Checkbox aria-label={t("turbines.selectRow", { label })} checked={chosen.has(index)} onChange={(event) => onSelect(event.currentTarget.checked ? [...selected, index] : selected.filter((n) => n !== index))} /></Table.Td>
                    <Table.Td className="ows-num ows-turbine-number">{index + 1}</Table.Td>
                    <Table.Td><TextInput aria-label={t("turbines.labelOf", { label })} size="xs" value={tb.id ?? ""} placeholder={label} maxLength={32} onChange={(event) => { const value = event.currentTarget.value; edit((item) => { item.id = value || null; }); }} /></Table.Td>
                    <Table.Td><NumberField aria-label={t("turbines.latOf", { label })} size="xs" min={-90} max={90} decimalScale={6} commitOnBlur value={tb.lat} onValue={(value) => edit((item) => { item.lat = value; })} /></Table.Td>
                    <Table.Td><NumberField aria-label={t("turbines.lonOf", { label })} size="xs" min={-180} max={180} decimalScale={6} commitOnBlur value={tb.lon} onValue={(value) => edit((item) => { item.lon = value; })} /></Table.Td>
                    <Table.Td><Select aria-label={t("turbines.typeOf", { label })} size="xs" data={typeOptions} value={String(tb.type)} allowDeselect={false} onChange={(value) => value && edit((item) => { item.type = Number(value); })} /></Table.Td>
                    <Table.Td>
                      <Tooltip label={t("turbines.locate")} openDelay={250}>
                        <ActionIcon variant="subtle" color="gray" aria-label={`${t("turbines.locate")} · ${label}`} onClick={() => onLocate(index)}><IconCurrentLocation size={16} /></ActionIcon>
                      </Tooltip>
                    </Table.Td>
                  </Table.Tr>
                );
              })}
              {after > 0 && <tr aria-hidden="true" style={{ height: after }} />}
            </Table.Tbody>
          </Table>
        </div>
      )}
    </Fold>
  );
}
