/** Operation history log display wrapper. */

import OperationLog from "./OperationLog";
import type { OperationLogEntry } from "./utils";

interface Props {
  logs: OperationLogEntry[];
  onClear: () => void;
}

export default function OperationsLog({ logs, onClear }: Props) {
  return <OperationLog logs={logs} onClear={onClear} />;
}
