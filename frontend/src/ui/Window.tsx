/**
 * The app's dialog window: Mantine's Modal growing out of the control focused when it opens (see
 * Morph); without one (a click on a map), the short entrance.
 */
import { Modal, type ModalProps } from "@mantine/core";
import { useEffect, useLayoutEffect, useState } from "react";

import { useMorph } from "./Morph";

const OPENERS = "button, a[href], [role=button], [role=menuitem], [role=option], [role=tab], [role=switch], [role=checkbox]";

export function Window({ opened, ...props }: ModalProps) {
  // Mantine plays no entrance for a window created open: it opens one image later
  const [ready, setReady] = useState(false);
  useEffect(() => setReady(true), []);
  const shown = opened && ready;
  const morph = useMorph(shown);
  const { trigger } = morph;
  useLayoutEffect(() => {
    if (!shown) return;
    const focused = document.activeElement;
    trigger(focused instanceof HTMLElement && focused.matches(OPENERS) ? focused : null);
  }, [shown, trigger]);
  return <Modal opened={shown} {...props} {...morph.dialog} />;
}
