import { Anchor, Button, Group, Select, SimpleGrid, Stack, Text } from "@mantine/core";
import { IconPlus } from "@tabler/icons-react";
import { useState } from "react";
import type { NamelistFile, NamelistValue, OptionSchema, Scalar } from "../../../api/types";
import { type ProjectSection, sectionMessages } from "../../../app/sections";
import { useT } from "../../../i18n";
import { href } from "../../../router";
import { type PickerItem, SearchPicker } from "../../../ui/SearchPicker";
import { fold } from "../outputs/variables";
import { managedBy } from "./managed";
import { messages } from "./messages";
import { NamelistField } from "./OptionEditor";
import { cleanDescription, formatNamelistValue } from "./values";

const NAME = /^[a-z][a-z0-9_]*$/i;

/**
 * Adds an option the project does not set yet: a group chosen in a list, the option found from
 * its first letters (or its role), then a value field suited to its type.
 */
export function AddOption({ file, caseId, groups, groupLabel, docs, isSet, domains, onAdd }: { file: NamelistFile; caseId: string; groups: string[]; groupLabel: (group: string) => string; docs: Record<string, Record<string, OptionSchema>>; isSet: (group: string, name: string) => boolean; domains: number; onAdd: (group: string, name: string, value: NamelistValue) => void }) {
  const t = useT(messages); const ts = useT(sectionMessages);
  const [group, setGroup] = useState<string | null>(file === "namelist.input" ? "physics" : groups[0] ?? null);
  const [search, setSearch] = useState("");
  const [name, setName] = useState<string | null>(null);
  const [value, setValue] = useState<Scalar | null>(null);
  const options = group ? docs[group] ?? {} : {};
  const schema = name ? options[name] : undefined;
  const text = fold(search.trim());
  // Only options the project does not set yet
  const matches = Object.entries(options)
    .filter(([option]) => !isSet(group ?? "", option))
    .filter(([option, entry]) => !text || fold(option).includes(text) || fold(entry.description).includes(text))
    .sort(([a], [b]) => Number(!fold(a).startsWith(text)) - Number(!fold(b).startsWith(text)) || a.localeCompare(b))
    .slice(0, 60);
  const items: PickerItem[] = matches.map(([option, entry]) => ({
    value: option,
    title: cleanDescription(entry.description) || option,
    code: option,
    detail: entry.units || undefined,
  }));
  const typed = search.trim();
  if (typed && NAME.test(typed) && !(typed.toLowerCase() in options) && !isSet(group ?? "", typed.toLowerCase())) items.push({ value: typed.toLowerCase(), title: t("customName", { name: typed.toLowerCase() }), code: typed.toLowerCase(), detail: t("customDetail") });
  const choose = (option: string) => {
    setName(option); setSearch(option);
    const entry = options[option];
    setValue(entry ? entry.default ?? null : null);
  };
  const owner: ProjectSection | "above" | null = group && name ? managedBy(file, group, name) : null;
  const ready = group && name && NAME.test(name) && value !== null && value !== "" && !owner;
  const add = () => {
    if (!ready || value === null) return;
    // An option per domain gets the same value on every domain, editable domain by domain afterwards
    onAdd(group, name, schema?.per_domain && domains > 0 ? Array.from({ length: domains }, () => value) : value);
    setName(null); setSearch(""); setValue(null);
  };
  return <Stack gap="md" className="ows-add-option">
    <SimpleGrid cols={{ base: 1, md: 3 }} spacing="lg">
      <Select label={t("addGroup")} data={groups.map((g) => ({ value: g, label: groupLabel(g) === `&${g}` ? `&${g}` : `${groupLabel(g)} · &${g}` }))} value={group} allowDeselect={false} searchable onChange={(next) => { setGroup(next); setName(null); setSearch(""); setValue(null); }} />
      <SearchPicker label={t("addName")} placeholder={t("addNamePlaceholder")} search={search} onSearch={(next) => { setSearch(next); if (next !== name) setName(null); }} items={items} onPick={choose} empty={t("empty")} onEnter={(next) => { if (NAME.test(next)) choose(next.toLowerCase()); }} />
      {name && !owner
        ? <NamelistField key={`${group}.${name}`} name={name} schema={schema} label={t("addValue")} value={value} onChange={setValue} />
        : <Stack gap={4}><Text size="sm" fw={500}>{t("addValue")}</Text><Text size="sm" c="dimmed" pt={6}>{owner ? (owner === "above" ? t("managedAbove") : <Anchor size="sm" href={href(`projects/${encodeURIComponent(caseId)}/${owner}`)}>{t("managedAdd", { page: ts(`project.${owner}`) })}</Anchor>) : "—"}</Text></Stack>}
    </SimpleGrid>
    {name && <Group justify="space-between" align="flex-start" gap="lg" wrap="nowrap">
      <Stack gap={2} style={{ minWidth: 0 }}>
        <Text size="sm" c="dimmed">{schema ? cleanDescription(schema.description) : t("customDetail")}</Text>
        {schema && <Text size="xs" c="dimmed">{t("wrfDefault", { value: formatNamelistValue(schema.default) })}{schema.per_domain && domains > 1 ? ` · ${t("sameAllDomains")}` : ""}</Text>}
      </Stack>
      <Button leftSection={<IconPlus size={15} />} disabled={!ready} onClick={add} style={{ flexShrink: 0 }}>{t("addButton")}</Button>
    </Group>}
  </Stack>;
}
