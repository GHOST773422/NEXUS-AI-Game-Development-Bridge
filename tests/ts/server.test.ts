import http from 'node:http';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createNexusPreviewApp } from '../../server';
import { NexusStatus, PreviewCapabilityReport, RestHealthResponse } from '../../sdk/ts';

describe('Node.js Preview Backend (server.ts)', () => {
  let server: http.Server;
  let baseUrl: string;

  beforeAll(async () => {
    const app = createNexusPreviewApp();
    await new Promise<void>((resolve) => {
      server = app.listen(0, '127.0.0.1', () => {
        const addr = server.address();
        if (addr && typeof addr === 'object') {
          baseUrl = `http://127.0.0.1:${addr.port}`;
        }
        resolve();
      });
    });
  });

  afterAll(async () => {
    await new Promise<void>((resolve, reject) => {
      server.close((err) => (err ? reject(err) : resolve()));
    });
  });

  it('GET /api/health returns honest preview capabilities', async () => {
    const res = await fetch(`${baseUrl}/api/health`);
    expect(res.status).toBe(200);
    const body = (await res.json()) as RestHealthResponse;
    expect(body.service).toBe('nexus-preview-backend');
    expect(body.status).toBe(NexusStatus.Available);
    expect(body.capabilities.localEngineExecution).toBe(false);
    expect(body.capabilities.tauriIpcAvailable).toBe(false);
    expect(body.capabilities.pythonDaemonRunning).toBe(false);
  });

  it('GET /api/runtime/capabilities reports zero fake tools and Planned engine adapters', async () => {
    const res = await fetch(`${baseUrl}/api/runtime/capabilities`);
    expect(res.status).toBe(200);
    const body = (await res.json()) as PreviewCapabilityReport;
    expect(body.registeredToolCount).toBe(0);
    expect(body.unityAdapterStatus).toBe(NexusStatus.Planned);
    expect(body.godotAdapterStatus).toBe(NexusStatus.Planned);
    expect(body.daemonStatus).toBe(NexusStatus.Disconnected);
  });

  it('POST /api/bridge/probe rejects non-loopback targets to prevent SSRF', async () => {
    const res = await fetch(`${baseUrl}/api/bridge/probe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ endpoint: 'https://example.com' }),
    });
    expect(res.status).toBe(400);
  });

  it('GET /api/protocol/schemas returns all 19 tool category contracts', async () => {
    const res = await fetch(`${baseUrl}/api/protocol/schemas`);
    expect(res.status).toBe(200);
    const body = (await res.json()) as { toolCategories: unknown[]; restRoutes: unknown[] };
    expect(body.toolCategories).toHaveLength(19);
    expect(body.restRoutes.length).toBeGreaterThanOrEqual(4);
  });

  it('POST /api/ai/providers/verify does not fabricate verification for local vault providers or missing keys', async () => {
    const claudeRes = await fetch(`${baseUrl}/api/ai/providers/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ providerId: 'conn-claude', modelId: 'claude-sonnet-4-20250514' }),
    });
    expect(claudeRes.status).toBe(200);
    const claudeBody = (await claudeRes.json()) as { verified: boolean; status: NexusStatus };
    expect(claudeBody.verified).toBe(false);
    expect(claudeBody.status).toBe(NexusStatus.Disconnected);
  });
});
