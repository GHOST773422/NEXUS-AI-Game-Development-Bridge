import {
  AdapterInstallGuide,
  BridgeEndpointConfig,
  BridgeProbeResult,
  BridgeTransport,
  DaemonHealthPayload,
  DaemonLifecycleStatus,
  DesktopConfigPayload,
  DesktopDiagnosticsReport,
  NexusApiErrorEnvelope,
  NexusStatus,
  PreviewCapabilityReport,
  ProviderVerificationPayload,
  RestHealthResponse,
  RuntimeEnvironmentInfo,
  TauriInvokeBridge,
} from '../types/nexus';

declare global {
  interface Window {
    __TAURI_INTERNALS__?: TauriInvokeBridge;
  }
}

export const DEFAULT_BRIDGE_CONFIG: BridgeEndpointConfig = {
  restBaseUrl: 'http://127.0.0.1:47100',
  wsUrl: 'ws://127.0.0.1:47101/events',
  mcpHttpUrl: 'http://127.0.0.1:47102/mcp',
  bindAddress: '127.0.0.1',
  requireBearerToken: true,
};

/**
 * Inspects actual browser / desktop container capabilities without fabricating
 * native desktop or game engine availability.
 */
export function detectRuntimeEnvironment(): RuntimeEnvironmentInfo {
  const hasTauriIPC =
    typeof window !== 'undefined' && typeof window.__TAURI_INTERNALS__ !== 'undefined';
  const nav = typeof navigator !== 'undefined' ? navigator : undefined;
  const loc = typeof window !== 'undefined' ? window.location : undefined;

  return {
    hostKind: hasTauriIPC ? 'TauriDesktop' : 'WebPreview',
    hasTauriIPC,
    isSecureContext: typeof window !== 'undefined' ? Boolean(window.isSecureContext) : false,
    origin: loc ? loc.origin : 'node-test',
    protocol: loc ? loc.protocol : 'none:',
    supportsWebSocket: typeof WebSocket !== 'undefined',
    platformHint: nav?.platform || 'Unknown',
    userAgent: nav?.userAgent || 'Unknown',
    detectedAt: new Date().toISOString(),
  };
}

export async function fetchPreviewBackendHealth(): Promise<{
  health: RestHealthResponse | null;
  capabilities: PreviewCapabilityReport | null;
  error: string | null;
}> {
  try {
    const [healthRes, capRes] = await Promise.all([
      fetch('/api/health', { headers: { Accept: 'application/json' } }),
      fetch('/api/runtime/capabilities', {
        headers: { Accept: 'application/json' },
      }),
    ]);

    if (!healthRes.ok || !capRes.ok) {
      return {
        health: null,
        capabilities: null,
        error: `Preview backend returned HTTP ${healthRes.status}/${capRes.status}.`,
      };
    }

    const [health, capabilities] = (await Promise.all([healthRes.json(), capRes.json()])) as [
      RestHealthResponse,
      PreviewCapabilityReport,
    ];

    return { health, capabilities, error: null };
  } catch (err) {
    return {
      health: null,
      capabilities: null,
      error: err instanceof Error ? err.message : 'Preview backend unavailable.',
    };
  }
}

export async function verifyAIProviderViaBackend(
  providerId: string,
  modelId: string
): Promise<ProviderVerificationPayload> {
  try {
    const res = await fetch('/api/ai/providers/verify', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify({ providerId, modelId }),
    });
    const body = (await res.json()) as ProviderVerificationPayload;
    return body;
  } catch (err) {
    return {
      providerId,
      verified: false,
      status: NexusStatus.Failed,
      credentialConfigured: false,
      modelId,
      latencyMs: null,
      message: err instanceof Error ? err.message : 'Provider verification request failed.',
      checkedAt: new Date().toISOString(),
    };
  }
}

export class DaemonRequestError extends Error {
  public readonly statusCode: number;
  public readonly code: string;

  constructor(statusCode: number, envelope: NexusApiErrorEnvelope) {
    super(envelope.error.message);
    this.statusCode = statusCode;
    this.code = envelope.error.code;
  }
}

/**
 * Replaceable HTTP transport speaking to the Python Core daemon on loopback
 * (or via Vite/Express preview).
 */
export class HttpDaemonBridgeTransport implements BridgeTransport {
  public readonly transportMode = 'WebHTTP' as const;
  private sessionBearerToken: string | null = null;

  public setSessionBearerToken(token: string | null): void {
    this.sessionBearerToken = token && token.trim() ? token.trim() : null;
  }

  public getSessionBearerToken(): string | null {
    return this.sessionBearerToken;
  }

  public buildLoopbackWsUrl(config: BridgeEndpointConfig): string | null {
    if (!this.sessionBearerToken) {
      return null;
    }
    try {
      const parsed = new URL(config.wsUrl);
      if (
        parsed.hostname !== '127.0.0.1' &&
        parsed.hostname !== 'localhost' &&
        parsed.hostname !== '[::1]'
      ) {
        return null;
      }
      parsed.searchParams.set('token', this.sessionBearerToken);
      return parsed.toString();
    } catch {
      return null;
    }
  }

  public detectEnvironment(): RuntimeEnvironmentInfo {
    return detectRuntimeEnvironment();
  }

  public async probeHealth(config: BridgeEndpointConfig): Promise<BridgeProbeResult> {
    const cleanBase = config.restBaseUrl.replace(/\/+$/, '');
    const targetUrl = `${cleanBase}/health`;
    const started = performance.now();
    const controller = new AbortController();
    const timer = globalThis.setTimeout(() => controller.abort(), 2500);

    try {
      const response = await fetch(targetUrl, {
        method: 'GET',
        mode: 'cors',
        signal: controller.signal,
        headers: {
          Accept: 'application/json',
        },
      });
      const elapsed = Math.round(performance.now() - started);

      if (response.ok) {
        const body = (await response.json()) as Partial<DaemonHealthPayload>;
        return {
          endpoint: targetUrl,
          status: NexusStatus.Connected,
          httpStatus: response.status,
          latencyMs: elapsed,
          message: `Daemon responded (${body.service ?? 'bridge'} · PID ${body.pid ?? 'N/A'}).`,
          checkedAt: new Date().toISOString(),
        };
      }

      return {
        endpoint: targetUrl,
        status: NexusStatus.Failed,
        httpStatus: response.status,
        latencyMs: elapsed,
        message: `Bridge endpoint returned HTTP ${response.status} (${response.statusText || 'Error'}).`,
        checkedAt: new Date().toISOString(),
      };
    } catch (err) {
      const elapsed = Math.round(performance.now() - started);
      const isAbort = err instanceof Error && err.name === 'AbortError';
      const detail = isAbort
        ? 'Request timed out after 2500ms (no local Python daemon listening).'
        : err instanceof Error
          ? `${err.message}. In AI Studio web preview, local Windows Python daemons are not running or may be blocked by browser mixed-content rules.`
          : 'Network request failed.';

      return {
        endpoint: targetUrl,
        status: NexusStatus.Disconnected,
        httpStatus: null,
        latencyMs: elapsed,
        message: detail,
        checkedAt: new Date().toISOString(),
      };
    } finally {
      globalThis.clearTimeout(timer);
    }
  }

  public async fetchAuthenticatedJson<T>(
    config: BridgeEndpointConfig,
    path: string,
    init?: RequestInit
  ): Promise<T> {
    const cleanBase = config.restBaseUrl.replace(/\/+$/, '');
    const headers = new Headers(init?.headers);
    headers.set('Accept', 'application/json');
    if (init?.body) {
      headers.set('Content-Type', 'application/json');
    }
    if (this.sessionBearerToken) {
      headers.set('Authorization', `Bearer ${this.sessionBearerToken}`);
    }

    const res = await fetch(`${cleanBase}${path}`, {
      ...init,
      headers,
    });
    const body = await res.json();
    if (!res.ok) {
      if (body && typeof body === 'object' && 'error' in body) {
        throw new DaemonRequestError(res.status, body as NexusApiErrorEnvelope);
      }
      throw new Error(`Daemon request failed with HTTP ${res.status}`);
    }
    return body as T;
  }
}

/**
 * Replaceable Tauri 2 IPC transport used when running inside the Windows desktop shell.
 */
export class TauriIpcBridgeTransport implements BridgeTransport {
  public readonly transportMode = 'TauriIPC' as const;
  private readonly tauri: TauriInvokeBridge;

  constructor(tauriBridge: TauriInvokeBridge) {
    this.tauri = tauriBridge;
  }

  public detectEnvironment(): RuntimeEnvironmentInfo {
    return detectRuntimeEnvironment();
  }

  public async probeHealth(config: BridgeEndpointConfig): Promise<BridgeProbeResult> {
    try {
      return await this.tauri.invoke<BridgeProbeResult>('probe_daemon_health', {
        endpoint: config.restBaseUrl,
      });
    } catch (err) {
      return {
        endpoint: `${config.restBaseUrl.replace(/\/+$/, '')}/health`,
        status: NexusStatus.Unavailable,
        httpStatus: null,
        latencyMs: null,
        message:
          err instanceof Error
            ? `Tauri IPC probe unavailable: ${err.message}`
            : 'Tauri IPC probe failed.',
        checkedAt: new Date().toISOString(),
      };
    }
  }

  public async getLifecycleStatus(): Promise<DaemonLifecycleStatus> {
    return await this.tauri.invoke<DaemonLifecycleStatus>('get_daemon_lifecycle_status');
  }

  public async startBackgroundDaemon(): Promise<DaemonLifecycleStatus> {
    return await this.tauri.invoke<DaemonLifecycleStatus>('start_background_daemon');
  }

  public async stopBackgroundDaemon(forceExternal = false): Promise<DaemonLifecycleStatus> {
    return await this.tauri.invoke<DaemonLifecycleStatus>('stop_background_daemon', {
      forceExternal,
    });
  }

  public async restartBackgroundDaemon(): Promise<DaemonLifecycleStatus> {
    return await this.tauri.invoke<DaemonLifecycleStatus>('restart_background_daemon');
  }

  public async getDaemonAuthToken(): Promise<string> {
    return await this.tauri.invoke<string>('get_daemon_auth_token');
  }

  public async loadDesktopConfig(): Promise<DesktopConfigPayload> {
    return await this.tauri.invoke<DesktopConfigPayload>('load_desktop_configuration');
  }

  public async saveDesktopConfig(config: DesktopConfigPayload): Promise<DesktopConfigPayload> {
    return await this.tauri.invoke<DesktopConfigPayload>('save_desktop_configuration', {
      config,
    });
  }

  public async collectDesktopDiagnostics(): Promise<DesktopDiagnosticsReport> {
    return await this.tauri.invoke<DesktopDiagnosticsReport>('collect_desktop_diagnostics');
  }

  public async getAdapterInstallInstructions(): Promise<AdapterInstallGuide[]> {
    return await this.tauri.invoke<AdapterInstallGuide[]>('get_adapter_install_instructions');
  }
}

export function createBridgeTransport(): BridgeTransport {
  if (typeof window !== 'undefined' && window.__TAURI_INTERNALS__) {
    return new TauriIpcBridgeTransport(window.__TAURI_INTERNALS__);
  }
  return new HttpDaemonBridgeTransport();
}

export const WebBridgeTransport = HttpDaemonBridgeTransport;

export const bridgeTransport: BridgeTransport = createBridgeTransport();

export const daemonRestClient: HttpDaemonBridgeTransport =
  bridgeTransport instanceof HttpDaemonBridgeTransport
    ? bridgeTransport
    : new HttpDaemonBridgeTransport();
