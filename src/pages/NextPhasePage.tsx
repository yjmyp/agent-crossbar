import { Blocks, FlaskConical, GitCompareArrows } from "lucide-react";
import { PageHeader } from "../components/layout/PageHeader";
import { StatusBadge } from "../components/ui/StatusBadge";

const content = {
  compare: {
    title: "Compare",
    eyebrow: "Advance",
    description: "Compare quality, latency, and cost across agent versions and runtime adapters.",
    body: "Run snapshots are designed to make framework comparisons reproducible. The comparison workspace activates after multi-adapter execution ships.",
    icon: GitCompareArrows,
  },
  evaluation: {
    title: "Evaluation Lab",
    eyebrow: "Release",
    description: "Turn agent behavior into repeatable evidence and enforce regression gates.",
    body: "Versioned datasets, deterministic assertions, and evaluator runs are the next engineering milestone after the run/trace vertical slice.",
    icon: FlaskConical,
  },
  registry: {
    title: "Registry",
    eyebrow: "Capabilities",
    description: "Govern the tools, MCP servers, model profiles, and adapters agents may use.",
    body: "The registry will hold explicit capability contracts. Tool execution is never implicit or open-ended.",
    icon: Blocks,
  },
} as const;

export function NextPhasePage({ phase }: { phase: keyof typeof content }) {
  const page = content[phase];
  const Icon = page.icon;
  return (
    <div className="page">
      <PageHeader
        eyebrow={page.eyebrow}
        title={page.title}
        description={page.description}
        actions={<StatusBadge tone="warning">Next milestone</StatusBadge>}
      />
      <section className="roadmap-panel">
        <span className="roadmap-panel__icon">
          <Icon size={28} aria-hidden="true" />
        </span>
        <h2>Foundation first</h2>
        <p>{page.body}</p>
        <div className="roadmap-panel__line" aria-hidden="true">
          <span className="is-complete" />
          <span className="is-active" />
          <span />
        </div>
        <div className="roadmap-panel__labels">
          <span>Runtime vertical slice</span>
          <span>Comparison & evaluation</span>
          <span>Release gates</span>
        </div>
      </section>
    </div>
  );
}
