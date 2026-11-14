/**
 * "Example" next to a paste or import field: shows a file in the expected format
 * (frontend/public/examples), which can be used as is to try, copied or saved.
 */
import { Button, Code, Group, Stack, Tabs, Text } from "@mantine/core";
import { IconDownload } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { defineMessages, useT } from "../i18n";
import { common } from "../i18n/common";
import { QueryView } from "./States";
import { GlideTabsList } from "./GlideTabs";
import { Window } from "./Window";

const messages = defineMessages({
  en: {
    open: "Example",
    title: "Expected format",
    use: "Use this example",
    download: "Save the file",
  },
  fr: {
    open: "Exemple",
    title: "Format attendu",
    use: "Utiliser cet exemple",
    download: "Enregistrer le fichier",
  },
});

const url = (file: string) => `examples/${encodeURIComponent(file)}`;

function Example({ file, onUse, onClose }: { file: string; onUse?: (text: string) => void; onClose: () => void }) {
  const t = useT(messages); const tc = useT(common); const [copied, setCopied] = useState(false);
  const query = useQuery({
    queryKey: ["example", file],
    queryFn: async () => { const response = await fetch(url(file)); if (!response.ok) throw new Error(`${file}: ${response.status}`); return response.text(); },
    staleTime: Infinity,
  });
  return <QueryView query={query}>{(text) => <Stack gap="sm">
    <Code block style={{ maxHeight: 340, overflow: "auto" }}>{text}</Code>
    <Group>
      {onUse && <Button onClick={() => { onUse(text); onClose(); }}>{t("use")}</Button>}
      <Button variant="default" component="a" href={url(file)} download={file} leftSection={<IconDownload size={16} />}>{t("download")}</Button>
      <Button variant="subtle" onClick={() => void navigator.clipboard.writeText(text).then(() => setCopied(true))}>{tc(copied ? "copied" : "copy")}</Button>
    </Group>
  </Stack>}</QueryView>;
}

export function ExampleFile({ files, onUse }: { files: string[]; onUse?: (text: string) => void }) {
  const t = useT(messages);
  const [opened, setOpened] = useState(false);
  const close = () => setOpened(false);
  return <>
    <Button variant="default" size="xs" style={{ flexShrink: 0 }} onClick={() => setOpened(true)}>{t("open")}</Button>
    <Window opened={opened} onClose={close} title={t("title")} size="lg">
      <Stack gap="sm">
        {opened && (files.length === 1 ? <Example file={files[0]} onUse={onUse} onClose={close} /> : <Tabs defaultValue={files[0]}>
          <GlideTabsList>{files.map((file) => <Tabs.Tab key={file} value={file}>{file}</Tabs.Tab>)}</GlideTabsList>
          {files.map((file) => <Tabs.Panel key={file} value={file} pt="sm"><Example file={file} onUse={onUse} onClose={close} /></Tabs.Panel>)}
        </Tabs>)}
        {files.length === 1 && <Text size="xs" c="dimmed">{files[0]}</Text>}
      </Stack>
    </Window>
  </>;
}
