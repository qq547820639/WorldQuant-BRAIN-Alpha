/**
 * ScoreBreakdown — 鼠标悬停时显示三层评分拆解 + 门禁状态。
 *
 * Reads from candidate.scorecard.attribution_tree for the three-layer tree,
 * and from candidate.scorecard.empirical.items for hard-gate pass/fail status.
 *
 * P1-5: Accept optional scoreHistory to render a mini sparkline at the bottom.
 */

import type { Scorecard } from "@/types";
import ScoreDetails from "@/components/ScoreBreakdown/ScoreDetails";
import ScoreHistory from "@/components/ScoreBreakdown/ScoreHistory";
import type { ScoreHistoryPoint } from "@/components/ScoreBreakdown/ScoreHistory";

interface ScoreBreakdownProps {
  scorecard: Scorecard;
  /** P1-5: Optional score history for mini sparkline display. */
  scoreHistory?: ScoreHistoryPoint[];
}

export default function ScoreBreakdown({ scorecard, scoreHistory }: ScoreBreakdownProps) {
  return (
    <div className="scorebreakdown-panel">
      <ScoreDetails scorecard={scorecard} />
      <ScoreHistory history={scoreHistory} />
    </div>
  );
}
