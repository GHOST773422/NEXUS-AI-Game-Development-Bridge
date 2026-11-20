import { ENVIRONMENT_INCOMPATIBILITIES } from '../../data/architectureSpec';
import {
  BridgeProbeResult,
  DaemonLifecycleStatus,
  DesktopDiagnosticsReport,
  NexusStatus,
  RestHealthResponse,
  RuntimeEnvironmentInfo,
} from '../../types/nexus';
import { StatusText } from '../ui/StatusText';

interface DiagnosticsViewProps {
  runtime: RuntimeEnvironmentInfo;
  previewHealth: RestHealthResponse | null;
  lastProbe: BridgeProbeResult | null;
  desktopLifecycle?: DaemonLifecycleStatus | null;
  desktopDiagnostics?: DesktopDiagnosticsReport | null;
  daemonDiagnostics?: Record<string, unknown> | null;
  probing: boolean;
  onProbeBridge: () => void;
  onRefreshRuntime: () => void;
  onControlDaemon?: (action: 'start' | 'stop' | 'restart') => void;
}

export function DiagnosticsView({
  runtime,
  previewHealth,
  lastProbe,
  desktopLifecycle,
  desktopDiagnostics,
  daemonDiagnostics,
  probing,
  onProbeBridge,
  onRefreshRuntime,
  onControlDaemon,
}: DiagnosticsViewProps) {
  return (
    <div className="space-y-8">
      <section className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-[#1E293B]">
        <div className="space-y-1">
          <h2 className="font-display text-xl font-semibold text-[#F1F5F9]">
            Runtime Diagnostics & Environment Audit
          </h2>
          <p className="text-sm text-[#94A3B8]">
            Live inspection of browser/Tauri capabilities, Node preview backend, and Windows desktop
            boundaries.
          </p>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <button
            type="button"
            onClick={onRefreshRuntime}
            className="px-3.5 py-2 text-xs font-medium rounded-md border border-[#1E293B] bg-[#121923] text-[#F1F5F9] hover:border-[#3987F5] transition-colors whitespace-nowrap shrink-0"
          >
            Re-check Runtime
          </button>
          <button
            type="button"
            onClick={onProbeBridge}
            disabled={probing}
            className="px-3.5 py-2 text-xs font-semibold rounded-md bg-[#35D6C5] text-[#081016] hover:bg-[#4BE0D0] disabled:opacity-60 transition-colors whitespace-nowrap shrink-0"
          >
            {probing ? 'Probing...' : 'Probe Bridge'}
          </button>
        </div>
      </section>

      <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="p-5 rounded-lg bg-[#121923] border border-[#1E293B] space-y-3">
          <h3 className="font-display text-base font-semibold text-[#F1F5F9]">
            Observed Client & Preview Backend
          </h3>
          <dl className="divide-y divide-[#1E293B] text-xs">
            <div className="py-2.5 flex justify-between gap-4">
              <dt className="text-[#94A3B8]">Detected Host</dt>
              <dd className="font-mono text-[#F1F5F9]">{runtime.hostKind}</dd>
            </div>
            <div className="py-2.5 flex justify-between gap-4">
              <dt className="text-[#94A3B8]">Node Preview Backend (/api/health)</dt>
              <dd>
                <StatusText
                  status={
                    runtime.hasTauriIPC
                      ? NexusStatus.Unavailable
                      : previewHealth
                        ? previewHealth.status
                        : NexusStatus.Disconnected
                  }
                />
              </dd>
            </div>
            <div className="py-2.5 flex justify-between gap-4">
              <dt className="text-[#94A3B8]">Tauri 2 IPC Bridge</dt>
              <dd>
                <StatusText
                  status={runtime.hasTauriIPC ? NexusStatus.Available : NexusStatus.Unavailable}
                />
              </dd>
            </div>
            <div className="py-2.5 flex justify-between gap-4">
              <dt className="text-[#94A3B8]">WebSocket API</dt>
              <dd>
                <StatusText
                  status={
                    runtime.supportsWebSocket ? NexusStatus.Available : NexusStatus.Unavailable
                  }
                />
              </dd>
            </div>
            <div className="py-2.5 flex justify-between gap-4">
              <dt className="text-[#94A3B8]">Protocol Version</dt>
              <dd className="font-mono text-[#94A3B8]">
                {desktopDiagnostics
                  ? desktopDiagnostics.protocolVersion
                  : previewHealth
                    ? previewHealth.protocolVersion
                    : 'Unavailable'}
              </dd>
            </div>
            <div className="py-2.5 flex justify-between gap-4">
              <dt className="text-[#94A3B8]">Origin / Protocol</dt>
              <dd className="font-mono text-[#94A3B8] truncate max-w-xs" title={runtime.origin}>
                {runtime.origin} ({runtime.protocol})
              </dd>
            </div>
            <div className="py-2.5 flex justify-between gap-4">
              <dt className="text-[#94A3B8]">Last Inspected</dt>
              <dd className="font-mono tabular-nums text-[#94A3B8]">
                {new Date(runtime.detectedAt).toLocaleTimeString()}
              </dd>
            </div>
          </dl>
        </div>

        <div className="p-5 rounded-lg bg-[#121923] border border-[#1E293B] space-y-3">
          <h3 className="font-display text-base font-semibold text-[#F1F5F9]">
            Loopback Daemon Health Check
          </h3>
          {lastProbe ? (
            <dl className="divide-y divide-[#1E293B] text-xs">
              <div className="py-2.5 flex justify-between gap-4">
                <dt className="text-[#94A3B8]">Health Endpoint</dt>
                <dd className="font-mono text-[#F1F5F9]">{lastProbe.endpoint}</dd>
              </div>
              <div className="py-2.5 flex justify-between gap-4">
                <dt className="text-[#94A3B8]">Connection Status</dt>
                <dd>
                  <StatusText status={lastProbe.status} />
                </dd>
              </div>
              <div className="py-2.5 flex justify-between gap-4">
                <dt className="text-[#94A3B8]">Measured Latency</dt>
                <dd className="font-mono tabular-nums text-[#F1F5F9]">
                  {lastProbe.latencyMs !== null ? `${lastProbe.latencyMs} ms` : 'N/A'}
                </dd>
              </div>
              <div className="py-2.5 space-y-1">
                <dt className="text-[#94A3B8]">Diagnostic Output</dt>
                <dd className="font-mono text-[#94A3B8] leading-relaxed">{lastProbe.message}</dd>
              </div>
            </dl>
          ) : (
            <p className="text-sm text-[#94A3B8]">No loopback health check executed yet.</p>
          )}
        </div>
      </section>

      {(desktopLifecycle || desktopDiagnostics) && (
        <section className="p-5 rounded-lg bg-[#121923] border border-[#1E293B] space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h3 className="font-display text-base font-semibold text-[#F1F5F9]">
                Windows Desktop Shell & Daemon Supervision
              </h3>
              <p className="text-xs text-[#94A3B8]">
                Local sidecar / Python 3.12+ background process and rotating log paths.
              </p>
            </div>
            {onControlDaemon && (
              <div className="flex items-center gap-2 shrink-0">
                <button
                  type="button"
                  onClick={() => onControlDaemon('start')}
                  className="px-3 py-1.5 text-xs font-medium rounded border border-[#1E293B] bg-[#0B0F14] text-[#F1F5F9] hover:border-[#35D6C5]"
                >
                  Start Daemon
                </button>
                <button
                  type="button"
                  onClick={() => onControlDaemon('restart')}
                  className="px-3 py-1.5 text-xs font-medium rounded border border-[#1E293B] bg-[#0B0F14] text-[#F1F5F9] hover:border-[#3987F5]"
                >
                  Restart
                </button>
                <button
                  type="button"
                  onClick={() => onControlDaemon('stop')}
                  className="px-3 py-1.5 text-xs font-medium rounded border border-[#1E293B] bg-[#0B0F14] text-[#D99B38] hover:border-[#D99B38]"
                >
                  Stop
                </button>
              </div>
            )}
          </div>

          <dl className="grid grid-cols-1 md:grid-cols-2 gap-x-6 divide-y divide-[#1E293B] text-xs">
            <div className="py-2 flex justify-between gap-4">
              <dt className="text-[#94A3B8]">Launch Mode</dt>
              <dd className="font-mono text-[#F1F5F9]">
                {desktopLifecycle?.launchMode ?? 'Unavailable'}
              </dd>
            </div>
            <div className="py-2 flex justify-between gap-4">
              <dt className="text-[#94A3B8]">Daemon PID</dt>
              <dd className="font-mono tabular-nums text-[#F1F5F9]">
                {desktopLifecycle?.pid ?? 'Not running'}
              </dd>
            </div>
            <div className="py-2 flex justify-between gap-4">
              <dt className="text-[#94A3B8]">Python Detection</dt>
              <dd className="font-mono text-[#94A3B8]">
                {desktopDiagnostics?.pythonCheck ?? 'Checked on desktop host'}
              </dd>
            </div>
            <div className="py-2 flex justify-between gap-4">
              <dt className="text-[#94A3B8]">Data Directory</dt>
              <dd className="font-mono text-[#94A3B8] truncate max-w-xs">
                {desktopDiagnostics?.dataDir ?? desktopLifecycle?.dataDir ?? 'N/A'}
              </dd>
            </div>
            <div className="py-2 flex justify-between gap-4">
              <dt className="text-[#94A3B8]">Desktop Log</dt>
              <dd className="font-mono text-[#94A3B8] truncate max-w-xs">
                {desktopDiagnostics?.desktopLogPath ?? 'N/A'}
              </dd>
            </div>
            <div className="py-2 flex justify-between gap-4">
              <dt className="text-[#94A3B8]">Daemon Log</dt>
              <dd className="font-mono text-[#94A3B8] truncate max-w-xs">
                {desktopDiagnostics?.daemonLogPath ?? 'N/A'}
              </dd>
            </div>
          </dl>
        </section>
      )}

      {daemonDiagnostics && (
        <section className="p-5 rounded-lg bg-[#121923] border border-[#1E293B] space-y-3">
          <div className="flex items-center justify-between gap-3">
            <h3 className="font-display text-base font-semibold text-[#F1F5F9]">
              Live Python Daemon Diagnostics (/api/v1/diagnostics)
            </h3>
            <StatusText status={NexusStatus.Connected} />
          </div>
          <pre className="p-3 rounded bg-[#0B0F14] border border-[#1E293B] font-mono text-xs text-[#94A3B8] max-h-64 overflow-auto leading-relaxed">
            {JSON.stringify(daemonDiagnostics, null, 2)}
          </pre>
        </section>
      )}

      <section className="space-y-3">
        <h3 className="font-display text-base font-semibold text-[#F1F5F9]">
          Google AI Studio Web Sandbox vs. Windows 10/11 Desktop Matrix
        </h3>
        <div className="overflow-x-auto rounded-lg border border-[#1E293B] bg-[#121923]">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-[#1E293B] text-xs font-medium text-[#94A3B8]">
                <th className="py-3 px-4">Capability</th>
                <th className="py-3 px-4">Windows 10/11 Desktop Target</th>
                <th className="py-3 px-4">AI Studio Web Preview</th>
                <th className="py-3 px-4">Mitigation</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1E293B] text-sm">
              {ENVIRONMENT_INCOMPATIBILITIES.map((row) => (
                <tr key={row.id} className="hover:bg-[#161F2C]">
                  <td className="py-3 px-4 align-top">
                    <div className="font-medium text-[#F1F5F9]">{row.capability}</div>
                    <div className="text-xs text-[#D99B38] mt-1">{row.severity}</div>
                  </td>
                  <td className="py-3 px-4 align-top text-xs text-[#94A3B8] max-w-xs">
                    {row.windowsDesktopTarget}
                  </td>
                  <td className="py-3 px-4 align-top text-xs text-[#94A3B8] max-w-xs">
                    {row.aiStudioWebBehavior}
                  </td>
                  <td className="py-3 px-4 align-top text-xs text-[#94A3B8] max-w-xs">
                    {row.mitigation}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
