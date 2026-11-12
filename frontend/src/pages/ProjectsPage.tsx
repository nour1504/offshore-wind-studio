import { ActionIcon, Button, Group, Menu, SegmentedControl, Select, Stack, Text, TextInput } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { IconCopy, IconDots, IconDownload, IconFolderPlus, IconTrash } from "@tabler/icons-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";

import { casesApi, useCases, useCreateCase, useDeleteCase } from "../api/cases";
import type { CaseSummary } from "../api/types";
import { common } from "../i18n/common";
import { defineMessages, useT } from "../i18n";
import { canViewTransition, EASE_OUT_POINTS } from "../motion";
import { navigate } from "../router";
import { HelpLink } from "../ui/Help";
import { Confirm } from "../ui/Inputs";
import { Page } from "../ui/Page";
import { QueryView } from "../ui/States";
import { HomeNebula } from "./home/HomeNebula";
import type { Engine } from "./home/nebula";
import { claimOrb, ProjectOrbs } from "./home/ProjectOrbs";
import { exportProject, ImportProjectButton, transferMessages } from "./projects/ProjectTransfer";
import { CompareProjects } from "./projects/CompareProjects";
import { Window } from "../ui/Window";

const messages = defineMessages({
  en: {
    title: "Projects",
    new: "New project",
    newTitle: "New project",
    name: "Name",
    template: "Start from",
    blank: "Blank project",
    copy: "Copy of a project",
    duplicate: "Duplicate",
    copyOf: "{name} (copy)",
    created: "Project created",
    deleted: "Project deleted",
    deleteText: "Also deletes its runs and results. Input data are kept.",
  },
  fr: {
    title: "Projets",
    new: "Nouveau projet",
    newTitle: "Nouveau projet",
    name: "Nom",
    template: "À partir de",
    blank: "Projet vierge",
    copy: "Copie d'un projet",
    duplicate: "Dupliquer",
    copyOf: "{name} (copie)",
    created: "Projet créé",
    deleted: "Projet supprimé",
    deleteText: "Supprime aussi ses calculs et résultats. Les données d'entrée sont conservées.",
  },
});

// Once the projects were opened in this session, the home page shows them at once
const OPENED = "ows.home.opened";
function openedBefore(): boolean {
  try {
    return window.sessionStorage.getItem(OPENED) === "1";
  } catch {
    return false;
  }
}

/** Duplicate, export, delete (with confirmation): the actions of a project on the map. */
function ProjectMenu({ project, onDuplicate, onOpenChange }: { project: CaseSummary; onDuplicate: () => void; onOpenChange: (open: boolean) => void }) {
  const t = useT(messages);
  const tc = useT(common);
  const tt = useT(transferMessages);
  const remove = useDeleteCase();
  return (
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
        <Menu position="bottom-start" withinPortal onChange={onOpenChange}>
          <Menu.Target>
            <ActionIcon variant="subtle" color="gray" radius="xl" size="sm" aria-label={`${project.name}: actions`}>
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
  );
}

/** The word's letters thicken and rise near the pointer, like a wave under it. */
function lean(word: HTMLElement, x: number | null) {
  word.querySelectorAll<HTMLElement>(".ows-home-letter").forEach((letter) => {
    if (x === null) {
      letter.style.removeProperty("--near");
      return;
    }
    const r = letter.getBoundingClientRect();
    const d = Math.abs(x - (r.left + r.width / 2)) / Math.max(40, r.height * 0.9);
    letter.style.setProperty("--near", Math.max(0, 1 - d * d).toFixed(3));
  });
}

/** Opening a project: its page grows out of its name (a view transition; the page changes at once). */
function openProject(project: CaseSummary, from: HTMLElement) {
  const root = document.getElementById("ows-page-root");
  if (root && canViewTransition()) {
    const r = from.getBoundingClientRect(), b = root.getBoundingClientRect();
    const html = document.documentElement;
    html.style.setProperty("--ows-open-from", `xywh(${Math.round(r.left - b.left)}px ${Math.round(r.top - b.top)}px ${Math.round(r.width)}px ${Math.round(r.height)}px round 8px)`);
    html.classList.add("ows-vt-open");
    window.setTimeout(() => html.classList.remove("ows-vt-open"), 1200);
  }
  navigate(`projects/${project.id}/overview`);
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
  const [revealed, setRevealed] = useState(openedBefore);
  const [burst, setBurst] = useState<{ x: number; y: number; at: number } | null>(null);
  const [engine, setEngine] = useState<Engine | null>(null);
  // The free orb a new project will take
  const orb = useRef<number | null>(null);
  const intro = !revealed && (cases.data?.length ?? 0) > 0;
  // Back to the word, from the page's title
  const back = () => {
    setRevealed(false);
    try {
      window.sessionStorage.removeItem(OPENED);
    } catch {
      // Storage blocked: nothing kept anyway
    }
  };
  const reveal = (x: number, y: number) => {
    setBurst({ x, y, at: performance.now() });
    setRevealed(true);
    try {
      window.sessionStorage.setItem(OPENED, "1");
    } catch {
      // Storage blocked: the word shows again next time
    }
  };
  // The wheel and the arrow keys open the projects too: the word is never a step to get past
  useEffect(() => {
    if (!intro) return;
    const centre = () => {
      const word = document.querySelector(".ows-home-word")?.getBoundingClientRect();
      return word ? [word.left + word.width / 2, word.top + word.height / 2] as const : [window.innerWidth / 2, window.innerHeight / 2] as const;
    };
    const onKey = (event: KeyboardEvent) => {
      if (!["ArrowDown", "ArrowRight", "PageDown"].includes(event.key) || document.querySelector(".mantine-Modal-root")) return;
      const target = event.target as HTMLElement;
      if (target.closest("input, textarea, select, [role=menu], [role=listbox]")) return;
      event.preventDefault();
      reveal(...centre());
    };
    const onWheel = (event: WheelEvent) => {
      if (event.deltaY > 0 && (event.target as HTMLElement).closest(".ows-home-page")) reveal(...centre());
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("wheel", onWheel, { passive: true });
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("wheel", onWheel);
    };
  }, [intro]);

  const startNew = (source?: CaseSummary, onOrb: number | null = null) => {
    orb.current = onOrb;
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
      if (orb.current !== null) claimOrb(id, orb.current);
      notifications.show({ color: "teal", message: t("created") });
      close();
      navigate(`projects/${id}/overview`);
    } catch (error) {
      notifications.show({ color: "red", title: tc("error"), message: (error as Error).message });
    }
  };

  return (
    <Page
      title={
        // The application's name, on the row of the actions; once the projects are open, it goes
        // back to the word
        !intro && (cases.data?.length ?? 0) > 0 ? (
          <button type="button" className="ows-home-title" aria-expanded onClick={back}>
            {tc("app")}
          </button>
        ) : (
          <span>{tc("app")}</span>
        )
      }
      fluid
      className="ows-home-page"
      actions={
        <>
          <HelpLink topic="getting-started" />
          {cases.data && <CompareProjects projects={cases.data} />}
          <ImportProjectButton />
          <Button leftSection={<IconFolderPlus size={18} />} onClick={() => startNew()}>
            {t("new")}
          </Button>
        </>
      }
    >
      <HomeNebula mode={intro ? "intro" : "orbs"} burst={burst} onEngine={setEngine}>
        {!intro && cases.data && (
          <ProjectOrbs
            engine={engine}
            projects={cases.data}
            onOpen={openProject}
            onCreate={(index) => startNew(undefined, index)}
            menu={(project, onOpenChange) => <ProjectMenu project={project} onDuplicate={() => startNew(project)} onOpenChange={onOpenChange} />}
          />
        )}
      </HomeNebula>
      {/* The word dissolves as the projects come out of the burst, and comes back the same way */}
      <AnimatePresence initial={false}>
      {intro && (
        <motion.div
          key="word"
          className="ows-home-stage"
          initial={{ opacity: 0, scale: 0.94, filter: "blur(14px)" }}
          animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
          exit={{ opacity: 0, scale: 1.1, filter: "blur(14px)", pointerEvents: "none" }}
          transition={{ duration: 0.45, ease: EASE_OUT_POINTS }}
        >
          <div className="ows-home-heading">
            <button
              type="button"
              className="ows-home-word"
              aria-expanded={false}
              aria-label={t("title")}
              onPointerMove={(event) => lean(event.currentTarget, event.clientX)}
              onPointerLeave={(event) => lean(event.currentTarget, null)}
              onClick={(event) => {
                const r = event.currentTarget.getBoundingClientRect();
                reveal(r.left + r.width / 2, r.top + r.height / 2);
              }}
            >
              {Array.from(t("title")).map((letter, i) => (
                <span key={i} className="ows-home-letter" aria-hidden="true">{letter}</span>
              ))}
            </button>
          </div>
        </motion.div>
      )}
      </AnimatePresence>
      {/* Loading and errors of the list; the orbs show the projects */}
      {!intro && (
        <div className="ows-home-empty">
          <QueryView query={cases} loading={null}>
            {() => null}
          </QueryView>
        </div>
      )}

      <Window opened={opened} onClose={close} title={<Text fw={600}>{t("newTitle")}</Text>}>
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
      </Window>
    </Page>
  );
}
