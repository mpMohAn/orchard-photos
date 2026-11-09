import { useEffect, useRef, useState } from 'react';
import { FolderOpen, Trash2, X } from 'lucide-react';
import { post, sizeLabel, type Picture } from './types';

interface Plan { token: string; files: { id: string; path: string; original: string; size: number }[]; bytes: number }
interface Outcome { state: string; moved: number; recovery: string; files: { path: string; state: string; trash?: string; error?: string }[] }

export default function PhotoActions({ folder, items, marked, selecting, available, onChanged }: {
  folder: string; items: Picture[]; marked: Set<string>; selecting: boolean; available: boolean; onChanged: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { if (plan || outcome) dialog.current?.showModal(); }, [plan, outcome]);
  const review = async (all: boolean) => {
    setBusy(true); setError(''); setConfirmed(false); setOutcome(null);
    try { setPlan(await post<Plan>('/api/trash/review', all ? { folder } : { paths: items.filter(item => marked.has(item.id)).map(item => item.path) })); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  const close = () => { if (busy) return; dialog.current?.close(); setPlan(null); setOutcome(null); };
  const move = async () => {
    if (!plan || !confirmed) return;
    setBusy(true); setError('');
    try { setOutcome(await post<Outcome>('/api/trash/confirm', { token: plan.token, confirmed: true })); setPlan(null); onChanged(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  const reveal = async () => {
    setError('');
    try { await post('/api/folder/reveal', { folder }); }
    catch (e) { setError((e as Error).message); }
  };
  return <>
    <button className="text-button" onClick={() => void reveal()}><FolderOpen /><span>Show in Finder</span></button>
    {available && <>{selecting && <button className="text-button danger-action" disabled={busy || !marked.size} onClick={() => void review(false)}><Trash2 />Trash selected</button>}
      <details className="folder-actions"><summary className="text-button" aria-label="Folder actions">•••</summary><button className="text-button danger-action" disabled={busy} onClick={() => void review(true)}>Review all photos in this folder for Trash</button></details></>}
    {error && !plan && !outcome && <p className="error-copy" role="alert">{error}</p>}
    <dialog ref={dialog} className="photo-trash-dialog" aria-label="Review photos for Trash" onCancel={event => { event.preventDefault(); close(); }}>
      <div className="trash-heading"><h2>{outcome ? 'Trash results' : 'Review photos for Trash'}</h2><button className="icon-button" aria-label="Close Trash review" disabled={busy} onClick={close}><X /></button></div>
      {plan && <><p>{plan.files.length.toLocaleString()} original files · {sizeLabel(plan.bytes)}. Review every path below. This includes indexed files in subfolders when you choose a whole folder; the folder itself stays.</p>
        <ul className="trash-file-list">{plan.files.map(file => <li key={file.path}>{file.original}</li>)}</ul>
        <label className="check"><input type="checkbox" checked={confirmed} disabled={busy} onChange={event => setConfirmed(event.target.checked)} /><span>I reviewed these files and want to move them to macOS Trash.</span></label>
        <p className="muted">Recover them with Put Back in macOS Trash, then rescan Orchard. Review expires in 10 minutes. Nothing is permanently deleted.</p>
        <div className="trash-buttons"><button className="text-button secondary" disabled={busy} onClick={close}>Cancel</button><button className="text-button primary" disabled={!confirmed || busy} onClick={() => void move()}>{busy ? 'Moving…' : 'Move to Trash'}</button></div></>}
      {outcome && <><p role={outcome.state === 'complete' ? 'status' : 'alert'}>{outcome.moved} files moved. {outcome.state !== 'complete' && 'The operation stopped. Check the recorded results before continuing.'}</p><p>{outcome.recovery}</p><ul className="trash-file-list">{outcome.files.map(file => <li key={file.path}>{file.path} — {file.state}{file.trash && <div>{file.trash}</div>}{file.error && <div>{file.error}</div>}</li>)}</ul><button className="text-button secondary" onClick={close}>Done</button></>}
      {error && <p className="error-copy" role="alert">{error}</p>}
    </dialog>
  </>;
}
