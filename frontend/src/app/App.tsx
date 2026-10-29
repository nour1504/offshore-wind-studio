import { Component, type ComponentType, type ErrorInfo, lazy, type ReactNode, Suspense } from "react";

import { common } from "../i18n/common";
import { useT } from "../i18n";
import { useRoute } from "../router";
import { ErrorState, LoadingState } from "../ui/States";
import { CaseDraftProvider, useDraft } from "./CaseDraft";
import { Layout } from "./Layout";
import { type ProjectSection, sectionMessages } from "./sections";

type PageModule = { default: ComponentType };

// Each page is its own chunk, loaded when first opened
const projectPages: Record<ProjectSection, () => Promise<PageModule>> = {
  overview: () => import("../pages/project/OverviewPage"),
  data: () => import("../pages/project/DataPage"),
  domains: () => import("../pages/project/DomainsPage"),
  farms: () => import("../pages/project/FarmsPage"),
  turbines: () => import("../pages/project/TurbinesPage"),
  physics: () => import("../pages/project/PhysicsPage"),
  outputs: () => import("../pages/project/OutputsPage"),
  run: () => import("../pages/project/RunPage"),
  results: () => import("../pages/project/ResultsPage"),
  explorer: () => import("../pages/project/ExplorerPage"),
  analyses: () => import("../pages/project/AnalysesPage"),
  media: () => import("../pages/project/MediaPage"),
};

const globalPages: Record<string, () => Promise<PageModule>> = {
  projects: () => import("../pages/ProjectsPage"),
  compute: () => import("../pages/ComputePage"),
  observations: () => import("../pages/ObservationsPage"),
  help: () => import("../pages/HelpPage"),
  settings: () => import("../pages/SettingsPage"),
};

const lazyPages = new Map<string, ComponentType>();
function page(key: string, load: () => Promise<PageModule>): ComponentType {
  let component = lazyPages.get(key);
  if (!component) {
    component = lazy(load);
    lazyPages.set(key, component);
  }
  return component;
}

class Boundary extends Component<{ children: ReactNode; resetKey: string }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(error, info.componentStack);
  }

  componentDidUpdate(previous: { resetKey: string }) {
    if (previous.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null });
  }

  render() {
    return this.state.error ? <ErrorState error={this.state.error} /> : this.props.children;
  }
}

function ProjectPage({ section }: { section: ProjectSection }) {
  const draft = useDraft();
  if (draft.loading || (!draft.draft && !draft.error)) return <LoadingState rows={6} />;
  if (draft.error) return <ErrorState error={draft.error} />;
  const Page = page(`project/${section}`, projectPages[section]);
  return <Page />;
}

export function App() {
  const route = useRoute();
  const t = useT(common);
  useT(sectionMessages);
  const [first = "projects", second, third] = route.segments;
  const resetKey = route.segments.join("/");

  if (first === "projects" && second) {
    const section = (third && third in projectPages ? third : "overview") as ProjectSection;
    return (
      <CaseDraftProvider key={second} caseId={second}>
        <Layout caseId={second} section={section}>
          <Boundary resetKey={resetKey}>
            <Suspense fallback={<LoadingState rows={6} />}>
              <ProjectPage section={section} />
            </Suspense>
          </Boundary>
        </Layout>
      </CaseDraftProvider>
    );
  }

  const key = first in globalPages ? first : "projects";
  const Page = page(key, globalPages[key]);
  return (
    <Layout caseId={null} section={key}>
      <Boundary resetKey={resetKey}>
        <Suspense fallback={<LoadingState rows={6} />}>
          <Page />
        </Suspense>
      </Boundary>
      <span hidden>{t("app")}</span>
    </Layout>
  );
}
