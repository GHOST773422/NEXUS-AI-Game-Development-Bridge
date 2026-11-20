import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Sidebar } from './components/layout/Sidebar';
import { TopBar } from './components/layout/TopBar';
import { DashboardView } from './components/views/DashboardView';
import { DEMO_ACTIVITY_ENTRIES, DEMO_PROJECTS, DEMO_TASKS } from './data/demoFixture';

const ActivityView = lazy(() =>
  import('./components/views/ActivityView').then((m) => ({ default: m.ActivityView }))
);
const ConnectionsView = lazy(() =>
  import('./components/views/ConnectionsView').then((m) => ({ default: m.ConnectionsView }))
);
const DiagnosticsView = lazy(() =>
  import('./components/views/DiagnosticsView').then((m) => ({ default: m.DiagnosticsView }))
);
const EnginesView = lazy(() =>
  import('./components/views/EnginesView').then((m) => ({ default: m.EnginesView }))
);
const PluginsView = lazy(() =>
  import('./components/views/PluginsView').then((m) => ({ default: m.PluginsView }))
);
const ProjectsView = lazy(() =>
  import('./components/views/ProjectsView').then((m) => ({ default: m.ProjectsView }))
);
const SettingsView = lazy(() =>
  import('./components/views/SettingsView').then((m) => ({ default: m.SettingsView }))
);
const TasksView = lazy(() =>
  import('./components/views/TasksView').then((m) => ({ default: m.TasksView }))
);
const ToolsView = lazy(() =>
  import('./components/views/ToolsView').then((m) => ({ default: m.ToolsView }))
);
import {
  bridgeTransport,
  daemonRestClient,
  DEFAULT_BRIDGE_CONFIG,
  detectRuntimeEnvironment,
  fetchPreviewBackendHealth,
  TauriIpcBridgeTransport,
  verifyAIProviderViaBackend,
} from './services/bridgeTransport';
import {
  buildDiagnosticsExportPayload,
  createDraftTaskRecord,
  createInitialAIProviders,
  createInitialEngines,
  createInitialSettings,
  mapDaemonAdapter,
  mapDaemonEngine,
  mapDaemonProject,
  mapDaemonProvider,
  mapDaemonTask,
  mapDaemonToolContract,
} from './services/controlCenterService';
import {
  ALL_HYDRATION_SCOPES,
  createHydrationCoalescer,
  HydrationScope,
  scopesForWebSocketEvent,
} from './services/hydrationScheduler';
import {
  AdapterInstallGuide,
  AIProviderConnection,
  AIProviderKind,
  BridgeEndpointConfig,
  BridgeProbeResult,
  DaemonLifecycleStatus,
  DaemonMcpStatusPayload,
  DesktopDiagnosticsReport,
  EngineCardState,
  EngineKind,
  LiveAdapterDescriptor,
  NavSection,
  NexusSettingsState,
  NexusStatus,
  ProviderVerificationPayload,
  RegisteredProject,
  RestHealthResponse,
  RuntimeEnvironmentInfo,
  SessionActivityEntry,
  TaskRecord,
  ToolContractSchema,
} from './types/nexus';

function createActivityEntry(
  category: SessionActivityEntry['category'],
  severity: SessionActivityEntry['severity'],
  status: NexusStatus,
  message: string,
  detail?: string
): SessionActivityEntry {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    timestamp: new Date().toISOString(),
    category,
    severity,
    status,
    message,
    detail,
  };
}

export default function App() {
  const [activeSection, setActiveSection] = useState<NavSection>(NavSection.Dashboard);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [demoMode, setDemoMode] = useState(false);
  const [streamPaused, setStreamPaused] = useState(false);

  const [runtime, setRuntime] = useState<RuntimeEnvironmentInfo>(() => detectRuntimeEnvironment());
  const [previewHealth, setPreviewHealth] = useState<RestHealthResponse | null>(null);
  const [settings, setSettings] = useState<NexusSettingsState>(() => createInitialSettings());
  const [providers, setProviders] = useState<AIProviderConnection[]>(() =>
    createInitialAIProviders(null)
  );
  const [projects, setProjects] = useState<RegisteredProject[]>([]);
  const [engines, setEngines] = useState<EngineCardState[]>(() => createInitialEngines([]));
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [liveTools, setLiveTools] = useState<ToolContractSchema[]>([]);
  const [liveAdapters, setLiveAdapters] = useState<LiveAdapterDescriptor[]>([]);
  const [mcpStatus, setMcpStatus] = useState<DaemonMcpStatusPayload | null>(null);
  const [daemonDiagnostics, setDaemonDiagnostics] = useState<Record<string, unknown> | null>(null);
  const [daemonAuthenticated, setDaemonAuthenticated] = useState(false);

  const [lastProbe, setLastProbe] = useState<BridgeProbeResult | null>(null);
  const [probing, setProbing] = useState(false);
  const [desktopLifecycle, setDesktopLifecycle] = useState<DaemonLifecycleStatus | null>(null);
  const [desktopDiagnostics, setDesktopDiagnostics] = useState<DesktopDiagnosticsReport | null>(
    null
  );
  const [adapterGuides, setAdapterGuides] = useState<AdapterInstallGuide[]>([]);
  const [activityLog, setActivityLog] = useState<SessionActivityEntry[]>(() => {
    const initialEnv = detectRuntimeEnvironment();
    return [
      createActivityEntry(
        'Runtime',
        'info',
        initialEnv.hasTauriIPC ? NexusStatus.Connected : NexusStatus.Available,
        `Frontend initialized in ${initialEnv.hostKind} mode.`,
        `Origin: ${initialEnv.origin} · Tauri IPC: ${initialEnv.hasTauriIPC ? 'present' : 'absent'}`
      ),
    ];
  });

  const streamPausedRef = useRef(streamPaused);
  const projectsRef = useRef(projects);
  const tasksRef = useRef(tasks);
  const providersRef = useRef(providers);
  const connectionsRef = useRef(settings.connections);
  const daemonAuthenticatedRef = useRef(daemonAuthenticated);

  useEffect(() => {
    streamPausedRef.current = streamPaused;
  }, [streamPaused]);
  useEffect(() => {
    projectsRef.current = projects;
  }, [projects]);
  useEffect(() => {
    tasksRef.current = tasks;
  }, [tasks]);
  useEffect(() => {
    providersRef.current = providers;
  }, [providers]);
  useEffect(() => {
    connectionsRef.current = settings.connections;
  }, [settings.connections]);
  useEffect(() => {
    daemonAuthenticatedRef.current = daemonAuthenticated;
  }, [daemonAuthenticated]);

  const appendActivity = useCallback((entry: SessionActivityEntry) => {
    if (streamPausedRef.current) return;
    setActivityLog((prev) => [entry, ...prev].slice(0, 150));
  }, []);

  // Keep engine card available project counts synchronized with registered projects.
  const syncEngineProjectCounts = useCallback((nextProjects: RegisteredProject[]) => {
    setEngines((prev) =>
      prev.map((card) => ({
        ...card,
        availableProjectCount: nextProjects.filter((p) => p.engine === card.engine).length,
      }))
    );
  }, []);

  const handleToggleDemoMode = useCallback(() => {
    setDemoMode((prevDemo) => {
      const nextDemo = !prevDemo;
      if (nextDemo) {
        setProjects((prev) => {
          const nonDemo = prev.filter((p) => !p.isDemoFixture);
          const merged = [...DEMO_PROJECTS, ...nonDemo];
          syncEngineProjectCounts(merged);
          return merged;
        });
        setTasks((prev) => [...DEMO_TASKS, ...prev.filter((t) => !t.isDemoFixture)]);
        setActivityLog((prev) => [
          ...DEMO_ACTIVITY_ENTRIES,
          ...prev.filter((e) => !e.isDemoFixture),
        ]);
      } else {
        setProjects((prev) => {
          const remaining = prev.filter((p) => !p.isDemoFixture);
          syncEngineProjectCounts(remaining);
          return remaining;
        });
        setTasks((prev) => prev.filter((t) => !t.isDemoFixture));
        setActivityLog((prev) => prev.filter((e) => !e.isDemoFixture));
      }
      return nextDemo;
    });
  }, [syncEngineProjectCounts]);

  const hydrateFromDaemon = useCallback(
    async (
      endpointConfig: BridgeEndpointConfig,
      scopes: readonly HydrationScope[] = ALL_HYDRATION_SCOPES
    ) => {
      if (!daemonRestClient.getSessionBearerToken() && endpointConfig.requireBearerToken) {
        return false;
      }
      const scopeSet = new Set(scopes);
      if (scopeSet.size === 0) {
        return true;
      }
      try {
        const needsProjects = scopeSet.has('projects');
        const needsTasks = scopeSet.has('tasks');
        const needsEngines = scopeSet.has('engines');

        const [projRes, taskRes, toolRes, adapterRes, engineRes, providerRes, mcpRes, diagRes] =
          await Promise.all([
            needsProjects
              ? daemonRestClient.fetchAuthenticatedJson<{
                  projects: Record<string, unknown>[];
                }>(endpointConfig, '/api/v1/projects')
              : Promise.resolve(null),
            needsTasks
              ? daemonRestClient.fetchAuthenticatedJson<{
                  tasks: Record<string, unknown>[];
                }>(endpointConfig, '/api/v1/tasks')
              : Promise.resolve(null),
            scopeSet.has('tools')
              ? daemonRestClient.fetchAuthenticatedJson<{
                  tools: Record<string, unknown>[];
                }>(endpointConfig, '/api/v1/tools')
              : Promise.resolve(null),
            scopeSet.has('adapters')
              ? daemonRestClient.fetchAuthenticatedJson<{
                  adapters: Record<string, unknown>[];
                }>(endpointConfig, '/api/v1/adapters')
              : Promise.resolve(null),
            needsEngines
              ? daemonRestClient.fetchAuthenticatedJson<{
                  engines: Record<string, unknown>[];
                }>(endpointConfig, '/api/v1/engines')
              : Promise.resolve(null),
            scopeSet.has('providers')
              ? daemonRestClient.fetchAuthenticatedJson<{
                  providers: Record<string, unknown>[];
                }>(endpointConfig, '/api/v1/providers')
              : Promise.resolve(null),
            scopeSet.has('mcp')
              ? daemonRestClient.fetchAuthenticatedJson<DaemonMcpStatusPayload>(
                  endpointConfig,
                  '/api/v1/mcp/status'
                )
              : Promise.resolve(null),
            scopeSet.has('diagnostics')
              ? daemonRestClient.fetchAuthenticatedJson<Record<string, unknown>>(
                  endpointConfig,
                  '/api/v1/diagnostics'
                )
              : Promise.resolve(null),
          ]);

        const mappedProjects = projRes
          ? projRes.projects.map(mapDaemonProject)
          : projectsRef.current;

        setDaemonAuthenticated(true);
        if (projRes) {
          setProjects((prev) => [...prev.filter((p) => p.isDemoFixture), ...mappedProjects]);
        }
        if (taskRes) {
          const mappedTasks = taskRes.tasks.map((t) => mapDaemonTask(t, mappedProjects));
          setTasks((prev) => [...prev.filter((t) => t.isDemoFixture), ...mappedTasks]);
        }
        if (toolRes) {
          setLiveTools(toolRes.tools.map(mapDaemonToolContract));
        }
        if (adapterRes) {
          setLiveAdapters(adapterRes.adapters.map(mapDaemonAdapter));
        }
        if (mcpRes) {
          setMcpStatus(mcpRes);
        }
        if (diagRes) {
          setDaemonDiagnostics(diagRes);
        }
        if (engineRes) {
          const mappedEngines = engineRes.engines.map((e) => mapDaemonEngine(e, mappedProjects));
          if (mappedEngines.length > 0) setEngines(mappedEngines);
        }
        if (providerRes) {
          const mappedProviders = providerRes.providers.map(mapDaemonProvider);
          if (mappedProviders.length > 0) setProviders(mappedProviders);
        }
        return true;
      } catch {
        setDaemonAuthenticated(false);
        setMcpStatus(null);
        setDaemonDiagnostics(null);
        setLiveTools([]);
        setLiveAdapters([]);
        return false;
      }
    },
    []
  );

  const handleProbeBridge = useCallback(async () => {
    setProbing(true);
    const result = await bridgeTransport.probeHealth(settings.connections);
    setLastProbe(result);
    if (result.status === NexusStatus.Connected) {
      if (bridgeTransport instanceof TauriIpcBridgeTransport) {
        try {
          const token = await bridgeTransport.getDaemonAuthToken();
          daemonRestClient.setSessionBearerToken(token);
        } catch {
          // Non-fatal: REST calls stay disabled until token loads
        }
      }
      await hydrateFromDaemon(settings.connections);
    } else {
      setDaemonAuthenticated(false);
      setMcpStatus(null);
      setDaemonDiagnostics(null);
      setLiveTools([]);
      setLiveAdapters([]);
    }
    setProbing(false);
    appendActivity(
      createActivityEntry(
        'Probe',
        result.status === NexusStatus.Connected ? 'info' : 'warning',
        result.status,
        `Local bridge probe to ${result.endpoint} completed as ${result.status}.`,
        result.message
      )
    );
  }, [appendActivity, hydrateFromDaemon, settings.connections]);

  const handleRefreshRuntime = useCallback(() => {
    const next = detectRuntimeEnvironment();
    setRuntime(next);
    appendActivity(
      createActivityEntry(
        'Runtime',
        'info',
        NexusStatus.Available,
        `Runtime environment re-evaluated (${next.hostKind}).`,
        `WebSocket: ${next.supportsWebSocket} · Platform: ${next.platformHint}`
      )
    );
    void (async () => {
      const res = await fetchPreviewBackendHealth();
      if (res.health) {
        setPreviewHealth(res.health);
        setProviders((prev) =>
          prev.map((p) =>
            p.kind === AIProviderKind.GoogleGemini
              ? {
                  ...p,
                  credentialConfigured: res.health!.capabilities.geminiServerKeyConfigured,
                  status: res.health!.capabilities.geminiServerKeyConfigured
                    ? NexusStatus.Available
                    : NexusStatus.Disconnected,
                }
              : p
          )
        );
      }
    })();
  }, [appendActivity]);

  const handleUpdateEndpointConfig = useCallback(
    (next: BridgeEndpointConfig) => {
      setSettings((prev) => ({
        ...prev,
        connections: { ...prev.connections, ...next },
      }));
      appendActivity(
        createActivityEntry(
          'Security',
          'info',
          NexusStatus.Available,
          'Local bridge transport endpoints updated.',
          `REST: ${next.restBaseUrl}`
        )
      );
    },
    [appendActivity]
  );

  const handleUpdateProvider = useCallback(
    (id: string, patch: Partial<AIProviderConnection>) => {
      setProviders((prev) => prev.map((p) => (p.id === id ? { ...p, ...patch } : p)));
      if (daemonAuthenticated) {
        void daemonRestClient
          .fetchAuthenticatedJson<{ provider: Record<string, unknown> }>(
            settings.connections,
            `/api/v1/providers/${encodeURIComponent(id)}`,
            {
              method: 'PATCH',
              body: JSON.stringify({
                enabled: patch.enabled,
                modelId: patch.modelId,
                endpointUrl: patch.endpointUrl,
                credentialRef: patch.credentialRef,
              }),
            }
          )
          .then((res) => {
            if (res.provider) {
              const updated = mapDaemonProvider(res.provider);
              setProviders((prev) => prev.map((p) => (p.id === id ? updated : p)));
            }
          })
          .catch(() => undefined);
      }
      appendActivity(
        createActivityEntry(
          'Security',
          'info',
          NexusStatus.Available,
          `Updated AI provider configuration (${id}).`
        )
      );
    },
    [appendActivity, daemonAuthenticated, settings.connections]
  );

  const handleAddCustomProvider = useCallback(
    (input: { name: string; modelId: string; endpointUrl: string; credentialRef: string }) => {
      if (daemonAuthenticated) {
        void daemonRestClient
          .fetchAuthenticatedJson<{ provider: Record<string, unknown> }>(
            settings.connections,
            '/api/v1/providers',
            {
              method: 'POST',
              body: JSON.stringify({
                name: input.name,
                kind: AIProviderKind.Custom,
                modelId: input.modelId,
                endpointUrl: input.endpointUrl,
                credentialRef: input.credentialRef,
                enabled: true,
              }),
            }
          )
          .then((res) => {
            const mapped = mapDaemonProvider(res.provider);
            setProviders((prev) => [...prev, mapped]);
            appendActivity(
              createActivityEntry(
                'Security',
                'info',
                NexusStatus.Available,
                `Registered custom AI provider "${mapped.name}" in Python daemon.`,
                mapped.endpointUrl
              )
            );
          })
          .catch((err: unknown) => {
            appendActivity(
              createActivityEntry(
                'Security',
                'error',
                NexusStatus.Failed,
                `Failed to register custom AI provider "${input.name}".`,
                err instanceof Error ? err.message : 'Daemon rejected provider registration.'
              )
            );
          });
        return;
      }

      const created: AIProviderConnection = {
        id: `conn-custom-${Date.now().toString(36)}`,
        name: input.name,
        kind: AIProviderKind.Custom,
        enabled: true,
        modelId: input.modelId,
        endpointUrl: input.endpointUrl,
        credentialRef: input.credentialRef,
        credentialConfigured: false,
        credentialBackend: 'Windows Credential Vault / Local Loopback',
        status: NexusStatus.Disconnected,
        supportsStreaming: true,
        supportsToolCalling: false,
        notes: 'Custom provider endpoint configured in session.',
        isCustom: true,
      };
      setProviders((prev) => [...prev, created]);
      appendActivity(
        createActivityEntry(
          'Security',
          'info',
          NexusStatus.Available,
          `Added custom AI provider "${created.name}".`,
          created.endpointUrl
        )
      );
    },
    [appendActivity, daemonAuthenticated, settings.connections]
  );

  const handleRemoveCustomProvider = useCallback(
    (id: string) => {
      if (daemonAuthenticated) {
        void daemonRestClient
          .fetchAuthenticatedJson<{ deleted: boolean }>(
            settings.connections,
            `/api/v1/providers/${encodeURIComponent(id)}`,
            { method: 'DELETE' }
          )
          .then(() => {
            setProviders((prev) => prev.filter((p) => p.id !== id));
            appendActivity(
              createActivityEntry(
                'Security',
                'info',
                NexusStatus.Available,
                `Deleted custom AI provider (${id}) from daemon vault & SQLite.`
              )
            );
          })
          .catch((err: unknown) => {
            appendActivity(
              createActivityEntry(
                'Security',
                'error',
                NexusStatus.Failed,
                `Failed to delete AI provider (${id}).`,
                err instanceof Error ? err.message : 'Daemon rejected provider deletion.'
              )
            );
          });
        return;
      }

      setProviders((prev) => prev.filter((p) => p.id !== id));
      appendActivity(
        createActivityEntry(
          'Security',
          'info',
          NexusStatus.Available,
          `Removed custom AI provider (${id}).`
        )
      );
    },
    [appendActivity, daemonAuthenticated, settings.connections]
  );

  const handleVerifyProvider = useCallback(
    async (id: string): Promise<ProviderVerificationPayload | null> => {
      const target = providersRef.current.find((p) => p.id === id);
      if (!target) return null;
      let result: ProviderVerificationPayload;
      if (daemonAuthenticated) {
        try {
          const res = await daemonRestClient.fetchAuthenticatedJson<{
            verification: ProviderVerificationPayload;
          }>(settings.connections, `/api/v1/providers/${encodeURIComponent(id)}/verify`, {
            method: 'POST',
            body: JSON.stringify({}),
          });
          result = res.verification;
        } catch (err) {
          result = {
            providerId: id,
            verified: false,
            status: NexusStatus.Failed,
            credentialConfigured: target.credentialConfigured,
            modelId: target.modelId,
            latencyMs: null,
            message: err instanceof Error ? err.message : 'Daemon verification failed.',
            checkedAt: new Date().toISOString(),
          };
        }
      } else {
        result = await verifyAIProviderViaBackend(target.id, target.modelId);
      }
      setProviders((prev) =>
        prev.map((p) =>
          p.id === id
            ? {
                ...p,
                status: result.status,
                credentialConfigured: result.credentialConfigured,
              }
            : p
        )
      );
      appendActivity(
        createActivityEntry(
          'Probe',
          result.verified ? 'info' : 'warning',
          result.status,
          `Verified AI provider "${target.name}" (${result.status}).`,
          result.message
        )
      );
      return result;
    },
    [appendActivity, daemonAuthenticated, settings.connections]
  );

  const handleUpdateEnginePath = useCallback(
    (engine: EngineKind, installPath: string) => {
      const normalized = installPath === 'Not detected' ? '' : installPath;
      if (daemonAuthenticated) {
        void daemonRestClient
          .fetchAuthenticatedJson<{ engines: Record<string, unknown>[] }>(
            settings.connections,
            `/api/v1/engines/${encodeURIComponent(engine)}`,
            {
              method: 'PATCH',
              body: JSON.stringify({ executablePath: normalized }),
            }
          )
          .then((res) => {
            if (Array.isArray(res.engines)) {
              setEngines(res.engines.map((e) => mapDaemonEngine(e, projectsRef.current)));
            }
            appendActivity(
              createActivityEntry(
                'Runtime',
                'info',
                NexusStatus.Available,
                normalized
                  ? `Verified ${engine} executable path override on local daemon.`
                  : `Cleared ${engine} executable path override.`,
                normalized || 'Default PATH probe active'
              )
            );
          })
          .catch((err: unknown) => {
            appendActivity(
              createActivityEntry(
                'Runtime',
                'error',
                NexusStatus.Failed,
                `Rejected ${engine} path update.`,
                err instanceof Error ? err.message : 'Invalid engine executable path.'
              )
            );
          });
        return;
      }

      setEngines((prev) =>
        prev.map((card) =>
          card.engine === engine
            ? {
                ...card,
                installationPath: normalized || 'Not detected (Web Preview)',
              }
            : card
        )
      );
      appendActivity(
        createActivityEntry(
          'Runtime',
          'info',
          NexusStatus.Available,
          `Configured ${engine} search path preference (syncs when daemon connects).`,
          installPath
        )
      );
    },
    [appendActivity, daemonAuthenticated, settings.connections]
  );

  const handleScanEngines = useCallback(() => {
    if (daemonAuthenticated) {
      void hydrateFromDaemon(settings.connections).then((ok) => {
        appendActivity(
          createActivityEntry(
            'Runtime',
            ok ? 'info' : 'warning',
            ok ? NexusStatus.Available : NexusStatus.Unavailable,
            ok
              ? 'Refreshed Unity and Godot binary probes & adapter states from local daemon.'
              : 'Failed to refresh local engine scan from Python daemon.'
          )
        );
      });
      return;
    }
    appendActivity(
      createActivityEntry(
        'Runtime',
        'warning',
        NexusStatus.Unavailable,
        'Local Unity/Godot installation scan skipped: native Python daemon is not connected.',
        'Start or install the Windows desktop daemon to inspect local Unity Hub and Godot binaries.'
      )
    );
  }, [appendActivity, daemonAuthenticated, hydrateFromDaemon, settings.connections]);

  const handleRegisterProject = useCallback(
    (input: { name: string; engine: EngineKind; rootPath: string; engineVersion: string }) => {
      if (daemonAuthenticated) {
        void daemonRestClient
          .fetchAuthenticatedJson<{ project: Record<string, unknown> }>(
            settings.connections,
            '/api/v1/projects',
            {
              method: 'POST',
              body: JSON.stringify(input),
            }
          )
          .then((res) => {
            const mapped = mapDaemonProject(res.project);
            setProjects((prev) => {
              const next = [mapped, ...prev.filter((p) => p.id !== mapped.id)];
              syncEngineProjectCounts(next);
              return next;
            });
            appendActivity(
              createActivityEntry(
                'Project',
                'info',
                NexusStatus.Available,
                `Registered ${mapped.engine} project "${mapped.name}" in SQLite.`,
                mapped.rootPath
              )
            );
          })
          .catch((err: unknown) => {
            appendActivity(
              createActivityEntry(
                'Project',
                'error',
                NexusStatus.Failed,
                `Failed to register project "${input.name}".`,
                err instanceof Error ? err.message : 'Project registration rejected.'
              )
            );
          });
        return;
      }

      const nextProject: RegisteredProject = {
        id: `proj-${Date.now().toString(36)}`,
        name: input.name,
        engine: input.engine,
        rootPath: input.rootPath,
        engineVersion: input.engineVersion,
        status: NexusStatus.Disconnected,
        lastInspectedAt: null,
        activeScene: null,
        notes: 'Registered manually; awaiting local engine adapter connection.',
      };
      setProjects((prev) => {
        const next = [nextProject, ...prev];
        syncEngineProjectCounts(next);
        return next;
      });
      appendActivity(
        createActivityEntry(
          'Project',
          'info',
          NexusStatus.Available,
          `Registered ${input.engine} project "${input.name}".`,
          input.rootPath
        )
      );
    },
    [appendActivity, daemonAuthenticated, settings.connections, syncEngineProjectCounts]
  );

  const handleAssociateEngine = useCallback(
    (projectId: string, engine: EngineKind) => {
      if (daemonAuthenticated) {
        void daemonRestClient
          .fetchAuthenticatedJson<{ project: Record<string, unknown> }>(
            settings.connections,
            `/api/v1/projects/${encodeURIComponent(projectId)}`,
            {
              method: 'PATCH',
              body: JSON.stringify({ engine }),
            }
          )
          .then((res) => {
            const mapped = mapDaemonProject(res.project);
            setProjects((prev) => {
              const next = prev.map((p) => (p.id === projectId ? mapped : p));
              syncEngineProjectCounts(next);
              return next;
            });
          })
          .catch(() => undefined);
      } else {
        setProjects((prev) => {
          const next = prev.map((p) => (p.id === projectId ? { ...p, engine } : p));
          syncEngineProjectCounts(next);
          return next;
        });
      }
      appendActivity(
        createActivityEntry(
          'Project',
          'info',
          NexusStatus.Available,
          `Updated engine association to ${engine} for project ${projectId}.`
        )
      );
    },
    [appendActivity, daemonAuthenticated, settings.connections, syncEngineProjectCounts]
  );

  const handleRemoveProject = useCallback(
    (projectId: string) => {
      if (daemonAuthenticated) {
        void daemonRestClient
          .fetchAuthenticatedJson<{ deleted: boolean }>(
            settings.connections,
            `/api/v1/projects/${encodeURIComponent(projectId)}`,
            { method: 'DELETE' }
          )
          .then(() => {
            setProjects((prev) => {
              const next = prev.filter((p) => p.id !== projectId);
              syncEngineProjectCounts(next);
              return next;
            });
          })
          .catch(() => undefined);
      } else {
        setProjects((prev) => {
          const next = prev.filter((p) => p.id !== projectId);
          syncEngineProjectCounts(next);
          return next;
        });
      }
      appendActivity(
        createActivityEntry(
          'Project',
          'info',
          NexusStatus.Available,
          `Removed project registration (${projectId}).`
        )
      );
    },
    [appendActivity, daemonAuthenticated, settings.connections, syncEngineProjectCounts]
  );

  const handleCreateDraftTask = useCallback(
    (
      title: string,
      projectId: string,
      priority: 'low' | 'normal' | 'high' | 'critical' = 'normal',
      agentId = 'operator'
    ) => {
      const target = projectsRef.current.find((p) => p.id === projectId);
      if (!target) return;

      if (daemonAuthenticated && !target.isDemoFixture) {
        void daemonRestClient
          .fetchAuthenticatedJson<{ task: Record<string, unknown> }>(
            settings.connections,
            '/api/v1/tasks',
            {
              method: 'POST',
              body: JSON.stringify({
                projectId,
                title,
                priority,
                agentId,
                executeNow: false,
              }),
            }
          )
          .then((res) => {
            const mapped = mapDaemonTask(res.task, projectsRef.current);
            setTasks((prev) => [mapped, ...prev.filter((t) => t.id !== mapped.id)]);
            appendActivity(
              createActivityEntry(
                'Task',
                'info',
                NexusStatus.Planned,
                `Created persisted task draft "${mapped.title}" [${priority}].`,
                `Project: ${target.name} · Agent: ${mapped.agentId ?? 'operator'}`
              )
            );
          })
          .catch((err: unknown) => {
            appendActivity(
              createActivityEntry(
                'Task',
                'error',
                NexusStatus.Failed,
                `Failed to create task draft "${title}".`,
                err instanceof Error ? err.message : 'Task creation failed.'
              )
            );
          });
        return;
      }

      const draft = createDraftTaskRecord({
        title,
        project: target,
        priority,
        agentId,
      });
      setTasks((prev) => [draft, ...prev]);
      appendActivity(
        createActivityEntry(
          'Task',
          'info',
          NexusStatus.Planned,
          `Created autonomous task plan draft "${draft.title}" [${priority}].`,
          `Project: ${target.name} · Agent: ${draft.agentId ?? 'operator'}`
        )
      );
    },
    [appendActivity, daemonAuthenticated, settings.connections]
  );

  const handleTaskControl = useCallback(
    (
      taskId: string,
      action: 'execute' | 'approve' | 'reject' | 'pause' | 'resume' | 'cancel' | 'rollback'
    ) => {
      const targetTask = tasksRef.current.find((t) => t.id === taskId);
      if (daemonAuthenticated && targetTask && !targetTask.isDemoFixture) {
        const endpoint =
          action === 'execute'
            ? `/api/v1/tasks/${encodeURIComponent(taskId)}/execute`
            : action === 'approve' || action === 'reject'
              ? `/api/v1/tasks/${encodeURIComponent(taskId)}/approve`
              : action === 'rollback'
                ? `/api/v1/tasks/${encodeURIComponent(taskId)}/rollback`
                : `/api/v1/tasks/${encodeURIComponent(taskId)}/control`;
        const payload =
          action === 'execute' || action === 'rollback'
            ? {}
            : action === 'approve'
              ? { approved: true, resumeExecution: true }
              : action === 'reject'
                ? { approved: false, resumeExecution: false }
                : { action };
        void daemonRestClient
          .fetchAuthenticatedJson<{ task: Record<string, unknown> }>(
            settings.connections,
            endpoint,
            {
              method: 'POST',
              body: JSON.stringify(payload),
            }
          )
          .then((res) => {
            const mapped = mapDaemonTask(res.task, projectsRef.current);
            setTasks((prev) => prev.map((t) => (t.id === taskId ? mapped : t)));
            appendActivity(
              createActivityEntry(
                'Task',
                'info',
                mapped.status,
                `Task control "${action}" synced for ${taskId}.`,
                mapped.currentOperation
              )
            );
          })
          .catch((err: unknown) => {
            appendActivity(
              createActivityEntry(
                'Task',
                'warning',
                NexusStatus.Failed,
                `Task control "${action}" failed for ${taskId}.`,
                err instanceof Error ? err.message : 'Daemon control error.'
              )
            );
          });
        return;
      }

      if (action === 'execute' || action === 'approve' || action === 'reject') {
        const reason = targetTask?.isDemoFixture
          ? 'Demonstration fixtures cannot run autonomous operations.'
          : 'Local Python daemon and engine adapter must be connected before execution or approval.';
        setTasks((prev) =>
          prev.map((t) =>
            t.id === taskId
              ? {
                  ...t,
                  logs: [
                    ...t.logs,
                    `[${new Date().toLocaleTimeString()}] [Blocked] ${action} refused: ${reason}`,
                  ],
                }
              : t
          )
        );
        appendActivity(
          createActivityEntry(
            'Task',
            'warning',
            NexusStatus.Unavailable,
            `Blocked "${action}" for ${taskId}: daemon or engine disconnected.`,
            reason
          )
        );
        return;
      }

      setTasks((prev) =>
        prev.map((t) => {
          if (t.id !== taskId) return t;
          const now = new Date().toISOString();
          const messageMap: Record<
            'pause' | 'resume' | 'cancel' | 'rollback',
            { status: NexusStatus; op: string; log: string }
          > = {
            pause: {
              status: NexusStatus.Unavailable,
              op: 'Paused by operator (awaiting connected Python daemon)',
              log: `[${new Date().toLocaleTimeString()}] Operator requested Pause.`,
            },
            resume: {
              status: NexusStatus.Planned,
              op: 'Ready to resume once Python daemon & engine adapter connect',
              log: `[${new Date().toLocaleTimeString()}] Operator requested Resume.`,
            },
            cancel: {
              status: NexusStatus.Disconnected,
              op: 'Cancelled by operator',
              log: `[${new Date().toLocaleTimeString()}] Task cancelled by operator.`,
            },
            rollback: {
              status: NexusStatus.Planned,
              op: 'Checkpoint rollback requires active Python CheckpointManager connection',
              log: `[${new Date().toLocaleTimeString()}] Checkpoint rollback requested (local daemon offline).`,
            },
          };
          const update = messageMap[action];
          return {
            ...t,
            status: update.status,
            currentOperation: update.op,
            updatedAt: now,
            logs: [...t.logs, update.log],
          };
        })
      );
      appendActivity(
        createActivityEntry(
          'Task',
          'info',
          NexusStatus.Planned,
          `Task control "${action}" applied to ${taskId}.`
        )
      );
    },
    [appendActivity, daemonAuthenticated, settings.connections]
  );

  const handleControlDesktopDaemon = useCallback(
    async (action: 'start' | 'stop' | 'restart') => {
      if (!(bridgeTransport instanceof TauriIpcBridgeTransport)) {
        return;
      }
      const nextStatus =
        action === 'start'
          ? await bridgeTransport.startBackgroundDaemon()
          : action === 'stop'
            ? await bridgeTransport.stopBackgroundDaemon(false)
            : await bridgeTransport.restartBackgroundDaemon();
      setDesktopLifecycle(nextStatus);
      const diag = await bridgeTransport.collectDesktopDiagnostics();
      setDesktopDiagnostics(diag);
      if (nextStatus.running) {
        try {
          const token = await bridgeTransport.getDaemonAuthToken();
          daemonRestClient.setSessionBearerToken(token);
          await hydrateFromDaemon(settings.connections);
        } catch {
          // Non-fatal while daemon initializes
        }
      } else {
        setDaemonAuthenticated(false);
        setMcpStatus(null);
        setDaemonDiagnostics(null);
        setLiveTools([]);
        setLiveAdapters([]);
      }
      appendActivity(
        createActivityEntry(
          'Runtime',
          nextStatus.running ? 'info' : 'warning',
          nextStatus.running ? NexusStatus.Connected : NexusStatus.Disconnected,
          `Desktop daemon ${action} completed (${nextStatus.launchMode}).`,
          nextStatus.lastError ?? nextStatus.endpoint
        )
      );
    },
    [appendActivity, hydrateFromDaemon, settings.connections]
  );

  useEffect(() => {
    let active = true;
    const initRuntime = async () => {
      if (runtime.hasTauriIPC && bridgeTransport instanceof TauriIpcBridgeTransport) {
        try {
          const [probeResult, lifecycle, diag, guides] = await Promise.all([
            bridgeTransport.probeHealth(DEFAULT_BRIDGE_CONFIG),
            bridgeTransport.getLifecycleStatus(),
            bridgeTransport.collectDesktopDiagnostics(),
            bridgeTransport.getAdapterInstallInstructions(),
          ]);
          if (!active) return;
          setLastProbe(probeResult);
          setDesktopLifecycle(lifecycle);
          setDesktopDiagnostics(diag);
          setAdapterGuides(guides);

          if (probeResult.status === NexusStatus.Connected) {
            try {
              const token = await bridgeTransport.getDaemonAuthToken();
              daemonRestClient.setSessionBearerToken(token);
              if (active) {
                await hydrateFromDaemon(DEFAULT_BRIDGE_CONFIG);
              }
            } catch {
              // Daemon auth token optional during startup probe
            }
          }
        } catch (err) {
          if (!active) return;
          appendActivity(
            createActivityEntry(
              'Runtime',
              'warning',
              NexusStatus.Disconnected,
              'Desktop Tauri IPC initialization returned an error.',
              err instanceof Error ? err.message : 'Unknown IPC error'
            )
          );
        }
        return;
      }

      const res = await fetchPreviewBackendHealth();
      if (!active) return;
      if (res.health) {
        setPreviewHealth(res.health);
        setProviders(createInitialAIProviders(res.health));
        appendActivity(
          createActivityEntry(
            'Runtime',
            'info',
            res.health.status,
            `Node preview backend responded (${res.health.protocolVersion}).`,
            `Gemini server key configured: ${res.health.capabilities.geminiServerKeyConfigured ? 'Yes' : 'No'}`
          )
        );
      } else if (res.error) {
        setPreviewHealth(null);
        appendActivity(
          createActivityEntry(
            'Runtime',
            'warning',
            NexusStatus.Disconnected,
            'Node preview backend /api/health unreachable.',
            res.error
          )
        );
      }
    };
    void initRuntime();
    return () => {
      active = false;
    };
  }, [appendActivity, hydrateFromDaemon, runtime.hasTauriIPC]);

  const wsEndpointKey = `${settings.connections.wsUrl}|${settings.connections.restBaseUrl}|${settings.connections.requireBearerToken ? '1' : '0'}`;

  useEffect(() => {
    if (!daemonAuthenticated || !settings.connections.enableWebSocketEvents) {
      return;
    }
    const endpointSnapshot = connectionsRef.current;
    const wsUrl = daemonRestClient.buildLoopbackWsUrl(endpointSnapshot);
    if (!wsUrl || typeof WebSocket === 'undefined') {
      return;
    }
    let closedByCleanup = false;
    const coalescer = createHydrationCoalescer(
      (scopes) => hydrateFromDaemon(connectionsRef.current, scopes),
      120
    );
    const ws = new WebSocket(wsUrl);
    ws.onmessage = (msg) => {
      try {
        const parsed = JSON.parse(String(msg.data)) as {
          type?: string;
          source?: string;
          data?: Record<string, unknown>;
        };
        const affectedScopes = scopesForWebSocketEvent(parsed.type);
        if (affectedScopes.length > 0) {
          void coalescer.schedule(affectedScopes);
        }
        if (parsed.type) {
          appendActivity(
            createActivityEntry(
              parsed.type.startsWith('task.')
                ? 'Task'
                : parsed.type.startsWith('error.')
                  ? 'Security'
                  : 'Runtime',
              parsed.type.startsWith('error.') ? 'warning' : 'info',
              NexusStatus.Connected,
              `WS ${parsed.type} (${parsed.source ?? 'daemon'})`
            )
          );
        }
      } catch {
        // Ignore malformed non-JSON frames
      }
    };
    ws.onclose = () => {
      if (!closedByCleanup) {
        appendActivity(
          createActivityEntry(
            'Runtime',
            'warning',
            NexusStatus.Disconnected,
            'Daemon WebSocket event stream closed.'
          )
        );
      }
    };
    return () => {
      closedByCleanup = true;
      coalescer.cancel();
      ws.close();
    };
  }, [
    appendActivity,
    daemonAuthenticated,
    hydrateFromDaemon,
    settings.connections.enableWebSocketEvents,
    wsEndpointKey,
  ]);

  const bridgeStatus = lastProbe ? lastProbe.status : NexusStatus.Disconnected;
  const handleCloseMobile = useCallback(() => setMobileMenuOpen(false), []);
  const handleOpenMobileMenu = useCallback(() => setMobileMenuOpen(true), []);
  const handleEnableDemoIfInactive = useCallback(() => {
    setDemoMode((prev) => {
      if (prev) return prev;
      setProjects((p) => {
        const merged = [...DEMO_PROJECTS, ...p.filter((item) => !item.isDemoFixture)];
        syncEngineProjectCounts(merged);
        return merged;
      });
      setTasks((t) => [...DEMO_TASKS, ...t.filter((item) => !item.isDemoFixture)]);
      setActivityLog((a) => [...DEMO_ACTIVITY_ENTRIES, ...a.filter((item) => !item.isDemoFixture)]);
      return true;
    });
  }, [syncEngineProjectCounts]);
  const handleToggleStreamPaused = useCallback(() => setStreamPaused((p) => !p), []);
  const handleClearSessionLog = useCallback(() => setActivityLog([]), []);
  const handleResetDefaults = useCallback(() => {
    setSettings(createInitialSettings());
    appendActivity(
      createActivityEntry(
        'Security',
        'info',
        NexusStatus.Available,
        'Settings reset to safety defaults.'
      )
    );
  }, [appendActivity]);
  const exportedProviderSummary = useMemo(
    () =>
      providers.map((p) => ({
        id: p.id,
        kind: p.kind,
        enabled: p.enabled,
        credentialConfigured: p.credentialConfigured,
        status: p.status,
      })),
    [providers]
  );
  const handleExportDiagnostics = useCallback(
    () =>
      buildDiagnosticsExportPayload({
        runtime,
        previewHealth,
        lastProbe,
        daemonDiagnostics,
        settings,
        providers: exportedProviderSummary,
        projectsCount: projects.length,
        tasksCount: tasks.length,
      }),
    [
      daemonDiagnostics,
      exportedProviderSummary,
      lastProbe,
      previewHealth,
      projects.length,
      runtime,
      settings,
      tasks.length,
    ]
  );

  return (
    <div className="min-h-screen flex bg-[#0B0F14] text-[#F1F5F9]">
      <Sidebar
        activeSection={activeSection}
        onSelectSection={setActiveSection}
        runtime={runtime}
        bridgeStatus={bridgeStatus}
        demoMode={demoMode}
        mobileOpen={mobileMenuOpen}
        onCloseMobile={handleCloseMobile}
      />

      <div className="flex-1 min-w-0 flex flex-col">
        <TopBar
          activeSection={activeSection}
          probing={probing}
          demoMode={demoMode}
          onToggleDemoMode={handleToggleDemoMode}
          onProbeBridge={handleProbeBridge}
          onOpenMobileMenu={handleOpenMobileMenu}
        />

        <main className="flex-1 px-5 py-6 lg:px-8 lg:py-8 max-w-7xl w-full mx-auto">
          {activeSection === NavSection.Dashboard && (
            <DashboardView
              runtime={runtime}
              previewHealth={previewHealth}
              lastProbe={lastProbe}
              providers={providers}
              engines={engines}
              projects={projects}
              tasks={tasks}
              activityLog={activityLog}
              demoMode={demoMode}
              daemonAuthenticated={daemonAuthenticated}
              mcpStatus={mcpStatus}
              onNavigate={setActiveSection}
            />
          )}

          {activeSection !== NavSection.Dashboard && (
            <Suspense
              fallback={
                <div className="py-12 text-center text-xs font-mono text-[#94A3B8]">
                  Loading module view...
                </div>
              }
            >
              {activeSection === NavSection.Connections && (
                <ConnectionsView
                  runtime={runtime}
                  config={settings.connections}
                  providers={providers}
                  lastProbe={lastProbe}
                  probing={probing}
                  daemonAuthenticated={daemonAuthenticated}
                  mcpStatus={mcpStatus}
                  onUpdateConfig={handleUpdateEndpointConfig}
                  onUpdateProvider={handleUpdateProvider}
                  onAddCustomProvider={handleAddCustomProvider}
                  onRemoveCustomProvider={handleRemoveCustomProvider}
                  onVerifyProvider={handleVerifyProvider}
                  onProbeBridge={handleProbeBridge}
                />
              )}

              {activeSection === NavSection.Engines && (
                <EnginesView
                  engines={engines}
                  adapterGuides={adapterGuides}
                  onUpdateEnginePath={handleUpdateEnginePath}
                  onScanEngines={handleScanEngines}
                />
              )}

              {activeSection === NavSection.Projects && (
                <ProjectsView
                  runtime={runtime}
                  projects={projects}
                  demoMode={demoMode}
                  onRegisterProject={handleRegisterProject}
                  onAssociateEngine={handleAssociateEngine}
                  onRemoveProject={handleRemoveProject}
                  onLoadDemoFixture={handleEnableDemoIfInactive}
                  onNavigate={setActiveSection}
                />
              )}

              {activeSection === NavSection.Tools && <ToolsView liveTools={liveTools} />}

              {activeSection === NavSection.Tasks && (
                <TasksView
                  tasks={tasks}
                  projects={projects}
                  demoMode={demoMode}
                  daemonAuthenticated={daemonAuthenticated}
                  onCreateDraftTask={handleCreateDraftTask}
                  onTaskControl={handleTaskControl}
                  onLoadDemoFixture={handleEnableDemoIfInactive}
                />
              )}

              {activeSection === NavSection.Activity && (
                <ActivityView
                  entries={activityLog}
                  streamPaused={streamPaused}
                  onToggleStreamPaused={handleToggleStreamPaused}
                  onClearSessionLog={handleClearSessionLog}
                />
              )}

              {activeSection === NavSection.Plugins && (
                <PluginsView
                  liveAdapters={liveAdapters}
                  daemonAuthenticated={daemonAuthenticated}
                />
              )}

              {activeSection === NavSection.Diagnostics && (
                <DiagnosticsView
                  runtime={runtime}
                  previewHealth={previewHealth}
                  lastProbe={lastProbe}
                  desktopLifecycle={desktopLifecycle}
                  desktopDiagnostics={desktopDiagnostics}
                  daemonDiagnostics={daemonDiagnostics}
                  probing={probing}
                  onProbeBridge={handleProbeBridge}
                  onRefreshRuntime={handleRefreshRuntime}
                  onControlDaemon={handleControlDesktopDaemon}
                />
              )}

              {activeSection === NavSection.Settings && (
                <SettingsView
                  settings={settings}
                  providers={providers}
                  onUpdateSettings={setSettings}
                  onResetDefaults={handleResetDefaults}
                  onExportDiagnostics={handleExportDiagnostics}
                />
              )}
            </Suspense>
          )}
        </main>
      </div>
    </div>
  );
}
