/**
 * A stage of an engine installation in the words of the interface: its name, and what there is to
 * say of it (a usual duration, or the size the installer reports). The installer's own detail, in
 * English, is read for its numbers only.
 */
import { useFormat, useT } from "../../i18n";
import { engineMessages } from "./engineMessages";

type Stage = keyof typeof engineMessages.en.stages;
type Detail = keyof typeof engineMessages.en.details;

// "1.2 GB of 2.6 GB" (download), "1.2 GB" (download of unknown size), "0.3 GB unpacked"
const SIZES = /^(\d+(?:\.\d+)?) GB(?: of (\d+(?:\.\d+)?) GB| unpacked)?$/;

export function useStage(): (stage: string, detail: string) => { known: boolean; label: string; detail: string } {
  const te = useT(engineMessages);
  const format = useFormat();
  return (stage, detail) => {
    // One stage per geography complement ("complement-lake_depth")
    const key = stage.startsWith("complement-") ? "complement" : stage;
    const known = key in engineMessages.en.stages;
    const sizes = SIZES.exec(detail.trim());
    let said = "";
    if (sizes) {
      const done = format.number(Number(sizes[1]), 1);
      // A download too small for the installer's one decimal says nothing
      if (sizes[2] !== undefined) said = Number(sizes[2]) > 0 ? te("sizes.of", { done, total: format.number(Number(sizes[2]), 1) }) : "";
      else if (Number(sizes[1]) > 0) said = te("sizes.done", { done });
    } else if (key in engineMessages.en.details) {
      said = te(`details.${key as Detail}`);
    }
    return { known, label: known ? te(`stages.${key as Stage}`) : stage, detail: said };
  };
}
