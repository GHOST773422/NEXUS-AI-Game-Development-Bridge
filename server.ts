import 'dotenv/config';
import { GoogleGenAI } from '@google/genai';
import express, { Express, Request, Response } from 'express';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { AI_PROVIDER_CAPABILITIES } from './integrations/ai-providers/registry';
import { MCP_DEFAULT_CAPABILITIES } from './integrations/mcp/schema';
import { NEXUS_REST_ROUTES } from './integrations/rest-api/schema';
import { WEBSOCKET_EVENT_TOPICS } from './integrations/websocket/schema';
import {
  NEXUS_PROTOCOL_VERSION,
  NexusStatus,
  PreviewCapabilityReport,
  RestHealthResponse,
} from './sdk/ts';
import { TOOL_CATEGORY_DEFINITIONS } from './tools/categories';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

function isAllowedLoopbackUrl(rawUrl: string): boolean {
  try {
    const parsed = new URL(rawUrl);
    return (
      (parsed.protocol === 'http:' || parsed.protocol === 'https:') &&
      (parsed.hostname === '127.0.0.1' || parsed.hostname === 'localhost')
    );
  } catch {
    return false;
  }
}

export function createNexusPreviewApp(): Express {
  const app = express();
  app.use(express.json({ limit: '1mb' }));

  app.get('/api/health', (_req: Request, res: Response) => {
    const payload: RestHealthResponse = {
      service: 'nexus-preview-backend',
      protocolVersion: NEXUS_PROTOCOL_VERSION,
      status: NexusStatus.Available,
      runtime: 'node-express',
      bindAddress: '0.0.0.0:3000',
      capabilities: {
        localEngineExecution: false,
        tauriIpcAvailable: false,
        pythonDaemonRunning: false,
        sqlitePersistence: false,
        geminiServerKeyConfigured: Boolean(process.env.GEMINI_API_KEY),
      },
      timestamp: new Date().toISOString(),
    };
    res.json(payload);
  });

  app.get('/api/runtime/capabilities', (_req: Request, res: Response) => {
    const report: PreviewCapabilityReport = {
      environment: 'ai-studio-preview',
      nodeVersion: process.version,
      platform: process.platform,
      arch: process.arch,
      daemonStatus: NexusStatus.Disconnected,
      unityAdapterStatus: NexusStatus.Planned,
      godotAdapterStatus: NexusStatus.Planned,
      geminiConfigured: Boolean(process.env.GEMINI_API_KEY),
      registeredToolCount: 0,
      incompatibilitiesCount: 5,
    };
    res.json(report);
  });

  app.get('/api/protocol/schemas', (_req: Request, res: Response) => {
    res.json({
      protocolVersion: NEXUS_PROTOCOL_VERSION,
      restRoutes: NEXUS_REST_ROUTES,
      mcpCapabilities: MCP_DEFAULT_CAPABILITIES,
      websocketTopics: WEBSOCKET_EVENT_TOPICS,
      aiProviders: AI_PROVIDER_CAPABILITIES,
      toolCategories: TOOL_CATEGORY_DEFINITIONS,
    });
  });

  app.post('/api/bridge/probe', async (req: Request, res: Response) => {
    const endpoint = typeof req.body?.endpoint === 'string' ? req.body.endpoint : '';
    if (!isAllowedLoopbackUrl(endpoint)) {
      res.status(400).json({
        error: 'Only loopback URLs (127.0.0.1 or localhost) are permitted for bridge probes.',
      });
      return;
    }

    const started = Date.now();
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 2000);

    try {
      const target = `${endpoint.replace(/\/+$/, '')}/health`;
      const upstream = await fetch(target, { signal: controller.signal });
      const latencyMs = Date.now() - started;
      res.json({
        endpoint: target,
        status: upstream.ok ? NexusStatus.Connected : NexusStatus.Failed,
        httpStatus: upstream.status,
        latencyMs,
        message: upstream.ok
          ? `Loopback bridge responded with HTTP ${upstream.status}.`
          : `Loopback bridge returned HTTP ${upstream.status}.`,
        checkedAt: new Date().toISOString(),
      });
    } catch (err) {
      const latencyMs = Date.now() - started;
      const message =
        err instanceof Error
          ? `${err.message} (no local Python daemon listening on loopback).`
          : 'Loopback bridge unreachable.';
      res.json({
        endpoint: `${endpoint.replace(/\/+$/, '')}/health`,
        status: NexusStatus.Disconnected,
        httpStatus: null,
        latencyMs,
        message,
        checkedAt: new Date().toISOString(),
      });
    } finally {
      clearTimeout(timer);
    }
  });

  app.post('/api/ai/providers/verify', async (req: Request, res: Response) => {
    const providerId =
      typeof req.body?.providerId === 'string' ? req.body.providerId : 'conn-gemini';
    const modelId =
      typeof req.body?.modelId === 'string' && req.body.modelId.trim()
        ? req.body.modelId.trim()
        : 'gemini-4-hydrogen';

    if (providerId !== 'conn-gemini') {
      res.json({
        providerId,
        verified: false,
        status: NexusStatus.Disconnected,
        credentialConfigured: false,
        modelId,
        latencyMs: null,
        message:
          'This provider runs in the local Python daemon vault; connect the Windows daemon to verify.',
        checkedAt: new Date().toISOString(),
      });
      return;
    }

    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey) {
      res.json({
        providerId,
        verified: false,
        status: NexusStatus.Disconnected,
        credentialConfigured: false,
        modelId,
        latencyMs: null,
        message: 'GEMINI_API_KEY is not configured in server secrets.',
        checkedAt: new Date().toISOString(),
      });
      return;
    }

    const started = Date.now();
    try {
      const ai = new GoogleGenAI({
        apiKey,
        httpOptions: {
          headers: {
            'User-Agent': 'aistudio-build',
          },
        },
      });
      const modelInfo = await ai.models.get({ model: modelId });
      res.json({
        providerId,
        verified: true,
        status: NexusStatus.Connected,
        credentialConfigured: true,
        modelId: modelInfo.name?.split('/').pop() || modelId,
        latencyMs: Date.now() - started,
        message: `Server-side Gemini SDK verified model '${modelId}'.`,
        checkedAt: new Date().toISOString(),
      });
    } catch (err) {
      res.status(502).json({
        providerId,
        verified: false,
        status: NexusStatus.Failed,
        credentialConfigured: true,
        modelId,
        latencyMs: Date.now() - started,
        message: err instanceof Error ? err.message : 'Gemini verification failed.',
        checkedAt: new Date().toISOString(),
      });
    }
  });

  app.post('/api/ai/providers/generate', async (req: Request, res: Response) => {
    const prompt = typeof req.body?.prompt === 'string' ? req.body.prompt.trim() : '';
    const modelId =
      typeof req.body?.modelId === 'string' && req.body.modelId.trim()
        ? req.body.modelId.trim()
        : 'gemini-4-hydrogen';

    if (!prompt) {
      res.status(400).json({ error: 'Prompt text is required.' });
      return;
    }
    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey) {
      res.status(503).json({
        error: 'GEMINI_API_KEY is not configured in server environment secrets.',
      });
      return;
    }

    const started = Date.now();
    try {
      const ai = new GoogleGenAI({
        apiKey,
        httpOptions: {
          headers: {
            'User-Agent': 'aistudio-build',
          },
        },
      });
      const response = await ai.models.generateContent({
        model: modelId,
        contents: prompt,
        config: {
          systemInstruction:
            'You are the NEXUS bridge diagnostic assistant. Respond concisely with factual guidance.',
        },
      });
      res.json({
        providerId: 'conn-gemini',
        model: modelId,
        content: response.text ?? '',
        usage: {
          promptTokens: response.usageMetadata?.promptTokenCount ?? 0,
          completionTokens: response.usageMetadata?.candidatesTokenCount ?? 0,
          totalTokens: response.usageMetadata?.totalTokenCount ?? 0,
          latencyMs: Date.now() - started,
        },
      });
    } catch (err) {
      res.status(502).json({
        error: err instanceof Error ? err.message : 'Gemini generateContent failed.',
      });
    }
  });

  return app;
}

function parseCliArg(flag: string): string | undefined {
  const index = process.argv.indexOf(flag);
  if (index !== -1 && index + 1 < process.argv.length) {
    return process.argv[index + 1];
  }
  const prefixed = process.argv.find((arg) => arg.startsWith(`${flag}=`));
  return prefixed ? prefixed.slice(flag.length + 1) : undefined;
}

async function startServer() {
  const app = createNexusPreviewApp();
  const isProduction = process.env.NODE_ENV === 'production';
  const httpServer = http.createServer(app);
  const port = Number(parseCliArg('--port') || process.env.PORT || 3000);
  const host = parseCliArg('--host') || process.env.HOST || '0.0.0.0';

  if (!isProduction) {
    const { createServer: createViteServer } = await import('vite');
    const vite = await createViteServer({
      server: {
        middlewareMode: true,
        allowedHosts: true,
        hmr: process.env.DISABLE_HMR === 'true' ? false : { server: httpServer },
      },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distDir = path.resolve(__dirname, 'dist');
    app.use(express.static(distDir));
    app.get('*', (_req, res) => {
      res.sendFile(path.join(distDir, 'index.html'));
    });
  }

  httpServer.on('error', (error: NodeJS.ErrnoException) => {
    console.error(`NEXUS preview server error on ${host}:${port}:`, error.message);
    process.exit(1);
  });

  const shutdown = () => {
    httpServer.close(() => {
      process.exit(0);
    });
  };
  process.once('SIGINT', shutdown);
  process.once('SIGTERM', shutdown);

  httpServer.listen(port, host, () => {
    console.log(`NEXUS preview server listening on http://${host}:${port}`);
  });
}

function isDirectEntryPoint(): boolean {
  if (!process.argv[1]) {
    return false;
  }
  try {
    return fs.realpathSync(process.argv[1]) === fs.realpathSync(__filename);
  } catch {
    return path.resolve(process.argv[1]) === path.resolve(__filename);
  }
}

if (isDirectEntryPoint()) {
  void startServer();
}
