import {
  ActionIcon,
  Box,
  Button,
  Card,
  Group,
  Menu,
  Modal,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  ThemeIcon,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { IconCopy, IconDots, IconDownload, IconFolderPlus, IconMap2, IconTrash, IconWindmill } from "@tabler/icons-react";
import { useState } from "react";

import { casesApi, useCases, useCreateCase, useDeleteCase } from "../api/cases";
import type { CaseSummary } from "../api/types";
import { common } from "../i18n/common";
import { defineMessages, useFormat, useT } from "../i18n";
import { navigate } from "../router";
import { Confirm } from "../ui/Inputs";
import { Page } from "../ui/Page";
import { EmptyState, QueryView } from "../ui/States";
import { exportProject, ImportProjectButton, transferMessages } from "./projects/ProjectTransfer";
import { CompareProjects } from "./projects/CompareProjects";

const messages = defineMessages({
  en: {
    title: "Projects",
    description:
      "A project holds one WRF configuration (period, domains, farms, physics, outputs) and its runs.",
    new: "New project",
    newTitle: "New project",
    name: "Name",
    template: "Start from",
    blank: "Blank project",
    copy: "Copy of a project",
    duplicate: "Duplicate",
    copyOf: "{name} (copy)",
    emptyTitle: "No project yet",
    emptyText: "The Horns Rev reference case is added when the data folder is empty.",
    domains: "{n|# domain|# domains}",
    farms: "{n|# farm|# farms} · {t|# turbine|# turbines}",
    noFarm: "No wind farm",
    created: "Project created",
    deleted: "Project deleted",
    deleteText: "Also deletes its runs and results. Input data are kept.",
  },
  fr: {
    title: "Projets",
    description:
      "Un projet regroupe une configuration WRF (période, domaines, parcs, physique, sorties) et ses calculs.",
    new: "Nouveau projet",
    newTitle: "Nouveau projet",
    name: "Nom",
    template: "À partir de",
    blank: "Projet vierge",
    copy: "Copie d'un projet",
    duplicate: "Dupliquer",
    copyOf: "{name} (copie)",
    emptyTitle: "Aucun projet",
    emptyText:
      "Le cas de référence Horns Rev est ajouté quand le dossier de données est vide.",
    domains: "{n|# domaine|# domaines}",
    farms: "{n|# parc|# parcs} · {t|# éolienne|# éoliennes}",
    noFarm: "Aucun parc éolien",
    created: "Projet créé",
    deleted: "Projet supprimé",
    deleteText: "Supprime aussi ses calculs et résultats. Les données d'entrée sont conservées.",
  },
});

function ProjectCard({ project, onDuplicate }: { project: CaseSummary; onDuplicate: () => void }) {
  const t = useT(messages);
  const tc = useT(common);
  const f = useFormat();
  const tt = useT(transferMessages);
  const remove = useDeleteCase();
  const open = () => navigate(`projects/${project.id}/overview`);

  // The whole tile opens the project; the menu (duplicate, delete) stays apart
  return (
    <Card
      padding="lg"
      className="ows-choice ows-project"
      role="link"
      tabIndex={0}
      aria-label={`${tc("open")} ${project.name}`}
      onClick={open}
      onKeyDown={(event) => {
        if (event.key === "Enter") open();
      }}
      style={{ cursor: "pointer", display: "flex", flexDirection: "column", gap: 14 }}
    >
      <Group justify="space-between" align="flex-start" wrap="nowrap" className="ows-project-heading">
        <Group gap="sm" wrap="nowrap" style={{ minWidth: 0 }}>
          <ThemeIcon size={42} radius="md" variant="light">
            <IconWindmill size={22} stroke={1.6} />
          </ThemeIcon>
          <Stack gap={2} style={{ minWidth: 0 }}>
            <Text fw={600} size="lg" lineClamp={2} style={{ lineHeight: 1.3 }}>
              {project.name}
            </Text>
            <Text size="xs" c="dimmed" className="ows-num">
              {f.date(project.start)} → {f.date(project.end)}
            </Text>
          </Stack>
        </Group>
        <Box onClick={(event) => event.stopPropagation()} onKeyDown={(event) => event.stopPropagation()}>
          <Confirm
            title={tc("confirmDelete.title", { name: project.name })}
            text={t("deleteText")}
            confirmLabel={tc("delete")}
            onConfirm={() =>
              remove.mutate(project.id, {
                onSuccess: () => notifications.show({ message: t("deleted") }),
                onError: (e) => notifications.show({ color: "red", message: e.message }),
              })
            }
          >
            {(confirm) => (
              <Menu position="bottom-end" withinPortal>
                <Menu.Target>
                  <ActionIcon variant="subtle" color="gray" radius="xl" aria-label={`${project.name}: actions`}>
                    <IconDots size={18} />
                  </ActionIcon>
                </Menu.Target>
                <Menu.Dropdown>
                  <Menu.Item leftSection={<IconCopy size={16} />} onClick={onDuplicate}>
                    {t("duplicate")}
                  </Menu.Item>
                  <Menu.Item leftSection={<IconDownload size={16} />} onClick={() => exportProject(project.id)}>
                    {tt("export")}
                  </Menu.Item>
                  <Menu.Item color="red" leftSection={<IconTrash size={16} />} onClick={confirm}>
                    {tc("delete")}
                  </Menu.Item>
                </Menu.Dropdown>
              </Menu>
            )}
          </Confirm>
        </Box>
      </Group>
      {project.description && (
        <Text size="sm" c="dimmed" lineClamp={2} className="ows-project-description">
          {project.description}
        </Text>
      )}
      <Group gap="lg" wrap="wrap" className="ows-project-meta">
        <Group gap={6} wrap="nowrap">
          <IconMap2 size={15} stroke={1.6} color="var(--mantine-color-dimmed)" />
          <Text size="xs" c="dimmed">{t("domains", { n: project.domains })}</Text>
        </Group>
        <Group gap={6} wrap="nowrap">
          <IconWindmill size={15} stroke={1.6} color="var(--mantine-color-dimmed)" />
          <Text size="xs" c="dimmed">{project.farms > 0 ? t("farms", { n: project.farms, t: project.turbines }) : t("noFarm")}</Text>
        </Group>
      </Group>
    </Card>
  );
}

export default function ProjectsPage() {
  const t = useT(messages);
  const tc = useT(common);
  const cases = useCases();
  const create = useCreateCase();
  const [opened, { open, close }] = useDisclosure(false);
  const [name, setName] = useState("");
  const [template, setTemplate] = useState<string | null>(null);
  const [from, setFrom] = useState<"blank" | "copy">("blank");

  const startNew = (source?: CaseSummary) => {
    setFrom(source ? "copy" : "blank");
    setTemplate(source?.id ?? cases.data?.[0]?.id ?? null);
    setName(source ? t("copyOf", { name: source.name }) : "");
    open();
  };

  const submit = async () => {
    if (from === "copy" && !template) return;
    try {
      const source = from === "blank" || !template ? await casesApi.blank() : await casesApi.get(template);
      const { id } = await create.mutateAsync({ ...source, name: name.trim() });
      notifications.show({ color: "teal", message: t("created") });
      close();
      navigate(`projects/${id}/overview`);
    } catch (error) {
      notifications.show({ color: "red", title: tc("error"), message: (error as Error).message });
    }
  };

  return (
    <Page
      title={t("title")}
      help="projects"
      actions={
        <>
          {cases.data && <CompareProjects projects={cases.data} />}
          <ImportProjectButton />
          <Button leftSection={<IconFolderPlus size={18} />} onClick={() => startNew()}>
            {t("new")}
          </Button>
        </>
      }
    >
      <QueryView
        query={cases}
        empty={(data) =>
          data.length === 0 ? (
            <EmptyState icon={<IconWindmill size={26} stroke={1.5} />} title={t("emptyTitle")}>
              {t("emptyText")}
            </EmptyState>
          ) : null
        }
      >
        {(data) => (
          <SimpleGrid cols={1} spacing={0} className="ows-project-list ows-stagger">
            {data.map((project) => (
              <ProjectCard key={project.id} project={project} onDuplicate={() => startNew(project)} />
            ))}
          </SimpleGrid>
        )}
      </QueryView>

      <Modal opened={opened} onClose={close} title={<Text fw={600}>{t("newTitle")}</Text>}>
        <Stack>
          <TextInput label={t("name")} value={name} onChange={(e) => setName(e.currentTarget.value)} data-autofocus required />
          {(cases.data?.length ?? 0) > 0 && (
            <SegmentedControl value={from} onChange={(value) => setFrom(value as "blank" | "copy")} data={[{ value: "blank", label: t("blank") }, { value: "copy", label: t("copy") }]} />
          )}
          {from === "copy" && (
            <Select
              label={t("template")}
              value={template}
              onChange={setTemplate}
              allowDeselect={false}
              data={(cases.data ?? []).map((c) => ({ value: c.id, label: c.name }))}
            />
          )}
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>
              {tc("cancel")}
            </Button>
            <Button onClick={() => void submit()} loading={create.isPending} disabled={!name.trim() || (from === "copy" && !template)}>
              {tc("create")}
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Page>
  );
}
