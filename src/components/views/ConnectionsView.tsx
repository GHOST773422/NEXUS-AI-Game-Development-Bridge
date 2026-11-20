import { useState } from 'react';
import { EXTERNAL_MCP_CLIENTS } from '../../data/architectureSpec';
import { NEXUS_REST_ROUTES } from '../../../integrations/rest-api/schema';
import {
  AIProviderConnection,
  AIProviderKind,
  BridgeEndpointConfig,
  BridgeProbeResult,
  DaemonMcpStatusPayload,
  NexusStatus,
  ProviderVerificationPayload,
  RuntimeEnvironmentInfo,
} from '../../types/nexus';
import { StatusText } from '../ui/StatusText';

interface ConnectionsViewProps {
  runtime: RuntimeEnvironmentInfo;
  config: BridgeEndpointConfig;
  providers: AIProviderConnection[];
  lastProbe: BridgeProbeResult | null;
  probing: boolean;
  daemonAuthenticated?: boolean;
  mcpStatus?: DaemonMcpStatusPayload | null;
  onUpdateConfig: (next: BridgeEndpointConfig) => void;
  onUpdateProvider: (id: string, patch: Partial<AIProviderConnection>) => void;
  onAddCustomProvider: (input: {
    name: string;
    modelId: string;
    endpointUrl: string;
    credentialRef: string;
  }) => void;
  onRemoveCustomProvider: (id: string) => void;
  onVerifyProvider: (id: string) => Promise<ProviderVerificationPayload | null>;
  onProbeBridge: () => void;
}

const PROVIDER_MODEL_PRESETS: Record<AIProviderKind, string[]> = {
  [AIProviderKind.GoogleGemini]: [
    'gemini-4-hydrogen',
    'gemini-4-argon',
    'gemini-4-carbon',
    'gemini-3.1-flash-lite',
  ],
  [AIProviderKind.AnthropicClaude]: [
    'claude-sonnet-4-20250514',
    'claude-3-7-sonnet-latest',
    'claude-3-5-haiku-latest',
  ],
  [AIProviderKind.OpenAI]: ['gpt-4.1', 'gpt-4.1-mini', 'o4-mini'],
  [AIProviderKind.OpenAICompatible]: ['llama3.2', 'qwen2.5-coder:14b'],
  [AIProviderKind.Custom]: ['custom-model'],
};

const MCP_RESOURCES_SPEC = [
  { uri: 'nexus://engines', summary: 'Unity & Godot detection and adapter status' },
  { uri: 'nexus://projects', summary: 'Persistent SQLite engine project registry' },
  { uri: 'nexus://capabilities', summary: 'Host capabilities & 19 tool categories' },
  { uri: 'nexus://tasks', summary: '12-step task drafts and execution statuses' },
  { uri: 'nexus://diagnostics', summary: 'Daemon PID, SQLite integrity, safe config' },
  { uri: 'nexus://providers', summary: 'Built-in AI provider metadata (redacted)' },
];

const MCP_PROMPTS_SPEC = [
  'inspect_project_architecture',
  'plan_engine_automation_task',
  'diagnose_bridge_health',
];

type ConnectionTab = 'AI Providers' | 'MCP Clients' | 'REST API';

export function ConnectionsView({
  runtime,
  config,
  providers,
  lastProbe,
  probing,
  daemonAuthenticated = false,
  mcpStatus = null,
  onUpdateConfig,
  onUpdateProvider,
  onAddCustomProvider,
  onRemoveCustomProvider,
  onVerifyProvider,
  onProbeBridge,
}: ConnectionsViewProps) {
  const [activeTab, setActiveTab] = useState<ConnectionTab>('AI Providers');
  const [selectedProviderId, setSelectedProviderId] = useState<string>(providers[0]?.id ?? '');
  const [verifyingProvider, setVerifyingProvider] = useState(false);
  const [lastVerification, setLastVerification] = useState<ProviderVerificationPayload | null>(
    null
  );
  const [showAddCustom, setShowAddCustom] = useState(false);
  const [customName, setCustomName] = useState('');
  const [customModel, setCustomModel] = useState('');
  const [customEndpoint, setCustomEndpoint] = useState('http://127.0.0.1:11434/v1');
  const [customCredRef, setCustomCredRef] = useState('vault://nexus/custom_provider');

  const [restDraft, setRestDraft] = useState(config.restBaseUrl);
  const [wsDraft, setWsDraft] = useState(config.wsUrl);
  const [mcpDraft, setMcpDraft] = useState(config.mcpHttpUrl);

  const selectedProvider =
    providers.find((p) => p.id === selectedProviderId) ?? providers[0] ?? null;

  const handleRunVerifyProvider = async (id: string) => {
    setVerifyingProvider(true);
    const res = await onVerifyProvider(id);
    if (res) {
      setLastVerification(res);
    }
    setVerifyingProvider(false);
  };

  const handleCreateCustom = (e: React.FormEvent) => {
    e.preventDefault();
    if (!customName.trim() || !customEndpoint.trim()) return;
    onAddCustomProvider({
      name: customName.trim(),
      modelId: customModel.trim() || 'custom-model',
      endpointUrl: customEndpoint.trim(),
      credentialRef: customCredRef.trim() || 'wincred://nexus/custom_provider',
    });
    setCustomName('');
    setCustomModel('');
    setShowAddCustom(false);
  };

  const handleSaveEndpoints = (e: React.FormEvent) => {
    e.preventDefault();
    onUpdateConfig({
      ...config,
      restBaseUrl: restDraft.trim() || config.restBaseUrl,
      wsUrl: wsDraft.trim() || config.wsUrl,
      mcpHttpUrl: mcpDraft.trim() || config.mcpHttpUrl,
    });
  };

  return (
    <div className="space-y-8">
      <section className="flex flex-col lg:flex-row lg:items-end justify-between gap-4 pb-6 border-b border-[#1E293B]">
        <div className="space-y-1.5 max-w-3xl">
          <h2 className="font-display text-xl font-semibold text-[#F1F5F9]">
            Connections, AI Providers, MCP & REST Gateway
          </h2>
          <p className="text-sm text-[#94A3B8]">
            Manage Gemini, Claude, OpenAI, and custom providers separately from inbound MCP clients
            and local REST API access. Credentials use vault references or server-side secrets and
            are never saved in browser storage.
          </p>
        </div>

        <div className="flex items-center gap-1 p-1 rounded-md bg-[#121923] border border-[#1E293B] shrink-0">
          {(['AI Providers', 'MCP Clients', 'REST API'] as const).map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className={`px-3 py-1.5 text-xs font-medium rounded transition-colors whitespace-nowrap shrink-0 ${
                activeTab === tab
                  ? 'bg-[#1B2636] text-[#35D6C5]'
                  : 'text-[#94A3B8] hover:text-[#F1F5F9]'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
      </section>

      {activeTab === 'AI Providers' && (
        <section className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-start">
          <div className="xl:col-span-7 space-y-4">
            <div className="flex items-center justify-between gap-4">
              <h3 className="font-display text-base font-semibold text-[#F1F5F9]">
                Configured Model Providers ({providers.length})
              </h3>
              <button
                type="button"
                onClick={() => setShowAddCustom((v) => !v)}
                className="px-3.5 py-1.5 text-xs font-medium rounded-md border border-[#1E293B] bg-[#121923] text-[#F1F5F9] hover:border-[#35D6C5] transition-colors whitespace-nowrap shrink-0"
              >
                {showAddCustom ? 'Cancel' : 'Add Custom Provider'}
              </button>
            </div>

            {showAddCustom && (
              <form
                onSubmit={handleCreateCustom}
                className="p-4 rounded-lg bg-[#121923] border border-[#3987F5]/40 space-y-3"
              >
                <div className="text-xs font-semibold text-[#F1F5F9]">
                  New Custom / OpenAI-Compatible Provider
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                  <label className="space-y-1">
                    <span className="text-[#94A3B8]">Display Name</span>
                    <input
                      type="text"
                      required
                      value={customName}
                      onChange={(e) => setCustomName(e.target.value)}
                      placeholder="e.g. Local Ollama Qwen"
                      className="w-full px-3 py-2 rounded bg-[#0B0F14] border border-[#1E293B] text-[#F1F5F9] focus:outline-none focus:border-[#35D6C5]"
                    />
                  </label>
                  <label className="space-y-1">
                    <span className="text-[#94A3B8]">Model Identifier</span>
                    <input
                      type="text"
                      value={customModel}
                      onChange={(e) => setCustomModel(e.target.value)}
                      placeholder="e.g. qwen2.5-coder:14b"
                      className="w-full px-3 py-2 rounded bg-[#0B0F14] border border-[#1E293B] font-mono text-[#F1F5F9] focus:outline-none focus:border-[#35D6C5]"
                    />
                  </label>
                  <label className="space-y-1">
                    <span className="text-[#94A3B8]">Endpoint URL</span>
                    <input
                      type="url"
                      required
                      value={customEndpoint}
                      onChange={(e) => setCustomEndpoint(e.target.value)}
                      className="w-full px-3 py-2 rounded bg-[#0B0F14] border border-[#1E293B] font-mono text-[#F1F5F9] focus:outline-none focus:border-[#35D6C5]"
                    />
                  </label>
                  <label className="space-y-1">
                    <span className="text-[#94A3B8]">Credential Vault Alias (No Raw Keys)</span>
                    <input
                      type="text"
                      value={customCredRef}
                      onChange={(e) => setCustomCredRef(e.target.value)}
                      className="w-full px-3 py-2 rounded bg-[#0B0F14] border border-[#1E293B] font-mono text-[#F1F5F9] focus:outline-none focus:border-[#35D6C5]"
                    />
                  </label>
                </div>
                <div className="flex justify-end">
                  <button
                    type="submit"
                    className="px-4 py-1.5 text-xs font-semibold rounded-md bg-[#35D6C5] text-[#081016] hover:bg-[#4BE0D0] transition-colors whitespace-nowrap shrink-0"
                  >
                    Save Provider
                  </button>
                </div>
              </form>
            )}

            <div className="overflow-x-auto rounded-lg border border-[#1E293B] bg-[#121923]">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-[#1E293B] text-xs font-medium text-[#94A3B8]">
                    <th className="py-3 px-4">Provider</th>
                    <th className="py-3 px-4">Model</th>
                    <th className="py-3 px-4">Credential</th>
                    <th className="py-3 px-4">State</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#1E293B] text-sm">
                  {providers.map((provider) => {
                    const isSelected = selectedProvider?.id === provider.id;
                    return (
                      <tr
                        key={provider.id}
                        onClick={() => setSelectedProviderId(provider.id)}
                        className={`cursor-pointer transition-colors ${
                          isSelected ? 'bg-[#182230]' : 'hover:bg-[#161F2C]'
                        }`}
                      >
                        <td className="py-3 px-4">
                          <div className="font-medium text-[#F1F5F9]">{provider.name}</div>
                          <div className="text-xs text-[#94A3B8]">{provider.kind}</div>
                        </td>
                        <td className="py-3 px-4 font-mono text-xs text-[#F1F5F9]">
                          {provider.modelId}
                        </td>
                        <td className="py-3 px-4 text-xs text-[#94A3B8]">
                          {provider.credentialConfigured ? 'Vault / Env Ready' : 'Not Configured'}
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap">
                          <StatusText status={provider.status} />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {selectedProvider && (
            <aside className="xl:col-span-5 p-5 rounded-lg bg-[#121923] border border-[#1E293B] space-y-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-xs text-[#94A3B8]">Provider Configuration</div>
                  <h3 className="font-display text-base font-semibold text-[#F1F5F9] mt-0.5">
                    {selectedProvider.name}
                  </h3>
                </div>
                <StatusText status={selectedProvider.status} />
              </div>

              <p className="text-xs text-[#94A3B8] leading-relaxed">{selectedProvider.notes}</p>

              <div className="space-y-3 text-xs pt-2 border-t border-[#1E293B]">
                <label className="block space-y-1">
                  <span className="text-[#94A3B8]">Model ID</span>
                  <div className="space-y-2">
                    <input
                      type="text"
                      value={selectedProvider.modelId}
                      onChange={(e) =>
                        onUpdateProvider(selectedProvider.id, { modelId: e.target.value })
                      }
                      className="w-full px-3 py-2 rounded bg-[#0B0F14] border border-[#1E293B] font-mono text-[#F1F5F9] focus:outline-none focus:border-[#35D6C5]"
                    />
                    <div className="flex flex-wrap gap-1.5">
                      {PROVIDER_MODEL_PRESETS[selectedProvider.kind].map((preset) => (
                        <button
                          key={preset}
                          type="button"
                          onClick={() => onUpdateProvider(selectedProvider.id, { modelId: preset })}
                          className={`px-2 py-1 rounded font-mono text-[11px] border transition-colors whitespace-nowrap shrink-0 ${
                            selectedProvider.modelId === preset
                              ? 'border-[#35D6C5]/60 bg-[#122625] text-[#35D6C5]'
                              : 'border-[#1E293B] bg-[#0B0F14] text-[#94A3B8] hover:text-[#F1F5F9]'
                          }`}
                        >
                          {preset}
                        </button>
                      ))}
                    </div>
                  </div>
                </label>

                <label className="block space-y-1">
                  <span className="text-[#94A3B8]">Endpoint / Route</span>
                  <input
                    type="text"
                    value={selectedProvider.endpointUrl}
                    disabled={selectedProvider.kind === AIProviderKind.GoogleGemini}
                    onChange={(e) =>
                      onUpdateProvider(selectedProvider.id, { endpointUrl: e.target.value })
                    }
                    className="w-full px-3 py-2 rounded bg-[#0B0F14] border border-[#1E293B] font-mono text-[#F1F5F9] disabled:opacity-60 focus:outline-none focus:border-[#35D6C5]"
                  />
                </label>

                <label className="block space-y-1">
                  <span className="text-[#94A3B8]">Credential Vault Reference (OS / Server)</span>
                  <input
                    type="text"
                    value={selectedProvider.credentialRef}
                    onChange={(e) =>
                      onUpdateProvider(selectedProvider.id, { credentialRef: e.target.value })
                    }
                    className="w-full px-3 py-2 rounded bg-[#0B0F14] border border-[#1E293B] font-mono text-[#F1F5F9] focus:outline-none focus:border-[#35D6C5]"
                  />
                </label>
              </div>

              {lastVerification && lastVerification.providerId === selectedProvider.id && (
                <div className="p-3 rounded bg-[#0B0F14] border border-[#1E293B] text-xs space-y-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[#94A3B8]">Latest Verification Check</span>
                    <StatusText status={lastVerification.status} />
                  </div>
                  <div className="text-[#F1F5F9] leading-relaxed">{lastVerification.message}</div>
                </div>
              )}

              <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-[#1E293B]">
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => handleRunVerifyProvider(selectedProvider.id)}
                    disabled={verifyingProvider}
                    className="px-3.5 py-1.5 text-xs font-semibold rounded-md bg-[#35D6C5] text-[#081016] hover:bg-[#4BE0D0] disabled:opacity-60 transition-colors whitespace-nowrap shrink-0"
                  >
                    {verifyingProvider ? 'Verifying...' : 'Verify Connection'}
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      onUpdateProvider(selectedProvider.id, {
                        enabled: !selectedProvider.enabled,
                      })
                    }
                    className={`px-3.5 py-1.5 text-xs font-medium rounded-md border transition-colors whitespace-nowrap shrink-0 ${
                      selectedProvider.enabled
                        ? 'bg-[#122625] border-[#35D6C5]/50 text-[#35D6C5]'
                        : 'bg-[#0B0F14] border-[#1E293B] text-[#94A3B8]'
                    }`}
                  >
                    {selectedProvider.enabled ? 'Enabled in Registry' : 'Disabled'}
                  </button>
                </div>

                {selectedProvider.isCustom && (
                  <button
                    type="button"
                    onClick={() => onRemoveCustomProvider(selectedProvider.id)}
                    className="px-3.5 py-1.5 text-xs font-medium rounded-md border border-[#E5534B]/40 text-[#E5534B] hover:bg-[#E5534B]/10 transition-colors whitespace-nowrap shrink-0"
                  >
                    Remove Custom Provider
                  </button>
                )}
              </div>
            </aside>
          )}
        </section>
      )}

      {activeTab === 'MCP Clients' && (
        <section className="space-y-6">
          <div className="p-5 rounded-lg bg-[#121923] border border-[#1E293B] space-y-2">
            <div className="flex items-center justify-between gap-4">
              <h3 className="font-display text-base font-semibold text-[#F1F5F9]">
                Inbound MCP Server Transports (External AI Clients)
              </h3>
              <StatusText
                status={
                  mcpStatus || (daemonAuthenticated && lastProbe?.status === NexusStatus.Connected)
                    ? NexusStatus.Connected
                    : NexusStatus.Disconnected
                }
              />
            </div>
            <p className="text-xs text-[#94A3B8] leading-relaxed">
              External AI applications connect inbound to{' '}
              <span className="font-mono text-[#F1F5F9]">
                {mcpStatus?.serverName ?? 'nexus-mcp'}
              </span>{' '}
              via <span className="font-mono text-[#35D6C5]">stdio</span> or loopback{' '}
              <span className="font-mono text-[#35D6C5]">Streamable HTTP</span>
              {mcpStatus
                ? ` (port ${mcpStatus.mcpHttpPort}, ${mcpStatus.tools.length} tools exposed)`
                : ''}
              . Connecting an API provider key on the AI Providers tab never automatically connects
              desktop MCP clients.
            </p>
          </div>

          <div className="overflow-x-auto rounded-lg border border-[#1E293B] bg-[#121923]">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-[#1E293B] text-xs font-medium text-[#94A3B8]">
                  <th className="py-3 px-4">External Client Profile</th>
                  <th className="py-3 px-4">Transports</th>
                  <th className="py-3 px-4">Command / URI</th>
                  <th className="py-3 px-4">Authentication</th>
                  <th className="py-3 px-4">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1E293B] text-sm">
                {EXTERNAL_MCP_CLIENTS.map((client) => {
                  const liveClientStatus =
                    client.id === 'mcp-http-clients'
                      ? mcpStatus
                        ? NexusStatus.Connected
                        : NexusStatus.Disconnected
                      : runtime.hostKind === 'WebPreview'
                        ? NexusStatus.Unavailable
                        : NexusStatus.Available;
                  const resolvedCommand =
                    client.id === 'mcp-http-clients' && mcpStatus
                      ? `http://127.0.0.1:${mcpStatus.mcpHttpPort}/mcp`
                      : client.endpointOrCommand;
                  return (
                    <tr key={client.id} className="hover:bg-[#161F2C]">
                      <td className="py-3 px-4">
                        <div className="font-medium text-[#F1F5F9]">{client.name}</div>
                        <div className="text-xs text-[#94A3B8] mt-0.5">{client.notes}</div>
                      </td>
                      <td className="py-3 px-4 font-mono text-xs text-[#F1F5F9]">
                        {client.supportedTransports.join(' · ')}
                      </td>
                      <td className="py-3 px-4 font-mono text-xs text-[#35D6C5]">
                        {resolvedCommand}
                      </td>
                      <td className="py-3 px-4 text-xs text-[#94A3B8]">{client.authMode}</td>
                      <td className="py-3 px-4 whitespace-nowrap">
                        <StatusText status={liveClientStatus} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="p-5 rounded-lg bg-[#121923] border border-[#1E293B] space-y-3">
              <h4 className="font-display text-sm font-semibold text-[#F1F5F9]">
                Exposed MCP Resources (
                {mcpStatus ? mcpStatus.resources.length : MCP_RESOURCES_SPEC.length}) & Prompts (
                {mcpStatus ? mcpStatus.prompts.length : MCP_PROMPTS_SPEC.length})
                {!mcpStatus ? ' — Offline Spec' : ' — Live Daemon'}
              </h4>
              <div className="space-y-2 text-xs">
                {(mcpStatus
                  ? mcpStatus.resources.map((r) => ({
                      uri: r.uri,
                      summary: r.description ?? r.name,
                    }))
                  : MCP_RESOURCES_SPEC
                ).map((res) => (
                  <div
                    key={res.uri}
                    className="flex items-center justify-between gap-3 py-1.5 border-b border-[#1E293B] last:border-b-0"
                  >
                    <span className="font-mono text-[#35D6C5]">{res.uri}</span>
                    <span className="text-[#94A3B8] text-right">{res.summary}</span>
                  </div>
                ))}
              </div>
              <div className="pt-2 text-xs text-[#94A3B8]">
                Prompts:{' '}
                <span className="font-mono text-[#F1F5F9]">
                  {(mcpStatus ? mcpStatus.prompts.map((p) => p.name) : MCP_PROMPTS_SPEC).join(
                    ' · '
                  )}
                </span>
              </div>
            </div>

            <div className="p-5 rounded-lg bg-[#121923] border border-[#1E293B] space-y-3">
              <h4 className="font-display text-sm font-semibold text-[#F1F5F9]">
                External MCP Client Configuration (Stdio / Loopback HTTP)
              </h4>
              <pre className="p-3 rounded bg-[#0B0F14] border border-[#1E293B] font-mono text-[11px] text-[#F1F5F9] overflow-x-auto leading-relaxed">
                {`{
  "mcpServers": {
    "nexus-bridge": {
      "command": "python",
      "args": ["-m", "core.nexus_core", "--mcp-stdio"]
    }
  }
}`}
              </pre>
              <div className="text-xs text-[#94A3B8]">
                Optional Streamable HTTP endpoint:{' '}
                <span className="font-mono text-[#35D6C5]">{config.mcpHttpUrl}</span> (requires{' '}
                <span className="font-mono text-[#F1F5F9]">Authorization: Bearer</span> from{' '}
                <span className="font-mono text-[#F1F5F9]">~/.nexus/daemon.token</span>).
              </div>
            </div>
          </div>
        </section>
      )}

      {activeTab === 'REST API' && (
        <section className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          <form
            onSubmit={handleSaveEndpoints}
            className="lg:col-span-5 p-5 rounded-lg bg-[#121923] border border-[#1E293B] space-y-4"
          >
            <div className="flex items-center justify-between gap-2">
              <h3 className="font-display text-base font-semibold text-[#F1F5F9]">
                Local REST & WebSocket Endpoints
              </h3>
              <StatusText status={lastProbe ? lastProbe.status : NexusStatus.Disconnected} />
            </div>

            <div className="space-y-3 text-xs">
              <label className="block space-y-1">
                <span className="text-[#94A3B8]">REST Base URL</span>
                <input
                  type="url"
                  value={restDraft}
                  onChange={(e) => setRestDraft(e.target.value)}
                  className="w-full px-3 py-2 rounded bg-[#0B0F14] border border-[#1E293B] font-mono text-[#F1F5F9] focus:outline-none focus:border-[#35D6C5]"
                />
              </label>

              <label className="block space-y-1">
                <span className="text-[#94A3B8]">WebSocket Events URL</span>
                <input
                  type="text"
                  value={wsDraft}
                  onChange={(e) => setWsDraft(e.target.value)}
                  className="w-full px-3 py-2 rounded bg-[#0B0F14] border border-[#1E293B] font-mono text-[#F1F5F9] focus:outline-none focus:border-[#35D6C5]"
                />
              </label>

              <label className="block space-y-1">
                <span className="text-[#94A3B8]">MCP HTTP URL</span>
                <input
                  type="url"
                  value={mcpDraft}
                  onChange={(e) => setMcpDraft(e.target.value)}
                  className="w-full px-3 py-2 rounded bg-[#0B0F14] border border-[#1E293B] font-mono text-[#F1F5F9] focus:outline-none focus:border-[#35D6C5]"
                />
              </label>
            </div>

            <div className="flex flex-wrap items-center gap-3 pt-1">
              <button
                type="submit"
                className="px-4 py-1.5 text-xs font-medium rounded-md border border-[#1E293B] bg-[#0B0F14] text-[#F1F5F9] hover:border-[#3987F5] transition-colors whitespace-nowrap shrink-0"
              >
                Save Endpoints
              </button>
              <button
                type="button"
                onClick={onProbeBridge}
                disabled={probing}
                className="px-4 py-1.5 text-xs font-semibold rounded-md bg-[#35D6C5] text-[#081016] hover:bg-[#4BE0D0] disabled:opacity-60 transition-colors whitespace-nowrap shrink-0"
              >
                {probing ? 'Probing...' : 'Test Loopback Health'}
              </button>
            </div>
          </form>

          <div className="lg:col-span-7 overflow-x-auto rounded-lg border border-[#1E293B] bg-[#121923]">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-[#1E293B] text-xs font-medium text-[#94A3B8]">
                  <th className="py-3 px-4">Method</th>
                  <th className="py-3 px-4">Path</th>
                  <th className="py-3 px-4">Scope</th>
                  <th className="py-3 px-4">Bearer Auth</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1E293B] text-xs">
                {NEXUS_REST_ROUTES.map((route) => (
                  <tr key={`${route.method}-${route.path}`} className="hover:bg-[#161F2C]">
                    <td className="py-3 px-4 font-mono font-semibold text-[#3987F5]">
                      {route.method}
                    </td>
                    <td className="py-3 px-4">
                      <div className="font-mono text-[#F1F5F9]">{route.path}</div>
                      <div className="text-[#94A3B8] mt-0.5">{route.summary}</div>
                    </td>
                    <td className="py-3 px-4 font-mono text-[#94A3B8] whitespace-nowrap">
                      {route.runtimeScope}
                    </td>
                    <td className="py-3 px-4 whitespace-nowrap text-[#F1F5F9]">
                      {route.requiresAuth ? 'Required' : 'Public Local'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
