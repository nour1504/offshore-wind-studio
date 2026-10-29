import { useQuery } from "@tanstack/react-query";

import { get } from "./client";

export interface DocTopic {
  id: string;
  title: string;
  section: string;
  summary: string;
}

export interface DocPage extends DocTopic {
  markdown: string;
  related: { id: string; title: string }[];
}

export interface DocHit {
  id: string;
  title: string;
  section: string;
  excerpt: string;
}

export const docsApi = {
  index: (lang: string) => get<{ topics: DocTopic[] }>("/api/docs", { lang }),
  page: (id: string, lang: string) => get<DocPage>(`/api/docs/${encodeURIComponent(id)}`, { lang }),
  search: (q: string, lang: string) => get<{ results: DocHit[] }>("/api/docs/search", { q, lang }),
};

export function useDocIndex(lang: string) {
  return useQuery({ queryKey: ["docs", lang], queryFn: () => docsApi.index(lang), staleTime: Infinity });
}

export function useDocPage(id: string | null, lang: string) {
  return useQuery({
    queryKey: ["doc", id, lang],
    queryFn: () => docsApi.page(id!, lang),
    enabled: Boolean(id),
    staleTime: Infinity,
    retry: false,
  });
}
