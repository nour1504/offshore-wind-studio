import { sectionMessages } from "../../app/sections";
import { useT } from "../../i18n";
import { Page } from "../../ui/Page";
import { FilesSection } from "./run/FilesSection";

/** The WPS and WRF files, exported to run on a cluster or a Linux computer: the application
 * does not run the simulations itself. Their outputs come back through the import (Results). */
export default function RunPage() {
  const ts = useT(sectionMessages);
  return <Page title={ts("project.run")} help="run" className="ows-run"><FilesSection /></Page>;
}
