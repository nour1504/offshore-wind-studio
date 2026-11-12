import { Anchor, Button, Code, Group, Paper, Select, SimpleGrid, Stack, Table, Tabs, Text, TextInput } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { useQuery } from "@tanstack/react-query";
import { IconArrowLeft, IconArrowRight, IconBook, IconSearch } from "@tabler/icons-react";
import { type RefObject, useEffect, useMemo, useRef, useState } from "react";

import { useNamelistSchema } from "../api/cases";
import { get } from "../api/client";
import { docsApi, useDocIndex, useDocPage } from "../api/docs";
import { sectionMessages } from "../app/sections";
import { defineMessages, useLang, useT } from "../i18n";
import { prefersReducedMotion } from "../motion";
import { href, navigate, setParams, useRoute } from "../router";
import { Markdown } from "../ui/Markdown";
import { useRowsAsScrolled } from "../ui/rows";
import { Page, Section } from "../ui/Page";
import { EmptyState, ErrorState, LoadingState } from "../ui/States";
import { useFlip } from "../ui/flip";
import { useVanish } from "../ui/vanish";
import { GlideTabsList } from "../ui/GlideTabs";

const messages = defineMessages({
  en: {
    guides: "User guide", options: "WRF namelist options", variables: "Output variables",
    search: "Search the documentation", back: "All topics", contents: "Contents",
    none: "No matching topic", group: "Namelist group", all: "All groups",
    parameter: "Parameter", meaning: "Meaning", unit: "Unit", default: "Default",
    type: "Type", name: "Name", history: "History output",
    yes: "Yes", no: "Add it in Outputs",
    fiche: "Variable documentation",
    count: "{n|# parameter|# parameters}", unitIs: "Unit: {unit}", registry: "Unit: {unit} · Dimensions: {dims} · Type: {type}",
  },
  fr: {
    guides: "Guide d'utilisation", options: "Options des namelists WRF", variables: "Variables de sortie",
    search: "Rechercher dans la documentation", back: "Tous les sujets", contents: "Sommaire",
    none: "Aucun sujet correspondant", group: "Groupe de namelist", all: "Tous les groupes",
    parameter: "Paramètre", meaning: "Signification", unit: "Unité", default: "Valeur par défaut",
    type: "Type", name: "Nom", history: "Sortie historique",
    yes: "Oui", no: "À ajouter dans Sorties",
    fiche: "Documentation de la variable",
    count: "{n|# paramètre|# paramètres}", unitIs: "Unité : {unit}", registry: "Unité : {unit} · Dimensions : {dims} · Type : {type}",
  },
});

interface Variable { name: string; description: string; units: string; dims: string; history: boolean; type: string; stagger: string; use: string }

function NamelistReference({ search }: { search: string }) {
  const t = useT(messages);
  const [group, setGroup] = useState("");
  const schema = useNamelistSchema();
  const rows = useMemo(() => Object.entries(schema.data?.groups ?? {}).flatMap(([g, entries]) =>
    Object.entries(entries).map(([name, value]) => ({ g, name, ...value }))).filter(row =>
    (!group || row.g === group) && `${row.name} ${row.description}`.toLowerCase().includes(search.toLowerCase())), [schema.data, group, search]);
  // Filtered: the entries kept slide to their new places, the others come out of a scatter
  const body = useRef<HTMLTableSectionElement>(null);
  useFlip(body, rows);
  const { shown, end } = useRowsAsScrolled(rows.length);
  if (schema.isLoading) return <LoadingState rows={6} />;
  if (schema.error) return <ErrorState error={schema.error} />;
  return <Section>
    <Select label={t("group")} value={group} onChange={v => setGroup(v ?? "")} mb="md" searchable data={[{ value: "", label: t("all") }, ...Object.keys(schema.data?.groups ?? {}).map(g => ({ value: g, label: `&${g}` }))]} />
    <Text size="sm" c="dimmed" mb="sm">{t("count", { n: rows.length })}</Text>
    <Table.ScrollContainer minWidth={800}>
      <Table striped highlightOnHover>
        <Table.Thead><Table.Tr><Table.Th>{t("parameter")}</Table.Th><Table.Th>{t("meaning")}</Table.Th><Table.Th>{t("type")}</Table.Th><Table.Th>{t("default")}</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody ref={body}>{rows.slice(0, shown).map(row => <Table.Tr key={`${row.g}.${row.name}`} data-flip={`${row.g}.${row.name}`}>
          <Table.Td><Code>{row.name}</Code><Text size="xs" c="dimmed">&{row.g}</Text></Table.Td>
          <Table.Td maw={560}>{row.description || "—"}{row.units && <Text size="xs" c="dimmed">{t("unitIs", { unit: row.units })}</Text>}</Table.Td>
          <Table.Td>{row.type}<Text size="xs" c="dimmed">{row.dimension}</Text></Table.Td>
          <Table.Td><Code>{JSON.stringify(row.default) ?? "—"}</Code></Table.Td>
        </Table.Tr>)}</Table.Tbody>
      </Table>
    </Table.ScrollContainer>
    <div ref={end} />
  </Section>;
}

function VariableReference({ search }: { search: string }) {
  const t = useT(messages);
  const route = useRoute();
  const selected = route.params.get("variable");
  const variables = useQuery({ queryKey: ["help-variables", search], queryFn: () => get<Variable[]>("/api/variables", { q: search, limit: 500 }), placeholderData: (previous) => previous });
  const body = useRef<HTMLTableSectionElement>(null);
  useFlip(body, variables.data);
  const { shown, end } = useRowsAsScrolled(variables.data?.length ?? 0);
  const fiche = useQuery({ queryKey: ["help-variable", selected], queryFn: () => get<{ registry?: Variable; diagnostic?: { label: string; method: string; requires?: string[] }; how_to_add?: string }>(`/api/variables/${encodeURIComponent(selected!)}`), enabled: Boolean(selected) });
  return <Stack>
    <Section>
      {variables.isLoading && <LoadingState rows={4} />}
      {variables.error && <ErrorState error={variables.error} />}
      <Table.ScrollContainer minWidth={620}><Table highlightOnHover>
        <Table.Thead><Table.Tr><Table.Th>{t("name")}</Table.Th><Table.Th>{t("meaning")}</Table.Th><Table.Th>{t("unit")}</Table.Th><Table.Th>{t("history")}</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody ref={body}>{variables.data?.slice(0, shown).map(v => <Table.Tr key={v.name} data-flip={v.name}>
          <Table.Td><Button variant="subtle" size="compact-sm" onClick={() => setParams({ variable: v.name })}>{v.name}</Button></Table.Td>
          <Table.Td>{v.description}</Table.Td><Table.Td>{v.units}</Table.Td><Table.Td c={v.history ? undefined : "dimmed"}>{t(v.history ? "yes" : "no")}</Table.Td>
        </Table.Tr>)}</Table.Tbody>
      </Table></Table.ScrollContainer>
      <div ref={end} />
    </Section>
    {selected && <Section title={`${t("fiche")} · ${selected}`}>
      {fiche.isLoading && <LoadingState rows={3} />}
      {fiche.error && <ErrorState error={fiche.error} />}
      {fiche.data && <Stack gap="xs">
        <Text>{fiche.data.registry?.description ?? fiche.data.diagnostic?.label}</Text>
        {fiche.data.registry && <Text size="sm">{t("registry", { unit: fiche.data.registry.units, dims: fiche.data.registry.dims, type: fiche.data.registry.type })}</Text>}
        <Text size="sm">{fiche.data.how_to_add ?? fiche.data.diagnostic?.method}</Text>
      </Stack>}
    </Section>}
  </Stack>;
}

/** A guide's headings as dashes beside it: the one being read is longer; a click goes there. */
function GuideToc({ doc, label }: { doc: RefObject<HTMLDivElement | null>; label: string }) {
  const [heads, setHeads] = useState<HTMLElement[]>([]);
  const [active, setActive] = useState(0);
  useEffect(() => {
    const found = Array.from(doc.current?.querySelectorAll<HTMLElement>("h2, h3") ?? []);
    setHeads(found);
    if (found.length < 3) return;
    // The last heading above the reading line, a third down the window
    const pick = () => {
      const line = window.innerHeight * 0.3;
      let k = 0;
      found.forEach((head, i) => { if (head.getBoundingClientRect().top <= line) k = i; });
      setActive(k);
    };
    const seen = new IntersectionObserver(pick, { rootMargin: "0px 0px -70% 0px", threshold: [0, 1] });
    found.forEach((head) => seen.observe(head));
    return () => seen.disconnect();
  }, [doc]);
  if (heads.length < 3) return null;
  return (
    <nav className="ows-guide-toc" aria-label={label}>
      {heads.map((head, k) => (
        <button key={k} type="button" className="ows-toc-item" data-level={head.tagName === "H3" ? 3 : 2} data-active={k === active || undefined} aria-current={k === active ? "location" : undefined}
          onClick={() => head.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" })}>
          <span className="ows-toc-dash" aria-hidden="true" />
          <span className="ows-toc-name">{head.textContent}</span>
        </button>
      ))}
    </nav>
  );
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
  const doc = useRef<HTMLDivElement>(null);
  const vanish = useVanish();
  return <Page title={ts("global.help")} help="getting-started">
    <TextInput ref={vanish} leftSection={<IconSearch size={17} />} label={t("search")} value={search} onChange={e => setSearch(e.currentTarget.value)} />
    <Tabs value={tab} onChange={v => setParams({ tab: v ?? "guides" })}>
      <GlideTabsList mb="lg"><Tabs.Tab value="guides" leftSection={<IconBook size={16} />}>{t("guides")}</Tabs.Tab><Tabs.Tab value="options">{t("options")}</Tabs.Tab><Tabs.Tab value="variables">{t("variables")}</Tabs.Tab></GlideTabsList>
      <Tabs.Panel value="guides">
        {topic ? <Stack>
          <Button variant="subtle" w="fit-content" leftSection={<IconArrowLeft size={16} />} onClick={() => navigate("help")}>{t("back")}</Button>
          {page.isLoading && <LoadingState rows={6} />}{page.error && <ErrorState error={page.error} />}
          {page.data && <Section title={page.data.title}>
            <div className="ows-guide">
              <div ref={doc} className="ows-guide-text"><Markdown text={page.data.markdown} /></div>
              <GuideToc key={`${topic}:${lang}:${page.data.markdown.length}`} doc={doc} label={t("contents")} />
            </div>
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
