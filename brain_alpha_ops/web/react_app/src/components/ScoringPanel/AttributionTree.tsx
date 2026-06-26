import type { AttributionNode } from '@/types';
import { safeScoringText, fmtNum, childNodes } from './utils';
import AttributionTooltip from './AttributionTooltip';

interface Props {
  attribution: AttributionNode | null;
}

export default function AttributionTree({ attribution }: Props) {
  if (!attribution) return null;
  return <AttributionNodeView node={attribution} depth={0} />;
}

function AttributionNodeView({ node, depth }: { node: AttributionNode; depth: number }) {
  return (
    <div
      style={{ marginLeft: depth > 0 ? 16 : 0, paddingLeft: depth > 0 ? 12 : 0 }}
      className={depth > 0 ? 'border-l border-border-subtle' : ''}
    >
      <div
        style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontSize: 12 }}
      >
        <AttributionTooltip
          name={node.name}
          score={node.score}
          weight={node.weight}
          contribution={node.contribution}
          explanation={node.explanation}
        />
        <span className="tabular text-text-tertiary">
          {fmtNum(node.score, 1)} x {fmtNum(node.weight, 2)}
        </span>
      </div>
      {node.explanation && (
        <p className="text-2xs text-text-tertiary pb-1">
          {safeScoringText(node.explanation, '说明待确认')}
        </p>
      )}
      {childNodes(node).map((child, i) => (
        <div
          key={`${safeScoringText((child as AttributionNode).name, 'attribution')}-${depth}-${i}`}
        >
          <AttributionNodeView node={child as AttributionNode} depth={depth + 1} />
        </div>
      ))}
    </div>
  );
}
