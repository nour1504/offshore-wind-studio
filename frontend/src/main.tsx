import "@mantine/core/styles.css";
import "@mantine/charts/styles.css";
import "@mantine/notifications/styles.css";
import "maplibre-gl/dist/maplibre-gl.css";
import "./styles.css";

import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode, useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";

import { setRequestLanguage } from "./api/client";
import { usePatchSettings, useSettings } from "./api/system";
import { App } from "./app/App";
import { I18nProvider, type Lang } from "./i18n";
import { cssVariablesResolver, theme } from "./theme";
import { HelpProvider } from "./ui/Help";

// First load: the menu entries arrive one after the other (styles.css "ows-booting")
document.documentElement.classList.add("ows-booting");
window.setTimeout(() => document.documentElement.classList.remove("ows-booting"), 1600);

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } },
});

const STORED_LANG = "ows-lang";

function initialLang(): Lang {
  // Written in the page by the application server from the settings: right from the first image
  const saved = document.documentElement.dataset.savedLang;
  if (saved === "en" || saved === "fr") return saved;
  try {
    const stored = localStorage.getItem(STORED_LANG);
    if (stored === "en" || stored === "fr") return stored;
  } catch {
    // storage unavailable: use the browser language
  }
  return navigator.language.toLowerCase().startsWith("fr") ? "fr" : "en";
}

/** The language comes from the settings (shared with the server, written in the page at start);
    once chosen in the window, the window's choice prevails (a late answer never brings back the
    former one). Every request carries it, and texts made by the server are asked again in it. */
function Root() {
  const settings = useSettings();
  const patchSettings = usePatchSettings();
  const [lang, setLangState] = useState<Lang>(initialLang);
  const chosen = useRef(false);
  setRequestLanguage(lang);

  useEffect(() => {
    if (!chosen.current && settings.data?.language) setLangState(settings.data.language);
  }, [settings.data?.language]);

  // Messages, checks and file previews made by the server, in the new language (the project
  // itself holds no text of the application: its draft is left alone)
  const shown = useRef(lang);
  useEffect(() => {
    if (shown.current === lang) return;
    shown.current = lang;
    void queryClient.invalidateQueries({ predicate: (query) => !["case", "cases"].includes(String(query.queryKey[0])) });
  }, [lang]);

  useEffect(() => {
    document.documentElement.lang = lang;
    try {
      localStorage.setItem(STORED_LANG, lang);
    } catch {
      // ignore
    }
  }, [lang]);

  const setLang = useCallback(
    (next: Lang) => {
      chosen.current = true;
      setLangState(next);
      patchSettings.mutate({ language: next });
    },
    [patchSettings],
  );

  return (
    <I18nProvider lang={lang} setLang={setLang}>
      <HelpProvider>
        <App />
      </HelpProvider>
    </I18nProvider>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <MantineProvider theme={theme} cssVariablesResolver={cssVariablesResolver} defaultColorScheme="auto">
      <Notifications position="top-right" limit={4} transitionDuration={240} />
      <QueryClientProvider client={queryClient}>
        <Root />
      </QueryClientProvider>
    </MantineProvider>
  </StrictMode>,
);
