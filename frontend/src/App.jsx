import { useEffect, useMemo, useState } from "react";
import { fetchChampions, fetchPatches, fetchDiff } from "./api";
import DiffChip from "./DiffChip";
import "./App.css";

export default function App() {
  const [champions, setChampions] = useState([]);
  const [patches, setPatches] = useState([]);
  const [champion, setChampion] = useState("");
  const [query, setQuery] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [showFluctuations, setShowFluctuations] = useState(false);
  const [diff, setDiff] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchChampions().then(setChampions).catch(() => setError("Couldn't reach the API. Is it running?"));
    fetchPatches().then((p) => {
      setPatches(p);
      if (p.length) {
        setStart(p[0]);
        setEnd(p[p.length - 1]);
      }
    }).catch(() => {});
  }, []);

  const filteredChampions = useMemo(() => {
    if (!query) return champions;
    return champions.filter((c) => c.toLowerCase().includes(query.toLowerCase()));
  }, [champions, query]);

  async function handleCheck() {
    if (!champion || !start || !end) return;
    setLoading(true);
    setError(null);
    setDiff(null);
    try {
      const result = await fetchDiff(champion, start, end);
      setDiff(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page">
      <header className="masthead">
        <p className="eyebrow">Summoner's Rift · patch history</p>
        <h1>Patch Ledger</h1>
        <p className="tagline">Pick a champion and a range. See what actually changed — not every bounce along the way.</p>
      </header>

      <section className="controls">
        <div className="field">
          <label htmlFor="champion-search">Champion</label>
          <input
            id="champion-search"
            type="text"
            placeholder="Search a champion…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoComplete="off"
          />
          {query && filteredChampions.length > 0 && (
            <ul className="suggestions">
              {filteredChampions.slice(0, 8).map((c) => (
                <li key={c}>
                  <button onClick={() => { setChampion(c); setQuery(c); }}>{c}</button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="field">
          <label htmlFor="patch-start">From patch</label>
          <select id="patch-start" value={start} onChange={(e) => setStart(e.target.value)}>
            {patches.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>

        <div className="field">
          <label htmlFor="patch-end">To patch</label>
          <select id="patch-end" value={end} onChange={(e) => setEnd(e.target.value)}>
            {patches.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>

        <button className="check-button" onClick={handleCheck} disabled={!champion || loading}>
          {loading ? "Checking…" : "Show changes"}
        </button>
      </section>

      {error && <p className="error">{error}</p>}

      {diff && (
        <section className="results">
          <div className="results-header">
            <h2>{diff.champion}</h2>
            <span className="range">{diff.patch_range[0]} → {diff.patch_range[1]}</span>
          </div>

          {diff.net_changes.length === 0 && diff.new_effects.length === 0 &&
           diff.removed_effects.length === 0 && diff.notes.length === 0 && (
            <p className="empty">No recorded changes in this range.</p>
          )}

          {diff.net_changes.length > 0 && (
            <ul className="entry-list">
              {diff.net_changes.map((c, i) => (
                <li key={i} className="entry">
                  <span className="entry-ability">{c.ability}</span>
                  <span className="entry-stat">{c.stat}</span>
                  <DiffChip oldValue={c.old_value} newValue={c.new_value} />
                  <span className="entry-patches">{c.patches_touched.join(", ")}</span>
                </li>
              ))}
            </ul>
          )}

          {diff.new_effects.length > 0 && (
            <>
              <h3 className="section-label">New</h3>
              <ul className="entry-list">
                {diff.new_effects.map((e, i) => (
                  <li key={i} className="entry entry-note">
                    <span className="entry-ability">{e.ability}</span>
                    <span className="entry-stat">{e.effect_name}</span>
                    <span className="entry-description">{e.description}</span>
                  </li>
                ))}
              </ul>
            </>
          )}

          {diff.removed_effects.length > 0 && (
            <>
              <h3 className="section-label">Removed</h3>
              <ul className="entry-list">
                {diff.removed_effects.map((e, i) => (
                  <li key={i} className="entry entry-note">
                    <span className="entry-ability">{e.ability}</span>
                    <span className="entry-stat">{e.effect_name}</span>
                    <span className="entry-description">{e.description}</span>
                  </li>
                ))}
              </ul>
            </>
          )}

          {(diff.fluctuated_no_net_change.length > 0 || diff.netted_out_effects.length > 0) && (
            <div className="fluctuations">
              <button className="fluctuations-toggle" onClick={() => setShowFluctuations((s) => !s)}>
                {showFluctuations ? "Hide" : "Show"} {diff.fluctuated_no_net_change.length + diff.netted_out_effects.length} fluctuated (no net change)
              </button>
              {showFluctuations && (
                <ul className="entry-list muted">
                  {diff.fluctuated_no_net_change.map((c, i) => (
                    <li key={`f${i}`} className="entry">
                      <span className="entry-ability">{c.ability}</span>
                      <span className="entry-stat">{c.stat}</span>
                      <span className="entry-description">touched in {c.patches_touched.join(", ")}, ended back at {c.old_value}</span>
                    </li>
                  ))}
                  {diff.netted_out_effects.map((e, i) => (
                    <li key={`n${i}`} className="entry">
                      <span className="entry-ability">{e.ability}</span>
                      <span className="entry-stat">{e.effect_name}</span>
                      <span className="entry-description">added then removed within this range</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
