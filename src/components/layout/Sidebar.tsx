import {
  Activity,
  Blocks,
  Bot,
  ChartNoAxesColumnIncreasing,
  FlaskConical,
  GitCompareArrows,
  LayoutDashboard,
  Network,
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
  { href: "/", label: "指挥中心", icon: LayoutDashboard, section: "overview" },
  { href: "/studio", label: "智能体工作室", icon: Bot, section: "studio" },
  { href: "/runs", label: "运行中心", icon: Activity, section: "runs" },
  { href: "/trace", label: "轨迹浏览器", icon: Waypoints, section: "trace" },
  { href: "/compare", label: "运行对比", icon: GitCompareArrows, section: "compare" },
  { href: "/evaluation", label: "评测实验室", icon: FlaskConical, section: "evaluation" },
  { href: "/registry", label: "能力注册中心", icon: Blocks, section: "registry" },
  { href: "/workers", label: "私有执行节点", icon: Network, section: "workers" },
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
          <small>智能体运行时控制台</small>
        </span>
      </div>

      <nav className="primary-nav" aria-label="主导航">
        <p className="primary-nav__eyebrow">工作区</p>
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
            <strong>本地工作区</strong>
            <small>v0.1 基础版本</small>
          </span>
        </button>
      </div>
    </aside>
  );
}
