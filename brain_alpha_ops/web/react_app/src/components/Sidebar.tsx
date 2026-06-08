/**
 * Sidebar — Phase-grouped navigation (UI Design System v3.0)
 * Replaces flat 10-item nav with 4 collapsible phase groups + global tools.
 */
import { memo, useCallback } from "react";
import type { CardViewId, PhaseGroup } from "@/types";

interface SidebarBadges {
  candidates?: number;
  official_backtests?: string;
  scoring?: number;
  checkpoint_status?: number;
  cloud?: string;
}

interface Props {
  activeView: CardViewId;
  badges?: SidebarBadges;
  onNavigate: (view: CardViewId) => void;
  onClose?: () => void;
  onTogglePhase?: (phaseId: string) => void;
  phases?: PhaseGroup[];
  className?: string;
}

const PHASE_STATUS_LABELS: Record<string, string> = {
  complete: "已完成",
  active: "进行中",
  pending: "待解锁",
  blocked: "已阻断",
  locked: "未解锁",
};

const TOOLS_ITEMS: Array<{ id: CardViewId; label: string; icon: string; statsKey?: string }> = [
  { id: "dashboard",          label: "运行总览", icon: "01" },
  { id: "cloud",              label: "云端快照", icon: "09", statsKey: "cloud" },
  { id: "checkpoint_status",  label: "续跑记录", icon: "08", statsKey: "checkpoint_status" },
  { id: "config",             label: "系统配置", icon: "10" },
];

function resolveToolBadge(statsKey: string | undefined, badges?: SidebarBadges): string | undefined {
  if (!statsKey || !badges) return undefined;
  if (statsKey === "cloud" && badges.cloud) return badges.cloud;
  if (statsKey === "checkpoint_status" && badges.checkpoint_status != null) return String(badges.checkpoint_status);
  return undefined;
}

const ChevronRight = memo(function ChevronRight({ expanded, locked }: { expanded: boolean; locked: boolean }) {
  return (
    <svg className={`phase-group-chevron${expanded ? "" : ""}`} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" style={{ transform: expanded ? "rotate(90deg)" : "rotate(0deg)", opacity: locked ? 0.25 : 0.5 }}>
      <polyline points="9 18 15 12 9 6" />
    </svg>
  );
});

export default memo(function Sidebar({
  activeView, badges, onNavigate, onClose, onTogglePhase, phases, className = "",
}: Props) {
  const handlePhaseToggle = useCallback((phaseId: string) => {
    onTogglePhase?.(phaseId);
  }, [onTogglePhase]);

  return (
    <nav className={`app-sidebar ${className}`} aria-label="主导航">
      {/* Brand */}
      <div className="sidebar-brand">
        <div className="sidebar-brand-mark">B</div>
        <span className="sidebar-brand-text">Alpha Ops</span>
      </div>

      {/* Phase Groups */}
      {phases?.map((group) => {
        const isLocked = group.status === "locked" || group.status === "pending";
        const statusLabel = PHASE_STATUS_LABELS[group.status] || group.status;
        return (
          <div key={group.id} className={`phase-group ${group.expanded ? "is-expanded" : ""} ${isLocked ? "is-locked" : ""}`}>
            <button
              type="button"
              className="phase-group-header"
              onClick={() => handlePhaseToggle(group.id)}
              aria-expanded={group.expanded}
              aria-controls={`phase-${group.id}-items`}
            >
              <ChevronRight expanded={group.expanded} locked={isLocked} />
              <span className="phase-group-label">{group.label}</span>
              <span className={`phase-group-status ${group.status}`}>{statusLabel}</span>
            </button>
            {group.expanded && (
              <div id={`phase-${group.id}-items`} role="region" aria-label={`${group.label} 导航项`} className="sidebar-nav">
                {group.items.map((item) => {
                  const isActive = activeView === item.id;
                  const badge = item.badge != null ? String(item.badge) : undefined;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => { onNavigate(item.id); onClose?.(); }}
                      className={`sidebar-nav-item${isActive ? " is-active" : ""}`}
                      aria-current={isActive ? "page" : undefined}
                    >
                      <span style={{ fontSize: 11, opacity: 0.6, minWidth: 18 }}>{item.icon}</span>
                      <span>{item.label}</span>
                      {badge && <span className="nav-badge">{badge}</span>}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}

      {/* Global Tools */}
      <div className="sidebar-section-label">工具</div>
      <div className="sidebar-nav">
        {TOOLS_ITEMS.map((item) => {
          const isActive = activeView === item.id;
          const badge = resolveToolBadge(item.statsKey, badges);
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => { onNavigate(item.id); onClose?.(); }}
              className={`sidebar-nav-item${isActive ? " is-active" : ""}`}
              aria-current={isActive ? "page" : undefined}
            >
              <span style={{ fontSize: 11, opacity: 0.6, minWidth: 18 }}>{item.icon}</span>
              <span>{item.label}</span>
              {badge && <span className="nav-badge">{badge}</span>}
            </button>
          );
        })}
      </div>

      {/* User Info (bottom) */}
      <div style={{ marginTop: "auto", padding: "14px 16px", borderTop: "0.5px solid oklch(0.22 0.007 45)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{
            width: 24, height: 24, borderRadius: "50%",
            background: "oklch(0.135 0.008 45)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 10, color: "oklch(0.52 0.006 45)",
          }}>U</div>
          <div>
            <div style={{ fontSize: 12, color: "oklch(0.92 0.003 45)" }}>operator</div>
            <div style={{ fontSize: 10, color: "oklch(0.52 0.006 45)" }}>本地非提交</div>
          </div>
        </div>
      </div>
    </nav>
  );
});
