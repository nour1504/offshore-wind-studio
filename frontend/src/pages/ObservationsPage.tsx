import { Button } from "@mantine/core";
import { useMutation,useQuery,useQueryClient } from "@tanstack/react-query";
import { observationsApi } from "../api/observations";
import { sectionMessages } from "../app/sections";
import { defineMessages,useFormat,useT } from "../i18n";
import { DataTable } from "../ui/DataTable";
import { Confirm } from "../ui/Inputs";
import { Page,Section } from "../ui/Page";
import { ErrorState,QueryView } from "../ui/States";
import { ImportSection } from "./observations/ImportSection";
import { ComparisonSection } from "./observations/ComparisonSection";
const messages=defineMessages({en:{description:"Import LiDAR, mast and buoy measurements with explicit conversions, then compare them with your simulations.",datasets:"Imported datasets",name:"Name",station:"Station",series:"Series",date:"Imported",source:"Source",remove:"Delete imported dataset",removeHint:"Deletes the imported series and stored source copy. The original measurement file remains unchanged.",empty:"No imported measurements",refresh:"Refresh datasets"},fr:{description:"Importez les mesures de LiDAR, mâts et bouées avec des conversions explicites, puis comparez-les aux simulations.",datasets:"Jeux de données importés",name:"Nom",station:"Station",series:"Séries",date:"Date d'import",source:"Source",remove:"Supprimer le jeu importé",removeHint:"Supprime les séries importées et la copie stockée. Le fichier de mesures original reste inchangé.",empty:"Aucune mesure importée",refresh:"Actualiser les jeux de données"}});

export default function ObservationsPage() {
  const t = useT(sectionMessages);
  const m=useT(messages);const f=useFormat();const client=useQueryClient();const datasets=useQuery({queryKey:["observations-datasets"],queryFn:observationsApi.datasets});
  const remove=useMutation({mutationFn:observationsApi.remove,onSuccess:()=>void client.invalidateQueries({queryKey:["observations-datasets"]})});
  return <Page title={t("global.observations")} description={m("description")} help="observations"><Section title={m("datasets")} actions={<Button variant="default" onClick={()=>void datasets.refetch()}>{m("refresh")}</Button>}><QueryView query={datasets}>{items=><DataTable rows={items} rowKey={r=>r.id} empty={m("empty")} columns={[{key:"name",header:m("name")},{key:"station",header:m("station"),render:r=>r.station.name||r.station.id},{key:"series",header:m("series"),render:r=>f.number(r.series.length,0)},{key:"imported_at",header:m("date"),render:r=>f.dateTime(r.imported_at)},{key:"source",header:m("source"),render:r=>r.source.name},{key:"remove",header:"",render:r=><Confirm title={m("remove")} text={m("removeHint")} onConfirm={()=>remove.mutate(r.id)}>{open=><Button color="red" variant="subtle" size="xs" onClick={open}>{m("remove")}</Button>}</Confirm>}]}/>}</QueryView>{remove.error&&<ErrorState error={remove.error}/>}</Section><ImportSection/><ComparisonSection/></Page>;
}
