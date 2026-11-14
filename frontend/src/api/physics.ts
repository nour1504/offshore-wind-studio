import { useDebouncedValue } from "@mantine/hooks";
import { useMutation, useQuery } from "@tanstack/react-query";
import { casesApi } from "./cases";
import { post } from "./client";
import type { Case } from "./types";

/** Stateless previews of the project draft. Never writes a project or starts WRF. */
export function useNamelistPreviews(draft: Case) {
  const [debounced] = useDebouncedValue(draft, 350);
  const pending = JSON.stringify(draft) !== JSON.stringify(debounced);
  const structuredQuery = useQuery({ queryKey: ["structured-namelists", debounced], queryFn: () => casesApi.structuredNamelists(debounced), retry: false });
  const textsQuery = useQuery({ queryKey: ["namelist-texts", debounced], queryFn: () => casesApi.namelists(debounced), retry: false });
  // During debounce, dates shown or downloaded must never come from the previous period.
  const structured = { ...structuredQuery, data: pending ? undefined : structuredQuery.data, isLoading: pending || structuredQuery.isLoading };
  const texts = { ...textsQuery, data: pending ? undefined : textsQuery.data, isLoading: pending || textsQuery.isLoading };
  return { structured, texts };
}
export function useOffshorePreset() { return useMutation({ mutationFn: casesApi.offshorePreset }); }
export function useNamelistImport() { return useMutation({ mutationFn: (body: { case: Case; input: string; wps: string }) => post<{ case: Case; warnings: string[] }>("/api/geo/namelist-import", body) }); }
