import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, Users } from 'lucide-react';
import Gallery from './Gallery';
import { post, request, type Picture, type Results } from './types';

interface Person { id: string; name: string; photos: number; cover: string }
interface Face { id: string; image_id: string; box: string }
interface State { enabled: boolean; paused: boolean; state: string; error: string; processed: number; total: number; people: Person[] }

export default function People({ onOpen }: { onOpen: (picture: Picture) => void }) {
  const [state, setState] = useState<State | null>(null);
  const [person, setPerson] = useState('');
  const [faces, setFaces] = useState<Face[]>([]);
  const [pictures, setPictures] = useState<Picture[]>([]);
  const [more, setMore] = useState(false);
  const [name, setName] = useState('');
  const [target, setTarget] = useState('');
  const [consent, setConsent] = useState(false);
  const [clearConfirmed, setClearConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const photoRequest = useRef(0);
  const selected = state?.people.find(item => item.id === person);
  const refresh = async () => {
    try { setState(await request<State>('/api/people')); }
    catch (e) { setError((e as Error).message); }
  };
  useEffect(() => {
    const controller = new AbortController();
    const load = () => request<State>('/api/people', { signal: controller.signal }).then(setState, e => { if (!controller.signal.aborted) setError((e as Error).message); });
    void load(); const timer = setInterval(() => void load(), 2500);
    return () => { controller.abort(); clearInterval(timer); };
  }, []);
  useEffect(() => {
    setName(selected?.name ?? ''); setTarget('');
  }, [person, selected?.name]);
  useEffect(() => {
    const controller = new AbortController();
    photoRequest.current += 1;
    setFaces([]); setPictures([]);
    if (!person) return () => controller.abort();
    request<Face[]>(`/api/people/members?person=${person}`, { signal: controller.signal }).then(setFaces, e => { if (!controller.signal.aborted) setError((e as Error).message); });
    request<Results>(`/api/images?person=${person}&limit=80`, { signal: controller.signal }).then(data => { setPictures(data.items); setMore(data.hasMore); }, e => { if (!controller.signal.aborted) setError((e as Error).message); });
    return () => controller.abort();
  }, [person, state?.processed, selected?.photos]);
  const update = async (values: object) => {
    setBusy(true); setError('');
    try {
      setState(await post<State>('/api/people', values));
      if (person) setFaces(await request<Face[]>(`/api/people/members?person=${person}`));
      return true;
    } catch (e) { setError((e as Error).message); return false; }
    finally { setBusy(false); }
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
      {state?.enabled && <div className="people-progress"><span role="status">{state.processed.toLocaleString()} of {state.total.toLocaleString()} photos checked{state.paused ? ' · Paused' : state.state === 'loading' ? ' · Setting up' : state.state === 'indexing' ? ' · Processing' : ''}</span><button className="text-button" disabled={busy} onClick={() => void update({ action: state.paused ? 'resume' : 'pause' })}>{state.paused ? 'Resume' : 'Pause'}</button>{state.state === 'error' && <button className="text-button" disabled={busy} onClick={() => void update({ action: 'resume' })}>Retry</button>}</div>}
    </header>
    {error || state?.error ? <p className="error-copy" role="alert">{error || state?.error}</p> : null}
    {!state ? <p role="status">Loading People…</p> : !state.enabled ? <div className="people-setup"><Users /><h2>Find the people in your photos</h2><p>Group similar faces on this Mac, then add names and correct matches.</p><p className="muted">Setup downloads about 39 MB of face models once. Face processing uses up to two CPU threads and saves progress as it goes.</p><label className="check"><input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} /><span>Enable local face processing for this library.</span></label><button className="text-button primary" disabled={!consent || busy} onClick={() => void update({ action: 'enable', consent: true })}>Enable People</button></div>
    : selected ? <>
      <div className="people-edit"><form onSubmit={event => { event.preventDefault(); void update({ action: 'name', person, name }); }}><label htmlFor="person-name">Name</label><input id="person-name" value={name} maxLength={80} onChange={event => setName(event.target.value)} placeholder="Add a name" /><button className="text-button secondary" disabled={busy || !name.trim()}>Save name</button></form>
        {state.people.length > 1 && <div className="people-merge"><label htmlFor="merge-person">Same person?</label><select id="merge-person" value={target} onChange={event => setTarget(event.target.value)}><option value="">Choose another group</option>{state.people.filter(item => item.id !== person).map(item => <option key={item.id} value={item.id}>{item.name || 'Unnamed person'} · {item.photos} photos</option>)}</select><button className="text-button secondary" disabled={busy || !target} onClick={() => { void update({ action: 'merge', source: person, target }).then(success => { if (success) setPerson(target); }); }}>Merge groups</button></div>}
      </div>
      <details className="face-corrections"><summary>Review detected faces</summary><p className="muted">Separate an incorrect match into a new group, or dismiss a false detection.</p><div className="face-review-grid">{faces.map(face => <div key={face.id}><img loading="lazy" decoding="async" src={`/api/people/face/${face.id}`} alt="Detected face" /><button className="text-button" disabled={busy} onClick={() => void update({ action: 'separate', face: face.id })}>Separate face</button><button className="text-button" disabled={busy} onClick={() => void update({ action: 'ignore', face: face.id })}>Not a face</button></div>)}</div></details>
      {!!pictures.length && <Gallery items={pictures} sections onOpen={index => onOpen(pictures[index])} />}{more && <button className="text-button secondary" disabled={busy} onClick={() => void loadMore()}>Load more photos</button>}
    </> : <>
      {!state.people.length ? <div className="people-empty"><Users /><h2>{state.processed < state.total ? 'Looking for faces' : 'No face groups yet'}</h2><p className="muted">Groups appear as photos are processed. Small, blurred, or turned-away faces may be missed.</p></div> : <div className="people-grid">{state.people.map(item => <button className="person-card" key={item.id} onClick={() => setPerson(item.id)}><img loading="lazy" decoding="async" src={`/api/people/face/${item.cover}`} alt="" /><strong>{item.name || 'Add a name'}</strong><span>{item.photos.toLocaleString()} {item.photos === 1 ? 'photo' : 'photos'}</span></button>)}</div>}
    </>}
    {state && (state.enabled || !!state.people.length) && <details className="people-settings"><summary>People settings</summary><p>Clear face crops, names and groups for this library. Your photos stay in their folders. Processing turns off.</p><label className="check"><input type="checkbox" checked={clearConfirmed} onChange={event => setClearConfirmed(event.target.checked)} /><span>Clear this library’s face data.</span></label><button className="text-button danger-action" disabled={busy || !clearConfirmed} onClick={() => { void update({ action: 'clear', confirmed: true }).then(success => { if (success) { setPerson(''); setConsent(false); setClearConfirmed(false); } }); }}>Clear face data</button><button className="text-button" onClick={() => void refresh()}>Refresh</button></details>}
  </section>;
}
