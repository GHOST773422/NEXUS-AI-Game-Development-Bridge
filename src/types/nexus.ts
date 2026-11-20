/**
 * NEXUS Frontend Domain Contracts
 * Re-exports shared SDK contracts and defines complete UI & daemon service models.
 */

export * from '../../sdk/ts';

import type {
  AIProviderKind,
  EngineKind,
  MCPTransportKind,
  NexusStatus,
  PermissionScope,
  RuntimeEnvironmentInfo,
} from '../../sdk/ts';

export type RuntimeHostKind = 'TauriDesktop' | 'WebPreview';

export interface BridgeEndpointConfig {
  restBaseUrl: string;
  wsUrl: string;
  mcpHttpUrl: string;
  bindAddress: string;
  requireBearerToken: boolean;
}

export interface BridgeProbeResult {
  endpoint: string;
  status: NexusStatus;
  httpStatus: number | null;
  latencyMs: number | null;
  message: string;
  checkedAt: string;
}

export interface SubsystemRecord {
  id: string;
  name: string;
  layer:
    | 'Frontend'
    | 'Desktop Shell'
    | 'Daemon & Gateway'
    | 'AI & Orchestration'
    | 'Engine Adapters'
    | 'Security & Storage';
  status: NexusStatus;
  targetRuntime: string;
  summary: string;
  plannedStage: string;
}

export interface AIProviderSpec {
  id: string;
  kind: AIProviderKind;
  credentialBackend: string;
  status: NexusStatus;
  supportsStreaming: boolean;
  supportsToolCalling: boolean;
  notes: string;
}

export interface AIProviderConnection {
  id: string;
  name: string;
  kind: AIProviderKind;
  enabled: boolean;
  modelId: string;
  endpointUrl: string;
  credentialRef: string;
  credentialConfigured: boolean;
  credentialBackend: string;
  status: NexusStatus;
  supportsStreaming: boolean;
  supportsToolCalling: boolean;
  notes: string;
  isCustom?: boolean;
}

export interface ExternalMCPClientSpec {
  id: string;
  name: string;
  supportedTransports: MCPTransportKind[];
  endpointOrCommand: string;
  authMode: string;
  status: NexusStatus;
  notes: string;
}

export interface EngineCardState {
  id: string;
  engine: EngineKind;
  displayName: string;
  detectionStatus: NexusStatus;
  connectionStatus: NexusStatus;
  installationPath: string;
  version: string;
  adapterVersion: string;
  availableProjectCount: number;
  verifiedCapabilityCount: number;
  contractMethodCount: number;
  notes: string;
}

export interface EngineAdapterCapabilitySpec {
  method: string;
  description: string;
  unityMechanism: string;
  godotMechanism: string;
  status: NexusStatus;
}

export interface RegisteredProject {
  id: string;
  name: string;
  engine: EngineKind;
  rootPath: string;
  engineVersion: string;
  status: NexusStatus;
  lastInspectedAt: string | null;
  activeScene: string | null;
  notes: string;
  isDemoFixture?: boolean;
}

export interface OrchestrationStepSpec {
  stepNumber: number;
  name: string;
  subsystem: string;
  description: string;
  gateRequired: boolean;
}

export interface TaskStepRun extends OrchestrationStepSpec {
  status: NexusStatus;
}

export type TaskPriority = 'low' | 'normal' | 'high' | 'critical';

export interface TaskRecord {
  id: string;
  title: string;
  projectId: string;
  projectName: string;
  engine: EngineKind;
  priority?: TaskPriority;
  agentId?: string;
  progress?: number;
  status: NexusStatus;
  currentOperation: string;
  createdAt: string;
  updatedAt: string;
  checkpointId: string | null;
  retryAttempts?: number;
  maxRepairAttempts?: number;
  approvalPending?: { requiredScopes: string[]; reason: string } | null;
  report?: Record<string, unknown> | null;
  steps: TaskStepRun[];
  logs: string[];
  isDemoFixture?: boolean;
}

export interface EnvironmentIncompatibility {
  id: string;
  capability: string;
  windowsDesktopTarget: string;
  aiStudioWebBehavior: string;
  mitigation: string;
  severity: 'Blocking in Web Preview' | 'Transport Restricted' | 'Environment Difference';
}

export interface SessionActivityEntry {
  id: string;
  timestamp: string;
  category: 'Runtime' | 'Probe' | 'Navigation' | 'Security' | 'Project' | 'Task';
  severity: 'info' | 'warning' | 'error';
  status: NexusStatus;
  message: string;
  detail?: string;
  isDemoFixture?: boolean;
}

export type SettingsCategory =
  | 'General'
  | 'Appearance'
  | 'AI providers'
  | 'Connections'
  | 'Permissions'
  | 'Execution limits'
  | 'Storage'
  | 'Diagnostics';

export interface NexusSettingsState {
  general: {
    autoProbeOnDesktopLaunch: boolean;
    confirmBeforeClosingActiveTasks: boolean;
    defaultProjectSearchRoot: string;
  };
  appearance: {
    tableDensity: 'compact' | 'comfortable';
    logFontSize: '12px' | '13px';
    reducedMotion: boolean;
  };
  aiProviders: {
    defaultProviderId: string;
    requestTimeoutMs: number;
    streamResponses: boolean;
    allowPaidApiCalls: boolean;
  };
  connections: BridgeEndpointConfig & {
    reconnectBackoffMs: number;
    enableRestApi: boolean;
    enableWebSocketEvents: boolean;
  };
  permissions: {
    projectDirectorySandboxing: boolean;
    allowOutOfProjectWrites: boolean;
    approvalScopes: PermissionScope[];
  };
  executionLimits: {
    maxRepairAttempts: number;
    stepTimeoutSec: number;
    maxConcurrentTasks: number;
  };
  storage: {
    sqliteFilename: string;
    checkpointRetentionCount: number;
    auditLogRetentionDays: number;
  };
  diagnostics: {
    logVerbosity: 'warn' | 'info' | 'debug';
    captureStackTraces: boolean;
  };
}

export interface DaemonLifecycleStatus {
  running: boolean;
  supervisedByShell: boolean;
  launchMode: 'None' | 'ExternalIndependent' | 'BundledSidecar' | 'PythonModule';
  pid: number | null;
  endpoint: string;
  daemonVersion: string | null;
  dataDir: string;
  sidecarPath: string | null;
  keepAliveOnExit: boolean;
  lastStartedAt: string | null;
  lastError: string | null;
}

export interface DesktopConfigPayload {
  bindHost: string;
  restPort: number;
  wsPort: number;
  mcpHttpPort: number;
  launchDaemonOnStartup: boolean;
  keepDaemonAliveOnExit: boolean;
  pythonExecutable: string;
  daemonMode: string;
  dataDirOverride: string | null;
}

export interface DesktopDiagnosticsReport {
  appVersion: string;
  protocolVersion: string;
  os: string;
  arch: string;
  dataDir: string;
  tokenConfigured: boolean;
  desktopLogPath: string;
  desktopLogBytes: number;
  daemonLogPath: string;
  daemonLogBytes: number;
  pythonCheck: string;
  sidecarDetected: boolean;
  sidecarPath: string | null;
  lifecycle: DaemonLifecycleStatus;
  daemonHealth: Record<string, unknown> | null;
  daemonDiagnostics: Record<string, unknown> | null;
  bundledAdapters: {
    unityStaged: boolean;
    unityPath: string;
    godotStaged: boolean;
    godotPath: string;
  };
}

export interface AdapterInstallGuide {
  engine: string;
  displayName: string;
  resourcePath: string;
  stagedPresent: boolean;
  minEngineVersion: string;
  defaultEndpoint: string;
  steps: string[];
}

export interface LiveAdapterDescriptor {
  adapterId: string;
  displayName: string;
  version: string;
  engineKind: string;
  runtimeLanguage: string;
  isTestAdapter: boolean;
  protocolVersion: string;
  lifecycleState: NexusStatus;
  transportKind: string;
  registeredToolCount: number;
  testToolCount: number;
  reconnectAttempts: number;
  lastHeartbeatAt: string | null;
}

export interface DaemonMcpStatusPayload {
  serverName: string;
  protocolVersion: string;
  transports: string[];
  mcpHttpPort: number;
  tools: Array<{
    name: string;
    description?: string;
    annotations?: Record<string, unknown>;
  }>;
  resources: Array<{
    uri: string;
    name: string;
    description?: string;
    mimeType?: string;
  }>;
  prompts: Array<{
    name: string;
    description?: string;
  }>;
}

export interface BridgeTransport {
  readonly transportMode: 'WebHTTP' | 'TauriIPC';
  detectEnvironment(): RuntimeEnvironmentInfo;
  probeHealth(config: BridgeEndpointConfig): Promise<BridgeProbeResult>;
}
