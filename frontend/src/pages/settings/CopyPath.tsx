import { ActionIcon, CopyButton, Group, Text, Tooltip } from "@mantine/core";
import { IconCheck, IconCopy } from "@tabler/icons-react";

import { defineMessages, useT } from "../../i18n";

const messages = defineMessages({
  en: { copy: "Copy the path", copied: "Path copied", copyOf: "Copy the path of {name}" },
  fr: { copy: "Copier le chemin", copied: "Chemin copié", copyOf: "Copier le chemin de {name}" },
});

/** A button that copies a path to the clipboard, with a visible and spoken confirmation. */
export function CopyPathButton({ path, name }: { path: string; name?: string }) {
  const t = useT(messages);
  return (
    <CopyButton value={path} timeout={1500}>
      {({ copied, copy }) => (
        <Tooltip label={copied ? t("copied") : t("copy")} withArrow>
          <ActionIcon
            variant="subtle"
            color={copied ? "teal" : "gray"}
            onClick={(e) => { e.stopPropagation(); copy(); }}
            aria-label={copied ? t("copied") : name ? t("copyOf", { name }) : t("copy")}
          >
            {copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
          </ActionIcon>
        </Tooltip>
      )}
    </CopyButton>
  );
}

/** A path in monospace that wraps anywhere, with its copy button. */
export function PathLine({ path, name, size = "sm" }: { path: string; name?: string; size?: "xs" | "sm" }) {
  return (
    <Group gap={4} wrap="nowrap" align="center" style={{ minWidth: 0 }}>
      <Text
        size={size}
        className="ows-mono"
        style={{ overflowWrap: "anywhere", minWidth: 0, fontSize: size === "xs" ? 12 : undefined }}
        title={path}
      >
        {path}
      </Text>
      <CopyPathButton path={path} name={name} />
    </Group>
  );
}
