/**
 * Skeleton — loading skeleton component for better UX.
 * Shows animated placeholder content while data is loading.
 */
import { memo } from "react";

interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  borderRadius?: string;
  className?: string;
}

function Skeleton({ width = "100%", height = "20px", borderRadius = "4px", className = "" }: SkeletonProps) {
  return (
    <div
      className={`skeleton ${className}`}
      style={{
        width,
        height,
        borderRadius,
        background: "linear-gradient(90deg, oklch(0.92 0.006 45) 25%, oklch(0.88 0.006 45) 50%, oklch(0.92 0.006 45) 75%)",
        backgroundSize: "200% 100%",
        animation: "skeleton-pulse 1.5s ease-in-out infinite",
      }}
      aria-hidden="true"
    />
  );
}

interface SkeletonTextProps {
  lines?: number;
  lastLineWidth?: string;
}

export const SkeletonText = memo(function SkeletonText({ lines = 3, lastLineWidth = "60%" }: SkeletonTextProps) {
  return (
    <div className="skeleton-text">
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton
          key={i}
          width={i === lines - 1 ? lastLineWidth : "100%"}
          height="14px"
          borderRadius="4px"
        />
      ))}
    </div>
  );
});

interface SkeletonCardProps {
  showHeader?: boolean;
  showActions?: boolean;
}

export const SkeletonCard = memo(function SkeletonCard({ showHeader = true, showActions = false }: SkeletonCardProps) {
  return (
    <div className="panel" style={{ padding: 16 }}>
      {showHeader && (
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 12 }}>
          <Skeleton width="120px" height="20px" />
          <Skeleton width="60px" height="24px" borderRadius="12px" />
        </div>
      )}
      <SkeletonText lines={2} />
      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <Skeleton width="80px" height="32px" borderRadius="6px" />
        {showActions && <Skeleton width="80px" height="32px" borderRadius="6px" />}
      </div>
    </div>
  );
});

interface SkeletonTableProps {
  rows?: number;
  columns?: number;
}

export const SkeletonTable = memo(function SkeletonTable({ rows = 5, columns = 4 }: SkeletonTableProps) {
  return (
    <div className="skeleton-table">
      {/* Header */}
      <div style={{ display: "flex", gap: 8, padding: "8px 12px", borderBottom: "1px solid oklch(0.92 0.006 45)" }}>
        {Array.from({ length: columns }, (_, i) => (
          <Skeleton key={i} width="80px" height="14px" />
        ))}
      </div>
      {/* Rows */}
      {Array.from({ length: rows }, (_, rowIndex) => (
        <div key={rowIndex} style={{ display: "flex", gap: 8, padding: "12px", borderBottom: "1px solid oklch(0.95 0.006 45)" }}>
          {Array.from({ length: columns }, (_, colIndex) => (
            <Skeleton
              key={colIndex}
              width={colIndex === 0 ? "100px" : "60px"}
              height="14px"
            />
          ))}
        </div>
      ))}
    </div>
  );
});

export default Skeleton;
