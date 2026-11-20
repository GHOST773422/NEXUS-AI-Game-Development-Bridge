import { NexusStatus } from './status';

export type NexusErrorCode =
  | 'NEXUS_UNAUTHORIZED'
  | 'NEXUS_PERMISSION_DENIED'
  | 'NEXUS_VALIDATION_ERROR'
  | 'NEXUS_NOT_FOUND'
  | 'NEXUS_CONFLICT'
  | 'NEXUS_ADAPTER_INCOMPATIBLE'
  | 'NEXUS_ADAPTER_PROTOCOL_ERROR'
  | 'NEXUS_DAEMON_UNAVAILABLE'
  | 'NEXUS_INTERNAL_ERROR';

export interface NexusApiErrorEnvelope {
  error: {
    code: NexusErrorCode;
    message: string;
    details: Record<string, unknown>;
    timestamp: string;
    requestId?: string;
  };
}

export interface DaemonHealthPayload {
  service: 'nexus-python-daemon';
  status: NexusStatus;
  daemonState: NexusStatus;
  os: string;
  pid: number;
  startedAt: string | null;
  sqliteInitialized: boolean;
  registeredProjectCount: number;
  connectedEngineCount: number;
  connectedTestAdaptersCount?: number;
  installedAdaptersCount?: number;
  registeredToolCount: number;
  mcpToolsCount?: number;
  restPort: number | null;
  wsPort: number | null;
  mcpHttpPort?: number | null;
  timestamp: string;
}

export interface TauriInvokeBridge {
  invoke<T = unknown>(command: string, args?: Record<string, unknown>): Promise<T>;
}

export interface ProviderVerificationPayload {
  providerId: string;
  verified: boolean;
  status: NexusStatus;
  credentialConfigured: boolean;
  modelId: string;
  latencyMs: number | null;
  message: string;
  checkedAt: string;
}

export interface ProviderGenerateResult {
  providerId: string;
  model: string;
  content: string;
  usage: {
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
    latencyMs: number;
  };
}
