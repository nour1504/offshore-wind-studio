import { useState } from "react";
import { useDeleteProfile, useSetDefaultProfile } from "../api/compute";
import { useProfiles } from "../api/system";
import type { ComputeProfile } from "../api/types";
import { sectionMessages } from "../app/sections";
import { useT } from "../i18n";
import { Page } from "../ui/Page";
import { Sheet, SheetRow, SheetRows } from "../ui/Sheet";
import { ErrorState, QueryView } from "../ui/States";
import { EngineHome } from "./compute/EngineHome";
import { MachineCard } from "./compute/MachineCard";
import { engineMessages } from "./compute/engineMessages";
import { localProfile } from "./compute/profile";
import { ProfileEditor } from "./compute/ProfileEditor";


/** The Compute page, as technical sheets: the engine and the machines. */
export default function ComputePage() {
  const ts = useT(sectionMessages);
  const te = useT(engineMessages);
  const profiles = useProfiles();
  const [editing, setEditing] = useState<ComputeProfile | null>(null);
  const remove = useDeleteProfile();
  const settings = useSetDefaultProfile();
  const taken = profiles.data?.profiles.map(p => p.id) ?? [];
  return <Page title={ts("global.compute")} help="compute">
    <EngineHome profiles={(profiles.data?.profiles ?? []).filter(localProfile)} taken={taken} />
    <Sheet title={te("home.machines")}>
      <QueryView query={profiles}>{data => <SheetRows>{!data.profiles.some(localProfile) ? <SheetRow label="–">{te("home.noMachines")}</SheetRow> : data.profiles.filter(localProfile).map(profile => <MachineCard key={profile.id} profile={profile} onEdit={() => setEditing(profile)} onDefault={() => settings.mutate(profile.id)} onDelete={() => remove.mutate(profile.id)} />)}</SheetRows>}</QueryView>
      {remove.error && <ErrorState error={remove.error} />}{settings.error && <ErrorState error={settings.error} />}
    </Sheet>
    {editing && <ProfileEditor key={editing.id} initial={editing} isNew={false} taken={taken} onClose={() => setEditing(null)} />}
  </Page>;
}
