import {
  Activity,
  Blocks,
  Bot,
  ChartNoAxesColumnIncreasing,
  FlaskConical,
  GitCompareArrows,
  LayoutDashboard,
  Waypoints,
} from "lucide-react";
import clsx from "clsx";

type NavigationItem = {
  href: string;
  label: string;
  icon: React.ComponentType<{ size?: number; strokeWidth?: number }>;
  section: string;
};

const navigation: NavigationItem[] = [
  { href: "/", label: "Command Center", icon: LayoutDashboard, section: "overview" },
  { href: "/studio", label: "Agent Studio", icon: Bot, section: "studio" },
  { href: "/runs", label: "Run Center", icon: Activity, section: "runs" },
  { href: "/trace", label: "Trace Explorer", icon: Waypoints, section: "trace" },
  { href: "/compare", label: "Compare", icon: GitCompareArrows, section: "compare" },
  { href: "/evaluation", label: "Evaluation Lab", icon: FlaskConical, section: "evaluation" },
  { href: "/registry", label: "Registry", icon: Blocks, section: "registry" },
];

export function Sidebar({
  currentSection,
  onNavigate,
}: {
  currentSection: string;
  onNavigate: (path: string) => void;
}) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand__mark" aria-hidden="true">
          <span />
          <span />
          <span />
        </span>
        <span className="brand__copy">
          <strong>Agent Crossbar</strong>
          <small>Runtime control plane</small>
        </span>
      </div>

      <nav className="primary-nav" aria-label="Primary navigation">
        <p className="primary-nav__eyebrow">Workspace</p>
        {navigation.map((item) => {
          const Icon = item.icon;
          const active = item.section === currentSection;
          return (
            <a
              key={item.href}
              href={`#${item.href}`}
              aria-current={active ? "page" : undefined}
              className={clsx("nav-item", active && "nav-item--active")}
              onClick={(event) => {
                event.preventDefault();
                onNavigate(item.href);
              }}
            >
              <Icon size={17} strokeWidth={1.8} />
              <span>{item.label}</span>
              {["compare", "evaluation"].includes(item.section) ? (
                <span className="nav-item__phase">Next</span>
              ) : null}
            </a>
          );
        })}
      </nav>

      <div className="sidebar__footer">
        <button type="button" className="workspace-switcher">
          <span className="workspace-switcher__icon">
            <ChartNoAxesColumnIncreasing size={15} />
          </span>
          <span>
            <strong>Local workspace</strong>
            <small>v0.1 foundation</small>
          </span>
        </button>
      </div>
    </aside>
  );
}
