import { sectionMessages } from "../app/sections";
import { useT } from "../i18n";
import { Page } from "../ui/Page";
import { DisplaySection } from "./settings/DisplaySection";
import { StorageSection } from "./settings/StorageSection";
import { CleanupSection } from "./settings/CleanupSection";
import { AccessSection, AboutSection, settingsMessages } from "./settings/AccessSection";

export default function SettingsPage() {
  const t = useT(sectionMessages);
  const ts = useT(settingsMessages);
  return <Page title={t("global.settings")} description={ts("description")} help="storage">
    <DisplaySection />
    <StorageSection />
    <AccessSection />
    <CleanupSection />
    <AboutSection />
  </Page>;
}
