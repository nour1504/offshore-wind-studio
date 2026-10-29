import { Accordion, Anchor, Group, SimpleGrid, Stack, Tabs, Text } from "@mantine/core";
import { IconPlus } from "@tabler/icons-react";
import { type ReactNode, useState } from "react";
import { useNamelistSchema } from "../../../api/cases";
import type { Case, NamelistFile, NamelistValue, OptionSchema, StructuredNamelists } from "../../../api/types";
import { sectionMessages } from "../../../app/sections";
import { useT } from "../../../i18n";
import { href } from "../../../router";
import { GlideTabsList } from "../../../ui/GlideTabs";
import { ErrorState, LoadingState } from "../../../ui/States";
import { AddOption } from "./AddOption";
import { ChoiceValue } from "./ChoiceEditor";
import { DYNAMICS, managedBy, PHYSICS } from "./managed";
import { messages } from "./messages";
import { OptionEditor } from "./OptionEditor";
import { SettingsGrid, settingValue } from "./SettingsGrid";

// The groups a wind study meets first, then the others in alphabetical order
const ORDER = ["time_control", "domains", "physics", "dynamics", "bdy_control", "share", "geogrid", "ungrib", "metgrid"];
// The physics block opens on these topics, with named choices
const TOPICS = [
  { id: "turbulence", summary: "bl_pbl_physics", options: ["bl_pbl_physics", "sf_sfclay_physics", "bl_mynn_tkeadvect"] },
  { id: "clouds", summary: "mp_physics", options: ["mp_physics", "cu_physics"] },
  { id: "radiation", summary: "ra_lw_physics", options: ["ra_lw_physics", "ra_sw_physics", "radt"] },
  { id: "ground", summary: "sf_surface_physics", options: ["sf_surface_physics"] },
] as const;
const ROW = { control: { paddingBlock: 18 }, content: { paddingTop: 4, paddingBottom: 24 } };

type Structured = { data?: StructuredNamelists; error: unknown; isLoading: boolean; refetch: () => unknown };

/**
 * namelist.input or namelist.wps, block by block (&physics, &dynamics…), every block folded at
 * first. Physics and dynamics open on their named settings; the other blocks list the options
 * the project sets. "Add an option" at the bottom adds any other documented option.
 */
export function NamelistEditor({ caseId, draft, update, structured }: { caseId: string; draft: Case; update: (change: (c: Case) => void) => void; structured: Structured }) {
  const t = useT(messages); const ts = useT(sectionMessages); const schema = useNamelistSchema();
  const [file, setFile] = useState<NamelistFile>("namelist.input");
  const key = file === "namelist.input" ? "namelist_input" : "namelist_wps";
  const input = file === "namelist.input";
  const content = structured.data?.[file];
  const generated = structured.data?.["namelist.input"].generated;
  const docs: Record<string, Record<string, OptionSchema>> = input ? schema.data?.groups ?? {} : {};
  const order = (a: string, b: string) => (ORDER.indexOf(a) + 1 || 99) - (ORDER.indexOf(b) + 1 || 99) || a.localeCompare(b);
  const groupLabel = (g: string) => /^wrfvar/.test(g) ? `${t("assimilation")} ${g.slice(6)}` : (messages.en.groups as Record<string, string>)[g] ? t(`groups.${g}` as never) : `&${g}`;
  const override = (g: string, name: string, value: NamelistValue | undefined) => update((c) => { if (value === undefined) { delete c[key][g]?.[name]; if (c[key][g] && !Object.keys(c[key][g]).length) delete c[key][g]; } else c[key][g] = { ...c[key][g], [name]: value }; });
  const inProject = (g: string, name: string) => content?.generated[g]?.[name] !== undefined || name in (draft[key][g] ?? {});
  const projectOptions = (g: string) => [...new Set([...Object.keys(content?.generated[g] ?? {}), ...Object.keys(draft[key][g] ?? {})])].sort();
  const groups = [...new Set([...Object.keys(content?.generated ?? {}), ...Object.keys(draft[key]), ...(input ? ["physics", "dynamics"] : [])])].filter((g) => (input && (g === "physics" || g === "dynamics")) || projectOptions(g).length > 0).sort(order);
  const allGroups = [...new Set([...groups, ...Object.keys(docs)])].sort(order);
  const domains = draft.grid.domains.length;

  const options = (group: string, names: string[]) => names.length > 0 && <SimpleGrid cols={{ base: 1, md: 2 }} spacing={32} verticalSpacing={28}>{names.map((name) => {
    const owner = managedBy(file, group, name); const optionSchema = docs[group]?.[name];
    const value = (owner ? content?.final[group.toLowerCase()]?.[name.toLowerCase()] : draft[key][group]?.[name] ?? content?.final[group]?.[name]) ?? optionSchema?.default ?? "";
    return <OptionEditor key={`${file}.${group}.${name}`} name={name} value={value} schema={optionSchema} domains={domains} overridden={name in (draft[key][group] ?? {})}
      managedBy={owner === null || owner === "above" ? undefined : <Anchor size="xs" href={href(`projects/${encodeURIComponent(caseId)}/${owner}`)}>{t("managedBy", { page: ts(`project.${owner}`) })}</Anchor>}
      onChange={(next) => override(group, name, next)} onReset={() => override(group, name, undefined)} />;
  })}</SimpleGrid>;
  const sub = (items: { id: string; title: string; aside?: ReactNode; body: ReactNode }[]) => <Accordion multiple variant="default" className="ows-namelist-sub" styles={ROW}>{items.map((item) => <Accordion.Item key={item.id} value={item.id}>
    <Accordion.Control><Group justify="space-between" gap="sm" pr="sm" wrap="nowrap"><Text fw={500} size="sm">{item.title}</Text>{item.aside}</Group></Accordion.Control>
    <Accordion.Panel>{item.body}</Accordion.Panel>
  </Accordion.Item>)}</Accordion>;
  const restItem = (group: string, rest: string[]) => rest.length ? [{ id: "other", title: t("otherOptions"), aside: <Text size="sm" c="dimmed">{t("optionCount", { n: rest.length })}</Text>, body: options(group, rest) }] : [];
  const blockBody = (group: string) => {
    const names = projectOptions(group);
    if (input && group === "physics") {
      return sub([
        ...TOPICS.map((topic) => { const summary = settingValue(draft, schema.data, "physics", topic.summary, generated); return { id: topic.id, title: t(`topics.${topic.id}.title`), aside: summary !== undefined ? <ChoiceValue name={topic.summary} value={summary} domains={domains} /> : undefined, body: <SettingsGrid group="physics" names={topic.options} draft={draft} update={update} generated={generated} /> }; }),
        ...restItem(group, names.filter((name) => !(PHYSICS as readonly string[]).includes(name))),
      ]);
    }
    if (input && group === "dynamics") {
      return sub([
        { id: "main", title: t("dynamicsMain"), body: <SettingsGrid group="dynamics" names={DYNAMICS} draft={draft} update={update} generated={generated} /> },
        ...restItem(group, names.filter((name) => !(DYNAMICS as readonly string[]).includes(name))),
      ]);
    }
    return options(group, names);
  };

  return <Stack gap={24} maw={1040}>
    <Tabs value={file} onChange={(value) => setFile(value as NamelistFile)}><GlideTabsList><Tabs.Tab value="namelist.input">namelist.input</Tabs.Tab><Tabs.Tab value="namelist.wps">namelist.wps</Tabs.Tab></GlideTabsList></Tabs>
    {structured.error ? <ErrorState error={structured.error} onRetry={() => void structured.refetch()} /> : structured.isLoading || schema.isLoading ? <LoadingState /> :
      <Accordion key={file} multiple variant="default" className="ows-namelist-groups" styles={ROW}>
        {groups.map((group) => <Accordion.Item key={group} value={group}>
          <Accordion.Control><Group justify="space-between" gap="sm" pr="sm" wrap="nowrap"><Group gap="sm" wrap="nowrap" style={{ minWidth: 0 }}><Text fw={600} truncate>{groupLabel(group)}</Text>{groupLabel(group) !== `&${group}` && <Text size="xs" ff="monospace" c="dimmed">&{group}</Text>}</Group><Text size="sm" c="dimmed" style={{ flexShrink: 0 }}>{t("optionCount", { n: projectOptions(group).length })}</Text></Group></Accordion.Control>
          <Accordion.Panel>{blockBody(group)}</Accordion.Panel>
        </Accordion.Item>)}
        <Accordion.Item value="add">
          <Accordion.Control icon={<IconPlus size={16} />}><Text fw={600}>{t("add")}</Text></Accordion.Control>
          <Accordion.Panel><AddOption file={file} caseId={caseId} groups={allGroups} groupLabel={groupLabel} docs={docs} isSet={inProject} domains={domains} onAdd={override} /></Accordion.Panel>
        </Accordion.Item>
      </Accordion>}
  </Stack>;
}
