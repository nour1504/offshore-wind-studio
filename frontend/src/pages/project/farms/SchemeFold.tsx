/**
 * The farm scheme of WRF, in two columns: the scheme in large type with the grid spacing in rotor
 * diameters on the left; on the right the choice, the domains where it runs and its settings.
 */
import { Alert, Button, Group, SegmentedControl, SimpleGrid, Select, Stack, Switch, Text, Tooltip } from "@mantine/core";

import type { Case, FarmScheme } from "../../../api/types";
import { useFormat, useT } from "../../../i18n";
import { Fold } from "../../../ui/Fold";
import { FieldLabel, NumberField } from "../../../ui/Inputs";
import { glossary } from "../../../ui/Term";
import { domainDx, domainName } from "../domains/grid";
import { farmMessages } from "./messages";
import { newScheme, type TypeInfo, valueForDomain } from "./model";

export function SchemeFold({ draft, types, update }: { draft: Case; types: Map<number, TypeInfo>; update: (change: (c: Case) => void) => void }) {
  const t = useT(farmMessages);
  const tg = useT(glossary);
  const f = useFormat();
  const scheme = draft.farm_scheme;
  const setScheme = (change: (value: FarmScheme) => void) => update((c) => { if (c.farm_scheme) change(c.farm_scheme); });
  // Grid spacing of the scheme's domains in diameters of the largest rotor simulated (README.windturbine)
  const rotor = Math.max(0, ...draft.farms.filter((item) => item.enabled).flatMap((item) => item.turbines.map((tb) => types.get(tb.type)?.rotorM ?? 0)));
  const spacing = domainDx(draft.grid);
  const cells = scheme && rotor > 0 ? scheme.domains.filter((n) => n >= 1 && n <= spacing.length).map((n) => `${domainName(n - 1)} · ${f.number(spacing[n - 1] / rotor, 1)} D`) : [];
  const name = scheme?.scheme === "fitch" ? "Fitch" : scheme?.scheme === "mav" ? "MAV" : t("scheme.none");
  const choice = (value: "fitch" | "mav", word: string) => ({ value, label: <Tooltip label={tg(`defs.${value}`)} maw={300} multiline openDelay={300}><span>{word}</span></Tooltip> });
  const pbl = scheme?.domains.filter((domain) => Number(valueForDomain(draft.physics.bl_pbl_physics, domain)) !== 5) ?? [];

  return (
    <Fold title={t("page.scheme")} value={name} detail={cells.length ? cells.join("   ") : undefined}>
      <SegmentedControl fullWidth maw={420} aria-label={t("page.scheme")} value={scheme?.scheme ?? "none"}
        data={[{ value: "none", label: t("scheme.none") }, choice("fitch", "Fitch"), choice("mav", "MAV")]}
        onChange={(value) => update((c) => { c.farm_scheme = value === "none" ? null : newScheme(value as "fitch" | "mav", c, c.farm_scheme); })} />
      {!scheme ? <Text size="sm" c="dimmed">{t("scheme.noneText")}</Text> : <>
        <Stack gap={6}>
          <Text size="sm" fw={500}><FieldLabel label={t("scheme.domains")} info={t("scheme.domainsInfo")} /></Text>
          <Group gap={6} role="group" aria-label={t("scheme.domains")}>
            {draft.grid.domains.map((_, index) => {
              const on = scheme.domains.includes(index + 1);
              return <Button key={index} size="xs" miw={64} variant={on ? "light" : "default"} aria-pressed={on} className="ows-num"
                onClick={() => setScheme((s) => { s.domains = on ? s.domains.filter((n) => n !== index + 1) : [...s.domains, index + 1].sort((a, b) => a - b); })}>{domainName(index)}</Button>;
            })}
          </Group>
          {!scheme.domains.length && <Text size="xs" c="red">{t("scheme.noDomain")}</Text>}
        </Stack>
        {pbl.length > 0 && <Alert color="orange" variant="light">{t("scheme.pblMissing", { domains: pbl.map((domain) => domainName(domain - 1)).join(", "), value: String(draft.physics.bl_pbl_physics ?? t("scheme.pblUnset")) })}</Alert>}
        <SimpleGrid cols={{ base: 1, sm: scheme.scheme === "mav" ? 3 : 2 }} spacing="lg" className="ows-scheme-settings">
          <NumberField label={t("scheme.tke")} info={t("scheme.tkeInfo")} min={0} value={scheme.tke_factor} onValue={(value) => setScheme((s) => { s.tke_factor = value; })} />
          {scheme.scheme === "fitch" ? (
            <Stack gap={6}>
              <Text size="sm" fw={500}><FieldLabel label={t("scheme.induction")} info={t("scheme.inductionInfo")} /></Text>
              <Switch size="md" aria-label={t("scheme.induction")} checked={scheme.induction} onChange={(event) => { const value = event.currentTarget.checked; setScheme((s) => { s.induction = value; }); }} />
            </Stack>
          ) : <>
            <Select label={<FieldLabel label={t("scheme.wakeModel")} info={t("scheme.wakeModelInfo")} />} value={String(scheme.wake_model)} allowDeselect={false} data={([1, 2, 3, 4, 5] as const).map((value) => ({ value: String(value), label: `${value} · ${t(`scheme.wake.${value}`)}` }))} onChange={(value) => setScheme((s) => { s.wake_model = Number(value) as FarmScheme["wake_model"]; })} />
            <Select label={<FieldLabel label={t("scheme.overlap")} info={t("scheme.overlapInfo")} />} disabled={scheme.wake_model === 3} description={scheme.wake_model === 3 ? t("scheme.overlapGm") : undefined} inputWrapperOrder={["label", "input", "description", "error"]} value={String(scheme.overlap_method)} allowDeselect={false} data={([1, 2, 3, 4] as const).map((value) => ({ value: String(value), label: `${value} · ${t(`scheme.overlapMethod.${value}`)}` }))} onChange={(value) => setScheme((s) => { s.overlap_method = Number(value) as FarmScheme["overlap_method"]; })} />
          </>}
        </SimpleGrid>
      </>}
    </Fold>
  );
}
