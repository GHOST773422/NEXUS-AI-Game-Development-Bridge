import { AIProviderKind, MCPTransportKind, NexusStatus } from './status';

export const NEXUS_PROTOCOL_VERSION = '2026.1.0-stage1';

export interface RuntimeEnvironmentInfo {
  hostKind: 'TauriDesktop' | 'WebPreview';
  hasTauriIPC: boolean;
  isSecureContext: boolean;
  origin: string;
  protocol: string;
  supportsWebSocket: boolean;
  platformHint: string;
  userAgent: string;
  detectedAt: string;
}

export interface ProtocolEnvelope<T = unknown> {
  protocolVersion: string;
  messageId: string;
  timestamp: string;
  payload: T;
}

export interface RestHealthResponse {
  service: 'nexus-preview-backend' | 'nexus-python-daemon';
  protocolVersion: string;
  status: NexusStatus;
  runtime: 'node-express' | 'python-daemon';
  bindAddress: string;
  capabilities: {
    localEngineExecution: boolean;
    tauriIpcAvailable: boolean;
    pythonDaemonRunning: boolean;
    sqlitePersistence: boolean;
    geminiServerKeyConfigured: boolean;
  };
  timestamp: string;
}

export interface MCPJsonRpcRequest {
  jsonrpc: '2.0';
  id: string | number;
  method: string;
  params?: Record<string, unknown>;
}

export interface MCPJsonRpcResponse {
  jsonrpc: '2.0';
  id: string | number;
  result?: unknown;
  error?: {
    code: number;
    message: string;
    data?: unknown;
  };
}

export interface MCPToolDescriptor {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
  annotations?: {
    readOnlyHint?: boolean;
    destructiveHint?: boolean;
    idempotentHint?: boolean;
  };
}

export type WebSocketEventType =
  | 'bridge.status'
  | 'engine.health'
  | 'engine.log'
  | 'engine.scene_changed'
  | 'task.step_updated'
  | 'error.diagnostic';

export interface WebSocketEventEnvelope<T = unknown> {
  type: WebSocketEventType;
  protocolVersion: string;
  sequence: number;
  timestamp: string;
  source: string;
  data: T;
}

export interface AIProviderCapabilities {
  kind: AIProviderKind;
  supportsStreaming: boolean;
  supportsToolCalling: boolean;
  requiresPaidKey: boolean;
  transportsSupported: MCPTransportKind[];
}

export interface PreviewCapabilityReport {
  environment: 'ai-studio-preview' | 'local-node' | 'tauri-desktop';
  nodeVersion: string;
  platform: string;
  arch: string;
  daemonStatus: NexusStatus;
  unityAdapterStatus: NexusStatus;
  godotAdapterStatus: NexusStatus;
  geminiConfigured: boolean;
  registeredToolCount: number;
  incompatibilitiesCount: number;
}
