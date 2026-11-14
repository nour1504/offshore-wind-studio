/**
 * The turbine models of the project, one section each: closed, its name with its power and rotor;
 * open, its rows (ModelRows). A model added from the catalogue or created opens at once.
 */
import { Button, Stack, Text } from "@mantine/core";
import { IconPropeller } from "@tabler/icons-react";
import { useState } from "react";

import { useBuiltInTurbine, useTurbineCatalog } from "../../api/turbines";
import type { TurbineType } from "../../api/types";
import { useLoadedDraft } from "../../app/CaseDraft";
import { sectionMessages } from "../../app/sections";
import { useFormat, useT } from "../../i18n";
import { Fold } from "../../ui/Fold";
import { Page } from "../../ui/Page";
import { EmptyState, LoadingState } from "../../ui/States";
import { CatalogPicker } from "./turbines/CatalogPicker";
import { blankTurbine, nextTypeNumber, powerDigits, typeUsage } from "./turbines/curve";
import { messages } from "./turbines/messages";
import { ModelRows } from "./turbines/ModelRows";

export default function TurbinesPage() {
  const t = useT(messages);
  const ts = useT(sectionMessages);
  const f = useFormat();
  const { caseId, draft, update } = useLoadedDraft();
  const catalog = useTurbineCatalog();
  const builtIn = useBuiltInTurbine();
  const [opened, setOpened] = useState<Set<number>>(new Set());
  const [catalogOpen, setCatalogOpen] = useState(false);
  const usage = typeUsage(draft);
  const keys = [...new Set([...Object.keys(draft.turbine_types).map(Number), ...usage.keys()])].sort((a, b) => a - b);
  const show = (key: number, open: boolean) => setOpened((now) => {
    const next = new Set(now);
    if (open) next.add(key);
    else next.delete(key);
    return next;
  });
  const add = (value: TurbineType, explicit?: number) => {
    const n = explicit ?? nextTypeNumber(draft);
    update((c) => { c.turbine_types[String(n)] = structuredClone(value); });
    show(n, true);
    setCatalogOpen(false);
  };
  // Model 1 without its own definition is WRF's built-in turbine: shown like any model, and
  // copied into the project on its first change
  const edit = (key: number) => (change: (value: TurbineType) => void) => update((c) => {
    const id = String(key);
    if (!c.turbine_types[id] && key === 1 && builtIn.data?.turbine) c.turbine_types[id] = structuredClone(builtIn.data.turbine);
    const value = c.turbine_types[id];
    if (value) change(value);
  });

  return (
    <Page
      title={ts("project.turbines")}
      help="turbines"
      fluid
      actions={<>
        <Button variant="light" onClick={() => setCatalogOpen(true)}>{t("addCatalog")}</Button>
        <Button onClick={() => { const n = nextTypeNumber(draft); add(blankTurbine(t("blankName", { n })), n); }}>{t("addBlank")}</Button>
      </>}
    >
      {!keys.length ? (
        <EmptyState icon={<IconPropeller size={26} stroke={1.5} />} title={t("list.emptyTitle")}>{t("list.emptyText")}</EmptyState>
      ) : keys.map((key) => {
        const stored = draft.turbine_types[String(key)];
        const model = stored ?? (key === 1 ? builtIn.data?.turbine : undefined);
        const count = (usage.get(key) ?? []).reduce((sum, row) => sum + row.count, 0);
        const name = model ? model.name || t("unnamed") : t(key === 1 ? "builtIn.fallbackName" : "list.notDefined");
        return (
          <Fold
            key={key}
            title={`${t("typeN", { n: key })} · ${name}`}
            aside={model ? `${f.number(model.rated_power_mw, powerDigits(model.rated_power_mw))} MW · ${f.number(model.rotor_diameter_m, 0)} m` : undefined}
            open={opened.has(key)}
            onOpenChange={(open) => show(key, open)}
            lazy
          >
            {model ? (
              <ModelRows
                caseId={caseId}
                draft={draft}
                number={key}
                model={model}
                stored={Boolean(stored)}
                edit={edit(key)}
                update={update}
                onDuplicate={() => add({ ...structuredClone(model), name: t("copyName", { name: model.name }) })}
                onDelete={() => update((c) => { delete c.turbine_types[String(key)]; })}
              />
            ) : key === 1 ? <LoadingState rows={4} /> : (
              // A model used by turbines but defined nowhere
              <Stack gap="sm" align="flex-start">
                <Text size="sm">{t("missing.text", { n: key, count })}</Text>
                <Button size="xs" variant="default" onClick={() => add(blankTurbine(t("blankName", { n: key })), key)}>{t("missing.blank")}</Button>
              </Stack>
            )}
          </Fold>
        );
      })}
      <CatalogPicker opened={catalogOpen} onClose={() => setCatalogOpen(false)} catalog={catalog} onPick={(entry) => add(entry.turbine)} />
    </Page>
  );
}
