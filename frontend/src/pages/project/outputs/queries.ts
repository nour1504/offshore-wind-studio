/**
 * Server helpers of the outputs page, on the project being edited (saved or not): the tslist
 * file the run would write (a stateless POST request).
 */
import { useDebouncedValue } from "@mantine/hooks";
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { casesApi } from "../../../api/cases";
import type { Case } from "../../../api/types";

const DEBOUNCE_MS = 400;

/**
 * The tslist file of the draft, as generated for the run (locations at the turbines or their
 * cells, then the extra locations); undefined text when the case writes no time series.
 */
export function useTslistPreview(draft: Case) {
  const [debounced] = useDebouncedValue(draft, DEBOUNCE_MS);
  return useQuery({
    // Only these parts of the case change the locations
    queryKey: ["outputs-tslist", debounced.time_series, debounced.farms, debounced.grid, debounced.farm_scheme],
    queryFn: async () => (await casesApi.namelists(debounced)).tslist ?? "",
    enabled: debounced.time_series !== null,
    placeholderData: keepPreviousData,
    retry: false,
  });
}

