import type { OfficialGateCheckItem, OfficialGateResult } from "@/types";
import { safeScoringText } from "./utils";

interface Props {
  hardGates: OfficialGateResult[];
  softGates: OfficialGateResult[];
}

export default function GateResults({ hardGates, softGates }: Props) {
  return (
    <div className="panel mb-4">
      <div className="panel-header"><span>官方门禁检查</span></div>
      <div className="panel-body-padded">
        <GateGroup title="硬门禁" gates={hardGates} />
        <div style={{ marginTop: 16 }}>
          <GateGroup title="软门禁" gates={softGates} />
        </div>
      </div>
    </div>
  );
}

function GateGroup({ title, gates }: { title: string; gates: OfficialGateResult[] }) {
  const safeGates = Array.isArray(gates) ? gates : [];
  if (!safeGates.length) return <p className="text-xs text-text-tertiary">{title}: 暂无数据</p>;
  return (
    <div>
      <p className="text-xs font-medium text-text-secondary mb-2">{title}</p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {safeGates.flatMap((gate) => {
          const checkItems = Array.isArray(gate.check_items) ? gate.check_items : [];
          const checks: OfficialGateCheckItem[] = checkItems.length ? checkItems : [{ name: gate.gate_name, passed: gate.passed }];
          return checks.map((check, i) => (
            <div key={`${safeScoringText(gate.gate_name, "gate")}-${safeScoringText(check.name, "check")}-${i}`}
              className={check.passed ? "bg-positive-subtle border-positive-subtle" : "bg-negative-subtle border-negative-subtle"}
              style={{
                display: "flex", alignItems: "flex-start", gap: 8, padding: "8px 10px",
                borderRadius: 4, fontSize: 12, borderWidth: "0.5px", borderStyle: "solid",
              }}
            >
              <span className={check.passed ? "text-positive" : "text-negative"}>{check.passed ? "\u2713" : "\u2715"}</span>
              <div>
                <span className="font-medium">{safeScoringText(check.name, "检查项待确认")}</span>
                <p className="text-text-tertiary text-2xs">{formatGateDetail(check.actual, check.direction, check.target, check.meaning)}</p>
                <p className="text-text-tertiary text-2xs">{safeScoringText(gate.gate_name, "门禁待确认")}</p>
              </div>
            </div>
          ));
        })}
      </div>
    </div>
  );
}

function formatGateDetail(actual: unknown, direction: unknown, target: unknown, fallback: unknown) {
  const parts = [actual, direction, target]
    .map((value) => safeScoringText(value, ""))
    .filter((value) => value);
  if (parts.length) return parts.join(" ");
  return safeScoringText(fallback, "--");
}
