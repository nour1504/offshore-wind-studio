import { Accordion, Alert, Button, Code, Group, Modal, Stack, Tabs, Text } from "@mantine/core";
import { useState } from "react";
import { useWindowPlan } from "../../api/method";
import { useNamelistPreviews, useOffshorePreset } from "../../api/physics";
import { useLoadedDraft } from "../../app/CaseDraft";
import { sectionMessages } from "../../app/sections";
import { useT } from "../../i18n";
import { Page, Section } from "../../ui/Page";
import { ErrorState, LoadingState, QueryView } from "../../ui/States";
import { NamelistEditor } from "./physics/NamelistEditor";
import { NamelistImport, importMessages } from "./physics/NamelistImport";
import { messages } from "./physics/messages";
import { formatNamelistValue } from "./physics/values";
import { GlideTabsList } from "../../ui/GlideTabs";
import { Fold } from "../../ui/Fold";

function download(text: string, name: string) { const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" })); const a = document.createElement("a"); a.href = url; a.download = name; a.click(); URL.revokeObjectURL(url); }

export default function PhysicsPage() {
  const t = useT(messages); const ti = useT(importMessages); const ts = useT(sectionMessages); const { caseId, draft, update, replace, issues } = useLoadedDraft();
  const { structured, texts } = useNamelistPreviews(draft); const plan = useWindowPlan(draft); const preset = useOffshorePreset();
  const [presetOpen, setPresetOpen] = useState(false); const [importOpen, setImportOpen] = useState(false); const [copyError, setCopyError] = useState<unknown>(null);
  const errors = issues.filter((issue) => /physics|namelist|MYNN|PBL|cumulus|dynamics/i.test(issue.message));
  const copy = async (text: string) => { try { await navigator.clipboard.writeText(text); setCopyError(null); } catch (error) { setCopyError(error); } };
  // The dates in each previewed file, and which script rewrites them
  const when = (iso: string) => iso.replace("T", " ").slice(0, 16);
  const datesOf = (name: string) => {
    const windowPlan = plan.data;
    if (!windowPlan?.windows.length) return null;
    if (name === "namelist.wps") { const pass = windowPlan.wps_passes[0]; return pass ? t("wpsDates", { year: pass.year, start: when(pass.start), end: when(pass.end) }) : null; }
    if (name !== "namelist.input") return null;
    const first = [...windowPlan.windows].sort((a, b) => a.order - b.order)[0];
    return t("inputDates", { n: windowPlan.windows.length, start: when(first.simulation_start), end: when(first.simulation_end) });
  };
  return <Page className="ows-physics" title={ts("project.physics")} help="physics" actions={<><Button variant="default" onClick={() => setImportOpen(true)}>{ti("button")}</Button><Button variant="light" loading={preset.isPending} onClick={() => { setPresetOpen(true); preset.mutate(draft); }}>{t("preset")}</Button></>}>
    {errors.length > 0 && <Fold title={t("checks")} aside={String(errors.length)}><Alert color="gray"><Stack gap={4}>{errors.map((issue, index) => <Text size="sm" key={index}>{issue.message}</Text>)}</Stack></Alert></Fold>}
    <Tabs defaultValue="namelists" keepMounted={false}>
      <GlideTabsList style={{ flexWrap: "nowrap", overflowX: "auto" }}><Tabs.Tab value="namelists">{t("namelists")}</Tabs.Tab><Tabs.Tab value="files">{t("preview")}</Tabs.Tab></GlideTabsList>
      <Tabs.Panel value="namelists" pt="xl">
        <NamelistEditor caseId={caseId} draft={draft} update={update} structured={structured} />
      </Tabs.Panel>
      <Tabs.Panel value="files" pt="xl"><Section help="namelists">
        <QueryView query={texts}>{(files) => <Accordion>{Object.entries(files).map(([name, text]) => <Accordion.Item value={name} key={name}><Accordion.Control><Group justify="space-between" gap="sm" pr="sm"><Text size="sm" fw={600} ff="monospace">{name}</Text>{datesOf(name) && <Text size="xs" c="dimmed" className="ows-num">{datesOf(name)}</Text>}</Group></Accordion.Control><Accordion.Panel><Stack><Group><Button size="xs" variant="light" onClick={() => void copy(text)}>{t("copy")}</Button><Button size="xs" variant="default" onClick={() => download(text, name)}>{t("download")}</Button></Group><Code block style={{ maxHeight: 480, overflow: "auto" }}>{text}</Code></Stack></Accordion.Panel></Accordion.Item>)}</Accordion>}</QueryView>{Boolean(copyError) && <ErrorState error={copyError} />}
      </Section></Tabs.Panel>
    </Tabs>
    <Modal opened={presetOpen} onClose={() => setPresetOpen(false)} title={t("preset")} size="lg"><Stack><Text size="sm">{t("presetExplain")}</Text>{preset.isPending ? <LoadingState /> : preset.error ? <ErrorState error={preset.error} /> : preset.data && <>{(["physics", "dynamics"] as const).map((g) => <Stack gap={2} key={g}><Text fw={600}>{t(g)}</Text>{Object.entries(preset.data[g]).map(([name, value]) => <Text size="xs" ff="monospace" key={name}>{name}: {formatNamelistValue(draft[g][name])} → {formatNamelistValue(value)}</Text>)}</Stack>)}<Button onClick={() => { const proposed = preset.data; if (proposed) update((c) => { c.physics = structuredClone(proposed.physics); c.dynamics = structuredClone(proposed.dynamics); }); setPresetOpen(false); }}>{t("apply")}</Button></>}</Stack></Modal>
    <NamelistImport draft={draft} opened={importOpen} onClose={() => setImportOpen(false)} onApply={replace} />
  </Page>;
}
