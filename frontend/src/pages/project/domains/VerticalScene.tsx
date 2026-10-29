/** The scene module, its query and its WebGL context exist only while this view is open. */
import { Accordion, Text } from "@mantine/core";
import { lazy, Suspense, useState } from "react";

import type { Case } from "../../../api/types";
import { defineMessages, useT } from "../../../i18n";
import { LoadingState } from "../../../ui/States";

const SceneControls = lazy(() => import("./LevelsScene").then((module) => ({ default: module.SceneControls })));
const messages = defineMessages({ en: { title: "3D view" }, fr: { title: "Vue 3D" } });

export function LevelsScene({ draft }: { draft: Case }) {
  const t = useT(messages);
  const [opened, setOpened] = useState(false);
  if (!draft.grid.domains.length) return null;
  return <Accordion value={opened ? "scene" : null} onChange={(value) => setOpened(value === "scene")} variant="contained" radius="lg" className="ows-disclosure" styles={{ control: { paddingBlock: 14 }, content: { paddingTop: 4, paddingBottom: 22 } }}>
    <Accordion.Item value="scene">
      <Accordion.Control><Text fw={600} size="17px">{t("title")}</Text></Accordion.Control>
      <Accordion.Panel>{opened && <Suspense fallback={<LoadingState rows={3} />}><SceneControls draft={draft} /></Suspense>}</Accordion.Panel>
    </Accordion.Item>
  </Accordion>;
}
