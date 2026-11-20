import { describe, expect, it } from 'vitest';
import { createWebSocketEvent, WEBSOCKET_EVENT_TOPICS } from '../../integrations/websocket/schema';
import { AI_PROVIDER_CAPABILITIES } from '../../integrations/ai-providers/registry';
import { MCP_DEFAULT_CAPABILITIES } from '../../integrations/mcp/schema';
import {
  ADAPTER_MANIFEST_SCHEMA_VERSION,
  ADAPTER_PROTOCOL_METHODS,
  AIProviderKind,
  EngineKind,
  NEXUS_PROTOCOL_VERSION,
  NexusStatus,
  PermissionScope,
  ToolCategory,
} from '../../sdk/ts';
import { TOOL_CATEGORY_DEFINITIONS } from '../../tools/categories';

describe('NEXUS SDK & Protocol Contracts', () => {
  it('defines all 7 required explicit operational statuses', () => {
    expect(Object.values(NexusStatus)).toEqual([
      'Connected',
      'Disconnected',
      'Available',
      'Unavailable',
      'Running',
      'Failed',
      'Planned',
    ]);
  });

  it('defines all 19 tool category contracts without registering fake live tools', () => {
    expect(Object.values(ToolCategory)).toHaveLength(19);
    expect(TOOL_CATEGORY_DEFINITIONS).toHaveLength(19);
    for (const def of TOOL_CATEGORY_DEFINITIONS) {
      expect(def.implementationStatus).toBe(NexusStatus.Planned);
      expect(def.engineCompatibility).toContain(EngineKind.Unity);
      expect(def.engineCompatibility).toContain(EngineKind.Godot);
      expect(def.requiredPermissions.length).toBeGreaterThan(0);
      expect(def.requiredPermissions).toContain(def.requiredPermissions[0] as PermissionScope);
    }
  });

  it('separates built-in AI providers from inbound MCP server capabilities', () => {
    const providerKinds = AI_PROVIDER_CAPABILITIES.map((p) => p.kind);
    expect(providerKinds).toContain(AIProviderKind.GoogleGemini);
    expect(providerKinds).toContain(AIProviderKind.AnthropicClaude);
    expect(providerKinds).toContain(AIProviderKind.OpenAI);
    expect(providerKinds).toContain(AIProviderKind.OpenAICompatible);
    expect(providerKinds).toContain(AIProviderKind.Custom);

    expect(MCP_DEFAULT_CAPABILITIES.tools).toEqual([]);
    expect(MCP_DEFAULT_CAPABILITIES.transports.length).toBe(3);
  });

  it('creates typed WebSocket event envelopes matching protocol version', () => {
    const evt = createWebSocketEvent('bridge.status', 1, 'nexus-test', { ok: true });
    expect(evt.protocolVersion).toBe(NEXUS_PROTOCOL_VERSION);
    expect(WEBSOCKET_EVENT_TOPICS).toContain(evt.type);
    expect(evt.sequence).toBe(1);
    expect(evt.data).toEqual({ ok: true });
  });

  it('exposes the 11 canonical language-neutral adapter protocol methods and manifest schema version', () => {
    expect(ADAPTER_MANIFEST_SCHEMA_VERSION).toBe('1.0');
    expect(ADAPTER_PROTOCOL_METHODS).toEqual([
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
    ]);
  });
});
