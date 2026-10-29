import { ActionIcon, Group, Stack, Text } from "@mantine/core";
import { IconX } from "@tabler/icons-react";
import { useState } from "react";

import type { Outputs } from "../../../api/types";
import { useLang, useT } from "../../../i18n";
import { FieldLabel } from "../../../ui/Inputs";
import { type PickerItem, SearchPicker } from "../../../ui/SearchPicker";
import { messages } from "./messages";
import { hasName, REGISTRY_NAME } from "./rules";
import { fold, plainDescription, unitOf, useNamedVariables, useVariableSearch, variableNames, type WrfVariable } from "./variables";

// Proposed before anything is typed: what wind studies add, and the heavy fields studies drop
const SUGGESTED = {
  add: ["RMOL", "ZNT", "UST", "HFX", "LH", "QFX", "PBLH", "TKE_PBL", "QKE", "POWER", "RUBLTEN", "RVBLTEN"],
  remove: ["QCLOUD", "QRAIN", "QICE", "QSNOW", "QGRAUP", "CLDFRA", "REFL_10CM"],
} as const;

/**
 * One list of variables of the full maps (to add or to remove): a search proposing WRF's
 * variables by their plain name, code and unit, and the variables already chosen.
 */
export function VariableList({ kind, outputs, onChange }: { kind: "add" | "remove"; outputs: Outputs; onChange: (values: string[], other: string[]) => void }) {
  const t = useT(messages); const { lang } = useLang();
  const [search, setSearch] = useState("");
  const found = useVariableSearch(search); const named = useNamedVariables(); const listed = useNamedVariables(outputs[kind]);
  const plain = (variable: Pick<WrfVariable, "name" | "description">) => (variableNames[lang] as Record<string, string>)[variable.name.toUpperCase()] ?? plainDescription(variable.description);
  const hint = (name: string) => kind === "add" ? (messages[lang].history.vars as Record<string, string>)[name] : undefined;
  const known = new Map([...(named.data ?? []), ...(listed.data ?? []), ...(found.data ?? [])].map((variable) => [variable.name.toUpperCase(), variable]));
  const chosen = outputs[kind];
  const text = fold(search.trim());
  const typed = search.trim();
  const entries = (text
    ? [...(named.data ?? []).filter((variable) => fold(variable.name).startsWith(text) || fold(plain(variable)).includes(text)), ...(found.data ?? [])]
    : SUGGESTED[kind].map((name) => known.get(name)).filter((variable): variable is WrfVariable => Boolean(variable)))
    .filter((variable, index, all) => all.findIndex((other) => other.name === variable.name) === index && !hasName(chosen, variable.name))
    .slice(0, 40);
  const free = typed && REGISTRY_NAME.test(typed) && !known.has(typed.toUpperCase()) && !hasName(chosen, typed) && !found.isFetching;
  const items: PickerItem[] = entries.map((variable) => ({
    value: variable.name,
    title: plain(variable),
    code: variable.name,
    detail: hint(variable.name) ?? (variable.history ? t("history.written") : t("history.notWritten")),
    aside: <><Text size="xs" c="dimmed">{variable.dims.includes("k") ? t("history.levels") : t("history.surface")}</Text>{unitOf(variable) && <Text size="xs" className="ows-unit">{unitOf(variable)}</Text>}</>,
  }));
  if (free) items.push({ value: typed, title: t("history.free", { name: typed }), code: typed, detail: t("history.freeDetail") });
  const add = (name: string) => {
    const unique = [...chosen.filter((value) => !hasName([name], value)), name];
    onChange(unique, outputs[kind === "add" ? "remove" : "add"].filter((value) => !hasName([name], value)));
    setSearch("");
  };
  return <Stack gap="sm">
    <Text size="sm" fw={600}><FieldLabel label={t(`history.${kind}`)} info={t(`history.${kind}Info`)} /></Text>
    <SearchPicker
      aria-label={t(`history.${kind}`)}
      placeholder={t(kind === "add" ? "history.addPlaceholder" : "history.removePlaceholder")}
      search={search}
      onSearch={setSearch}
      items={items}
      heading={text ? undefined : t(kind === "add" ? "history.suggestedAdd" : "history.suggestedRemove")}
      loading={found.isFetching}
      empty={t("history.noMatch")}
      onPick={add}
      onEnter={(value) => { if (REGISTRY_NAME.test(value)) add(known.get(value.toUpperCase())?.name ?? value); }}
    />
    {chosen.length === 0 ? <Text size="sm" c="dimmed">{t(kind === "add" ? "history.emptyAdd" : "history.emptyRemove")}</Text> : <Stack gap={0} className="ows-variable-list">
      {chosen.map((name) => {
        const variable = known.get(name.toUpperCase());
        return <Group key={name} justify="space-between" wrap="nowrap" gap="sm" className="ows-variable-row">
          <Group gap="sm" wrap="nowrap" style={{ minWidth: 0 }}>
            <Text size="xs" ff="monospace" className="ows-picker-code">{name}</Text>
            <Text size="sm" lineClamp={1}>{variable ? plain(variable) : ""}</Text>
          </Group>
          <Group gap={6} wrap="nowrap" style={{ flexShrink: 0 }}>
            {variable && unitOf(variable) && <Text size="xs" className="ows-unit">{unitOf(variable)}</Text>}
            <ActionIcon variant="subtle" color="gray" size="sm" aria-label={t("history.removeName", { name })} onClick={() => onChange(chosen.filter((value) => value !== name), outputs[kind === "add" ? "remove" : "add"])}><IconX size={14} /></ActionIcon>
          </Group>
        </Group>;
      })}
    </Stack>}
  </Stack>;
}
