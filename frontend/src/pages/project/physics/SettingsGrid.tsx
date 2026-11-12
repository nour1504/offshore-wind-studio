import { SimpleGrid } from "@mantine/core";
import { useNamelistSchema } from "../../../api/cases";
import type { Case, NamelistGroups } from "../../../api/types";
import { useT } from "../../../i18n";
import { ErrorState, LoadingState } from "../../../ui/States";
import { CHOICES, ChoiceEditor, sameEverywhere } from "./ChoiceEditor";
import type { ChoiceName } from "./managed";
import { messages } from "./messages";
import { OptionEditor } from "./OptionEditor";

/** The value WRF will read: a priority value of the editor, the project's, the generated one, WRF's default. */
export function settingValue(draft: Case, schema: ReturnType<typeof useNamelistSchema>["data"], g: "physics" | "dynamics", name: string, generated?: NamelistGroups) {
  return draft.namelist_input[g]?.[name] ?? draft[g][name] ?? generated?.[g]?.[name] ?? schema?.groups[g]?.[name]?.default;
}

/**
 * Named settings of the physics or of the flow dynamics, two by two: menus of named choices,
 * switches, or the detailed editor for numbers and options set differently per domain.
 */
export function SettingsGrid({ group, names, draft, update, generated, cols = 2 }: { group: "physics" | "dynamics"; names: readonly ChoiceName[]; draft: Case; update: (change: (c: Case) => void) => void; generated?: NamelistGroups; cols?: number }) {
  const t = useT(messages); const schema = useNamelistSchema();
  if (schema.isLoading) return <LoadingState />;
  if (schema.error) return <ErrorState error={schema.error} onRetry={() => void schema.refetch()} />;
  const domains = draft.grid.domains.length;
  return <SimpleGrid cols={{ base: 1, md: cols }} spacing={32} verticalSpacing={28}>{names.map((name) => {
    const optionSchema = schema.data?.groups[group]?.[name]; const forced = draft.namelist_input[group]?.[name]; const value = settingValue(draft, schema.data, group, name, generated);
    if (value === undefined) return null;
    if (name in CHOICES || typeof sameEverywhere(value, domains) === "boolean") return <ChoiceEditor key={name} name={name} label={t(`labels.${name}`)} info={optionSchema?.description} value={value} domains={domains} forced={forced !== undefined} onChange={(next) => update((c) => { c[group][name] = next; })} />;
    return <OptionEditor key={name} name={name} label={t(`labels.${name}`)} schema={optionSchema} domains={domains} value={value} onChange={(next) => update((c) => { c[group][name] = next; })} onReset={() => update((c) => { delete c[group][name]; })} />;
  })}</SimpleGrid>;
}
