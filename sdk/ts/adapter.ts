import { EngineKind, NexusStatus, PermissionScope, ToolCategory } from './status';

export interface EngineDetectionResult {
  engine: EngineKind;
  executablePath: string;
  installSource: string;
  detectedAt: string;
}

export interface EngineVersionInfo {
  engine: EngineKind;
  rawVersion: string;
  major: number;
  minor: number;
  patch: number;
  scriptingBackend?: string;
  renderPipeline?: string;
}

export interface ProjectManifest {
  id: string;
  name: string;
  engine: EngineKind;
  rootPath: string;
  engineVersion: string;
  lastOpenedAt?: string;
}

export interface EngineCapabilitySnapshot {
  engine: EngineKind;
  version: EngineVersionInfo;
  editorConnected: boolean;
  isCompilingOrImporting: boolean;
  supportedToolIds: string[];
  activeScenePath?: string;
}

export interface ToolContractSchema {
  id: string;
  category: ToolCategory;
  description: string;
  inputSchema: Record<string, unknown>;
  outputSchema: Record<string, unknown>;
  engineCompatibility: EngineKind[];
  requiredPermissions: PermissionScope[];
  executionContext: 'EditorMainThread' | 'BridgeDaemon' | 'BuildRunner';
  errorHandling: string;
  implementationStatus: NexusStatus;
}

export interface ToolInvocationRequest {
  requestId: string;
  toolId: string;
  projectId: string;
  arguments: Record<string, unknown>;
  dryRun?: boolean;
}

export interface ToolInvocationResult {
  requestId: string;
  toolId: string;
  status: NexusStatus.Available | NexusStatus.Failed | NexusStatus.Unavailable;
  verified: boolean;
  output?: Record<string, unknown>;
  error?: {
    code: string;
    message: string;
    file?: string;
    line?: number;
  };
  durationMs: number;
}

export interface ScreenshotArtifact {
  projectId: string;
  viewport: 'GameView' | 'SceneView' | 'SubViewport';
  mimeType: 'image/png';
  width: number;
  height: number;
  capturedAt: string;
  artifactPath: string;
}

export interface EngineHealthReport {
  engine: EngineKind;
  projectId: string;
  status: NexusStatus;
  mainThreadResponsive: boolean;
  isCompiling: boolean;
  lastHeartbeatAt: string;
  message?: string;
}

/**
 * Universal Engine Adapter Contract.
 * Every native Unity or Godot adapter must implement these 13 lifecycle operations.
 */
export interface EngineAdapterContract {
  readonly engineKind: EngineKind;
  detectEngine(): Promise<EngineDetectionResult[]>;
  identifyVersion(projectPath: string): Promise<EngineVersionInfo>;
  discoverProjects(searchRoots: string[]): Promise<ProjectManifest[]>;
  connectProject(projectId: string): Promise<EngineHealthReport>;
  discoverCapabilities(projectId: string): Promise<EngineCapabilitySnapshot>;
  registerTools(projectId: string): Promise<ToolContractSchema[]>;
  executeTool(request: ToolInvocationRequest): Promise<ToolInvocationResult>;
  inspectProjectState(projectId: string): Promise<Record<string, unknown>>;
  subscribeEvents(projectId: string, onEvent: (event: unknown) => void): () => void;
  captureScreenshot(
    projectId: string,
    viewport: ScreenshotArtifact['viewport']
  ): Promise<ScreenshotArtifact>;
  checkHealth(projectId: string): Promise<EngineHealthReport>;
  reportError(error: unknown): { code: string; message: string };
  disconnectAndReconnect(projectId: string): Promise<EngineHealthReport>;
}

export const ADAPTER_MANIFEST_SCHEMA_VERSION = '1.0' as const;
export const ADAPTER_WIRE_PROTOCOL_VERSION = '1.0.0' as const;

export const ADAPTER_PROTOCOL_METHODS = [
  'getEngineInfo',
  'discoverProjects',
  'connect',
  'disconnect',
  'getCapabilities',
  'listTools',
  'executeTool',
  'getProjectState',
  'subscribeEvents',
  'captureScreenshot',
  'healthCheck',
] as const;

export type AdapterProtocolMethod = (typeof ADAPTER_PROTOCOL_METHODS)[number];

export type AdapterRuntimeLanguage =
  'C#' | 'GDScript' | 'C++' | 'Python' | 'NodeTS' | 'Rust' | 'Other';

export type AdapterEngineKind = 'Unity' | 'Godot' | 'Unreal' | 'Custom' | 'TestHarness';

export type AdapterLifecycleState =
  | 'Installed'
  | 'Validated'
  | 'Connecting'
  | 'Connected'
  | 'Degraded'
  | 'Reconnecting'
  | 'Disconnected'
  | 'Failed';

export interface AdapterManifestTransportSpec {
  kind: 'stdio' | 'tcp-loopback';
  command?: string[];
  host?: string;
  port?: number;
  workingDir?: string | null;
}

export interface AdapterManifestSchema {
  manifestVersion: string;
  adapterId: string;
  displayName: string;
  version: string;
  runtimeLanguage: AdapterRuntimeLanguage;
  engineKind: AdapterEngineKind;
  isTestAdapter: boolean;
  protocolVersion: string;
  minDaemonProtocolVersion?: string;
  maxDaemonProtocolVersion?: string;
  transport: AdapterManifestTransportSpec;
  entrypoint: string;
  capabilities?: string[];
  requestedPermissions?: PermissionScope[];
  supportedEngineVersions?: string[];
  checksumSha256?: string | null;
  author?: string;
  description?: string;
}

export interface AdapterRuntimeDescriptor {
  adapterId: string;
  displayName: string;
  version: string;
  engineKind: AdapterEngineKind;
  runtimeLanguage: AdapterRuntimeLanguage;
  isTestAdapter: boolean;
  protocolVersion: string;
  lifecycleState: AdapterLifecycleState;
  transportKind: 'stdio' | 'tcp-loopback';
  registeredToolCount: number;
  testToolCount: number;
  reconnectAttempts: number;
  lastHeartbeatAt: string | null;
}
