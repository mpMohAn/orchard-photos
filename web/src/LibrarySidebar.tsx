import { useEffect, useState } from 'react';
import { Copy, Folder, FolderPlus, Images } from 'lucide-react';
import { Lockup } from './Logo';
import WorkspaceFolders from './WorkspaceFolders';
import { IndexingSettings } from './Panels';
import { Progress } from './Progress';
import { searchWork } from './Activity';
import { post, request, type Facets, type Status } from './types';

/** Navigation scopes the existing library. Switching libraries still opens one at a time. */
export default function LibrarySidebar({ status, folder, open, onFolder, onAll, onChoose, onOpened, onRefresh, onDuplicates }: {
  status: Status; folder: string; open: boolean; onFolder: (path: string) => void; onAll: () => void;
  onChoose: () => void; onOpened: (status: Status) => void; onRefresh: () => void; onDuplicates: () => void;
}) {
  const [facets, setFacets] = useState<Facets | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const root = status.folder!.id;
  const revision = status.library!.revision;
  useEffect(() => {
    const controller = new AbortController();
    setFacets(null); setError('');
    request<Facets>('/api/facets', { signal: controller.signal }).then(setFacets, e => {
      if (!controller.signal.aborted) setError((e as Error).message);
    });
    return () => controller.abort();
  }, [root, revision]);
  const switchLibrary = async (path: string) => {
    setBusy(true); setError('');
    try { onOpened(await post<Status>('/api/folder', { path })); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  const library = status.library!;
  const work = searchWork(library.search);
  const searchLabel = work?.label ?? (library.search.state === 'ready' ? 'Visual search ready' : 'Visual search not set up');
  return <aside id="library-sidebar" className="library-sidebar" data-open={open || undefined} aria-label="Library workspace">
    <button className="sidebar-brand" aria-label="Orchard, show every image" onClick={onAll}><Lockup /></button>
    <nav className="sidebar-navigation" aria-label="Photo libraries">
      <p className="sidebar-label">Library</p>
      <button className="sidebar-row" aria-current={!folder ? 'page' : undefined} onClick={onAll}><Images /><span>All photos</span><span className="sidebar-count">{library.counts.images.toLocaleString()}</span></button>
      <button className="sidebar-row" onClick={onDuplicates}><Copy /><span>Duplicates</span></button>
      <WorkspaceFolders status={status} onOpened={onOpened} onFolder={onFolder} />
      <div className="sidebar-section"><p className="sidebar-label">Folders</p><button className="icon-button" aria-label="Choose library" onClick={onChoose}><FolderPlus /></button></div>
      <p className="sidebar-root" title={status.folder!.path}>{status.folder!.name}</p>
      {!facets && !error && <p className="sidebar-note">Loading folders…</p>}
      {facets && !facets.folders.some(item => item.path) && <p className="sidebar-note">Images are in the library folder.</p>}
      {facets?.folders.filter(item => item.path).map(item => <button key={item.path} className="sidebar-row" aria-label={`Folder ${item.path}`} aria-current={folder === item.path ? 'page' : undefined} title={item.path} onClick={() => onFolder(item.path)}><Folder /><span>{item.path}</span><span className="sidebar-count">{item.count.toLocaleString()}</span></button>)}
      {status.recent.some(item => item.path !== status.folder!.path) && <><p className="sidebar-label recent-label">Recent libraries</p>{status.recent.filter(item => item.path !== status.folder!.path).map(item => <button key={item.path} className="sidebar-row" disabled={busy || !item.available} title={item.available ? item.path : `${item.path} is unavailable`} onClick={() => void switchLibrary(item.path)}><Folder /><span>{item.label}</span></button>)}</>}
      {busy && <p className="sidebar-note" role="status">Opening library…</p>}
      {error && <p className="error-copy" role="alert">{error}</p>}
    </nav>
    <div className="sidebar-indexing">
      <p className="sidebar-label">Background activity</p>
      <p className="indexing-state" aria-live="polite">{searchLabel}</p>
      {work && !work.error && <><Progress value={work.value} label="Visual search progress" /><p className="sidebar-note numbers">{work.detail}</p></>}
      {library.scan.state === 'scanning' && <p className="sidebar-note">Scanning photo folders…</p>}
      <IndexingSettings compact onRefresh={onRefresh} /><p className="sidebar-note">Pause takes effect after the current batch. CPU changes apply on restart.</p>
    </div>
  </aside>;
}
