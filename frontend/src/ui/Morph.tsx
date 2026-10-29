/**
 * A dialog opened by a button, with the dialog's usual short fade.
 *
 *   const morph = useMorphingDialog();
 *   <Button ref={morph.trigger} onClick={morph.open}>…</Button>
 *   <Modal {...morph.modalProps} title="…">…</Modal>
 */
import type { ModalProps } from "@mantine/core";
import { useCallback, useState } from "react";

export function useMorphingDialog() {
  const [opened, setOpened] = useState(false);
  const [instant, setInstant] = useState(false);

  // No-op ref, so that trigger buttons can still pass a ref
  const trigger = useCallback((_node: HTMLElement | null) => undefined, []);

  const open = useCallback(() => {
    setInstant(false);
    setOpened(true);
  }, []);

  const close = useCallback(() => setOpened(false), []);

  /** Closes at once, without any animation (before going to another page). */
  const dismiss = useCallback(() => {
    setInstant(true);
    setOpened(false);
  }, []);

  const modalProps: Pick<ModalProps, "opened" | "onClose" | "transitionProps"> = {
    opened,
    onClose: close,
    transitionProps: instant ? { duration: 0, exitDuration: 0 } : undefined,
  };
  return { opened, open, close, dismiss, trigger, modalProps };
}
