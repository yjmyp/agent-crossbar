import { useEffect, useState } from "react";
import { WifiOff } from "lucide-react";
import type { Bridge } from "./lib/bridge";
import { connectDesktop } from "./lib/bridge";
import { errorMessage } from "./lib/errors";
import { Sidebar } from "./components/layout/Sidebar";
import { TopBar, type ServiceState } from "./components/layout/TopBar";
import { ErrorState, LoadingState } from "./components/ui/States";
import { AgentStudioPage } from "./pages/AgentStudioPage";
import { CommandCenterPage } from "./pages/CommandCenterPage";
import { NextPhasePage } from "./pages/NextPhasePage";
import { RunCenterPage } from "./pages/RunCenterPage";
import { RunDetailPage } from "./pages/RunDetailPage";
import { TraceExplorerPage } from "./pages/TraceExplorerPage";

type AppProps = {
  bridge?: Bridge;
  initialRoute?: string;
};

type LoadedBridge =
  | { status: "loading"; bridge: null; error: null }
  | { status: "ready"; bridge: Bridge; error: null }
  | { status: "failed"; bridge: null; error: string };

const sectionTitles: Record<string, string> = {
  overview: "Command Center",
  studio: "Agent Studio",
  runs: "Run Center",
  trace: "Trace Explorer",
  compare: "Compare",
  evaluation: "Evaluation Lab",
  registry: "Registry",
};

export function App({ bridge: suppliedBridge, initialRoute }: AppProps) {
  const [route, setRoute] = useState(() => normalizeRoute(initialRoute ?? hashRoute()));
  const [loadedBridge, setLoadedBridge] = useState<LoadedBridge>(() =>
    suppliedBridge
      ? { status: "ready", bridge: suppliedBridge, error: null }
      : { status: "loading", bridge: null, error: null },
  );
  const [serviceState, setServiceState] = useState<ServiceState>("checking");

  useEffect(() => {
    if (suppliedBridge) return;

    let current = true;
    connectDesktop()
      .then((bridge) => {
        if (current) setLoadedBridge({ status: "ready", bridge, error: null });
      })
      .catch((reason: unknown) => {
        if (current) {
          setLoadedBridge({
            status: "failed",
            bridge: null,
            error: errorMessage(reason),
          });
        }
      });
    return () => {
      current = false;
    };
  }, [suppliedBridge]);

  useEffect(() => {
    if (loadedBridge.status !== "ready") return;
    let current = true;
    loadedBridge.bridge
      .health()
      .then(() => {
        if (current) setServiceState("online");
      })
      .catch(() => {
        if (current) setServiceState("offline");
      });
    return () => {
      current = false;
    };
  }, [loadedBridge]);

  useEffect(() => {
    function handleHashChange() {
      setRoute(normalizeRoute(hashRoute()));
    }
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  function navigate(path: string) {
    const nextRoute = normalizeRoute(path);
    window.history.replaceState(null, "", `#${nextRoute}`);
    setRoute(nextRoute);
  }

  const section = routeSection(route);
  const title = sectionTitles[section];

  return (
    <div className="app-shell">
      <Sidebar currentSection={section} onNavigate={navigate} />
      <div className="app-main">
        <TopBar title={title} serviceState={serviceState} />
        <main className="app-content" id="main-content">
          {loadedBridge.status === "loading" ? (
            <div className="connection-gate">
              <LoadingState label="Starting the private desktop service" />
            </div>
          ) : null}
          {loadedBridge.status === "failed" ? (
            <div className="connection-gate">
              <ErrorState
                title="The desktop service is unavailable"
                message={loadedBridge.error}
              />
              <p className="connection-gate__hint">
                <WifiOff size={14} aria-hidden="true" />
                Launch through the Agent Crossbar desktop shell. A browser-only preview cannot
                access the protected local sidecar.
              </p>
            </div>
          ) : null}
          {loadedBridge.status === "ready" ? (
            <RouteView
              bridge={loadedBridge.bridge}
              route={route}
              navigate={navigate}
            />
          ) : null}
        </main>
      </div>
    </div>
  );
}

function RouteView({
  bridge,
  route,
  navigate,
}: {
  bridge: Bridge;
  route: string;
  navigate: (path: string) => void;
}) {
  if (route === "/") {
    return <CommandCenterPage bridge={bridge} navigate={navigate} />;
  }
  if (route === "/studio") {
    return <AgentStudioPage bridge={bridge} navigate={navigate} />;
  }
  if (route === "/runs") {
    return <RunCenterPage bridge={bridge} navigate={navigate} />;
  }
  if (route.startsWith("/runs/")) {
    const runId = route.slice("/runs/".length);
    return (
      <RunDetailPage
        key={runId}
        bridge={bridge}
        runId={runId}
        navigate={navigate}
      />
    );
  }
  if (route === "/trace") {
    return <TraceExplorerPage bridge={bridge} navigate={navigate} />;
  }
  if (route === "/compare") {
    return <NextPhasePage phase="compare" />;
  }
  if (route === "/evaluation") {
    return <NextPhasePage phase="evaluation" />;
  }
  if (route === "/registry") {
    return <NextPhasePage phase="registry" />;
  }
  return <CommandCenterPage bridge={bridge} navigate={navigate} />;
}

function hashRoute(): string {
  return window.location.hash.replace(/^#/, "") || "/";
}

function normalizeRoute(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "/";
  if (!trimmed.startsWith("/")) return `/${trimmed}`;
  return trimmed;
}

function routeSection(route: string): string {
  if (route === "/") return "overview";
  if (route === "/studio") return "studio";
  if (route === "/runs" || route.startsWith("/runs/")) return "runs";
  if (route === "/trace") return "trace";
  if (route === "/compare") return "compare";
  if (route === "/evaluation") return "evaluation";
  if (route === "/registry") return "registry";
  return "overview";
}

