/** Historical score chart — mini sparkline showing score trends. */

import { useState } from 'react';

export interface ScoreHistoryPoint {
  timestamp: string;
  totalScore: number;
}

interface Props {
  history?: ScoreHistoryPoint[];
}

function formatLabel(ts: string): string {
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts.slice(0, 5);
    return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  } catch {
    return ts.slice(0, 5);
  }
}

export default function ScoreHistory({ history }: Props) {
  const [expanded, setExpanded] = useState(false);
  if (!history || history.length < 2) return null;

  const points = history.slice(-10);
  const scores = points.map((p) => p.totalScore);
  const minScore = Math.min(...scores);
  const maxScore = Math.max(...scores);
  const range = maxScore - minScore || 1;

  const trend = scores[scores.length - 1] - scores[0];
  const trendIcon = trend > 0 ? '▲' : trend < 0 ? '▼' : '─';
  const trendColor =
    trend > 0 ? 'text-positive' : trend < 0 ? 'text-negative' : 'text-text-tertiary';

  return (
    <>
      <div className="scorebreakdown-divider" />
      <div className="scorebreakdown-history">
        <button
          type="button"
          className="scorebreakdown-history-toggle"
          onClick={() => setExpanded(!expanded)}
          aria-expanded={expanded}
        >
          <span className="scorebreakdown-history-title">
            评分历史
            <span className={`ml-1.5 text-xs ${trendColor}`}>
              {trendIcon} {Math.abs(trend).toFixed(1)}
            </span>
          </span>
          <span className="scorebreakdown-history-chevron" aria-hidden="true">
            {expanded ? '▾' : '▸'}
          </span>
        </button>

        {expanded && (
          <div className="scorebreakdown-sparkline-container">
            <div
              className="scorebreakdown-sparkline"
              aria-label={`评分历史趋势，共 ${points.length} 个数据点`}
            >
              {points.map((point, i) => {
                const heightPct = ((point.totalScore - minScore) / range) * 100;
                return (
                  <div
                    key={`${point.timestamp}-${i}`}
                    className="scorebreakdown-sparkline-bar-wrapper"
                    title={`${formatLabel(point.timestamp)}: ${point.totalScore.toFixed(1)}`}
                  >
                    <div
                      className="scorebreakdown-sparkline-bar"
                      style={{ height: `${Math.max(4, heightPct)}%` }}
                    />
                    <span className="scorebreakdown-sparkline-label">
                      {formatLabel(point.timestamp)}
                    </span>
                  </div>
                );
              })}
            </div>

            <div className="scorebreakdown-history-list">
              {points
                .slice()
                .reverse()
                .map((point, i) => (
                  <div key={i} className="scorebreakdown-history-row">
                    <span className="scorebreakdown-history-time">
                      {formatLabel(point.timestamp)}
                    </span>
                    <span className="scorebreakdown-history-score">
                      {point.totalScore.toFixed(1)}
                    </span>
                  </div>
                ))}
            </div>
          </div>
        )}

        {!expanded && (
          <div className="scorebreakdown-sparkline-inline" aria-hidden="true">
            {points.map((point, i) => {
              const heightPct = ((point.totalScore - minScore) / range) * 100;
              return (
                <div
                  key={i}
                  className="scorebreakdown-sparkline-dot"
                  style={{ height: `${Math.max(3, heightPct)}%` }}
                />
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
