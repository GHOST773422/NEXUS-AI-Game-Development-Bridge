import { memo, useMemo } from 'react';
import {
  ARCHITECTURAL_SUBSYSTEMS,
  ENVIRONMENT_INCOMPATIBILITIES,
} from '../../data/architectureSpec';
import { formatCachedLocalTime } from '../../services/formatCache';
import {
  AIProviderConnection,
  BridgeProbeResult,
  DaemonMcpStatusPayload,
  EngineCardState,
  NavSection,
  NexusStatus,
  RegisteredProject,
  RestHealthResponse,
  RuntimeEnvironmentInfo,
  SessionActivityEntry,
  TaskRecord,
} from '../../types/nexus';
import { StatusText } from '../ui/StatusText';

interface DashboardViewProps {
  runtime: RuntimeEnvironmentInfo;
  previewHealth: RestHealthResponse | null;
  lastProbe: BridgeProbeResult | null;
  providers: AIProviderConnection[];
  engines: EngineCardState[];
  projects: RegisteredProject[];
  tasks: TaskRecord[];
  activityLog: SessionActivityEntry[];
  demoMode: boolean;
  daemonAuthenticated?: boolean;
  mcpStatus?: DaemonMcpStatusPayload | null;
  onNavigate: (section: NavSection) => void;
}

export const DashboardView = memo(function DashboardView({
  runtime,
  previewHealth,
  lastProbe,
  providers,
  engines,
  projects,
  tasks,
  activityLog,
  demoMode,
  daemonAuthenticated = false,
  mcpStatus = null,
  onNavigate,
}: DashboardViewProps) {
  const bridgeStatus = lastProbe ? lastProbe.status : NexusStatus.Disconnected;
  const connectedEngines = useMemo(
    () => engines.filter((e) => e.connectionStatus === NexusStatus.Connected).length,
    [engines]
  );
  const { activeTasks, completedTasks } = useMemo(() => {
    let active = 0;
    let completed = 0;
    for (const t of tasks) {
      if (t.status === NexusStatus.Running) active++;
      else if (t.status === NexusStatus.Available || t.status === NexusStatus.Connected)
        completed++;
    }
    return { activeTasks: active, completedTasks: completed };
  }, [tasks]);
  const activeBridgeLinks =
    (bridgeStatus === NexusStatus.Connected ? 1 : 0) + (mcpStatus ? 1 : 0) + activeTasks;
  const errorsAndWarnings = useMemo(
    () => activityLog.filter((e) => e.severity === 'error' || e.severity === 'warning'),
    [activityLog]
  );
  const recentActivity = useMemo(() => activityLog.slice(0, 6), [activityLog]);
  const { configuredProviders, enabledProvidersCount } = useMemo(() => {
    let configured = 0;
    let enabled = 0;
    for (const p of providers) {
      if (p.credentialConfigured) configured++;
      if (p.enabled) enabled++;
    }
    return { configuredProviders: configured, enabledProvidersCount: enabled };
  }, [providers]);
  const hasDemoProject = useMemo(() => projects.some((p) => p.isDemoFixture), [projects]);

  return (
    <div className="space-y-8">
      {demoMode && (
        <div className="px-4 py-3 rounded-lg bg-[#1F1A10] border border-[#D99B38]/40 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
          <span className="text-[#F4BF64] font-medium">
            Demonstration Fixture Active — Sample projects, task plan, and activity entries are
            labeled [Demo] for layout review.
          </span>
          <span className="text-[#94A3B8] font-mono whitespace-nowrap">
            Engine connections remain Disconnected
          </span>
        </div>
      )}

      <section className="flex flex-col lg:flex-row lg:items-end justify-between gap-4 pb-6 border-b border-[#1E293B]">
        <div className="max-w-3xl space-y-2">
          <div className="flex flex-wrap items-center gap-2 text-xs text-[#94A3B8]">
            <span>AI Game Development Bridge</span>
            <span aria-hidden="true">·</span>
            <span>
              {runtime.hostKind === 'TauriDesktop'
                ? 'Windows Desktop Host'
                : 'AI Studio Web Preview'}
            </span>
            <span aria-hidden="true">·</span>
            <span>{configuredProviders} AI Credential(s) Ready</span>
          </div>
          <h2 className="font-display text-2xl font-semibold tracking-tight text-[#F1F5F9]">
            Operational Control Overview
          </h2>
          <p className="text-sm leading-relaxed text-[#94A3B8]">
            Live overview of bridge connectivity, AI sessions, engine adapters, registered projects,
            orchestrator tasks, system health, and diagnostics.
          </p>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <button
            type="button"
            onClick={() => onNavigate(NavSection.Connections)}
            className="px-4 py-2 text-xs font-medium rounded-md border border-[#1E293B] bg-[#121923] text-[#F1F5F9] hover:border-[#3987F5] transition-colors whitespace-nowrap shrink-0"
          >
            Manage Connections
          </button>
        </div>
      </section>

      <section
        aria-label="Primary operational metrics"
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4"
      >
        <button
          type="button"
          onClick={() => onNavigate(NavSection.Connections)}
          className="text-left p-4 rounded-lg bg-[#121923] border border-[#1E293B] hover:border-[#35D6C5]/50 transition-colors space-y-2"
        >
          <div className="text-xs text-[#94A3B8]">Bridge Status</div>
          <div className="font-mono text-base font-semibold text-[#F1F5F9] tabular-nums">
            127.0.0.1:47100
          </div>
          <StatusText status={bridgeStatus} />
        </button>

        <button
          type="button"
          onClick={() => onNavigate(NavSection.Connections)}
          className="text-left p-4 rounded-lg bg-[#121923] border border-[#1E293B] hover:border-[#35D6C5]/50 transition-colors space-y-2"
        >
          <div className="text-xs text-[#94A3B8]">Live Bridge & MCP Links</div>
          <div className="font-display text-xl font-semibold text-[#F1F5F9] tabular-nums">
            {activeBridgeLinks}
          </div>
          <span className="text-xs text-[#94A3B8]">
            {enabledProvidersCount} provider(s) ·{' '}
            {mcpStatus ? `${mcpStatus.tools.length} MCP tools` : 'MCP offline'}
          </span>
        </button>

        <button
          type="button"
          onClick={() => onNavigate(NavSection.Engines)}
          className="text-left p-4 rounded-lg bg-[#121923] border border-[#1E293B] hover:border-[#35D6C5]/50 transition-colors space-y-2"
        >
          <div className="text-xs text-[#94A3B8]">Connected Engines</div>
          <div className="font-display text-xl font-semibold text-[#F1F5F9] tabular-nums">
            {connectedEngines} / {engines.length}
          </div>
          <StatusText
            status={connectedEngines > 0 ? NexusStatus.Connected : NexusStatus.Disconnected}
          />
        </button>

        <button
          type="button"
          onClick={() => onNavigate(NavSection.Projects)}
          className="text-left p-4 rounded-lg bg-[#121923] border border-[#1E293B] hover:border-[#35D6C5]/50 transition-colors space-y-2"
        >
          <div className="text-xs text-[#94A3B8]">Registered Projects</div>
          <div className="font-display text-xl font-semibold text-[#F1F5F9] tabular-nums">
            {projects.length}
          </div>
          <span className="text-xs text-[#94A3B8]">
            {hasDemoProject ? 'Includes Demo Fixture' : 'Local Workspace'}
          </span>
        </button>

        <button
          type="button"
          onClick={() => onNavigate(NavSection.Tasks)}
          className="text-left p-4 rounded-lg bg-[#121923] border border-[#1E293B] hover:border-[#35D6C5]/50 transition-colors space-y-2"
        >
          <div className="text-xs text-[#94A3B8]">Active Tasks</div>
          <div className="font-display text-xl font-semibold text-[#F1F5F9] tabular-nums">
            {activeTasks}
          </div>
          <span className="text-xs text-[#94A3B8] tabular-nums">{tasks.length} queued/planned</span>
        </button>

        <button
          type="button"
          onClick={() => onNavigate(NavSection.Tasks)}
          className="text-left p-4 rounded-lg bg-[#121923] border border-[#1E293B] hover:border-[#35D6C5]/50 transition-colors space-y-2"
        >
          <div className="text-xs text-[#94A3B8]">Completed Tasks</div>
          <div className="font-display text-xl font-semibold text-[#F1F5F9] tabular-nums">
            {completedTasks}
          </div>
          <span className="text-xs text-[#94A3B8]">Verified completions</span>
        </button>
      </section>

      <section className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        <div className="lg:col-span-7 p-5 rounded-lg bg-[#121923] border border-[#1E293B] space-y-4">
          <div className="flex items-center justify-between gap-4">
            <h3 className="font-display text-base font-semibold text-[#F1F5F9]">Recent Activity</h3>
            <button
              type="button"
              onClick={() => onNavigate(NavSection.Activity)}
              className="text-xs font-medium text-[#35D6C5] hover:underline whitespace-nowrap shrink-0"
            >
              View Full Stream
            </button>
          </div>

          {recentActivity.length > 0 ? (
            <div className="divide-y divide-[#1E293B]">
              {recentActivity.map((entry) => (
                <div key={entry.id} className="py-3 flex items-start justify-between gap-4">
                  <div className="min-w-0 space-y-1">
                    <div className="text-sm text-[#F1F5F9]">{entry.message}</div>
                    <div className="flex flex-wrap items-center gap-2 text-xs text-[#94A3B8]">
                      <span className="font-mono tabular-nums">
                        {formatCachedLocalTime(entry.timestamp)}
                      </span>
                      <span aria-hidden="true">·</span>
                      <span>{entry.category}</span>
                      {entry.isDemoFixture && (
                        <>
                          <span aria-hidden="true">·</span>
                          <span className="text-[#D99B38]">Demonstration Data</span>
                        </>
                      )}
                    </div>
                  </div>
                  <StatusText status={entry.status} />
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-[#94A3B8]">No session events recorded yet.</p>
          )}
        </div>

        <div className="lg:col-span-5 space-y-6">
          <div className="p-5 rounded-lg bg-[#121923] border border-[#1E293B] space-y-3">
            <div className="flex items-center justify-between gap-4">
              <h3 className="font-display text-base font-semibold text-[#F1F5F9]">System Health</h3>
              <button
                type="button"
                onClick={() => onNavigate(NavSection.Diagnostics)}
                className="text-xs font-medium text-[#3987F5] hover:underline whitespace-nowrap shrink-0"
              >
                Diagnostics
              </button>
            </div>

            <dl className="divide-y divide-[#1E293B] text-xs">
              <div className="py-2.5 flex items-center justify-between gap-4">
                <dt className="text-[#94A3B8]">Frontend Control Center</dt>
                <dd>
                  <StatusText status={NexusStatus.Available} />
                </dd>
              </div>
              <div className="py-2.5 flex items-center justify-between gap-4">
                <dt className="text-[#94A3B8]">Node Preview Backend</dt>
                <dd>
                  <StatusText
                    status={previewHealth ? previewHealth.status : NexusStatus.Disconnected}
                  />
                </dd>
              </div>
              <div className="py-2.5 flex items-center justify-between gap-4">
                <dt className="text-[#94A3B8]">Python Background Daemon</dt>
                <dd>
                  <StatusText status={bridgeStatus} />
                </dd>
              </div>
              <div className="py-2.5 flex items-center justify-between gap-4">
                <dt className="text-[#94A3B8]">Tauri 2 Desktop Shell</dt>
                <dd>
                  <StatusText
                    status={runtime.hasTauriIPC ? NexusStatus.Connected : NexusStatus.Unavailable}
                  />
                </dd>
              </div>
              <div className="py-2.5 flex items-center justify-between gap-4">
                <dt className="text-[#94A3B8]">Subsystem Runtime</dt>
                <dd className="font-mono tabular-nums text-[#F1F5F9]">
                  {daemonAuthenticated
                    ? `${ARCHITECTURAL_SUBSYSTEMS.length} Modules (${connectedEngines > 0 ? 'Engine Live' : 'Daemon Active'})`
                    : `${ARCHITECTURAL_SUBSYSTEMS.length} Specs (${runtime.hasTauriIPC ? 'Desktop Shell' : 'Web Preview'})`}
                </dd>
              </div>
            </dl>
          </div>

          <div className="p-5 rounded-lg bg-[#121923] border border-[#1E293B] space-y-3">
            <div className="flex items-center justify-between gap-4">
              <h3 className="font-display text-base font-semibold text-[#F1F5F9]">
                Errors & Warnings
              </h3>
              <span className="font-mono text-xs tabular-nums text-[#94A3B8]">
                {errorsAndWarnings.length} event(s) · {ENVIRONMENT_INCOMPATIBILITIES.length} env
                boundaries
              </span>
            </div>

            {errorsAndWarnings.length > 0 ? (
              <div className="divide-y divide-[#1E293B]">
                {errorsAndWarnings.slice(0, 3).map((item) => (
                  <div key={item.id} className="py-2.5 space-y-1 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-[#F1F5F9]">{item.message}</span>
                      <StatusText status={item.status} />
                    </div>
                    {item.detail && <div className="font-mono text-[#94A3B8]">{item.detail}</div>}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-[#94A3B8] leading-relaxed">
                No runtime errors logged in this session. Note that native Windows Tauri IPC, Python
                daemon, and game engine binaries remain unavailable inside browser preview.
              </p>
            )}
          </div>
        </div>
      </section>
    </div>
  );
});
