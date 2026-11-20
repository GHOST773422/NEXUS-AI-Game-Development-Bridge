import { AIProviderCapabilities, AIProviderKind, MCPTransportKind } from '../../sdk/ts';

export const AI_PROVIDER_CAPABILITIES: AIProviderCapabilities[] = [
  {
    kind: AIProviderKind.GoogleGemini,
    supportsStreaming: true,
    supportsToolCalling: true,
    requiresPaidKey: false,
    transportsSupported: [MCPTransportKind.StreamableHTTP],
  },
  {
    kind: AIProviderKind.AnthropicClaude,
    supportsStreaming: true,
    supportsToolCalling: true,
    requiresPaidKey: true,
    transportsSupported: [MCPTransportKind.Stdio, MCPTransportKind.StreamableHTTP],
  },
  {
    kind: AIProviderKind.OpenAI,
    supportsStreaming: true,
    supportsToolCalling: true,
    requiresPaidKey: true,
    transportsSupported: [MCPTransportKind.StreamableHTTP],
  },
  {
    kind: AIProviderKind.OpenAICompatible,
    supportsStreaming: true,
    supportsToolCalling: true,
    requiresPaidKey: false,
    transportsSupported: [MCPTransportKind.StreamableHTTP],
  },
  {
    kind: AIProviderKind.Custom,
    supportsStreaming: true,
    supportsToolCalling: false,
    requiresPaidKey: false,
    transportsSupported: [
      MCPTransportKind.Stdio,
      MCPTransportKind.StreamableHTTP,
      MCPTransportKind.SSE,
    ],
  },
];
