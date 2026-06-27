/** AttributionTooltip — wraps an attribution label with a Tooltip (D4.1).
 *
 * Renders the dimension name as a hoverable label whose tooltip explains
 * the contribution (score × weight) and the backend-supplied explanation.
 * Used by AttributionTree so users can see "why this dimension matters"
 * without leaving the scoring panel.
 */
import Tooltip from '../Tooltip';
import { fmtNum, safeScoringText } from './utils';

interface Props {
  name: string;
  score?: number;
  weight?: number;
  contribution?: number;
  explanation?: string;
  fallback?: string;
}

export default function AttributionTooltip({
  name,
  score,
  weight,
  contribution,
  explanation,
  fallback = '归因项待确认',
}: Props) {
  const label = safeScoringText(name, fallback);
  const parts: string[] = [];
  if (Number.isFinite(score)) parts.push(`分数: ${fmtNum(score, 1)}`);
  if (Number.isFinite(weight)) parts.push(`权重: ${fmtNum(weight, 2)}`);
  if (Number.isFinite(contribution)) parts.push(`贡献: ${fmtNum(contribution, 2)}`);
  if (explanation) parts.push(safeScoringText(explanation, '说明待确认'));
  const tooltipText = parts.length ? parts.join(' · ') : label;
  return (
    <Tooltip content={tooltipText} placement="top">
      <span
        className="text-text-secondary cursor-help"
        style={{ borderBottom: '1px dotted var(--color-border-subtle)' }}
      >
        {label}
      </span>
    </Tooltip>
  );
}
