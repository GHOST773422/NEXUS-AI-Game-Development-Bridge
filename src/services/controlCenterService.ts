import {
  AIProviderConnection,
  AIProviderKind,
  EngineCardState,
  EngineKind,
  LiveAdapterDescriptor,
  NexusSettingsState,
  NexusStatus,
  PermissionScope,
  RegisteredProject,
  RestHealthResponse,
  TaskPriority,
  TaskRecord,
  TaskStepRun,
  ToolCategory,
  ToolContractSchema,
} from '../types/nexus';
import { ORCHESTRATION_PIPELINE } from '../data/architectureSpec';

export function createInitialSettings(): NexusSettingsState {
  return {
    general: {
      autoProbeOnDesktopLaunch: true,
      confirmBeforeClosingActiveTasks: true,
      defaultProjectSearchRoot: 'C:\\Games',
    },
    appearance: {
      tableDensity: 'comfortable',
      logFontSize: '12px',
      reducedMotion: false,
    },
    aiProviders: {
      defaultProviderId: 'conn-gemini',
      requestTimeoutMs: 30000,
      streamResponses: true,
      allowPaidApiCalls: false,
    },
    connections: {
      restBaseUrl: 'http://127.0.0.1:47100',
      wsUrl: 'ws://127.0.0.1:47101/events',
      mcpHttpUrl: 'http://127.0.0.1:47102/mcp',
      bindAddress: '127.0.0.1',
      requireBearerToken: true,
      reconnectBackoffMs: 2000,
      enableRestApi: true,
      enableWebSocketEvents: true,
    },
    permissions: {
      projectDirectorySandboxing: true,
      allowOutOfProjectWrites: false,
      approvalScopes: [
        PermissionScope.ModifyAssets,
        PermissionScope.BuildExport,
        PermissionScope.ProcessSpawnRestricted,
      ],
    },
    executionLimits: {
      maxRepairAttempts: 3,
      stepTimeoutSec: 60,
      maxConcurrentTasks: 1,
    },
    storage: {
      sqliteFilename: 'nexus.db',
      checkpointRetentionCount: 25,
      auditLogRetentionDays: 30,
    },
    diagnostics: {
      logVerbosity: 'info',
      captureStackTraces: true,
    },
  };
}

export function createInitialAIProviders(
  previewHealth: RestHealthResponse | null
): AIProviderConnection[] {
  const geminiConfigured = Boolean(previewHealth?.capabilities.geminiServerKeyConfigured);
  return [
    {
      id: 'conn-gemini',
      name: 'Google Gemini',
      kind: AIProviderKind.GoogleGemini,
      enabled: true,
      modelId: 'gemini-4-hydrogen',
      endpointUrl: '/api/ai/providers/generate (Server Proxy)',
      credentialRef: geminiConfigured ? 'env://GEMINI_API_KEY' : 'wincred://nexus/gemini_api_key',
      credentialConfigured: geminiConfigured,
      credentialBackend: 'Server Env Secret / Windows Credential Vault',
      status: geminiConfigured ? NexusStatus.Available : NexusStatus.Disconnected,
      supportsStreaming: true,
      supportsToolCalling: true,
      notes:
        'Built-in Gemini API client (via server proxy or daemon vault). Independent from Gemini CLI MCP connections.',
    },
    {
      id: 'conn-claude',
      name: 'Anthropic Claude',
      kind: AIProviderKind.AnthropicClaude,
      enabled: false,
      modelId: 'claude-sonnet-4-20250514',
      endpointUrl: 'https://api.anthropic.com/v1',
      credentialRef: 'wincred://nexus/anthropic_api_key',
      credentialConfigured: false,
      credentialBackend: 'Windows Credential Vault / Local Daemon',
      status: NexusStatus.Disconnected,
      supportsStreaming: true,
      supportsToolCalling: true,
      notes:
        'Anthropic API adapter. Connecting an Anthropic API key does not connect Claude Desktop over MCP.',
    },
    {
      id: 'conn-openai',
      name: 'OpenAI',
      kind: AIProviderKind.OpenAI,
      enabled: false,
      modelId: 'gpt-4.1',
      endpointUrl: 'https://api.openai.com/v1',
      credentialRef: 'wincred://nexus/openai_api_key',
      credentialConfigured: false,
      credentialBackend: 'Windows Credential Vault / Local Daemon',
      status: NexusStatus.Disconnected,
      supportsStreaming: true,
      supportsToolCalling: true,
      notes: 'OpenAI API adapter. Separate from external ChatGPT or Codex MCP clients.',
    },
    {
      id: 'conn-local-openai-compat',
      name: 'OpenAI-Compatible Server',
      kind: AIProviderKind.OpenAICompatible,
      enabled: false,
      modelId: 'llama3.2',
      endpointUrl: 'http://127.0.0.1:11434/v1',
      credentialRef: 'vault://nexus/openai_compatible_key',
      credentialConfigured: false,
      credentialBackend: 'Optional Local Vault (Ollama / LM Studio / vLLM)',
      status: NexusStatus.Disconnected,
      supportsStreaming: true,
      supportsToolCalling: true,
      notes: 'Operates locally without requiring a paid cloud AI API key.',
      isCustom: false,
    },
  ];
}

export function createInitialEngines(projects: RegisteredProject[]): EngineCardState[] {
  const unityProjects = projects.filter((p) => p.engine === EngineKind.Unity).length;
  const godotProjects = projects.filter((p) => p.engine === EngineKind.Godot).length;

  return [
    {
      id: 'engine-unity',
      engine: EngineKind.Unity,
      displayName: 'Unity Editor',
      detectionStatus: NexusStatus.Unavailable,
      connectionStatus: NexusStatus.Disconnected,
      installationPath: 'Not detected (Web Preview)',
      version: 'Not detected',
      adapterVersion: '0.1.0 (com.nexus.bridge)',
      availableProjectCount: unityProjects,
      verifiedCapabilityCount: 0,
      contractMethodCount: 13,
      notes:
        'Native C# UPM package (adapters/unity/). Handles main-thread dispatch, Undo.RecordObject, and AssemblyReloadEvents.',
    },
    {
      id: 'engine-godot',
      engine: EngineKind.Godot,
      displayName: 'Godot Engine 4.x',
      detectionStatus: NexusStatus.Unavailable,
      connectionStatus: NexusStatus.Disconnected,
      installationPath: 'Not detected (Web Preview)',
      version: 'Not detected',
      adapterVersion: '0.1.0 (nexus_bridge)',
      availableProjectCount: godotProjects,
      verifiedCapabilityCount: 0,
      contractMethodCount: 13,
      notes:
        'Native GDScript EditorPlugin (adapters/godot/). Uses EditorInterface, EditorUndoRedoManager, and SubViewport capture.',
    },
  ];
}

export function createDraftTaskRecord(params: {
  title: string;
  project: RegisteredProject;
  priority?: 'low' | 'normal' | 'high' | 'critical';
  agentId?: string;
}): TaskRecord {
  const now = new Date().toISOString();
  const priority = params.priority ?? 'normal';
  const agentId = params.agentId?.trim() || 'operator';
  return {
    id: `task-${Date.now().toString(36)}`,
    title: params.title.trim(),
    projectId: params.project.id,
    projectName: params.project.name,
    engine: params.project.engine,
    priority,
    agentId,
    progress: 0,
    status: NexusStatus.Planned,
    currentOperation:
      'Queued in frontend draft; requires local Python Autonomous Orchestrator & connected engine adapter.',
    createdAt: now,
    updatedAt: now,
    checkpointId: null,
    retryAttempts: 0,
    maxRepairAttempts: 3,
    approvalPending: null,
    report: null,
    steps: ORCHESTRATION_PIPELINE.map((step) => ({
      ...step,
      status: NexusStatus.Planned,
    })),
    logs: [
      `Task draft registered for ${params.project.name} (${params.project.engine}) [priority=${priority}, agent=${agentId}].`,
      'Live execution blocked: local Python Autonomous Orchestrator and engine adapter are not connected.',
    ],
    isDemoFixture: params.project.isDemoFixture,
  };
}

export function buildDiagnosticsExportPayload(data: unknown): string {
  return JSON.stringify(
    {
      exportedAt: new Date().toISOString(),
      product: 'NEXUS',
      runtimeProfile: 'NEXUS Desktop & Daemon Control Center',
      payload: data,
    },
    null,
    2
  );
}

function coerceNexusStatus(raw: unknown, fallback: NexusStatus): NexusStatus {
  const values = Object.values(NexusStatus) as string[];
  return typeof raw === 'string' && values.includes(raw) ? (raw as NexusStatus) : fallback;
}

export function mapDaemonProject(raw: Record<string, unknown>): RegisteredProject {
  const engineRaw = raw.engine === EngineKind.Godot ? EngineKind.Godot : EngineKind.Unity;
  return {
    id: String(raw.id ?? ''),
    name: String(raw.name ?? 'Unnamed Project'),
    engine: engineRaw,
    rootPath: String(raw.root_path ?? raw.rootPath ?? ''),
    engineVersion: String(raw.engine_version ?? raw.engineVersion ?? 'Unverified'),
    status: coerceNexusStatus(raw.status, NexusStatus.Disconnected),
    lastInspectedAt: raw.updated_at ? String(raw.updated_at) : null,
    activeScene: raw.active_scene ? String(raw.active_scene) : null,
    notes: String(raw.notes ?? ''),
  };
}

export function mapDaemonTask(
  raw: Record<string, unknown>,
  projects: RegisteredProject[]
): TaskRecord {
  const projectId = String(raw.projectId ?? raw.project_id ?? '');
  const matchedProj = projects.find((p) => p.id === projectId);
  const rawSteps = Array.isArray(raw.steps) ? raw.steps : [];
  const mappedSteps: TaskStepRun[] = rawSteps.map((s, idx) => {
    const rec = (s && typeof s === 'object' ? s : {}) as Record<string, unknown>;
    return {
      stepNumber: Number(rec.stepNumber ?? rec.step_number ?? idx + 1),
      name: String(rec.name ?? `Step ${idx + 1}`),
      subsystem: String(rec.subsystem ?? 'Orchestrator'),
      description: String(rec.description ?? ''),
      gateRequired: Boolean(rec.gateRequired ?? rec.gate_required ?? false),
      status: coerceNexusStatus(rec.status, NexusStatus.Planned),
    };
  });
  const plan =
    raw.plan && typeof raw.plan === 'object' ? (raw.plan as Record<string, unknown>) : {};
  const retryPolicy =
    plan.retryPolicy && typeof plan.retryPolicy === 'object'
      ? (plan.retryPolicy as Record<string, unknown>)
      : {};
  const approval =
    plan.approvalPending && typeof plan.approvalPending === 'object'
      ? (plan.approvalPending as { requiredScopes: string[]; reason: string })
      : null;

  return {
    id: String(raw.id ?? ''),
    title: String(raw.title ?? 'Autonomous Task'),
    projectId,
    projectName: matchedProj?.name ?? String(raw.projectName ?? (projectId || 'Project')),
    engine: raw.engine === EngineKind.Godot ? EngineKind.Godot : EngineKind.Unity,
    priority: (['low', 'normal', 'high', 'critical'].includes(String(raw.priority))
      ? String(raw.priority)
      : 'normal') as TaskPriority,
    agentId: String(raw.agentId ?? raw.agent_id ?? 'operator'),
    progress: Number(raw.progress ?? 0),
    status: coerceNexusStatus(raw.status, NexusStatus.Planned),
    currentOperation: String(raw.currentOperation ?? raw.current_operation ?? ''),
    createdAt: String(raw.createdAt ?? raw.created_at ?? new Date().toISOString()),
    updatedAt: String(raw.updatedAt ?? raw.updated_at ?? new Date().toISOString()),
    checkpointId: raw.checkpointId ? String(raw.checkpointId) : null,
    retryAttempts: Number(plan.repairAttempts ?? 0),
    maxRepairAttempts: Number(retryPolicy.maxRepairAttempts ?? 3),
    approvalPending: approval,
    report:
      raw.report && typeof raw.report === 'object' ? (raw.report as Record<string, unknown>) : null,
    steps: mappedSteps.length
      ? mappedSteps
      : ORCHESTRATION_PIPELINE.map((step) => ({
          ...step,
          status: NexusStatus.Planned,
        })),
    logs: Array.isArray(raw.logs) ? raw.logs.map((l) => String(l)) : [],
  };
}

export function mapDaemonToolContract(raw: Record<string, unknown>): ToolContractSchema {
  const rawEngines = Array.isArray(raw.engine_compatibility)
    ? raw.engine_compatibility
    : Array.isArray(raw.engineCompatibility)
      ? raw.engineCompatibility
      : [];
  const engines = rawEngines.map((e) =>
    String(e) === EngineKind.Godot ? EngineKind.Godot : EngineKind.Unity
  );
  const rawPerms = Array.isArray(raw.required_permissions)
    ? raw.required_permissions
    : Array.isArray(raw.requiredPermissions)
      ? raw.requiredPermissions
      : [];
  const rawCategory = String(raw.category ?? ToolCategory.Debugging);
  const categoryValues = Object.values(ToolCategory) as string[];
  const category: ToolCategory = categoryValues.includes(rawCategory)
    ? (rawCategory as ToolCategory)
    : ToolCategory.Debugging;
  const rawContext = String(raw.execution_context ?? raw.executionContext ?? 'EditorMainThread');
  const executionContext: ToolContractSchema['executionContext'] =
    rawContext === 'BridgeDaemon' || rawContext === 'BuildRunner' ? rawContext : 'EditorMainThread';

  return {
    id: String(raw.id ?? ''),
    category,
    description: String(raw.description ?? ''),
    inputSchema:
      raw.input_schema && typeof raw.input_schema === 'object'
        ? (raw.input_schema as Record<string, unknown>)
        : {},
    outputSchema:
      raw.output_schema && typeof raw.output_schema === 'object'
        ? (raw.output_schema as Record<string, unknown>)
        : {},
    engineCompatibility: engines,
    requiredPermissions: rawPerms.map((p) => String(p) as PermissionScope),
    executionContext,
    errorHandling: String(raw.error_handling ?? 'Structured error envelope'),
    implementationStatus: coerceNexusStatus(raw.implementation_status, NexusStatus.Connected),
  };
}

export function mapDaemonEngine(
  raw: Record<string, unknown>,
  projects: RegisteredProject[]
): EngineCardState {
  const engine = raw.engine === EngineKind.Godot ? EngineKind.Godot : EngineKind.Unity;
  return {
    id: String(raw.id ?? `engine-${engine.toLowerCase()}`),
    engine,
    displayName: String(raw.display_name ?? `${engine} Engine`),
    detectionStatus: coerceNexusStatus(raw.detection_status, NexusStatus.Unavailable),
    connectionStatus: coerceNexusStatus(raw.connection_status, NexusStatus.Disconnected),
    installationPath: raw.executable_path
      ? String(raw.executable_path)
      : 'Not detected on local host',
    version: String(raw.version ?? 'Not detected'),
    adapterVersion: String(raw.adapter_version ?? '0.1.0'),
    availableProjectCount: projects.filter((p) => p.engine === engine).length,
    verifiedCapabilityCount: Number(raw.verified_capability_count ?? 0),
    contractMethodCount: Number(raw.contract_method_count ?? 13),
    notes:
      engine === EngineKind.Unity
        ? 'Native C# UPM package (adapters/unity/). Reported live by local Python daemon.'
        : 'Native GDScript EditorPlugin (adapters/godot/). Reported live by local Python daemon.',
  };
}

export function mapDaemonProvider(raw: Record<string, unknown>): AIProviderConnection {
  const configured = Boolean(raw.credentialConfigured);
  const enabled = Boolean(raw.enabled);
  return {
    id: String(raw.id ?? ''),
    name: String(raw.name ?? 'Provider'),
    kind: (raw.kind as AIProviderKind) ?? AIProviderKind.Custom,
    enabled,
    modelId: String(raw.modelId ?? ''),
    endpointUrl: String(raw.endpointUrl ?? ''),
    credentialRef: String(raw.credentialRef ?? ''),
    credentialConfigured: configured,
    credentialBackend: String(raw.credentialBackend ?? 'Local Credential Vault'),
    status: configured && enabled ? NexusStatus.Available : NexusStatus.Disconnected,
    supportsStreaming: Boolean(raw.supportsStreaming ?? true),
    supportsToolCalling: Boolean(raw.supportsToolCalling ?? true),
    notes: String(raw.notes ?? ''),
    isCustom: Boolean(raw.isCustom ?? false),
  };
}

export function mapDaemonAdapter(raw: Record<string, unknown>): LiveAdapterDescriptor {
  return {
    adapterId: String(raw.adapterId ?? ''),
    displayName: String(raw.displayName ?? ''),
    version: String(raw.version ?? '0.0.0'),
    engineKind: String(raw.engineKind ?? 'Custom'),
    runtimeLanguage: String(raw.runtimeLanguage ?? 'Unknown'),
    isTestAdapter: Boolean(raw.isTestAdapter),
    protocolVersion: String(raw.protocolVersion ?? '1.0.0'),
    lifecycleState: coerceNexusStatus(raw.lifecycleState, NexusStatus.Disconnected),
    transportKind: String(raw.transportKind ?? 'tcp-loopback'),
    registeredToolCount: Number(raw.registeredToolCount ?? 0),
    testToolCount: Number(raw.testToolCount ?? 0),
    reconnectAttempts: Number(raw.reconnectAttempts ?? 0),
    lastHeartbeatAt: raw.lastHeartbeatAt ? String(raw.lastHeartbeatAt) : null,
  };
}
