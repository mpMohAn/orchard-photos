import { useCallback, useEffect, useRef, useState } from 'react';
import { RefreshCw, X } from 'lucide-react';
import { fileName, imageUrl, plural, post, request, sizeLabel } from './types';

type Kind = 'exact' | 'similar';
interface Copy { path: string; size: number; modified: string }
interface Image { id: string; width: number; height: number; size: number; files: Copy[] }
interface Group { id: string; kind: Kind; images: Image[]; extraBytes: number }
interface Listing { items: Group[]; total: number; hasMore: boolean; nextOffset: number; trashAvailable: boolean }
interface ReviewedFile { id: string; path: string; original: string; size: number }
interface Plan { token: string; files: ReviewedFile[]; kept: ReviewedFile[]; bytes: number }
interface Outcome { token: string; state: string; moved: number; files: (ReviewedFile & { state: string; trash?: string; error?: string })[]; recovery: string }

export default function DuplicateReview({ root, onClose, onRefresh }: { root: string; onClose: () => void; onRefresh: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [kind, setKind] = useState<Kind>('exact');
  const [data, setData] = useState<Listing | null>(null);
  const [groupId, setGroupId] = useState('');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [plan, setPlan] = useState<Plan | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [history, setHistory] = useState<Outcome[]>([]);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => {
    const node = dialog.current!;
    const focus = document.activeElement as HTMLElement;
    const overflow = document.body.style.overflow;
    node.showModal(); node.focus(); document.body.style.overflow = 'hidden';
    return () => { node.close(); document.body.style.overflow = overflow; focus?.focus(); };
  }, []);
  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true); setError('');
    try {
      const [listing, recent] = await Promise.all([
        request<Listing>(`/api/duplicates?kind=${kind}`, { signal }),
        request<Outcome[]>('/api/duplicates/history', { signal }),
      ]);
      if (signal?.aborted) return;
      setData(listing); setHistory(recent); setGroupId(listing.items[0]?.id ?? ''); setSelected(new Set());
    } catch (e) { if (!signal?.aborted) setError((e as Error).message); }
    finally { if (!signal?.aborted) setLoading(false); }
  }, [kind]);
  useEffect(() => {
    const controller = new AbortController();
    setData(null); setPlan(null); setConfirmed(false);
    void load(controller.signal);
    return () => controller.abort();
  }, [load, root]);
  const group = data?.items.find(item => item.id === groupId);
  const files = group?.images.flatMap(image => image.files.map(file => ({ ...file, image }))) ?? [];
  const bytes = files.filter(file => selected.has(file.path)).reduce((total, file) => total + file.size, 0);
  const toggle = (path: string) => setSelected(previous => {
    const next = new Set(previous);
    if (next.has(path)) next.delete(path); else next.add(path);
    return next;
  });
  const review = async () => {
    if (!group) return;
    setBusy(true); setError('');
    try { setPlan(await post<Plan>('/api/duplicates/plan', { kind, group: group.id, paths: [...selected] })); setConfirmed(false); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  const move = async () => {
    if (!plan || !confirmed) return;
    setBusy(true); setError('');
    try {
      const result = await post<Outcome>('/api/duplicates/trash', { token: plan.token, confirmed: true });
      setPlan(null); setConfirmed(false); setSelected(new Set()); setOutcome(result);
      await load(); setHistory(previous => [result, ...previous.filter(item => item.token !== result.token)]); onRefresh();
    } catch (e) {
      setError((e as Error).message);
      try { setHistory(await request<Outcome[]>('/api/duplicates/history')); } catch { /* The visible error retains the failed request. */ }
    }
    finally { setBusy(false); }
  };
  const more = async () => {
    if (!data) return;
    setBusy(true); setError('');
    try {
      const next = await request<Listing>(`/api/duplicates?kind=${kind}&offset=${data.nextOffset}`);
      setData({ ...next, items: [...data.items, ...next.items] });
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  return <dialog ref={dialog} tabIndex={-1} className="duplicate-review" aria-label="Duplicate review" onCancel={event => { if (busy) event.preventDefault(); else onClose(); }}>
    <header className="duplicate-header"><div><h1>Duplicate review</h1><p>Compare photos and choose which files to keep.</p></div><button className="icon-button" aria-label="Close duplicate review" disabled={busy} onClick={onClose}><X /></button></header>
    <div className="duplicate-tabs" role="group" aria-label="Duplicate category"><button className="text-button" aria-pressed={kind === 'exact'} disabled={busy || !!plan} onClick={() => setKind('exact')}>Exact copies</button><button className="text-button" aria-pressed={kind === 'similar'} disabled={busy || !!plan} onClick={() => setKind('similar')}>Similar photos</button><button className="icon-button" aria-label="Refresh duplicate review" disabled={busy || !!plan} onClick={() => void load()}><RefreshCw /></button></div>
    <div className="duplicate-body">
      {error && <p className="notice error-copy" role="alert">{error}</p>}
      {outcome && <div className="notice" aria-label="Trash operation result" role={outcome.state === 'complete' ? 'status' : 'alert'}>{outcome.state === 'complete' ? `${plural(outcome.moved, 'file')} moved to Trash.` : 'The operation is partial or interrupted. Check Recent Trash operations before continuing.'}</div>}
      {loading ? <p className="duplicate-note" role="status">Loading duplicate groups…</p> : data && !data.items.length ? <div className="duplicate-empty"><h2>{kind === 'exact' ? 'No exact copies' : 'No similar groups'}</h2><p>{kind === 'exact' ? 'Each indexed image has one file in this workspace.' : 'Similar groups appear after visual indexing and grouping.'}</p></div> : <div className="duplicate-workspace">
        <nav className="duplicate-groups" aria-label="Duplicate groups"><p>{plural(data?.total ?? 0, 'group')}</p>{data?.items.map((item, index) => <button key={item.id} className="duplicate-group" aria-label={`Review ${kind} group ${index + 1}`} aria-current={item.id === groupId ? 'true' : undefined} disabled={busy || !!plan} onClick={() => { setGroupId(item.id); setSelected(new Set()); }}><img src={imageUrl(item.images[0].id)} alt="" /><span>{plural(item.images.flatMap(image => image.files).length, 'file')}<small>{sizeLabel(item.extraBytes)} in extra files</small></span></button>)}{data?.hasMore && <button className="text-button secondary" disabled={busy || !!plan} onClick={() => void more()}>More groups</button>}</nav>
        {group && <section className="duplicate-comparison" aria-label="Side-by-side comparison"><h2>{kind === 'exact' ? 'Identical file contents' : 'Visually similar photos'}</h2><p className="muted">{kind === 'exact' ? 'These copies share the same indexed content hash.' : 'Compare details and edits before choosing files.'}</p><div className="duplicate-candidates">{files.map(file => <article className="duplicate-candidate" key={file.path} data-selected={selected.has(file.path) || undefined}><img src={imageUrl(file.image.id, 'display')} alt={fileName(file.path)} /><div><p className="path" title={file.path}>{file.path}</p><p className="muted numbers">{file.image.width} × {file.image.height} · {sizeLabel(file.size)}</p><label className="check"><input type="checkbox" checked={selected.has(file.path)} disabled={busy || !!plan} onChange={() => toggle(file.path)} aria-label={`Move ${file.path} to Trash`} /><span>{selected.has(file.path) ? 'Selected for Trash' : 'Keep this file'}</span></label></div></article>)}</div></section>}
      </div>}
      {history.length > 0 && <details className="duplicate-history" open={history.some(item => item.state !== 'complete') || undefined}><summary>Recent Trash operations</summary>{history.map(item => <section key={item.token}><h3>{item.state === 'complete' ? `${plural(item.moved, 'file')} moved to Trash` : 'Partial or interrupted operation'}</h3><p>{item.recovery}</p><ul>{item.files.map(file => <li key={file.path}><span className="path">{file.original}</span> — {file.state}{file.trash && <p className="path">Trash location {file.trash}</p>}{file.error && <p className="error-copy">{file.error}</p>}</li>)}</ul></section>)}</details>}
    </div>
    <footer className="duplicate-footer">{plan ? <section aria-label="Confirm Trash move"><h2>Review {plural(plan.files.length, 'file')} for Trash</h2><ul>{plan.files.map(file => <li className="path" key={file.path}>{file.original}</li>)}</ul><p>Selected size {sizeLabel(plan.bytes)}. Keeping {plan.kept.map(file => file.original).join(', ')}.</p><label className="check"><input type="checkbox" checked={confirmed} disabled={busy} onChange={event => setConfirmed(event.target.checked)} /><span>I reviewed these files and want to move them to Trash</span></label><div className="duplicate-actions"><button className="text-button secondary" disabled={busy} onClick={() => { setPlan(null); setConfirmed(false); }}>Cancel review</button><button className="text-button primary" disabled={busy || !confirmed} onClick={() => void move()}>{busy ? 'Moving…' : 'Confirm move to Trash'}</button></div></section> : <><div><p aria-live="polite">{plural(selected.size, 'file')} selected · {sizeLabel(bytes)}</p><p className="muted">Keep at least one file in each group. Trash still uses disk space until emptied.</p>{!data?.trashAvailable && <p className="muted">Trash cleanup requires macOS and a regular folder library.</p>}</div><button className="text-button secondary" disabled={busy || loading || !data?.trashAvailable || !selected.size || selected.size >= files.length || selected.size > 50} onClick={() => void review()}>Review selected files</button></>}</footer>
  </dialog>;
}
