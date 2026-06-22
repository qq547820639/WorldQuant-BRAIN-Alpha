/** Blocker list display for readiness diagnostics. */

interface Props {
  title: string;
  rows: string[];
  empty: string;
}

export default function BlockerList({ title, rows, empty }: Props) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-text-tertiary">{title}</p>
      <ul className="mt-1 space-y-1">
        {(rows.length ? rows : [empty]).map((row, index) => (
          <li key={`${title}_${index}`} className="break-words">{row}</li>
        ))}
      </ul>
    </div>
  );
}
