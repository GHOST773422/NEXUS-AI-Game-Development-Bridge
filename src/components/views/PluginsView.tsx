import { Cable, Cpu, FileCode2, ShieldAlert, ShieldCheck } from 'lucide-react';
import {
  ADAPTER_MANIFEST_SCHEMA_VERSION,
  ADAPTER_PROTOCOL_METHODS,
  ADAPTER_WIRE_PROTOCOL_VERSION,
} from '../../../sdk/ts';
import { LiveAdapterDescriptor, NexusStatus } from '../../types/nexus';
import { StatusText } from '../ui/StatusText';

interface AdapterManifestSummary {
  id: string;
  displayName: string;
  runtimeLanguage: 'C#' | 'GDScript' | 'C++' | 'Python';
  engineKind: string;
  transport: string;
  manifestPath: string;
  isTestAdapter: boolean;
  status: NexusStatus;
  notes: string;
}

const KNOWN_ADAPTER_MANIFESTS: AdapterManifestSummary[] = [
  {
    id: 'nexus.unity.csharp_editor',
    displayName: 'Unity C# Editor Bridge Adapter',
    runtimeLanguage: 'C#',
    engineKind: 'Unity',
    transport: 'tcp-loopback (127.0.0.1:47201)',
    manifestPath: 'adapters/unity/nexus-adapter.manifest.json',
    isTestAdapter: false,
    status: NexusStatus.Disconnected,
    notes: 'Native Unity Editor UPM C# listener. Connects only when running inside Unity Editor.',
  },
  {
    id: 'nexus.godot.gdscript_editor',
    displayName: 'Godot GDScript EditorPlugin Adapter',
    runtimeLanguage: 'GDScript',
    engineKind: 'Godot',
    transport: 'tcp-loopback (127.0.0.1:47202)',
    manifestPath: 'adapters/godot/nexus-adapter.manifest.json',
    isTestAdapter: false,
    status: NexusStatus.Disconnected,
    notes:
      'Native Godot 4.x GDScript TCPServer plugin. Requires active local Godot editor session.',
  },
  {
    id: 'nexus.unreal.cpp_editor',
    displayName: 'Unreal C++ Editor Bridge Adapter',
    runtimeLanguage: 'C++',
    engineKind: 'Unreal',
    transport: 'tcp-loopback (127.0.0.1:47203)',
    manifestPath: 'adapters/cpp/nexus-adapter.manifest.json',
    isTestAdapter: false,
    status: NexusStatus.Planned,
    notes:
      'Planned manifest contract only — no native C++ Unreal Editor plugin binary is implemented yet.',
  },
  {
    id: 'nexus.test.protocol_harness',
    displayName: '[TEST ADAPTER] Synthetic Protocol Harness',
    runtimeLanguage: 'Python',
    engineKind: 'TestHarness',
    transport: 'stdio / tcp-loopback',
    manifestPath: 'adapters/test-adapter/nexus-adapter.manifest.json',
    isTestAdapter: true,
    status: NexusStatus.Disconnected,
    notes:
      'Explicit out-of-process synthetic harness for protocol tests. Never counted as a real engine.',
  },
];

interface PluginsViewProps {
  liveAdapters?: LiveAdapterDescriptor[];
  daemonAuthenticated?: boolean;
}

export function PluginsView({ liveAdapters = [], daemonAuthenticated = false }: PluginsViewProps) {
  const realConnectedCount = liveAdapters.filter(
    (adapter) => !adapter.isTestAdapter && adapter.lifecycleState === NexusStatus.Connected
  ).length;

  const mergedAdapters: AdapterManifestSummary[] = KNOWN_ADAPTER_MANIFESTS.map((spec) => {
    const live = liveAdapters.find(
      (item) =>
        item.adapterId === spec.id ||
        (!spec.isTestAdapter &&
          !item.isTestAdapter &&
          item.engineKind.toLowerCase() === spec.engineKind.toLowerCase() &&
          item.lifecycleState === NexusStatus.Connected)
    );
    if (!live) {
      return spec;
    }
    return {
      ...spec,
      status: live.lifecycleState,
      notes: `${spec.notes} Live state: ${live.lifecycleState} (${live.registeredToolCount} tools).`,
    };
  });

  const extraLiveAdapters: AdapterManifestSummary[] = liveAdapters
    .filter((item) => !KNOWN_ADAPTER_MANIFESTS.some((spec) => spec.id === item.adapterId))
    .map((item) => ({
      id: item.adapterId,
      displayName: item.displayName,
      runtimeLanguage: (['C#', 'GDScript', 'C++', 'Python'].includes(item.runtimeLanguage)
        ? item.runtimeLanguage
        : 'Python') as AdapterManifestSummary['runtimeLanguage'],
      engineKind: item.engineKind,
      transport: item.transportKind,
      manifestPath: `installed://${item.adapterId}`,
      isTestAdapter: item.isTestAdapter,
      status: item.lifecycleState,
      notes: `Installed daemon adapter v${item.version} (${item.registeredToolCount} registered tools).`,
    }));

  const displayedAdapters = [...extraLiveAdapters, ...mergedAdapters];

  return (
    <div className="space-y-8">
      <section className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-[#1E293B]">
        <div className="space-y-1 max-w-3xl">
          <h2 className="font-display text-xl font-semibold text-[#F1F5F9]">
            Universal Engine Adapters &amp; Plugin Manifests
          </h2>
          <p className="text-sm text-[#94A3B8]">
            Language-neutral NDJSON JSON-RPC 2.0 adapter runtime supporting native C#, GDScript,
            future C++, and third-party engine extensions with strict SemVer and checksum gating.
          </p>
        </div>
        <StatusText
          status={
            realConnectedCount > 0
              ? NexusStatus.Connected
              : daemonAuthenticated
                ? NexusStatus.Available
                : NexusStatus.Disconnected
          }
        />
      </section>

      <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-5 rounded-lg bg-[#121923] border border-[#1E293B] space-y-2">
          <div className="flex items-center gap-2 text-xs text-[#94A3B8] uppercase tracking-wider">
            <Cable className="h-4 w-4 text-[#35D6C5]" aria-hidden="true" />
            Wire Protocol
          </div>
          <p className="font-mono text-lg font-semibold text-[#F1F5F9]">
            JSON-RPC 2.0 v{ADAPTER_WIRE_PROTOCOL_VERSION}
          </p>
          <p className="text-xs text-[#94A3B8]">
            {ADAPTER_PROTOCOL_METHODS.length} required methods over stdio or 127.0.0.1 TCP
          </p>
        </div>

        <div className="p-5 rounded-lg bg-[#121923] border border-[#1E293B] space-y-2">
          <div className="flex items-center gap-2 text-xs text-[#94A3B8] uppercase tracking-wider">
            <ShieldCheck className="h-4 w-4 text-[#3987F5]" aria-hidden="true" />
            Manifest Schema
          </div>
          <p className="font-mono text-lg font-semibold text-[#F1F5F9]">
            v{ADAPTER_MANIFEST_SCHEMA_VERSION}
          </p>
          <p className="text-xs text-[#94A3B8]">
            SemVer compatibility, PermissionScope checks, SHA-256 verification
          </p>
        </div>

        <div className="p-5 rounded-lg bg-[#121923] border border-[#1E293B] space-y-2">
          <div className="flex items-center gap-2 text-xs text-[#94A3B8] uppercase tracking-wider">
            <ShieldAlert className="h-4 w-4 text-[#F59E0B]" aria-hidden="true" />
            Connected Real Engines
          </div>
          <p className="font-mono text-lg font-semibold text-[#F1F5F9]">
            {realConnectedCount} Real Connected
          </p>
          <p className="text-xs text-[#94A3B8]">
            Test adapters remain strictly isolated from real engine and tool counters
          </p>
        </div>
      </section>

      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-display text-base font-semibold text-[#F1F5F9]">
            Registered Adapter Manifest Specifications
          </h3>
          <span className="text-xs font-mono text-[#94A3B8]">
            nexus-adapter.manifest.json ({displayedAdapters.length} specs)
          </span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {displayedAdapters.map((adapter) => (
            <div
              key={adapter.id}
              className="p-5 rounded-lg bg-[#121923] border border-[#1E293B] space-y-3"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <Cpu className="h-4 w-4 text-[#35D6C5]" aria-hidden="true" />
                    <h4 className="font-display text-sm font-semibold text-[#F1F5F9]">
                      {adapter.displayName}
                    </h4>
                  </div>
                  <p className="text-xs font-mono text-[#94A3B8]">
                    {adapter.id} · {adapter.runtimeLanguage} · {adapter.engineKind}
                  </p>
                </div>
                <StatusText status={adapter.status} />
              </div>

              <p className="text-xs text-[#94A3B8] leading-relaxed">{adapter.notes}</p>

              <div className="pt-2 border-t border-[#1E293B] flex flex-wrap items-center justify-between gap-2 text-xs font-mono text-[#94A3B8]">
                <span>{adapter.transport}</span>
                <span>{adapter.manifestPath}</span>
              </div>
              {adapter.isTestAdapter ? (
                <div className="text-xs text-[#F59E0B] font-mono">
                  isTestAdapter=true · Excluded from real engine connections &amp; verified tool
                  totals
                </div>
              ) : null}
            </div>
          ))}
        </div>
      </section>

      <section className="p-6 rounded-lg bg-[#121923] border border-[#1E293B] space-y-4">
        <div className="flex items-center gap-3">
          <FileCode2 className="h-5 w-5 text-[#3987F5]" aria-hidden="true" />
          <h3 className="font-display text-base font-semibold text-[#F1F5F9]">
            Canonical 11-Method Universal Adapter Contract
          </h3>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 text-xs font-mono">
          {ADAPTER_PROTOCOL_METHODS.map((method) => (
            <div
              key={method}
              className="px-3 py-2 rounded bg-[#0B0F14] border border-[#1E293B] text-[#35D6C5]"
            >
              {method}()
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
