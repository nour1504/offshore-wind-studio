/**
 * Import of WRF outputs into the project: a button that opens a short window (one folder, link
 * or copy), checked before the import, with its progress. A run without turbines is imported the
 * same way, then chosen next to the run it is compared with (ReferenceSelect).
 */
import { Button, Group, Modal, Progress, SegmentedControl, Stack, Text, Tooltip } from "@mantine/core";
import { IconFileImport } from "@tabler/icons-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { exploreApi } from "../../../api/explore";
import { systemApi, useJob } from "../../../api/system";
import { useLoadedDraft } from "../../../app/CaseDraft";
import { defineMessages, useFormat, useT } from "../../../i18n";
import { setParams } from "../../../router";
import { PathInput } from "../../../ui/PathInput";
import { FoundTree } from "../../../ui/FoundTree";
import { ErrorState } from "../../../ui/States";

const messages = defineMessages({
  en: {
    open: "Import",
    title: "Import outputs",
    folder: "Outputs folder",
    link: "Link",
    copy: "Copy",
    linkInfo: "No second copy; same disk only",
    copyInfo: "A copy in the project",
    check: "Check",
    import: "Import",
    files: "{n} files · {size}",
    done: "Imported",
    cancel: "Cancel",
    save: "Save the project first",
  },
  fr: {
    open: "Importer",
    title: "Importer des sorties",
    folder: "Dossier des sorties",
    link: "Lier",
    copy: "Copier",
    linkInfo: "Sans seconde copie ; même disque seulement",
    copyInfo: "Une copie dans le projet",
    check: "Vérifier",
    import: "Importer",
    files: "{n} fichiers · {size}",
    done: "Importé",
    cancel: "Annuler",
    save: "Enregistrez d'abord le projet",
  },
});

export function ImportOutputs({ compact = false }: { compact?: boolean }) {
  const t = useT(messages);
  const f = useFormat();
  const { caseId, dirty } = useLoadedDraft();
  const client = useQueryClient();
  const [opened, setOpened] = useState(false);
  const [folder, setFolder] = useState("");
  const [mode, setMode] = useState<"link" | "copy">("copy");
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useJob<{ run_id?: string }>(jobId);
  const body = { folder, control_folder: null, mode };
  const preview = useMutation({ mutationFn: () => exploreApi.previewImport(caseId, body) });
  const started = useMutation({ mutationFn: () => exploreApi.importOutputs(caseId, body), onSuccess: (result) => setJobId(result.job_id) });
  const cancel = useMutation({ mutationFn: () => systemApi.cancelJob(jobId!) });
  const running = job.data?.state === "running";

  useEffect(() => {
    if (job.data?.state !== "succeeded") return;
    void client.invalidateQueries({ queryKey: ["results", caseId] });
    void client.invalidateQueries({ queryKey: ["runs", caseId] });
    void client.invalidateQueries({ queryKey: ["cases"] });
    if (job.data.result?.run_id) setParams({ run: job.data.result.run_id });
    setOpened(false);
  }, [job.data?.state, job.data?.result?.run_id, caseId, client]);

  const reset = () => preview.reset();
  return (
    <>
      <Tooltip label={t("save")} disabled={!dirty} withArrow>
        <Button variant={compact ? "default" : "filled"} leftSection={<IconFileImport size={16} />} disabled={dirty} onClick={() => setOpened(true)}>
          {t("open")}
        </Button>
      </Tooltip>
      <Modal opened={opened} onClose={() => { if (!running) setOpened(false); }} title={t("title")} size="lg" centered>
        <Stack gap="md">
          <PathInput example="wrfout" label={t("folder")} value={folder} onChange={(value) => { setFolder(value); reset(); }} />
          <Group justify="space-between" wrap="nowrap">
            <SegmentedControl value={mode} onChange={(value) => { setMode(value as "link" | "copy"); reset(); }}
              data={(["copy", "link"] as const).map((value) => ({ value, label: <Tooltip label={t(`${value}Info`)} withArrow><span>{t(value)}</span></Tooltip> }))} />
            {preview.data && <Text size="sm" fw={600} className="ows-num">{t("files", { n: preview.data.files, size: f.bytes(preview.data.bytes) })}</Text>}
          </Group>
          {preview.data && <FoundTree summary={preview.data.tree} />}
          {preview.data?.warnings.map((warning) => <Text key={warning} size="sm" c="dimmed">{warning}</Text>)}
          {preview.error && <ErrorState error={preview.error} />}
          {started.error && <ErrorState error={started.error} />}
          {job.data?.error && <ErrorState error={job.data.error} />}
          {job.data && running && <Progress value={job.data.progress * 100} animated aria-label={t("import")} />}
          <Group justify="flex-end" gap="xs">
            {running
              ? <Button variant="subtle" color="gray" loading={cancel.isPending} onClick={() => cancel.mutate()}>{t("cancel")}</Button>
              : <Button variant="default" disabled={!folder} loading={preview.isPending} onClick={() => preview.mutate()}>{t("check")}</Button>}
            <Button disabled={!preview.data || running} loading={started.isPending || running} onClick={() => started.mutate()}>{t("import")}</Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}
