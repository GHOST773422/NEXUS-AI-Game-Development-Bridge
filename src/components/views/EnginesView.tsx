import { useState } from 'react';
import { ENGINE_ADAPTER_CONTRACT } from '../../data/architectureSpec';
import { AdapterInstallGuide, EngineCardState, EngineKind, NexusStatus } from '../../types/nexus';
import { StatusText } from '../ui/StatusText';

interface EnginesViewProps {
  engines: EngineCardState[];
  adapterGuides?: AdapterInstallGuide[];
  onUpdateEnginePath: (engine: EngineKind, path: string) => void;
  onScanEngines: () => void;
}

const DEFAULT_OFFLINE_GUIDES: AdapterInstallGuide[] = [
  {
    engine: 'unity',
    displayName: 'Unity Editor 2022.3 LTS+ (UPM Local Package)',
    resourcePath: 'adapters/unity/package.json',
    stagedPresent: true,
    minEngineVersion: '2022.3 LTS / Unity 6',
    defaultEndpoint: 'http://127.0.0.1:47100',
    steps: [
      'Open your Unity project in Unity Editor on Windows.',
      'Select Window > Package Manager > + > Add package from disk...',
      'Choose adapters/unity/package.json (or installed resources/adapters/unity/package.json).',
      'Open Window > NEXUS Bridge and point it to http://127.0.0.1:47100.',
    ],
  },
  {
    engine: 'godot',
    displayName: 'Godot Engine 4.2+ (EditorPlugin Addon)',
    resourcePath: 'adapters/godot/addons/nexus_bridge/',
    stagedPresent: true,
    minEngineVersion: '4.2+',
    defaultEndpoint: 'ws://127.0.0.1:47101/events',
    steps: [
      'Copy adapters/godot/addons/nexus_bridge/ into <YourGodotProject>/addons/nexus_bridge/.',
      'In Godot Editor open Project > Project Settings > Plugins and enable NEXUS Bridge.',
      'Confirm daemon endpoint http://127.0.0.1:47100 and local daemon.token authentication.',
    ],
  },
];

export function EnginesView({
  engines,
  adapterGuides,
  onUpdateEnginePath,
  onScanEngines,
}: EnginesViewProps) {
  const [editingEngine, setEditingEngine] = useState<EngineKind | null>(null);
  const [pathDraft, setPathDraft] = useState('');
  const guides = adapterGuides && adapterGuides.length > 0 ? adapterGuides : DEFAULT_OFFLINE_GUIDES;

  const hasAnyConnectedEngine = engines.some(
    (card) => card.connectionStatus === NexusStatus.Connected
  );

  const beginEdit = (card: EngineCardState) => {
    setEditingEngine(card.engine);
    const placeholder = card.installationPath.startsWith('Not detected')
      ? ''
      : card.installationPath;
    setPathDraft(placeholder);
  };

  const commitEdit = (engine: EngineKind) => {
    onUpdateEnginePath(engine, pathDraft.trim() || 'Not detected');
    setEditingEngine(null);
  };

  return (
    <div className="space-y-8">
      <section className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 pb-6 border-b border-[#1E293B]">
        <div className="space-y-1.5 max-w-3xl">
          <h2 className="font-display text-xl font-semibold text-[#F1F5F9]">
            Engine Manager & Universal Adapter Contract
          </h2>
          <p className="text-sm text-[#94A3B8]">
            Manage Unity and Godot detection paths and inspect the 13-method adapter contract.
            Connection status stays Disconnected until a real native editor plugin connects.
          </p>
        </div>

        <button
          type="button"
          onClick={onScanEngines}
          className="px-4 py-2 text-xs font-medium rounded-md border border-[#1E293B] bg-[#121923] text-[#F1F5F9] hover:border-[#35D6C5] transition-colors whitespace-nowrap shrink-0"
        >
          Check Local Engine Paths
        </button>
      </section>

      <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {engines.map((card) => (
          <div
            key={card.id}
            className="p-5 rounded-lg bg-[#121923] border border-[#1E293B] space-y-4"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="font-display text-base font-semibold text-[#F1F5F9]">
                  {card.displayName}
                </h3>
                <div className="text-xs text-[#94A3B8] mt-0.5">Adapter {card.adapterVersion}</div>
              </div>
              <StatusText status={card.connectionStatus} />
            </div>

            <p className="text-xs text-[#94A3B8] leading-relaxed">{card.notes}</p>

            <dl className="divide-y divide-[#1E293B] text-xs">
              <div className="py-2.5 flex items-center justify-between gap-4">
                <dt className="text-[#94A3B8]">Detection Status</dt>
                <dd>
                  <StatusText status={card.detectionStatus} />
                </dd>
              </div>

              <div className="py-2.5 flex items-center justify-between gap-4">
                <dt className="text-[#94A3B8]">Installation Path</dt>
                <dd className="flex items-center gap-2 min-w-0">
                  {editingEngine === card.engine ? (
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        value={pathDraft}
                        onChange={(e) => setPathDraft(e.target.value)}
                        className="px-2 py-1 rounded bg-[#0B0F14] border border-[#35D6C5] font-mono text-xs text-[#F1F5F9]"
                      />
                      <button
                        type="button"
                        onClick={() => commitEdit(card.engine)}
                        className="text-xs font-medium text-[#35D6C5] whitespace-nowrap"
                      >
                        Save
                      </button>
                    </div>
                  ) : (
                    <>
                      <span
                        className="font-mono text-[#F1F5F9] truncate max-w-[220px]"
                        title={card.installationPath}
                      >
                        {card.installationPath}
                      </span>
                      <button
                        type="button"
                        onClick={() => beginEdit(card)}
                        className="text-[#3987F5] hover:underline whitespace-nowrap shrink-0"
                      >
                        Configure
                      </button>
                    </>
                  )}
                </dd>
              </div>

              <div className="py-2.5 flex items-center justify-between gap-4">
                <dt className="text-[#94A3B8]">Engine Version</dt>
                <dd className="font-mono text-[#F1F5F9]">{card.version}</dd>
              </div>

              <div className="py-2.5 flex items-center justify-between gap-4">
                <dt className="text-[#94A3B8]">Adapter Version</dt>
                <dd className="font-mono text-[#F1F5F9]">{card.adapterVersion}</dd>
              </div>

              <div className="py-2.5 flex items-center justify-between gap-4">
                <dt className="text-[#94A3B8]">Available Projects</dt>
                <dd className="font-mono tabular-nums text-[#F1F5F9]">
                  {card.availableProjectCount}
                </dd>
              </div>

              <div className="py-2.5 flex items-center justify-between gap-4">
                <dt className="text-[#94A3B8]">Connection Status</dt>
                <dd>
                  <StatusText status={card.connectionStatus} />
                </dd>
              </div>

              <div className="py-2.5 flex items-center justify-between gap-4">
                <dt className="text-[#94A3B8]">Capability Count</dt>
                <dd className="font-mono tabular-nums text-[#F1F5F9]">
                  {card.verifiedCapabilityCount} live · {card.contractMethodCount} contract
                </dd>
              </div>
            </dl>
          </div>
        ))}
      </section>

      <section className="space-y-3">
        <h3 className="font-display text-base font-semibold text-[#F1F5F9]">
          Adapter Installation Instructions (Windows Editor Extensions)
        </h3>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {guides.map((guide) => (
            <div
              key={guide.engine}
              className="p-5 rounded-lg bg-[#121923] border border-[#1E293B] space-y-3"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h4 className="font-display text-sm font-semibold text-[#F1F5F9]">
                    {guide.displayName}
                  </h4>
                  <div className="text-xs font-mono text-[#94A3B8] mt-1 break-all">
                    {guide.resourcePath}
                  </div>
                </div>
                <span className="text-xs font-mono text-[#35D6C5] whitespace-nowrap">
                  {guide.minEngineVersion}
                </span>
              </div>
              <ol className="list-decimal list-inside space-y-1.5 text-xs text-[#94A3B8]">
                {guide.steps.map((step, idx) => (
                  <li key={idx} className="leading-relaxed">
                    {step}
                  </li>
                ))}
              </ol>
            </div>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between gap-4">
          <h3 className="font-display text-base font-semibold text-[#F1F5F9]">
            Universal Adapter Contract ({ENGINE_ADAPTER_CONTRACT.length} Methods)
          </h3>
          <span className="text-xs font-mono tabular-nums text-[#94A3B8]">
            Native Integration Boundary
          </span>
        </div>

        <div className="overflow-x-auto rounded-lg border border-[#1E293B] bg-[#121923]">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-[#1E293B] text-xs font-medium text-[#94A3B8]">
                <th className="py-3 px-4">Contract Method</th>
                <th className="py-3 px-4">Unity C# Implementation</th>
                <th className="py-3 px-4">Godot GDScript Implementation</th>
                <th className="py-3 px-4">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1E293B] text-sm">
              {ENGINE_ADAPTER_CONTRACT.map((cap) => (
                <tr key={cap.method} className="hover:bg-[#161F2C]">
                  <td className="py-3 px-4 align-top">
                    <div className="font-mono text-xs font-semibold text-[#35D6C5]">
                      {cap.method}
                    </div>
                    <div className="text-xs text-[#94A3B8] mt-1 max-w-xs">{cap.description}</div>
                  </td>
                  <td className="py-3 px-4 align-top text-xs text-[#F1F5F9] max-w-xs">
                    {cap.unityMechanism}
                  </td>
                  <td className="py-3 px-4 align-top text-xs text-[#F1F5F9] max-w-xs">
                    {cap.godotMechanism}
                  </td>
                  <td className="py-3 px-4 align-top whitespace-nowrap">
                    <StatusText
                      status={hasAnyConnectedEngine ? NexusStatus.Connected : cap.status}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
