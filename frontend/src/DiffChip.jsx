export default function DiffChip({ oldValue, newValue }) {
  return (
    <span className="diff-chip">
      <span className="diff-old">{oldValue}</span>
      <span className="diff-arrow" aria-hidden="true">→</span>
      <span className="diff-new">{newValue}</span>
    </span>
  );
}
