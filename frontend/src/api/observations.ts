import { del,get,post,put } from "./client";
import type { SeriesData,SeriesRef } from "./explore";
import type { AnalysisResult } from "./analysis";
export interface ObservationFlag {code:string;message:string;column?:string;severity:string}
export interface ObservationColumn {column:string;variable:string;height_m:number|null;unit:string;statistic:string;direction?:"from"|"to"|null;[key:string]:unknown}
export interface ObservationMapping {description:string;file:Record<string,unknown>;time:{columns:string[];format:string;timezone:string|null;label:string|null;averaging_s:number|null;[key:string]:unknown};station:{id:string;name:string;lat:number|null;lon:number|null;instrument:string;height_reference:string;[key:string]:unknown};columns:ObservationColumn[]}
export interface ObservationPreview {columns:string[];rows:Record<string,unknown>[];time_columns:string[];suggestions:{column:string;variable:string|null;height_m:number|null;unit:string;statistic:string}[];flags:ObservationFlag[];layout:Record<string,unknown>}
export interface ObservationDataset {id:string;name:string;imported_at:string;station:ObservationMapping["station"];series:{key:string;variable:string;unit:string;height_m:number|null;height_ref:"agl"|"asl"|"surface";count:number;start:string;end:string}[];source:{name:string;sha256:string;bytes:number};flags?:ObservationFlag[]}
export interface ObservationComparison extends AnalysisResult {unit:string;circular:boolean;overall:Record<string,number|null>;series:{times:string[];reference:(number|null)[];evaluated:(number|null)[]};scatter:{reference:number[];evaluated:number[]};alignment:string[];caveats:string[]}
export const observationsApi={
  preview:(path:string,file:Record<string,unknown>={})=>post<ObservationPreview>("/api/observations/preview",{path,file}),
  check:(path:string,mapping:ObservationMapping)=>post<{ready:boolean;flags:ObservationFlag[];series:SeriesData[]}>("/api/observations/check",{path,mapping}),
  import:(path:string,mapping:ObservationMapping,dataset_id:string,name:string)=>post<{job:string}>("/api/observations/import",{path,mapping,dataset_id,name}),
  mappings:()=>get<{name:string;description:string;station:string;columns:number}[]>("/api/observations/mappings"),
  mapping:(name:string)=>get<ObservationMapping>(`/api/observations/mappings/${encodeURIComponent(name)}`),
  saveMapping:(name:string,mapping:ObservationMapping)=>put(`/api/observations/mappings/${encodeURIComponent(name)}`,mapping),
  datasets:()=>get<ObservationDataset[]>("/api/observations/datasets"),
  dataset:(id:string)=>get<ObservationDataset>(`/api/observations/datasets/${id}`),
  remove:(id:string)=>del(`/api/observations/datasets/${id}`),
  compare:(observation:SeriesRef,simulation:SeriesRef,period_s:number,min_availability:number,tolerance_s:number,start:string|null,end:string|null)=>post<ObservationComparison>("/api/observations/compare",{observation,simulation,period_s,min_availability,tolerance_s,selection:{start,end}}),
};
