import { useState } from 'react';
import { Folder, Plus, X } from 'lucide-react';
import { post, type Status } from './types';

export default function WorkspaceFolders({ status, onOpened, onFolder }: {
  status: Status; onOpened: (status: Status) => void; onFolder: (path: string) => void;
}) {
  const roots = status.folder?.roots ?? [];
  const [adding, setAdding] = useState(false);
  const [path, setPath] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const change = async (paths: string[], choose = false) => {
    setBusy(true); setError('');
    try {
      const next = await post<Status & { cancelled?: boolean }>(choose ? '/api/workspace/choose' : '/api/workspace', { paths });
      if (!next.cancelled) { onOpened(next); setAdding(false); setPath(''); }
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  if (status.folder?.photos) return null;
  return <section className="workspace-sources" aria-label="Workspace folders">
    <div className="sidebar-section"><p className="sidebar-label">Workspace folders</p><button className="icon-button" aria-label="Add folder to workspace" aria-expanded={adding} disabled={busy || roots.length >= 16} onClick={() => setAdding(value => !value)}><Plus /></button></div>
    {roots.map(root => <div className="workspace-source" key={root.path}>
      <button className="sidebar-row" title={root.path} aria-label={`Browse source ${root.name}`} onClick={() => onFolder(root.prefix)}><Folder /><span>{root.prefix || root.name}</span></button>
      {roots.length > 1 && <button className="icon-button" aria-label={`Remove ${root.prefix} from workspace`} title="Remove from workspace" disabled={busy} onClick={() => void change(roots.filter(item => item.path !== root.path).map(item => item.path))}><X /></button>}
    </div>)}
    {adding && <form className="workspace-add" onSubmit={event => { event.preventDefault(); void change([...roots.map(root => root.path), path]); }}>
      <label htmlFor="workspace-add-path">Folder path to add</label>
      <input autoFocus id="workspace-add-path" placeholder="~/Pictures/More photos" value={path} onChange={event => setPath(event.target.value)} autoCapitalize="off" spellCheck={false} disabled={busy} />
      <div className="workspace-add-actions"><button className="text-button secondary" disabled={busy || !path.trim()}>{busy ? 'Opening…' : 'Add folder'}</button>{status.picker && <button className="text-button" type="button" disabled={busy} onClick={() => void change([], true)}>Choose…</button>}</div>
    </form>}
    {error && <p className="error-copy" role="alert">{error}</p>}
  </section>;
}
