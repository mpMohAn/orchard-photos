import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, Check, Users } from 'lucide-react';
import Gallery from './Gallery';
import { post, request, type Picture, type Results } from './types';

interface Person { id: string; name: string; photos: number; cover: string }
interface Face { id: string; image_id: string; box: string; person?: string; name?: string }
interface State { enabled: boolean; paused: boolean; state: string; error: string; processed: number; total: number; people: Person[]; selectedPerson?: string }

const personNames = new Intl.Collator(undefined, { sensitivity: 'base', numeric: true });

export default function People({ onOpen }: { onOpen: (picture: Picture) => void }) {
  const [state, setState] = useState<State | null>(null);
  const [person, setPerson] = useState('');
  const [faces, setFaces] = useState<Face[]>([]);
  const [memberRevision, setMemberRevision] = useState(0);
  const [pictures, setPictures] = useState<Picture[]>([]);
  const [more, setMore] = useState(false);
  const [name, setName] = useState('');
  const [picker, setPicker] = useState<string | null>(null);
  const [newName, setNewName] = useState('');
  const [applyGroup, setApplyGroup] = useState(false);
  const pickerDialog = useRef<HTMLDialogElement>(null);
  const [consent, setConsent] = useState(false);
  const [clearConfirmed, setClearConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const photoRequest = useRef(0);
  const stateRequest = useRef(0);
  const people = useMemo(() => [...(state?.people ?? [])].sort((left, right) => {
    const leftNamed = !!left.name.trim();
    const rightNamed = !!right.name.trim();
    if (leftNamed !== rightNamed) return leftNamed ? -1 : 1;
    if (leftNamed) return personNames.compare(left.name, right.name) || left.id.localeCompare(right.id);
    return right.photos - left.photos || left.id.localeCompare(right.id);
  }), [state?.people]);
  const selected = people.find(item => item.id === person);
  const pickerFace = faces.find(face => face.id === picker);
  const assignedPerson = pickerFace?.person ?? person;
  const refresh = async () => {
    const version = stateRequest.current;
    try {
      const result = await request<State>('/api/people');
      if (version === stateRequest.current) setState(result);
    }
    catch (e) { setError((e as Error).message); }
  };
  useEffect(() => {
    const controller = new AbortController();
    const load = () => {
      const version = stateRequest.current;
      return request<State>('/api/people', { signal: controller.signal }).then(data => {
        if (!controller.signal.aborted && version === stateRequest.current) setState(data);
      }, e => { if (!controller.signal.aborted) setError((e as Error).message); });
    };
    void load(); const timer = setInterval(() => void load(), 2500);
    return () => { controller.abort(); clearInterval(timer); };
  }, []);
  useEffect(() => {
    setName(selected?.name ?? '');
  }, [person, selected?.name]);
  useEffect(() => {
    const controller = new AbortController();
    photoRequest.current += 1;
    setFaces([]); setPictures([]);
    if (!person) return () => controller.abort();
    request<Face[]>(`/api/people/members?person=${person}`, { signal: controller.signal }).then(data => { if (!controller.signal.aborted) setFaces(data); }, e => { if (!controller.signal.aborted) setError((e as Error).message); });
    request<Results>(`/api/images?person=${person}&limit=80`, { signal: controller.signal }).then(data => { setPictures(data.items); setMore(data.hasMore); }, e => { if (!controller.signal.aborted) setError((e as Error).message); });
    return () => controller.abort();
  }, [person, state?.processed, selected?.photos, selected?.name, memberRevision]);
  const update = async (values: object) => {
    stateRequest.current += 1;
    setBusy(true); setError('');
    try {
      const result = await post<State>('/api/people', values);
      stateRequest.current += 1;
      setState(result);
      const resolved = result.selectedPerson ?? person;
      if (resolved && !result.people.some(item => item.id === resolved)) {
        setPerson(''); setFaces([]); setPictures([]);
      } else if (resolved) {
        setPerson(resolved);
        setMemberRevision(value => value + 1);
      }
      return true;
    } catch (e) { setError((e as Error).message); return false; }
    finally { stateRequest.current += 1; setBusy(false); }
  };
  useEffect(() => {
    const dialog = pickerDialog.current;
    if (picker && dialog && !dialog.open) {
      setNewName(''); setApplyGroup(!selected?.name); dialog.showModal();
    } else if (!picker) dialog?.close();
  }, [picker, selected?.name]);
  const choosePerson = async (target?: string) => {
    const success = await update(picker === 'merge'
      ? { action: 'merge', source: person, target }
      : { action: 'assign', face: picker, person: target, name: newName, scope: applyGroup ? 'group' : 'face' });
    if (success) { setPicker(null); if (picker === 'merge' && target) setPerson(target); }
  };
  const loadMore = async () => {
    const generation = photoRequest.current;
    setBusy(true);
    try {
      const data = await request<Results>(`/api/images?person=${person}&limit=80&offset=${pictures.length}`);
      if (generation !== photoRequest.current) return;
      setPictures(previous => [...previous, ...data.items]); setMore(data.hasMore);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  return <section className="people-page" aria-label="People">
    <header className="people-heading"><div>{person && <button className="text-button" onClick={() => setPerson('')}><ArrowLeft />People</button>}<h1>{selected ? selected.name || 'Unnamed person' : 'People'}</h1></div>
      {state?.enabled && <div className="people-progress"><span role="status">{state.processed.toLocaleString()} of {state.total.toLocaleString()} photos checked{state.paused ? ' · Paused' : state.state === 'loading' ? ' · Setting up' : state.state === 'indexing' ? ' · Processing' : state.state === 'waiting' ? ' · Waiting for processing time' : ''}</span><button className="text-button" disabled={busy} onClick={() => void update({ action: state.paused ? 'resume' : 'pause' })}>{state.paused ? 'Resume' : 'Pause'}</button>{state.state === 'error' && <button className="text-button" disabled={busy} onClick={() => void update({ action: 'resume' })}>Retry</button>}</div>}
    </header>
    {error || state?.error ? <p className="error-copy" role="alert">{error || state?.error}</p> : null}
    {!state ? <p role="status">Loading People…</p> : !state.enabled ? <div className="people-setup"><Users /><h2>Find the people in your photos</h2><p>Group similar faces on this Mac, then add names and correct matches.</p><p className="muted">Setup downloads about 39 MB of face models once. Face processing uses up to two CPU threads and saves progress as it goes.</p><label className="check"><input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} /><span>Enable local face processing for this library.</span></label><button className="text-button primary" disabled={!consent || busy} onClick={() => void update({ action: 'enable', consent: true })}>Enable People</button></div>
    : selected ? <>
      <div className="people-edit"><form onSubmit={event => { event.preventDefault(); void update({ action: 'name', person, name }); }}><label htmlFor="person-name">Name</label><input id="person-name" value={name} maxLength={80} onChange={event => setName(event.target.value)} placeholder="Add a name" /><button className="text-button secondary" disabled={busy || !name.trim()}>Save name</button></form>
        {state.people.length > 1 && <button className="text-button secondary" disabled={busy} onClick={() => setPicker('merge')}>Same person? Merge groups</button>}
      </div>
      <details className="face-corrections"><summary>Review detected faces</summary><p className="muted">Separate an incorrect match into a new group, or dismiss a false detection.</p><div className="face-review-grid">{faces.map(face => {
        const assignedName = selected?.name || face.name || '';
        return <div key={face.id}><img loading="lazy" decoding="async" src={`/api/people/face/${face.id}`} alt="Detected face" /><span className="face-assignment" data-named={!!assignedName || undefined}>{assignedName && <Check />}{assignedName || 'Unnamed person'}</span><button className="text-button" disabled={busy} onClick={() => setPicker(face.id)}>{assignedName ? 'Change person' : 'Name or match person'}</button><button className="text-button" disabled={busy} onClick={() => void update({ action: 'separate', face: face.id })}>Separate face</button><button className="text-button" disabled={busy} onClick={() => void update({ action: 'ignore', face: face.id })}>Not a face</button></div>;
      })}</div></details>
      {!!pictures.length && <Gallery items={pictures} sections onOpen={index => onOpen(pictures[index])} />}{more && <button className="text-button secondary" disabled={busy} onClick={() => void loadMore()}>Load more photos</button>}
    </> : <>
      {!state.people.length ? <div className="people-empty"><Users /><h2>{state.processed < state.total ? 'Looking for faces' : 'No face groups yet'}</h2><p className="muted">Groups appear as photos are processed. Small, blurred, or turned-away faces may be missed.</p></div> : <div className="people-grid">{people.map(item => <button className="person-card" key={item.id} onClick={() => setPerson(item.id)}><img loading="lazy" decoding="async" src={`/api/people/face/${item.cover}`} alt="" /><strong>{item.name || 'Add a name'}</strong><span>{item.photos.toLocaleString()} {item.photos === 1 ? 'photo' : 'photos'}</span></button>)}</div>}
    </>}
    <dialog className="person-picker" ref={pickerDialog} aria-label={picker === 'merge' ? 'Merge person groups' : 'Name or match person'} onCancel={() => setPicker(null)}>
      <header><h2>{picker === 'merge' ? 'Who is the same person?' : 'Who is this?'}</h2><button className="text-button" disabled={busy} onClick={() => setPicker(null)}>Close</button></header>
      {picker && picker !== 'merge' && <img className="assign-face" src={`/api/people/face/${picker}`} alt="Face to name or match" />}
      <p>Choose a person by their photo and name.</p>
      <div className="person-picker-grid">{picker && people.filter(item => picker !== 'merge' || item.id !== person).map(item => <button className="person-card" key={item.id} disabled={busy} aria-pressed={picker === 'merge' ? undefined : item.id === assignedPerson} onClick={() => void choosePerson(item.id)}><img loading="lazy" decoding="async" src={`/api/people/face/${item.cover}`} alt="" /><strong>{item.name || 'Unnamed person'}</strong>{picker !== 'merge' && item.id === assignedPerson && <span className="person-current"><Check />{item.name ? 'Current person' : 'Current group'}</span>}<span>{item.photos} {item.photos === 1 ? 'photo' : 'photos'}</span></button>)}</div>
      {picker && picker !== 'merge' && selected && selected.photos > 1 && <label className="check person-scope"><input type="checkbox" checked={applyGroup} onChange={event => setApplyGroup(event.target.checked)} /><span>Apply to all {selected.photos.toLocaleString()} photos in this group</span></label>}
      {picker && picker !== 'merge' && <form onSubmit={event => { event.preventDefault(); void choosePerson(); }}><label htmlFor="new-person-name">Or create a person</label><input id="new-person-name" maxLength={80} value={newName} onChange={event => setNewName(event.target.value)} placeholder="Enter a name" /><button className="text-button secondary" disabled={busy || !newName.trim()}>Save person</button></form>}
      {error && <p className="error-copy" role="alert">{error}</p>}
    </dialog>
    {state && (state.enabled || !!state.people.length) && <details className="people-settings"><summary>People settings</summary><p>Clear face crops, names and groups for this library. Your photos stay in their folders. Processing turns off.</p><label className="check"><input type="checkbox" checked={clearConfirmed} onChange={event => setClearConfirmed(event.target.checked)} /><span>Clear this library’s face data.</span></label><button className="text-button danger-action" disabled={busy || !clearConfirmed} onClick={() => { void update({ action: 'clear', confirmed: true }).then(success => { if (success) { setPerson(''); setConsent(false); setClearConfirmed(false); } }); }}>Clear face data</button><button className="text-button" onClick={() => void refresh()}>Refresh</button></details>}
  </section>;
}
