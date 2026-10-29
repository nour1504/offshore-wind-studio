import { Alert, Button, Group, List, Modal, Paper, Radio, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconAlertTriangle, IconArrowDown, IconInfoCircle } from "@tabler/icons-react";
import { useEffect, useState } from "react";

import type { StorageUsage } from "../../api/types";
import { common } from "../../i18n/common";
import { defineMessages, useFormat, useT } from "../../i18n";
import { PathInput } from "../../ui/PathInput";
import { ErrorState } from "../../ui/States";
import { PathLine } from "./CopyPath";
import { isFolderKey, locationMessages } from "./labels";
import { isAbsolutePath, isActive, isInside, samePath, useSetDataRoot } from "./queries";

/** Folders the server moves with the data folder, in its order. */
const MOVED = ["cases", "input", "observations", "exports", "videos", "reports"] as const;

type Mode = "move" | "switch";

const messages = defineMessages({
  en: {
    title: "Change the data folder",
    current: "Current data folder",
    target: "New data folder",
    targetInfo: "Full path, local or on a network share. Created if missing.",
    mode: "What happens to the current data",
    move: "Move the data to the new folder",
    moveText:
      "Projects, runs, downloaded input data, observations, exports, videos and reports are moved. Choose an empty folder.",
    switch: "Only use the new folder",
    switchText:
      "Nothing is moved or deleted. For a folder already holding data of the application.",
    notAbsolute: "Give a full path, for example D:\\WRF-data",
    same: "This is already the data folder.",
    nested: "The two folders are nested. Choose two separate folders.",
    continue: "Continue",
    back: "Back",
    from: "From",
    to: "To",
    moved: "Moved ({size} in total)",
    movedItem: "{name}: {size}",
    elsewhere: "{name}: stays at its custom place",
    notMoved:
      "Logs stay in the current folder. A folder is moved only if the destination is missing or empty, otherwise the move stops.",
    slow: "To another drive, every file is copied, which can take long. Keep the application open.",
    switchSummary:
      "Projects will be read from the new folder. Those of the current folder stay on disk.",
    active: "{n|# run is|# runs are} queued or running. The data cannot be moved until {n|it finishes|they finish}.",
    confirmMove: "Move the data",
    confirmSwitch: "Use this folder",
    moving: "Moving the data… Keep the application open.",
    done: "The data folder is now {path}",
  },
  fr: {
    title: "Changer de dossier de données",
    current: "Dossier de données actuel",
    target: "Nouveau dossier de données",
    targetInfo: "Chemin complet, local ou sur un partage réseau. Créé s'il n'existe pas.",
    mode: "Que deviennent les données actuelles",
    move: "Déplacer les données dans le nouveau dossier",
    moveText:
      "Les projets, calculs, données d'entrée téléchargées, observations, exports, vidéos et rapports sont déplacés. Choisissez un dossier vide.",
    switch: "Utiliser seulement le nouveau dossier",
    switchText:
      "Rien n'est déplacé ni supprimé. Pour un dossier qui contient déjà des données du logiciel.",
    notAbsolute: "Indiquez un chemin complet, par exemple D:\\Donnees-WRF",
    same: "C'est déjà le dossier de données.",
    nested: "Les deux dossiers sont imbriqués. Choisir deux dossiers distincts.",
    continue: "Continuer",
    back: "Retour",
    from: "De",
    to: "Vers",
    moved: "Déplacé ({size} au total)",
    movedItem: "{name} : {size}",
    elsewhere: "{name} : reste à son emplacement personnalisé",
    notMoved:
      "Les journaux restent dans le dossier actuel. Un dossier n'est déplacé que si la destination est absente ou vide, sinon le déplacement s'arrête.",
    slow: "Vers un autre disque, chaque fichier est copié, ce qui peut être long. Laisser le logiciel ouvert.",
    switchSummary:
      "Les projets seront lus dans le nouveau dossier. Ceux du dossier actuel restent sur le disque.",
    active:
      "{n|# calcul est|# calculs sont} en file d'attente ou en cours. Les données ne peuvent pas être déplacées avant {n|qu'il se termine|qu'ils se terminent}.",
    confirmMove: "Déplacer les données",
    confirmSwitch: "Utiliser ce dossier",
    moving: "Déplacement des données… Gardez l'application ouverte.",
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
    <Modal
      opened={opened}
      onClose={setRoot.isPending ? () => undefined : onClose}
      closeOnClickOutside={!setRoot.isPending}
      closeOnEscape={!setRoot.isPending}
      withCloseButton={!setRoot.isPending}
      title={<Text fw={600}>{t("title")}</Text>}
      size="lg"
    >
      {step === "choose" ? (
        <Stack>
          <Stack gap={2}>
            <Text size="sm" c="dimmed">
              {t("current")}
            </Text>
            <PathLine path={storage.data_root} name={t("current")} />
          </Stack>
          <PathInput example="data"
            label={t("target")}
            description={t("targetInfo")}
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
          <Radio.Group label={t("mode")} value={mode} onChange={(v) => setMode(v as Mode)}>
            <Stack gap="xs" mt="xs">
              <Radio.Card value="move" p="sm" radius="md">
                <Group wrap="nowrap" align="flex-start" gap="sm">
                  <Radio.Indicator mt={2} />
                  <Stack gap={2}>
                    <Text size="sm" fw={500}>
                      {t("move")}
                    </Text>
                    <Text size="xs" c="dimmed">
                      {t("moveText")}
                    </Text>
                  </Stack>
                </Group>
              </Radio.Card>
              <Radio.Card value="switch" p="sm" radius="md">
                <Group wrap="nowrap" align="flex-start" gap="sm">
                  <Radio.Indicator mt={2} />
                  <Stack gap={2}>
                    <Text size="sm" fw={500}>
                      {t("switch")}
                    </Text>
                    <Text size="xs" c="dimmed">
                      {t("switchText")}
                    </Text>
                  </Stack>
                </Group>
              </Radio.Card>
            </Stack>
          </Radio.Group>
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
            <Stack gap={4}>
              <Text size="xs" c="dimmed">
                {t("from")}
              </Text>
              <PathLine path={storage.data_root} name={t("from")} />
              <IconArrowDown size={16} aria-hidden style={{ color: "var(--ows-muted)" }} />
              <Text size="xs" c="dimmed">
                {t("to")}
              </Text>
              <PathLine path={target} name={t("to")} />
            </Stack>
          </Paper>

          {mode === "move" ? (
            <Stack gap="xs">
              <Text size="sm" fw={600}>
                {t("moved", { size: f.bytes(total) })}
              </Text>
              <List size="sm" spacing={2}>
                {moved.map((key) => (
                  <List.Item key={key}>{t("movedItem", { name: tl(`name.${key}`), size: f.bytes(sizeOf(key)) })}</List.Item>
                ))}
                {kept.map((key) => (
                  <List.Item key={key}>{t("elsewhere", { name: tl(`name.${key}`) })}</List.Item>
                ))}
              </List>
              <Alert color="gray" variant="light" icon={<IconInfoCircle size={18} />} py="xs">
                <Stack gap={4}>
                  <Text size="sm">{t("notMoved")}</Text>
                  <Text size="sm">{t("slow")}</Text>
                </Stack>
              </Alert>
            </Stack>
          ) : (
            <Alert color="gray" variant="light" icon={<IconInfoCircle size={18} />} py="xs">
              <Text size="sm">{t("switchSummary")}</Text>
            </Alert>
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
    </Modal>
  );
}
