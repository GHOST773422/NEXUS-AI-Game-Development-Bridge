import { describe, expect, it } from 'vitest';
import {
  DEFAULT_BRIDGE_CONFIG,
  detectRuntimeEnvironment,
  HttpDaemonBridgeTransport,
  TauriIpcBridgeTransport,
} from '../../src/services/bridgeTransport';
import { NexusStatus } from '../../sdk/ts';

describe('BridgeTransport Replaceable Service Abstraction', () => {
  it('honestly reports WebPreview when window.__TAURI_INTERNALS__ is absent', () => {
    const env = detectRuntimeEnvironment();
    expect(env.hasTauriIPC).toBe(false);
    expect(env.hostKind).toBe('WebPreview');
    expect(typeof env.detectedAt).toBe('string');
  });

  it('returns Disconnected rather than fake success when local daemon port is closed', async () => {
    const transport = new HttpDaemonBridgeTransport();
    const result = await transport.probeHealth({
      ...DEFAULT_BRIDGE_CONFIG,
      restBaseUrl: 'http://127.0.0.1:59999',
    });

    expect(result.status).toBe(NexusStatus.Disconnected);
    expect(result.httpStatus).toBeNull();
    expect(result.endpoint).toBe('http://127.0.0.1:59999/health');
  });

  it('supports replaceable TauriIpcBridgeTransport delegating to Tauri invoke', async () => {
    const transport = new TauriIpcBridgeTransport({
      async invoke<T>(cmd: string, args?: Record<string, unknown>): Promise<T> {
        expect(cmd).toBe('probe_daemon_health');
        expect(args?.endpoint).toBe('http://127.0.0.1:47100');
        return {
          endpoint: 'http://127.0.0.1:47100/health',
          status: NexusStatus.Connected,
          httpStatus: 200,
          latencyMs: 3,
          message: 'Tauri IPC bridge verified.',
          checkedAt: '2026-11-18T15:00:00.000Z',
        } as T;
      },
    });

    const result = await transport.probeHealth(DEFAULT_BRIDGE_CONFIG);
    expect(transport.transportMode).toBe('TauriIPC');
    expect(result.status).toBe(NexusStatus.Connected);
    expect(result.httpStatus).toBe(200);
  });

  it('builds authenticated WebSocket URLs strictly for loopback endpoints', () => {
    const transport = new HttpDaemonBridgeTransport();
    transport.setSessionBearerToken('tok_test_123');

    const localWs = transport.buildLoopbackWsUrl(DEFAULT_BRIDGE_CONFIG);
    expect(localWs).toBe('ws://127.0.0.1:47101/events?token=tok_test_123');

    const remoteWs = transport.buildLoopbackWsUrl({
      ...DEFAULT_BRIDGE_CONFIG,
      wsUrl: 'wss://evil.example/events',
    });
    expect(remoteWs).toBeNull();
  });
});
