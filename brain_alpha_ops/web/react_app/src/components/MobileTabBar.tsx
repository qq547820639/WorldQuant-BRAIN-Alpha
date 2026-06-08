/**
 * MobileTabBar — bottom tab navigation for mobile devices (UI Design System v3.0)
 * 4 tabs: Connect, Candidates, Evaluate, Tools
 * Replaces sidebar on screens < 1024px.
 */
import { memo } from "react";
import type { PhaseId } from "@/types";

interface Props {
  activePhase: PhaseId | "tools";
  onNavigate: (target: PhaseId | "tools") => void;
}

function ConnectIcon() {
  return <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
    <path d="M12 2a10 10 0 0 1 10 10" /><path d="M12 6a6 6 0 0 1 6 6" /><circle cx="12" cy="14" r="2" />
  </svg>;
}
function DiscoverIcon() {
  return <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
    <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
  </svg>;
}
function EvaluateIcon() {
  return <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
    <path d="M18 20V10" /><path d="M12 20V4" /><path d="M6 20v-6" />
  </svg>;
}
function ToolsIcon() {
  return <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
    <path d="M12 20h9" /><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
  </svg>;
}

const TABS: Array<{ id: PhaseId | "tools"; label: string; Icon: React.FC }> = [
  { id: "connect",   label: "连接", Icon: ConnectIcon },
  { id: "discover",  label: "候选", Icon: DiscoverIcon },
  { id: "evaluate",  label: "评估", Icon: EvaluateIcon },
  { id: "tools",     label: "工具", Icon: ToolsIcon },
];

export default memo(function MobileTabBar({ activePhase, onNavigate }: Props) {
  return (
    <nav className="mobile-tab-bar" role="navigation" aria-label="移动端导航">
      {TABS.map(({ id, label, Icon }) => (
        <button
          key={id}
          type="button"
          className="mobile-tab"
          onClick={() => onNavigate(id)}
          aria-current={activePhase === id ? "true" : undefined}
        >
          <Icon />
          <span>{label}</span>
        </button>
      ))}
    </nav>
  );
});
