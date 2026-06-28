import type { ScoreHistoryPoint } from '@/components/ScoreBreakdown/ScoreHistory';

interface Props {
  scoreHistory: ScoreHistoryPoint[];
  expanded: boolean;
  onToggleExpanded: () => void;
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

function formatTimestamp(ts: string): string {
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts.slice(0, 10);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  } catch {
    return ts.slice(0, 10);
  }
}

export default function ScoreHistory({ scoreHistory, expanded, onToggleExpanded }: Props) {
  return (
    <div className="panel mb-4">
      <button
        type="button"
        className="panel-header"
        style={{
          width: '100%',
          textAlign: 'left',
          cursor: 'pointer',
          border: 'none',
          background: 'none',
          font: 'inherit',
        }}
        onClick={onToggleExpanded}
        aria-expanded={expanded}
        aria-controls="score-history-content"
        aria-label={`评分历史，共 ${scoreHistory.length} 条记录，点击${expanded ? '收起' : '展开'}`}
      >
        <span>评分历史 ({scoreHistory.length})</span>
        <span className="text-text-tertiary" style={{ fontSize: 12 }} aria-hidden="true">
          {expanded ? '▾ 收起' : '▸ 展开'}
        </span>
      </button>
      {expanded && (
        <div
          id="score-history-content"
          className="panel-body-padded"
          role="region"
          aria-label="评分历史详情"
        >
          <ScoreHistoryBody scoreHistory={scoreHistory} />
        </div>
      )}
    </div>
  );
}

function ScoreHistoryBody({ scoreHistory }: { scoreHistory: ScoreHistoryPoint[] }) {
  return (
    <div
      className="scorebreakdown-panel"
      style={{ background: 'none', border: 'none', padding: 0 }}
    >
      <div className="scorebreakdown-history" style={{ padding: 0 }}>
        <div className="scorebreakdown-sparkline-container" style={{ marginTop: 0 }}>
          <ScoreHistorySparkline scoreHistory={scoreHistory} />
          <ScoreHistoryList scoreHistory={scoreHistory} />
        </div>
      </div>
    </div>
  );
}

function ScoreHistorySparkline({ scoreHistory }: { scoreHistory: ScoreHistoryPoint[] }) {
  const points = scoreHistory.slice(-10);
  const scores = points.map((p) => p.totalScore);
  const minScore = Math.min(...scores);
  const maxScore = Math.max(...scores);
  const range = maxScore - minScore || 1;
  return (
    <div
      className="scorebreakdown-sparkline"
      aria-label={`评分历史趋势，共 ${scoreHistory.length} 个数据点`}
      style={{
        height: 56,
        borderBottom: '0.5px solid var(--color-border-default)',
      }}
    >
      {points.map((point, i) => {
        const heightPct = ((point.totalScore - minScore) / range) * 100;
        return (
          <div
            key={`${point.timestamp}-${i}`}
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              height: '100%',
            }}
            title={`${formatLabel(point.timestamp)}: ${point.totalScore.toFixed(1)}`}
          >
            <div
              style={{
                width: '100%',
                maxWidth: 24,
                height: `${Math.max(4, heightPct)}%`,
                minHeight: 2,
                background: 'var(--color-sparkline-bar)',
                borderRadius: '1px 1px 0 0',
              }}
            />
            <span
              style={{
                fontSize: '0.5rem',
                color: 'var(--color-text-muted)',
                marginTop: 2,
                textAlign: 'center',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {formatLabel(point.timestamp)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function ScoreHistoryList({ scoreHistory }: { scoreHistory: ScoreHistoryPoint[] }) {
  return (
    <div
      style={{
        marginTop: 8,
        paddingTop: 6,
        borderTop: '0.5px solid var(--color-border-default)',
      }}
    >
      {scoreHistory
        .slice()
        .reverse()
        .slice(0, 10)
        .map((point, i) => (
          <div
            key={i}
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '2px 0',
              fontSize: '0.625rem',
            }}
          >
            <span style={{ color: 'var(--color-text-muted)', fontFamily: 'monospace' }}>
              {formatTimestamp(point.timestamp)}
            </span>
            <span
              style={{
                color: 'var(--color-score-highlight)',
                fontFamily: 'monospace',
              }}
            >
              {point.totalScore.toFixed(1)}
            </span>
          </div>
        ))}
    </div>
  );
}
