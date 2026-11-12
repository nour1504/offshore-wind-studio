import { Alert, Button, Group, List, Paper, SegmentedControl, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconAlertTriangle } from "@tabler/icons-react";
import { useEffect, useId, useState } from "react";

import { isActive } from "../../api/runs";
import type { StorageUsage } from "../../api/types";
import { common } from "../../i18n/common";
import { defineMessages, useFormat, useT } from "../../i18n";
import { FieldLabel } from "../../ui/Inputs";
import { PathInput } from "../../ui/PathInput";
import { ErrorState } from "../../ui/States";
import { Window } from "../../ui/Window";
import { isFolderKey, locationMessages } from "./labels";
import { isAbsolutePath, isInside, samePath, useSetDataRoot } from "./queries";

/** Folders the server moves with the data folder, in its order. */
const MOVED = ["cases", "input", "observations", "exports", "videos", "reports"] as const;

type Mode = "move" | "switch";

const messages = defineMessages({
  en: {
    title: "Data folder",
    target: "New folder",
    targetInfo: "Full path, local or on a network share. Created if missing.",
    mode: "Current data",
    modeInfo:
      "Move: projects, runs, downloaded data, observations, exports, videos and reports go to the new folder, which must be empty. Leave in place: nothing is moved or deleted, for a folder already holding data of the application.",
    move: "Move",
    switch: "Leave in place",
    notAbsolute: "Full path needed, e.g. D:\\WRF-data",
    same: "Already the data folder.",
    nested: "Nested folders: choose two separate ones.",
    continue: "Continue",
    back: "Back",
    from: "From",
    to: "To",
    moved: "Moved · {size}",
    movedItem: "{name}: {size}",
    elsewhere: "{name}: stays where it is",
    notMoved: "Logs stay. A folder moves only to a missing or empty destination; otherwise the move stops.",
    slow: "To another drive, every file is copied: possibly long. Keep the application open.",
    switchSummary: "Projects read from the new folder; those of the current one stay on disk.",
    active: "{n|# run is|# runs are} queued or running. The data cannot be moved until {n|it finishes|they finish}.",
    confirmMove: "Move the data",
    confirmSwitch: "Use this folder",
    moving: "Moving the data… Keep the application open.",
    done: "The data folder is now {path}",
  },
  fr: {
    title: "Dossier de données",
    target: "Nouveau dossier",
    targetInfo: "Chemin complet, local ou sur un partage réseau. Créé s'il n'existe pas.",
    mode: "Données actuelles",
    modeInfo:
      "Déplacer : projets, calculs, données téléchargées, observations, exports, vidéos et rapports vont dans le nouveau dossier, qui doit être vide. Laisser en place : rien n'est déplacé ni supprimé, pour un dossier qui contient déjà des données du logiciel.",
    move: "Déplacer",
    switch: "Laisser en place",
    notAbsolute: "Chemin complet requis, par exemple D:\\Donnees-WRF",
    same: "Déjà le dossier de données.",
    nested: "Dossiers imbriqués : en choisir deux distincts.",
    continue: "Continuer",
    back: "Retour",
    from: "De",
    to: "Vers",
    moved: "Déplacé · {size}",
    movedItem: "{name} : {size}",
    elsewhere: "{name} : reste à sa place",
    notMoved: "Les journaux restent. Un dossier n'est déplacé que vers une destination absente ou vide ; sinon, le déplacement s'arrête.",
    slow: "Vers un autre disque, chaque fichier est copié : parfois long. Garder le logiciel ouvert.",
    switchSummary: "Projets lus dans le nouveau dossier ; ceux de l'actuel restent sur le disque.",
    active:
      "{n|# calcul est|# calculs sont} en file d'attente ou en cours. Les données ne peuvent pas être déplacées avant {n|qu'il se termine|qu'ils se terminent}.",
    confirmMove: "Déplacer les données",
    confirmSwitch: "Utiliser ce dossier",
    moving: "Déplacement des données… Garder le logiciel ouvert.",
    done: "Le dossier de données est maintenant {path}",
  },
});

/** Two steps: choose the folder and what to do, then confirm with the exact consequences. */
export function MoveDataRoot({ opened, onClose, storage }: { opened: boolean; onClose: () => void; storage: StorageUsage }) {
  const t = useT(messages);
  const tc = useT(common);
  const tl = useT(locationMessages);
  const f = useFormat();
  const setRoot = useSetDataRoot();
  const [path, setPath] = useState("");
  const [mode, setMode] = useState<Mode>("move");
  const [step, setStep] = useState<"choose" | "confirm">("choose");
  const modeId = useId();
  const { reset } = setRoot;

  useEffect(() => {
    if (opened) {
      setPath("");
      setMode("move");
      setStep("choose");
      reset();
    }
  }, [opened, reset]);

  const target = path.trim();
  const error = !target
    ? null
    : !isAbsolutePath(target)
      ? t("notAbsolute")
      : samePath(target, storage.data_root)
        ? t("same")
        : null;
  const nested = Boolean(target) && !error && (isInside(target, storage.data_root) || isInside(storage.data_root, target));
  const activeRuns = storage.runs.filter((r) => isActive(r.state)).length;

  const sizeOf = (key: string) => storage.locations.find((l) => l.key === key)?.bytes ?? 0;
  const moved = MOVED.filter((key) => !(isFolderKey(key) && storage.folders[key].trim()));
  const kept = MOVED.filter((key) => isFolderKey(key) && storage.folders[key].trim());
  const total = moved.reduce((sum, key) => sum + sizeOf(key), 0);

  const submit = () =>
    setRoot.mutate(
      { path: target, move: mode === "move" },
      {
        onSuccess: (result) => {
          notifications.show({ color: "teal", message: t("done", { path: result.data_root }) });
          onClose();
        },
      },
    );

  return (
    <Window
      opened={opened}
      onClose={setRoot.isPending ? () => undefined : onClose}
      closeOnClickOutside={!setRoot.isPending}
      closeOnEscape={!setRoot.isPending}
      withCloseButton={!setRoot.isPending}
      title={<Text fw={600}>{t("title")}</Text>}
      size="lg"
    >
      {step === "choose" ? (
        <Stack gap="lg">
          <PathInput example="data"
            label={<FieldLabel label={t("target")} info={t("targetInfo")} />}
            value={path}
            onChange={setPath}
            error={error}
            placeholder="D:\OffshoreWindStudio"
            data-autofocus
          />
          {nested && (
            <Alert color="yellow" variant="light" icon={<IconAlertTriangle size={18} />} py="xs">
              <Text size="sm">{t("nested")}</Text>
            </Alert>
          )}
          <Stack gap={6}>
            <Text size="sm" fw={500} id={modeId} component="div">
              <FieldLabel label={t("mode")} info={t("modeInfo")} />
            </Text>
            <SegmentedControl<Mode>
              fullWidth
              aria-labelledby={modeId}
              value={mode}
              onChange={setMode}
              data={[{ value: "move", label: t("move") }, { value: "switch", label: t("switch") }]}
            />
          </Stack>
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              {tc("cancel")}
            </Button>
            <Button onClick={() => setStep("confirm")} disabled={!target || Boolean(error)}>
              {t("continue")}
            </Button>
          </Group>
        </Stack>
      ) : (
        <Stack>
          <Paper withBorder p="sm">
            <Stack gap={6}>
              {([["from", storage.data_root], ["to", target]] as const).map(([key, folder]) => (
                <Group key={key} gap="sm" wrap="nowrap" align="baseline">
                  <Text size="xs" c="dimmed" w={36} style={{ flexShrink: 0 }}>{t(key)}</Text>
                  <Text size="sm" className="ows-mono" style={{ overflowWrap: "anywhere", minWidth: 0 }}>{folder}</Text>
                </Group>
              ))}
            </Stack>
          </Paper>

          {mode === "move" ? (
            <Stack gap="xs">
              <Text size="sm" fw={600} component="div">
                <FieldLabel label={t("moved", { size: f.bytes(total) })} info={`${t("notMoved")} ${t("slow")}`} />
              </Text>
              {/* Empty folders are moved too, without being listed */}
              <List size="sm" spacing={2}>
                {moved.filter((key) => sizeOf(key) > 0).map((key) => (
                  <List.Item key={key}>{t("movedItem", { name: tl(`name.${key}`), size: f.bytes(sizeOf(key)) })}</List.Item>
                ))}
                {kept.map((key) => (
                  <List.Item key={key}>{t("elsewhere", { name: tl(`name.${key}`) })}</List.Item>
                ))}
              </List>
            </Stack>
          ) : (
            <Text size="sm" c="dimmed">{t("switchSummary")}</Text>
          )}

          {activeRuns > 0 && (
            <Alert color="yellow" variant="light" icon={<IconAlertTriangle size={18} />} py="xs">
              <Text size="sm">{t("active", { n: activeRuns })}</Text>
            </Alert>
          )}
          {setRoot.error && <ErrorState error={setRoot.error} />}
          {setRoot.isPending && mode === "move" && (
            <Text size="sm" c="dimmed" role="status">
              {t("moving")}
            </Text>
          )}

          <Group justify="flex-end">
            <Button variant="default" onClick={() => setStep("choose")} disabled={setRoot.isPending} data-autofocus>
              {t("back")}
            </Button>
            <Button color={mode === "move" ? "orange" : undefined} onClick={submit} loading={setRoot.isPending}>
              {mode === "move" ? t("confirmMove") : t("confirmSwitch")}
            </Button>
          </Group>
        </Stack>
      )}
    </Window>
  );
}
