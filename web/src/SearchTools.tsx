import { useEffect, useRef, useState } from 'react';
import { Bookmark, X } from 'lucide-react';
import { post, request, type Filters, type SearchMode, type Sort } from './types';

interface Saved { id: string; name: string; query: string; mode: SearchMode; filters: Filters; sort: Sort }
interface Suggestion { query: string; label: string; kind: string }

export default function SearchTools({ root, query, mode, filters, sort, canSave, onSearch, onRestore }: {
  root: string; query: string; mode: SearchMode; filters: Filters; sort: Sort; canSave: boolean;
  onSearch: (query: string) => void; onRestore: (saved: Saved) => void;
}) {
  const details = useRef<HTMLDetailsElement>(null);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [saved, setSaved] = useState<Saved[]>([]);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    request<Saved[]>('/api/searches', { signal: controller.signal }).then(setSaved, e => {
      if (!controller.signal.aborted) setError((e as Error).message);
    });
    return () => controller.abort();
  }, [root, open]);
  useEffect(() => {
    setSuggestions([]);
    if (!open || query.trim().length < 2) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      request<Suggestion[]>(`/api/search/suggestions?${new URLSearchParams({ q: query })}`, { signal: controller.signal }).then(setSuggestions, e => {
        if (!controller.signal.aborted) setError((e as Error).message);
      });
    }, 200);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [root, open, query]);
  const update = async (values: object) => {
    setBusy(true); setError('');
    try { setSaved(await post<Saved[]>('/api/searches', values)); setName(''); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  const close = () => { if (details.current) details.current.open = false; };
  return <details ref={details} className="search-tools" onToggle={event => { setOpen(event.currentTarget.open); event.currentTarget.style.setProperty('--search-tools-top', `${event.currentTarget.getBoundingClientRect().bottom + 8}px`); }}>
    <summary className="text-button"><Bookmark />Saved searches</summary>
    <section className="search-tools-body" aria-label="Suggestions and saved searches">
      <h2>Search suggestions</h2>
      <p className="muted">Use the main search bar. Suggestions come from this workspace. Try <code>year:2020</code>, <code>type:png</code>, or <code>camera:"Canon"</code>.</p>
      {suggestions.length ? <ul className="search-suggestions">{suggestions.map(item => <li key={item.query}><button className="text-button" onClick={() => { onSearch(item.query); close(); }}>{item.label}<span className="muted">{item.kind}</span></button></li>)}</ul> : <p className="muted">Type part of a filename, camera, or year in the search bar.</p>}
      <h2>Saved searches</h2>
      {saved.length ? <ul className="saved-searches">{saved.map(item => <li key={item.id}><button className="text-button" onClick={() => { onRestore(item); close(); }}>{item.name}</button><button className="icon-button" aria-label={`Remove saved search ${item.name}`} disabled={busy} onClick={() => void update({ action: 'remove', id: item.id })}><X /></button></li>)}</ul> : <p className="muted">Save a query and its filters for this workspace.</p>}
      <form onSubmit={event => { event.preventDefault(); void update({ action: 'save', name, query, mode, filters, sort }); }}>
        <label htmlFor="saved-search-name">Saved search name</label><input id="saved-search-name" value={name} maxLength={80} onChange={event => setName(event.target.value)} disabled={busy || !canSave} />
        <button className="text-button secondary" disabled={busy || !canSave || !name.trim()}>Save search</button>
      </form>
      {error && <p className="error-copy" role="alert">{error}</p>}
    </section>
  </details>;
}
