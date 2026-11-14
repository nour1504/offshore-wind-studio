/** The scene module, its query and its WebGL context exist only while this view is open. */
import { lazy, Suspense, useState } from "react";

import type { Case } from "../../../api/types";
import { defineMessages, useT } from "../../../i18n";
import { Fold } from "../../../ui/Fold";
import { LoadingState } from "../../../ui/States";

const SceneControls = lazy(() => import("./LevelsScene").then((module) => ({ default: module.SceneControls })));
const messages = defineMessages({ en: { title: "3D view" }, fr: { title: "Vue 3D" } });

export function LevelsScene({ draft }: { draft: Case }) {
  const t = useT(messages);
  const [opened, setOpened] = useState(false);
  if (!draft.grid.domains.length) return null;
  return (
    <Fold title={t("title")} open={opened} onOpenChange={setOpened}>
      {opened && <Suspense fallback={<LoadingState rows={3} />}><SceneControls draft={draft} /></Suspense>}
    </Fold>
  );
}
