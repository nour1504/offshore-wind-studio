import { Anchor, Badge, Button, Code, Group, Paper, Select, SimpleGrid, Stack, Table, Tabs, Text, TextInput } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { useQuery } from "@tanstack/react-query";
import { IconArrowLeft, IconArrowRight, IconBook, IconSearch } from "@tabler/icons-react";
import { useMemo, useState } from "react";

import { get } from "../api/client";
import { docsApi, useDocIndex, useDocPage } from "../api/docs";
import { sectionMessages } from "../app/sections";
import { defineMessages, useLang, useT } from "../i18n";
import { href, navigate, setParams, useRoute } from "../router";
import { Markdown } from "../ui/Markdown";
import { Page, Section } from "../ui/Page";
import { EmptyState, ErrorState, LoadingState } from "../ui/States";
import { GlideTabsList } from "../ui/GlideTabs";

const messages = defineMessages({
  en: {
    description: "Guides, methods and the complete reference shipped with the application.",
    guides: "User guide", options: "WRF namelist options", variables: "Output variables",
    search: "Search the documentation", back: "All topics", related: "Related topics",
    none: "No matching topic", group: "Namelist group", all: "All groups",
    parameter: "Parameter", meaning: "Meaning", unit: "Unit", default: "Default",
    dimensions: "Dimensions", type: "Type", name: "Name", history: "History output",
    yes: "Yes", no: "Add it in Outputs", source: "Reference source",
    reference: "Schema generated from the WRF 4.8 Registry and README.namelist. These options are edited in Physics and namelists.",
    fiche: "Variable documentation", choose: "Select a variable to read its documentation.",
  },
  fr: {
    description: "Guides, méthodes et référence complète embarqués dans l'application.",
    guides: "Guide d'utilisation", options: "Options des namelists WRF", variables: "Variables de sortie",
    search: "Rechercher dans la documentation", back: "Tous les sujets", related: "Sujets liés",
    none: "Aucun sujet correspondant", group: "Groupe de namelist", all: "Tous les groupes",
    parameter: "Paramètre", meaning: "Signification", unit: "Unité", default: "Valeur par défaut",
    dimensions: "Dimensions", type: "Type", name: "Nom", history: "Sortie historique",
    yes: "Oui", no: "À ajouter dans Sorties", source: "Source de référence",
    reference: "Schéma généré depuis le Registry et README.namelist de WRF 4.8. Ces options se modifient dans Physique et namelists.",
    fiche: "Documentation de la variable", choose: "Sélectionnez une variable pour consulter sa documentation.",
  },
});

interface Option { type: string; per_domain: boolean; dimension: string; default: unknown; description: string; units: string }
interface Variable { name: string; description: string; units: string; dims: string; history: boolean; type: string; stagger: string; use: string }

function NamelistReference({ search }: { search: string }) {
  const t = useT(messages);
  const [group, setGroup] = useState("");
  const schema = useQuery({ queryKey: ["namelist-schema"], queryFn: () => get<{ groups: Record<string, Record<string, Option>> }>("/api/namelist/schema"), staleTime: Infinity });
  const rows = useMemo(() => Object.entries(schema.data?.groups ?? {}).flatMap(([g, entries]) =>
    Object.entries(entries).map(([name, value]) => ({ g, name, ...value }))).filter(row =>
    (!group || row.g === group) && `${row.name} ${row.description}`.toLowerCase().includes(search.toLowerCase())), [schema.data, group, search]);
  if (schema.isLoading) return <LoadingState rows={6} />;
  if (schema.error) return <ErrorState error={schema.error} />;
  return <Section description={t("reference")}>
    <Select label={t("group")} value={group} onChange={v => setGroup(v ?? "")} mb="md" searchable data={[{ value: "", label: t("all") }, ...Object.keys(schema.data?.groups ?? {}).map(g => ({ value: g, label: `&${g}` }))]} />
    <Text size="sm" c="dimmed" mb="sm">{rows.length} {t("parameter").toLowerCase()}</Text>
    <Table.ScrollContainer minWidth={800}>
      <Table striped highlightOnHover>
        <Table.Thead><Table.Tr><Table.Th>{t("parameter")}</Table.Th><Table.Th>{t("meaning")}</Table.Th><Table.Th>{t("type")}</Table.Th><Table.Th>{t("default")}</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>{rows.map(row => <Table.Tr key={`${row.g}.${row.name}`}>
          <Table.Td><Code>{row.name}</Code><Text size="xs" c="dimmed">&{row.g}</Text></Table.Td>
          <Table.Td maw={560}>{row.description || "—"}{row.units && <Text size="xs" c="dimmed">{t("unit")}: {row.units}</Text>}</Table.Td>
          <Table.Td>{row.type}<Text size="xs" c="dimmed">{row.dimension}</Text></Table.Td>
          <Table.Td><Code>{JSON.stringify(row.default) ?? "—"}</Code></Table.Td>
        </Table.Tr>)}</Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  </Section>;
}

function VariableReference({ search }: { search: string }) {
  const t = useT(messages);
  const route = useRoute();
  const selected = route.params.get("variable");
  const variables = useQuery({ queryKey: ["help-variables", search], queryFn: () => get<Variable[]>("/api/variables", { q: search, limit: 500 }) });
  const fiche = useQuery({ queryKey: ["help-variable", selected], queryFn: () => get<{ registry?: Variable; diagnostic?: { label: string; method: string; requires?: string[] }; how_to_add?: string }>(`/api/variables/${encodeURIComponent(selected!)}`), enabled: Boolean(selected) });
  return <Stack>
    <Section>
      {variables.isLoading && <LoadingState rows={4} />}
      {variables.error && <ErrorState error={variables.error} />}
      <Table.ScrollContainer minWidth={620}><Table highlightOnHover>
        <Table.Thead><Table.Tr><Table.Th>{t("name")}</Table.Th><Table.Th>{t("meaning")}</Table.Th><Table.Th>{t("unit")}</Table.Th><Table.Th>{t("history")}</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>{variables.data?.map(v => <Table.Tr key={v.name}>
          <Table.Td><Button variant="subtle" size="compact-sm" onClick={() => setParams({ variable: v.name })}>{v.name}</Button></Table.Td>
          <Table.Td>{v.description}</Table.Td><Table.Td>{v.units}</Table.Td><Table.Td><Badge color={v.history ? "teal" : "gray"}>{t(v.history ? "yes" : "no")}</Badge></Table.Td>
        </Table.Tr>)}</Table.Tbody>
      </Table></Table.ScrollContainer>
    </Section>
    {selected && <Section title={`${t("fiche")} · ${selected}`}>
      {fiche.isLoading && <LoadingState rows={3} />}
      {fiche.error && <ErrorState error={fiche.error} />}
      {fiche.data && <Stack gap="xs">
        <Text>{fiche.data.registry?.description ?? fiche.data.diagnostic?.label}</Text>
        {fiche.data.registry && <Text size="sm">{t("unit")}: {fiche.data.registry.units} · {t("dimensions")}: {fiche.data.registry.dims} · {t("type")}: {fiche.data.registry.type}</Text>}
        <Text size="sm">{fiche.data.how_to_add ?? fiche.data.diagnostic?.method}</Text>
      </Stack>}
    </Section>}
  </Stack>;
}

export default function HelpPage() {
  const ts = useT(sectionMessages);
  const t = useT(messages);
  const { lang } = useLang();
  const route = useRoute();
  const topic = route.segments[1] ?? null;
  const tab = route.params.get("tab") ?? "guides";
  const [search, setSearch] = useState("");
  const [query] = useDebouncedValue(search, 200);
  const index = useDocIndex(lang);
  const page = useDocPage(topic, lang);
  const found = useQuery({ queryKey: ["doc-search", lang, query], queryFn: () => docsApi.search(query, lang), enabled: query.trim().length > 1 });
  const topics = query.trim().length > 1 ? found.data?.results ?? [] : index.data?.topics ?? [];
  return <Page title={ts("global.help")} help="getting-started">
    <TextInput leftSection={<IconSearch size={17} />} label={t("search")} value={search} onChange={e => setSearch(e.currentTarget.value)} />
    <Tabs value={tab} onChange={v => setParams({ tab: v ?? "guides" })}>
      <GlideTabsList mb="lg"><Tabs.Tab value="guides" leftSection={<IconBook size={16} />}>{t("guides")}</Tabs.Tab><Tabs.Tab value="options">{t("options")}</Tabs.Tab><Tabs.Tab value="variables">{t("variables")}</Tabs.Tab></GlideTabsList>
      <Tabs.Panel value="guides">
        {topic ? <Stack>
          <Button variant="subtle" w="fit-content" leftSection={<IconArrowLeft size={16} />} onClick={() => navigate("help")}>{t("back")}</Button>
          {page.isLoading && <LoadingState rows={6} />}{page.error && <ErrorState error={page.error} />}
          {page.data && <Section title={page.data.title} description={page.data.summary}>
            <Markdown text={page.data.markdown} />
            <Group mt="lg">{page.data.related.map(r => <Anchor key={r.id} href={href(`help/${r.id}`)}>{r.title}</Anchor>)}</Group>
          </Section>}
        </Stack> : <Stack>
          {(index.isLoading || found.isFetching) && <LoadingState rows={4} />}
          {(index.error || found.error) && <ErrorState error={index.error || found.error} />}
          {topics.length === 0 && !index.isLoading && <EmptyState icon={<IconSearch size={26} stroke={1.5} />} title={t("none")} />}
          {/* Grouped by subject, in the order of the guide; each whole card opens its page */}
          {[...new Set(topics.map(item => item.section))].map(section => <Stack key={section} gap="sm" mb="md">
            <Text size="xs" fw={600} c="dimmed" tt="uppercase" style={{ letterSpacing: 0.5 }}>{section}</Text>
            <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md" className="ows-help-list">{topics.filter(item => item.section === section).map(item => <Paper key={item.id} component="a" href={href(`help/${item.id}`)} withBorder p="lg" className="ows-choice ows-help-topic" style={{ color: "inherit", textDecoration: "none" }}>
              <Group justify="space-between" wrap="nowrap" align="flex-start" gap="sm"><Text fw={600}>{item.title}</Text><IconArrowRight size={16} style={{ flexShrink: 0, marginTop: 3, opacity: 0.5 }} /></Group>
              <Text size="sm" c="dimmed" mt={6}>{"excerpt" in item ? item.excerpt : item.summary}</Text>
            </Paper>)}</SimpleGrid>
          </Stack>)}
        </Stack>}
      </Tabs.Panel>
      <Tabs.Panel value="options"><NamelistReference search={query} /></Tabs.Panel>
      <Tabs.Panel value="variables"><VariableReference search={query} /></Tabs.Panel>
    </Tabs>
  </Page>;
}
