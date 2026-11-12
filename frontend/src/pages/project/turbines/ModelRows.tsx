/**
 * An open turbine model in rows, as the other sections: its rated power with what defines it, the
 * farms that use it, then its curves (TurbineCurve). Every characteristic stays editable here.
 */
import { ActionIcon, Button, Group, SimpleGrid, Stack, Text, TextInput, Tooltip } from "@mantine/core";
import { IconArrowRight, IconCheck, IconCopy, IconRestore, IconTrash } from "@tabler/icons-react";

import type { Case, TurbineType } from "../../../api/types";
import { useFormat, useT } from "../../../i18n";
import { href } from "../../../router";
import { Spec } from "../../../ui/Fold";
import { Confirm, NumberField } from "../../../ui/Inputs";
import { domainName } from "../domains/grid";
import { farmGrid, metrics, powerDigits, typeUsage } from "./curve";
import { messages } from "./messages";
import { TurbineCurve } from "./TurbineCurve";

const FIELDS = [
  { key: "rated_power_mw", label: "rated", unit: "MW", min: 0.001 },
  { key: "rotor_diameter_m", label: "rotor", unit: "m", min: 0.001 },
  { key: "hub_height_m", label: "hub", unit: "m", min: 0.001 },
  { key: "standing_thrust_coefficient", label: "standing", unit: undefined, min: 0 },
] as const;

interface Props {
  caseId: string;
  draft: Case;
  number: number;
  model: TurbineType;
  /** Defined in the project (model 1 may show WRF's built-in table instead) */
  stored: boolean;
  edit: (change: (value: TurbineType) => void) => void;
  update: (change: (c: Case) => void) => void;
  onDuplicate: () => void;
  onDelete: () => void;
}

export function ModelRows({ caseId, draft, number, model, stored, edit, update, onDuplicate, onDelete }: Props) {
  const t = useT(messages);
  const f = useFormat();
  const used = typeUsage(draft).get(number) ?? [];
  const count = used.reduce((sum, row) => sum + row.count, 0);
  // Without its definition, model 1 in use falls back to WRF's built-in table
  const fallsBack = number === 1 && count > 0;
  const m = metrics(model);
  const grid = farmGrid(draft);
  const spacing = grid && model.rotor_diameter_m > 0 ? grid.dx / model.rotor_diameter_m : null;
  const remove = t(fallsBack ? "editor.restore" : "editor.delete");

  const tools = (
    <>
      <Tooltip label={t("editor.duplicate")}>
        <ActionIcon variant="default" aria-label={t("editor.duplicate")} onClick={onDuplicate}><IconCopy size={16} /></ActionIcon>
      </Tooltip>
      {stored && (
        <Confirm title={t(fallsBack ? "editor.restoreTitle" : "editor.deleteTitle", { n: number, name: model.name })} text={t(fallsBack ? "editor.restoreText" : "editor.deleteText")} onConfirm={onDelete}>
          {(open) => (
            <Tooltip label={count > 0 && !fallsBack ? t("editor.inUse", { count }) : remove}>
              <ActionIcon variant="default" c={fallsBack ? undefined : "red.6"} aria-label={remove} disabled={count > 0 && !fallsBack} onClick={open}>
                {fallsBack ? <IconRestore size={16} /> : <IconTrash size={16} />}
              </ActionIcon>
            </Tooltip>
          )}
        </Confirm>
      )}
    </>
  );

  return (
    <>
      <Spec
        label={t("editor.rated")}
        value={f.number(model.rated_power_mw, powerDigits(model.rated_power_mw))}
        unit="MW"
        detail={m.specificPower === null ? undefined : <span title={t("metrics.specificInfo")}>{t("rows.specific", { w: f.number(m.specificPower, 0) })}</span>}
        tools={tools}
      >
        <TextInput label={t("editor.name")} value={model.name} onChange={(event) => { const value = event.currentTarget.value; edit((item) => { item.name = value; }); }} />
        <SimpleGrid cols={{ base: 1, xs: 2, lg: 4 }} spacing="md" verticalSpacing="lg">
          {FIELDS.map((field) => (
            <NumberField key={field.key} label={t(`editor.${field.label}`)} info={t(`editor.${field.label}Info`)} unit={field.unit} min={field.min}
              value={model[field.key]} onValue={(value) => edit((item) => { item[field.key] = value; })} />
          ))}
        </SimpleGrid>
      </Spec>

      <Spec
        label={t("rows.farms")}
        value={count ? f.number(count, 0) : "–"}
        unit={count ? t("rows.turbines", { n: count }) : undefined}
        detail={spacing === null ? undefined : (
          <span className={spacing < 5 ? "ows-spec-bad" : undefined} title={`${t("metrics.gridHint", { dx: f.number(grid!.dx / 1000, 2), domain: domainName(grid!.domain - 1), min: 5 })} · ${t("metrics.gridInfo")}`}>
            {t("rows.spacing", { d: f.number(spacing, 1) })}
          </span>
        )}
      >
        {!draft.farms.length ? (
          <Group justify="space-between" wrap="wrap" gap="sm">
            <Text size="sm" c="dimmed">{t("use.ready")}</Text>
            <Button component="a" size="xs" variant="default" href={href(`projects/${encodeURIComponent(caseId)}/farms`)} rightSection={<IconArrowRight size={14} />}>{t("use.goFarms")}</Button>
          </Group>
        ) : (
          <Stack gap={0} className="ows-model-farms">
            {draft.farms.map((farm) => {
              const mine = farm.turbines.filter((tb) => tb.type === number).length;
              const all = farm.turbines.length > 0 && mine === farm.turbines.length;
              return (
                <Group key={farm.id} justify="space-between" wrap="nowrap" gap="sm" className="ows-model-farm">
                  <Text size="sm" fw={all ? 600 : 500} truncate>{farm.name}</Text>
                  <Group gap="sm" wrap="nowrap">
                    <Text size="sm" c="dimmed" className="ows-num">{`${f.number(mine, 0)} / ${f.number(farm.turbines.length, 0)}`}</Text>
                    {all ? <IconCheck size={16} color="var(--mantine-primary-color-filled)" aria-hidden="true" /> : farm.turbines.length > 0 && (
                      <Button size="compact-sm" variant="default" aria-label={t("use.label", { n: number, farm: farm.name })}
                        onClick={() => update((c) => { c.farms.find((item) => item.id === farm.id)?.turbines.forEach((tb) => { tb.type = number; }); })}>
                        {t("use.assign")}
                      </Button>
                    )}
                  </Group>
                </Group>
              );
            })}
          </Stack>
        )}
      </Spec>

      <TurbineCurve turbine={model} number={number} onChange={(patch) => edit((item) => Object.assign(item, patch))} />
    </>
  );
}
