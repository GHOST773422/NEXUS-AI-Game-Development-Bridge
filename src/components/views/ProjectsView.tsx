import { useMemo, useState } from 'react';
import { FolderSearch } from 'lucide-react';
import {
  EngineKind,
  NavSection,
  RegisteredProject,
  RuntimeEnvironmentInfo,
} from '../../types/nexus';
import { StatusText } from '../ui/StatusText';

interface ProjectsViewProps {
  runtime: RuntimeEnvironmentInfo;
  projects: RegisteredProject[];
  demoMode: boolean;
  onRegisterProject: (input: {
    name: string;
    engine: EngineKind;
    rootPath: string;
    engineVersion: string;
  }) => void;
  onAssociateEngine: (projectId: string, engine: EngineKind) => void;
  onRemoveProject: (projectId: string) => void;
  onLoadDemoFixture: () => void;
  onNavigate: (section: NavSection) => void;
}

export function ProjectsView({
  runtime,
  projects,
  demoMode,
  onRegisterProject,
  onAssociateEngine,
  onRemoveProject,
  onLoadDemoFixture,
  onNavigate,
}: ProjectsViewProps) {
  const [search, setSearch] = useState('');
  const [engineFilter, setEngineFilter] = useState<'All' | EngineKind>('All');
  const [selectedId, setSelectedId] = useState<string | null>(projects[0]?.id ?? null);
  const [showRegisterForm, setShowRegisterForm] = useState(false);

  const [nameDraft, setNameDraft] = useState('');
  const [pathDraft, setPathDraft] = useState('');
  const [engineDraft, setEngineDraft] = useState<EngineKind>(EngineKind.Unity);
  const [versionDraft, setVersionDraft] = useState('');

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return projects.filter((p) => {
      if (engineFilter !== 'All' && p.engine !== engineFilter) return false;
      if (!q) return true;
      return (
        p.name.toLowerCase().includes(q) ||
        p.rootPath.toLowerCase().includes(q) ||
        p.engine.toLowerCase().includes(q)
      );
    });
  }, [projects, search, engineFilter]);

  const selectedProject = filtered.find((p) => p.id === selectedId) ?? filtered[0] ?? null;

  const handleSubmitRegister = (e: React.FormEvent) => {
    e.preventDefault();
    if (!nameDraft.trim() || !pathDraft.trim()) return;
    onRegisterProject({
      name: nameDraft.trim(),
      engine: engineDraft,
      rootPath: pathDraft.trim(),
      engineVersion: versionDraft.trim() || 'Unverified',
    });
    setNameDraft('');
    setPathDraft('');
    setVersionDraft('');
    setShowRegisterForm(false);
  };

  return (
    <div className="space-y-8">
      <section className="flex flex-col lg:flex-row lg:items-end justify-between gap-4 pb-6 border-b border-[#1E293B]">
        <div className="space-y-1.5 max-w-3xl">
          <h2 className="font-display text-xl font-semibold text-[#F1F5F9]">Project Manager</h2>
          <p className="text-sm text-[#94A3B8]">
            Register, browse, inspect, and associate Unity or Godot project directories with NEXUS.
            Registered projects stay Disconnected until a local engine adapter attaches.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3 shrink-0">
          {!demoMode && projects.length === 0 && (
            <button
              type="button"
              onClick={onLoadDemoFixture}
              className="px-3.5 py-2 text-xs font-medium rounded-md border border-[#1E293B] bg-[#121923] text-[#94A3B8] hover:text-[#F1F5F9] hover:border-[#3987F5] transition-colors whitespace-nowrap shrink-0"
            >
              Load Demo Projects
            </button>
          )}
          <button
            type="button"
            onClick={() => setShowRegisterForm((v) => !v)}
            className="px-4 py-2 text-xs font-semibold rounded-md bg-[#35D6C5] text-[#081016] hover:bg-[#4BE0D0] transition-colors whitespace-nowrap shrink-0"
          >
            {showRegisterForm ? 'Cancel Registration' : 'Register Project'}
          </button>
        </div>
      </section>

      {showRegisterForm && (
        <form
          onSubmit={handleSubmitRegister}
          className="p-5 rounded-lg bg-[#121923] border border-[#35D6C5]/40 space-y-4"
        >
          <div className="flex items-center justify-between gap-2">
            <h3 className="font-display text-base font-semibold text-[#F1F5F9]">
              Register Game Project Directory
            </h3>
            <span className="text-xs text-[#94A3B8]">Sandboxed to declared root path</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
            <label className="space-y-1">
              <span className="text-[#94A3B8]">Project Name</span>
              <input
                type="text"
                required
                value={nameDraft}
                onChange={(e) => setNameDraft(e.target.value)}
                placeholder="e.g. Starship Tactics"
                className="w-full px-3 py-2 rounded bg-[#0B0F14] border border-[#1E293B] text-[#F1F5F9] focus:outline-none focus:border-[#35D6C5]"
              />
            </label>

            <label className="space-y-1">
              <span className="text-[#94A3B8]">Engine Association</span>
              <select
                value={engineDraft}
                onChange={(e) => setEngineDraft(e.target.value as EngineKind)}
                className="w-full px-3 py-2 rounded bg-[#0B0F14] border border-[#1E293B] text-[#F1F5F9] focus:outline-none focus:border-[#35D6C5]"
              >
                <option value={EngineKind.Unity}>Unity</option>
                <option value={EngineKind.Godot}>Godot</option>
              </select>
            </label>

            <label className="space-y-1">
              <span className="text-[#94A3B8]">Local Project Root Path</span>
              <input
                type="text"
                required
                value={pathDraft}
                onChange={(e) => setPathDraft(e.target.value)}
                placeholder="C:\Games\StarshipTactics"
                className="w-full px-3 py-2 rounded bg-[#0B0F14] border border-[#1E293B] font-mono text-[#F1F5F9] focus:outline-none focus:border-[#35D6C5]"
              />
            </label>

            <label className="space-y-1">
              <span className="text-[#94A3B8]">Declared Version (Optional)</span>
              <input
                type="text"
                value={versionDraft}
                onChange={(e) => setVersionDraft(e.target.value)}
                placeholder="e.g. 2022.3.42f1 or 4.3"
                className="w-full px-3 py-2 rounded bg-[#0B0F14] border border-[#1E293B] font-mono text-[#F1F5F9] focus:outline-none focus:border-[#35D6C5]"
              />
            </label>
          </div>

          <div className="flex justify-end">
            <button
              type="submit"
              className="px-4 py-2 text-xs font-semibold rounded-md bg-[#35D6C5] text-[#081016] hover:bg-[#4BE0D0] transition-colors whitespace-nowrap shrink-0"
            >
              Add Project to Registry
            </button>
          </div>
        </form>
      )}

      {projects.length === 0 ? (
        <section className="p-8 rounded-lg bg-[#121923] border border-[#1E293B] flex flex-col items-start gap-4 max-w-2xl">
          <div className="p-2.5 rounded-md bg-[#0B0F14] border border-[#1E293B] text-[#3987F5]">
            <FolderSearch className="h-5 w-5" aria-hidden="true" />
          </div>
          <div className="space-y-2">
            <h3 className="font-display text-base font-semibold text-[#F1F5F9]">
              No Projects Registered
            </h3>
            <p className="text-sm text-[#94A3B8] leading-relaxed">
              {runtime.hasTauriIPC
                ? 'Register a Unity or Godot directory above or connect the Python daemon for automatic discovery.'
                : 'Automatic local filesystem discovery requires the Windows desktop shell and Python daemon. You can register a project manifest manually above or load clearly labeled demonstration fixtures.'}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => setShowRegisterForm(true)}
              className="px-4 py-2 text-xs font-semibold rounded-md bg-[#35D6C5] text-[#081016] hover:bg-[#4BE0D0] transition-colors whitespace-nowrap shrink-0"
            >
              Register Project
            </button>
            <button
              type="button"
              onClick={() => onNavigate(NavSection.Engines)}
              className="px-4 py-2 text-xs font-medium rounded-md border border-[#1E293B] text-[#94A3B8] hover:text-[#F1F5F9] transition-colors whitespace-nowrap shrink-0"
            >
              Inspect Engine Adapters
            </button>
          </div>
        </section>
      ) : (
        <section className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-start">
          <div className="xl:col-span-7 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <input
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search registered projects or paths..."
                aria-label="Search registered projects"
                className="flex-1 px-3.5 py-2 rounded-md bg-[#121923] border border-[#1E293B] text-sm text-[#F1F5F9] placeholder:text-[#64748B] focus:outline-none focus:border-[#35D6C5]"
              />
              <div className="flex items-center gap-1 p-1 rounded-md bg-[#121923] border border-[#1E293B] shrink-0">
                {(['All', EngineKind.Unity, EngineKind.Godot] as const).map((eng) => (
                  <button
                    key={eng}
                    type="button"
                    onClick={() => setEngineFilter(eng)}
                    className={`px-3 py-1 text-xs font-medium rounded transition-colors whitespace-nowrap shrink-0 ${
                      engineFilter === eng
                        ? 'bg-[#1B2636] text-[#35D6C5]'
                        : 'text-[#94A3B8] hover:text-[#F1F5F9]'
                    }`}
                  >
                    {eng}
                  </button>
                ))}
              </div>
            </div>

            <div className="overflow-x-auto rounded-lg border border-[#1E293B] bg-[#121923]">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-[#1E293B] text-xs font-medium text-[#94A3B8]">
                    <th className="py-3 px-4">Project</th>
                    <th className="py-3 px-4">Engine</th>
                    <th className="py-3 px-4">Version</th>
                    <th className="py-3 px-4">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#1E293B] text-sm">
                  {filtered.map((proj) => {
                    const active = selectedProject?.id === proj.id;
                    return (
                      <tr
                        key={proj.id}
                        onClick={() => setSelectedId(proj.id)}
                        className={`cursor-pointer transition-colors ${
                          active ? 'bg-[#182230]' : 'hover:bg-[#161F2C]'
                        }`}
                      >
                        <td className="py-3 px-4">
                          <div className="font-medium text-[#F1F5F9]">{proj.name}</div>
                          <div className="font-mono text-xs text-[#94A3B8] truncate max-w-xs">
                            {proj.rootPath}
                          </div>
                        </td>
                        <td className="py-3 px-4 text-xs text-[#F1F5F9] whitespace-nowrap">
                          {proj.engine}
                        </td>
                        <td className="py-3 px-4 font-mono text-xs text-[#94A3B8] whitespace-nowrap">
                          {proj.engineVersion}
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap">
                          <StatusText status={proj.status} />
                        </td>
                      </tr>
                    );
                  })}
                  {filtered.length === 0 && (
                    <tr>
                      <td colSpan={4} className="py-6 px-4 text-center text-sm text-[#94A3B8]">
                        No projects match your current filter.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {selectedProject && (
            <aside className="xl:col-span-5 p-5 rounded-lg bg-[#121923] border border-[#1E293B] space-y-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-xs text-[#94A3B8]">
                    {selectedProject.isDemoFixture ? 'Demonstration Fixture' : 'Project Inspector'}
                  </div>
                  <h3 className="font-display text-base font-semibold text-[#F1F5F9] mt-0.5">
                    {selectedProject.name}
                  </h3>
                </div>
                <StatusText status={selectedProject.status} />
              </div>

              <p className="text-xs text-[#94A3B8] leading-relaxed">{selectedProject.notes}</p>

              <dl className="divide-y divide-[#1E293B] text-xs">
                <div className="py-2.5 flex justify-between gap-4">
                  <dt className="text-[#94A3B8]">Root Directory</dt>
                  <dd className="font-mono text-[#F1F5F9] text-right break-all">
                    {selectedProject.rootPath}
                  </dd>
                </div>
                <div className="py-2.5 flex items-center justify-between gap-4">
                  <dt className="text-[#94A3B8]">Associated Engine</dt>
                  <dd>
                    <select
                      aria-label="Associated engine"
                      value={selectedProject.engine}
                      onChange={(e) =>
                        onAssociateEngine(selectedProject.id, e.target.value as EngineKind)
                      }
                      className="px-2.5 py-1 rounded bg-[#0B0F14] border border-[#1E293B] text-xs text-[#F1F5F9] focus:outline-none focus:border-[#35D6C5]"
                    >
                      <option value={EngineKind.Unity}>Unity</option>
                      <option value={EngineKind.Godot}>Godot</option>
                    </select>
                  </dd>
                </div>
                <div className="py-2.5 flex justify-between gap-4">
                  <dt className="text-[#94A3B8]">Engine Version</dt>
                  <dd className="font-mono text-[#F1F5F9]">{selectedProject.engineVersion}</dd>
                </div>
                <div className="py-2.5 flex justify-between gap-4">
                  <dt className="text-[#94A3B8]">Active Scene</dt>
                  <dd className="font-mono text-[#94A3B8] text-right">
                    {selectedProject.activeScene ?? 'Unavailable (Editor Disconnected)'}
                  </dd>
                </div>
              </dl>

              <div className="flex items-center justify-between gap-3 pt-2 border-t border-[#1E293B]">
                <button
                  type="button"
                  onClick={() => onNavigate(NavSection.Tasks)}
                  className="px-3.5 py-1.5 text-xs font-medium rounded-md border border-[#1E293B] text-[#F1F5F9] hover:border-[#35D6C5] transition-colors whitespace-nowrap shrink-0"
                >
                  Open Task Planner
                </button>
                <button
                  type="button"
                  onClick={() => onRemoveProject(selectedProject.id)}
                  className="px-3.5 py-1.5 text-xs font-medium rounded-md border border-[#E5534B]/40 text-[#E5534B] hover:bg-[#E5534B]/10 transition-colors whitespace-nowrap shrink-0"
                >
                  Remove Registration
                </button>
              </div>
            </aside>
          )}
        </section>
      )}
    </div>
  );
}
