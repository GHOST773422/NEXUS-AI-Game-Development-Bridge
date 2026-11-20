import { useState } from 'react';
import {
  AIProviderConnection,
  NexusSettingsState,
  PermissionScope,
  SettingsCategory,
} from '../../types/nexus';

interface SettingsViewProps {
  settings: NexusSettingsState;
  providers: AIProviderConnection[];
  onUpdateSettings: (next: NexusSettingsState) => void;
  onResetDefaults: () => void;
  onExportDiagnostics: () => string;
}

const SETTINGS_CATEGORIES: SettingsCategory[] = [
  'General',
  'Appearance',
  'AI providers',
  'Connections',
  'Permissions',
  'Execution limits',
  'Storage',
  'Diagnostics',
];

export function SettingsView({
  settings,
  providers,
  onUpdateSettings,
  onResetDefaults,
  onExportDiagnostics,
}: SettingsViewProps) {
  const [activeCategory, setActiveCategory] = useState<SettingsCategory>('General');
  const [exportedPreview, setExportedPreview] = useState<string | null>(null);

  const toggleApprovalScope = (scope: PermissionScope) => {
    const exists = settings.permissions.approvalScopes.includes(scope);
    const nextScopes = exists
      ? settings.permissions.approvalScopes.filter((s) => s !== scope)
      : [...settings.permissions.approvalScopes, scope];
    onUpdateSettings({
      ...settings,
      permissions: {
        ...settings.permissions,
        approvalScopes: nextScopes,
      },
    });
  };

  return (
    <div className="space-y-8">
      <section className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 pb-6 border-b border-[#1E293B]">
        <div className="space-y-1.5">
          <h2 className="font-display text-xl font-semibold text-[#F1F5F9]">Settings</h2>
          <p className="text-sm text-[#94A3B8]">
            Configure workspace behavior, appearance, AI providers, local connections, permissions,
            execution limits, storage, and diagnostics.
          </p>
        </div>

        <button
          type="button"
          onClick={onResetDefaults}
          className="px-3.5 py-2 text-xs font-medium rounded-md border border-[#1E293B] bg-[#121923] text-[#94A3B8] hover:text-[#F1F5F9] hover:border-[#3987F5] transition-colors whitespace-nowrap shrink-0"
        >
          Reset to Defaults
        </button>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        <nav
          aria-label="Settings categories"
          className="lg:col-span-3 p-2 rounded-lg bg-[#121923] border border-[#1E293B] space-y-0.5"
        >
          {SETTINGS_CATEGORIES.map((category) => {
            const active = activeCategory === category;
            return (
              <button
                key={category}
                type="button"
                onClick={() => setActiveCategory(category)}
                className={`w-full text-left px-3 py-2 text-sm font-medium rounded transition-colors whitespace-nowrap ${
                  active
                    ? 'bg-[#1B2636] text-[#35D6C5]'
                    : 'text-[#94A3B8] hover:text-[#F1F5F9] hover:bg-[#161F2C]'
                }`}
              >
                {category}
              </button>
            );
          })}
        </nav>

        <section className="lg:col-span-9 p-6 rounded-lg bg-[#121923] border border-[#1E293B] space-y-5">
          <h3 className="font-display text-base font-semibold text-[#F1F5F9] pb-3 border-b border-[#1E293B]">
            {activeCategory}
          </h3>

          {activeCategory === 'General' && (
            <div className="space-y-4 text-sm">
              <label className="flex items-center justify-between gap-4">
                <div>
                  <div className="text-[#F1F5F9]">Auto-probe local bridge on desktop launch</div>
                  <div className="text-xs text-[#94A3B8]">
                    Attempt immediate loopback health check when Tauri IPC is detected.
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={settings.general.autoProbeOnDesktopLaunch}
                  onChange={(e) =>
                    onUpdateSettings({
                      ...settings,
                      general: {
                        ...settings.general,
                        autoProbeOnDesktopLaunch: e.target.checked,
                      },
                    })
                  }
                  className="h-4 w-4 accent-[#35D6C5]"
                />
              </label>

              <label className="flex items-center justify-between gap-4 pt-3 border-t border-[#1E293B]">
                <div>
                  <div className="text-[#F1F5F9]">Confirm before closing active tasks</div>
                  <div className="text-xs text-[#94A3B8]">
                    Prevent accidental daemon shutdown while autonomous repairs are running.
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={settings.general.confirmBeforeClosingActiveTasks}
                  onChange={(e) =>
                    onUpdateSettings({
                      ...settings,
                      general: {
                        ...settings.general,
                        confirmBeforeClosingActiveTasks: e.target.checked,
                      },
                    })
                  }
                  className="h-4 w-4 accent-[#35D6C5]"
                />
              </label>

              <label className="block space-y-1.5 pt-3 border-t border-[#1E293B]">
                <span className="text-xs text-[#94A3B8]">Default Project Discovery Root</span>
                <input
                  type="text"
                  value={settings.general.defaultProjectSearchRoot}
                  onChange={(e) =>
                    onUpdateSettings({
                      ...settings,
                      general: {
                        ...settings.general,
                        defaultProjectSearchRoot: e.target.value,
                      },
                    })
                  }
                  className="w-full max-w-md px-3 py-2 rounded bg-[#0B0F14] border border-[#1E293B] font-mono text-xs text-[#F1F5F9] focus:outline-none focus:border-[#35D6C5]"
                />
              </label>
            </div>
          )}

          {activeCategory === 'Appearance' && (
            <div className="space-y-4 text-sm">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <div className="text-[#F1F5F9]">Data Table Density</div>
                  <div className="text-xs text-[#94A3B8]">
                    Adjust row padding across tools, projects, and diagnostics tables.
                  </div>
                </div>
                <select
                  value={settings.appearance.tableDensity}
                  onChange={(e) =>
                    onUpdateSettings({
                      ...settings,
                      appearance: {
                        ...settings.appearance,
                        tableDensity: e.target.value as 'compact' | 'comfortable',
                      },
                    })
                  }
                  className="px-3 py-1.5 rounded bg-[#0B0F14] border border-[#1E293B] text-xs text-[#F1F5F9]"
                >
                  <option value="comfortable">Comfortable</option>
                  <option value="compact">Compact</option>
                </select>
              </div>

              <div className="flex items-center justify-between gap-4 pt-3 border-t border-[#1E293B]">
                <div>
                  <div className="text-[#F1F5F9]">Monospace Log Size</div>
                  <div className="text-xs text-[#94A3B8]">
                    Applies to schemas and diagnostic logs.
                  </div>
                </div>
                <select
                  value={settings.appearance.logFontSize}
                  onChange={(e) =>
                    onUpdateSettings({
                      ...settings,
                      appearance: {
                        ...settings.appearance,
                        logFontSize: e.target.value as '12px' | '13px',
                      },
                    })
                  }
                  className="px-3 py-1.5 rounded bg-[#0B0F14] border border-[#1E293B] text-xs text-[#F1F5F9]"
                >
                  <option value="12px">12px</option>
                  <option value="13px">13px</option>
                </select>
              </div>

              <label className="flex items-center justify-between gap-4 pt-3 border-t border-[#1E293B]">
                <div>
                  <div className="text-[#F1F5F9]">Reduced Motion</div>
                  <div className="text-xs text-[#94A3B8]">
                    Disable non-essential UI transitions.
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={settings.appearance.reducedMotion}
                  onChange={(e) =>
                    onUpdateSettings({
                      ...settings,
                      appearance: { ...settings.appearance, reducedMotion: e.target.checked },
                    })
                  }
                  className="h-4 w-4 accent-[#35D6C5]"
                />
              </label>
            </div>
          )}

          {activeCategory === 'AI providers' && (
            <div className="space-y-4 text-sm">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <div className="text-[#F1F5F9]">Default Planning Provider</div>
                  <div className="text-xs text-[#94A3B8]">
                    Select primary built-in provider adapter for task orchestration.
                  </div>
                </div>
                <select
                  value={settings.aiProviders.defaultProviderId}
                  onChange={(e) =>
                    onUpdateSettings({
                      ...settings,
                      aiProviders: { ...settings.aiProviders, defaultProviderId: e.target.value },
                    })
                  }
                  className="px-3 py-1.5 rounded bg-[#0B0F14] border border-[#1E293B] text-xs text-[#F1F5F9]"
                >
                  {providers.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>

              <label className="flex items-center justify-between gap-4 pt-3 border-t border-[#1E293B]">
                <div>
                  <div className="text-[#F1F5F9]">Allow Paid Cloud Model Requests</div>
                  <div className="text-xs text-[#94A3B8]">
                    Local bridge inspection and MCP tool discovery always operate without a paid
                    key.
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={settings.aiProviders.allowPaidApiCalls}
                  onChange={(e) =>
                    onUpdateSettings({
                      ...settings,
                      aiProviders: {
                        ...settings.aiProviders,
                        allowPaidApiCalls: e.target.checked,
                      },
                    })
                  }
                  className="h-4 w-4 accent-[#35D6C5]"
                />
              </label>

              <label className="block space-y-1.5 pt-3 border-t border-[#1E293B]">
                <span className="text-xs text-[#94A3B8]">Provider Timeout (ms)</span>
                <input
                  type="number"
                  min={5000}
                  max={120000}
                  step={1000}
                  value={settings.aiProviders.requestTimeoutMs}
                  onChange={(e) =>
                    onUpdateSettings({
                      ...settings,
                      aiProviders: {
                        ...settings.aiProviders,
                        requestTimeoutMs: Number(e.target.value) || 30000,
                      },
                    })
                  }
                  className="w-44 px-3 py-2 rounded bg-[#0B0F14] border border-[#1E293B] font-mono tabular-nums text-xs text-[#F1F5F9]"
                />
              </label>
            </div>
          )}

          {activeCategory === 'Connections' && (
            <div className="space-y-4 text-sm">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <div className="text-[#F1F5F9]">Default Network Bind Address</div>
                  <div className="text-xs text-[#94A3B8]">
                    Locked to local loopback by default for workstation safety.
                  </div>
                </div>
                <span className="font-mono text-xs text-[#35D6C5]">
                  {settings.connections.bindAddress}
                </span>
              </div>

              <label className="flex items-center justify-between gap-4 pt-3 border-t border-[#1E293B]">
                <div>
                  <div className="text-[#F1F5F9]">Require Local Bearer Token</div>
                  <div className="text-xs text-[#94A3B8]">
                    Enforces bearer authorization on REST and Streamable HTTP MCP routes.
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={settings.connections.requireBearerToken}
                  onChange={(e) =>
                    onUpdateSettings({
                      ...settings,
                      connections: {
                        ...settings.connections,
                        requireBearerToken: e.target.checked,
                      },
                    })
                  }
                  className="h-4 w-4 accent-[#35D6C5]"
                />
              </label>

              <label className="block space-y-1.5 pt-3 border-t border-[#1E293B]">
                <span className="text-xs text-[#94A3B8]">Adapter Reconnect Backoff (ms)</span>
                <input
                  type="number"
                  min={500}
                  max={30000}
                  step={500}
                  value={settings.connections.reconnectBackoffMs}
                  onChange={(e) =>
                    onUpdateSettings({
                      ...settings,
                      connections: {
                        ...settings.connections,
                        reconnectBackoffMs: Number(e.target.value) || 2000,
                      },
                    })
                  }
                  className="w-44 px-3 py-2 rounded bg-[#0B0F14] border border-[#1E293B] font-mono tabular-nums text-xs text-[#F1F5F9]"
                />
              </label>
            </div>
          )}

          {activeCategory === 'Permissions' && (
            <div className="space-y-4 text-sm">
              <label className="flex items-center justify-between gap-4">
                <div>
                  <div className="text-[#F1F5F9]">Enforce Project Directory Sandboxing</div>
                  <div className="text-xs text-[#94A3B8]">
                    Blocks filesystem reads and writes outside registered project roots.
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={settings.permissions.projectDirectorySandboxing}
                  onChange={(e) =>
                    onUpdateSettings({
                      ...settings,
                      permissions: {
                        ...settings.permissions,
                        projectDirectorySandboxing: e.target.checked,
                      },
                    })
                  }
                  className="h-4 w-4 accent-[#35D6C5]"
                />
              </label>

              <div className="space-y-2 pt-3 border-t border-[#1E293B]">
                <div className="text-xs font-medium text-[#94A3B8]">
                  Scopes Requiring Explicit Human Approval
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {Object.values(PermissionScope).map((scope) => {
                    const checked = settings.permissions.approvalScopes.includes(scope);
                    return (
                      <label
                        key={scope}
                        className="flex items-center gap-2.5 p-2.5 rounded bg-[#0B0F14] border border-[#1E293B] text-xs font-mono text-[#F1F5F9]"
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleApprovalScope(scope)}
                          className="h-3.5 w-3.5 accent-[#35D6C5]"
                        />
                        <span>{scope}</span>
                      </label>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {activeCategory === 'Execution limits' && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
              <label className="space-y-1.5">
                <span className="text-[#94A3B8]">Max Bounded Repair Attempts</span>
                <input
                  type="number"
                  min={0}
                  max={10}
                  value={settings.executionLimits.maxRepairAttempts}
                  onChange={(e) =>
                    onUpdateSettings({
                      ...settings,
                      executionLimits: {
                        ...settings.executionLimits,
                        maxRepairAttempts: Number(e.target.value) || 0,
                      },
                    })
                  }
                  className="w-full px-3 py-2 rounded bg-[#0B0F14] border border-[#1E293B] font-mono tabular-nums text-[#F1F5F9]"
                />
              </label>

              <label className="space-y-1.5">
                <span className="text-[#94A3B8]">Step Timeout (seconds)</span>
                <input
                  type="number"
                  min={10}
                  max={600}
                  value={settings.executionLimits.stepTimeoutSec}
                  onChange={(e) =>
                    onUpdateSettings({
                      ...settings,
                      executionLimits: {
                        ...settings.executionLimits,
                        stepTimeoutSec: Number(e.target.value) || 60,
                      },
                    })
                  }
                  className="w-full px-3 py-2 rounded bg-[#0B0F14] border border-[#1E293B] font-mono tabular-nums text-[#F1F5F9]"
                />
              </label>

              <label className="space-y-1.5">
                <span className="text-[#94A3B8]">Max Concurrent Tasks</span>
                <input
                  type="number"
                  min={1}
                  max={4}
                  value={settings.executionLimits.maxConcurrentTasks}
                  onChange={(e) =>
                    onUpdateSettings({
                      ...settings,
                      executionLimits: {
                        ...settings.executionLimits,
                        maxConcurrentTasks: Number(e.target.value) || 1,
                      },
                    })
                  }
                  className="w-full px-3 py-2 rounded bg-[#0B0F14] border border-[#1E293B] font-mono tabular-nums text-[#F1F5F9]"
                />
              </label>
            </div>
          )}

          {activeCategory === 'Storage' && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
              <label className="space-y-1.5">
                <span className="text-[#94A3B8]">SQLite Database File</span>
                <input
                  type="text"
                  value={settings.storage.sqliteFilename}
                  onChange={(e) =>
                    onUpdateSettings({
                      ...settings,
                      storage: { ...settings.storage, sqliteFilename: e.target.value },
                    })
                  }
                  className="w-full px-3 py-2 rounded bg-[#0B0F14] border border-[#1E293B] font-mono text-[#F1F5F9]"
                />
              </label>

              <label className="space-y-1.5">
                <span className="text-[#94A3B8]">Checkpoint Retention Count</span>
                <input
                  type="number"
                  min={5}
                  max={200}
                  value={settings.storage.checkpointRetentionCount}
                  onChange={(e) =>
                    onUpdateSettings({
                      ...settings,
                      storage: {
                        ...settings.storage,
                        checkpointRetentionCount: Number(e.target.value) || 25,
                      },
                    })
                  }
                  className="w-full px-3 py-2 rounded bg-[#0B0F14] border border-[#1E293B] font-mono tabular-nums text-[#F1F5F9]"
                />
              </label>

              <label className="space-y-1.5">
                <span className="text-[#94A3B8]">Audit Log Retention (days)</span>
                <input
                  type="number"
                  min={7}
                  max={365}
                  value={settings.storage.auditLogRetentionDays}
                  onChange={(e) =>
                    onUpdateSettings({
                      ...settings,
                      storage: {
                        ...settings.storage,
                        auditLogRetentionDays: Number(e.target.value) || 30,
                      },
                    })
                  }
                  className="w-full px-3 py-2 rounded bg-[#0B0F14] border border-[#1E293B] font-mono tabular-nums text-[#F1F5F9]"
                />
              </label>
            </div>
          )}

          {activeCategory === 'Diagnostics' && (
            <div className="space-y-4 text-sm">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <div className="text-[#F1F5F9]">Structured Log Verbosity</div>
                  <div className="text-xs text-[#94A3B8]">
                    Controls client and daemon diagnostic detail level.
                  </div>
                </div>
                <select
                  value={settings.diagnostics.logVerbosity}
                  onChange={(e) =>
                    onUpdateSettings({
                      ...settings,
                      diagnostics: {
                        ...settings.diagnostics,
                        logVerbosity: e.target.value as 'warn' | 'info' | 'debug',
                      },
                    })
                  }
                  className="px-3 py-1.5 rounded bg-[#0B0F14] border border-[#1E293B] text-xs text-[#F1F5F9]"
                >
                  <option value="warn">warn</option>
                  <option value="info">info</option>
                  <option value="debug">debug</option>
                </select>
              </div>

              <div className="flex flex-wrap items-center gap-3 pt-3 border-t border-[#1E293B]">
                <button
                  type="button"
                  onClick={() => setExportedPreview(onExportDiagnostics())}
                  className="px-4 py-2 text-xs font-semibold rounded-md bg-[#35D6C5] text-[#081016] hover:bg-[#4BE0D0] transition-colors whitespace-nowrap shrink-0"
                >
                  Generate Diagnostic Snapshot
                </button>
              </div>

              {exportedPreview && (
                <pre className="p-3 rounded bg-[#0B0F14] border border-[#1E293B] font-mono text-xs text-[#94A3B8] max-h-64 overflow-auto">
                  {exportedPreview}
                </pre>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
