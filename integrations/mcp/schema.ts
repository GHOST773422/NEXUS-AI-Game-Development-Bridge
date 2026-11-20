import { MCPToolDescriptor, MCPTransportKind, NexusStatus } from '../../sdk/ts';

export interface MCPServerCapabilities {
  serverName: 'nexus-mcp';
  protocolVersion: string;
  transports: MCPTransportKind[];
  status: NexusStatus;
  tools: MCPToolDescriptor[];
}

export const MCP_DEFAULT_CAPABILITIES: MCPServerCapabilities = {
  serverName: 'nexus-mcp',
  protocolVersion: '2025-03-26',
  transports: [MCPTransportKind.Stdio, MCPTransportKind.StreamableHTTP, MCPTransportKind.SSE],
  status: NexusStatus.Planned,
  tools: [],
};
