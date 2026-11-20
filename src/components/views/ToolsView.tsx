import { useMemo, useState } from 'react';
import { TOOL_CATEGORY_CONTRACTS } from '../../data/architectureSpec';
import { EngineKind, ToolContractSchema } from '../../types/nexus';
import { StatusText } from '../ui/StatusText';

interface ToolsViewProps {
  liveTools?: ToolContractSchema[];
}

export function ToolsView({ liveTools = [] }: ToolsViewProps) {
  const [search, setSearch] = useState('');
  const [engineFilter, setEngineFilter] = useState<'All' | EngineKind>('All');
  const combinedCatalogue = useMemo(() => [...liveTools, ...TOOL_CATEGORY_CONTRACTS], [liveTools]);
  const [selectedTool, setSelectedTool] = useState<ToolContractSchema>(
    () => liveTools[0] ?? TOOL_CATEGORY_CONTRACTS[0]
  );

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return combinedCatalogue.filter((t) => {
      if (engineFilter !== 'All' && !t.engineCompatibility.includes(engineFilter)) {
        return false;
      }
      if (!q) return true;
      return (
        t.category.toLowerCase().includes(q) ||
        t.id.toLowerCase().includes(q) ||
        t.description.toLowerCase().includes(q)
      );
    });
  }, [combinedCatalogue, search, engineFilter]);

  return (
    <div className="space-y-8">
      <section className="flex flex-col lg:flex-row lg:items-end justify-between gap-4 pb-6 border-b border-[#1E293B]">
        <div className="space-y-1.5 max-w-3xl">
          <h2 className="font-display text-xl font-semibold text-[#F1F5F9]">
            Tool Catalogue & Capability Schemas
          </h2>
          <p className="text-sm text-[#94A3B8]">
            Dynamic tool discovery populates live tools only after an active engine adapter verifies
            support. Inspect verified tools and all 19 capability category contracts below.
          </p>
        </div>
        <div className="text-xs font-mono tabular-nums text-[#94A3B8] whitespace-nowrap shrink-0">
          {liveTools.length} Live Tools · {TOOL_CATEGORY_CONTRACTS.length} Category Contracts
        </div>
      </section>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-start">
        <div className="xl:col-span-7 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search 19 tool categories, IDs, or permissions..."
              aria-label="Filter tool categories"
              className="flex-1 px-3.5 py-2 rounded-md bg-[#121923] border border-[#1E293B] text-sm text-[#F1F5F9] placeholder:text-[#64748B] focus:outline-none focus:border-[#35D6C5]"
            />
            <div className="flex items-center gap-1 p-1 rounded-md bg-[#121923] border border-[#1E293B] shrink-0">
              {(['All', EngineKind.Unity, EngineKind.Godot] as const).map((eng) => (
                <button
                  key={eng}
                  type="button"
                  onClick={() => setEngineFilter(eng)}
                  className={`px-3 py-1 text-xs font-medium rounded transition-colors whitespace-nowrap shrink-0 ${
                    engineFilter === eng
                      ? 'bg-[#1B2636] text-[#35D6C5]'
                      : 'text-[#94A3B8] hover:text-[#F1F5F9]'
                  }`}
                >
                  {eng}
                </button>
              ))}
            </div>
          </div>

          <div className="overflow-x-auto rounded-lg border border-[#1E293B] bg-[#121923]">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-[#1E293B] text-xs font-medium text-[#94A3B8]">
                  <th className="py-3 px-4">Category</th>
                  <th className="py-3 px-4">Context</th>
                  <th className="py-3 px-4">Engines</th>
                  <th className="py-3 px-4">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1E293B] text-sm">
                {filtered.map((tool) => {
                  const active = selectedTool.id === tool.id;
                  return (
                    <tr
                      key={tool.id}
                      onClick={() => setSelectedTool(tool)}
                      className={`cursor-pointer transition-colors ${
                        active ? 'bg-[#182230]' : 'hover:bg-[#161F2C]'
                      }`}
                    >
                      <td className="py-2.5 px-4">
                        <div className="font-medium text-[#F1F5F9]">{tool.category}</div>
                        <div className="font-mono text-xs text-[#94A3B8]">{tool.id}</div>
                      </td>
                      <td className="py-2.5 px-4 text-xs font-mono text-[#94A3B8] whitespace-nowrap">
                        {tool.executionContext}
                      </td>
                      <td className="py-2.5 px-4 text-xs text-[#94A3B8] whitespace-nowrap">
                        {tool.engineCompatibility.join(' · ')}
                      </td>
                      <td className="py-2.5 px-4 whitespace-nowrap">
                        <StatusText status={tool.implementationStatus} />
                      </td>
                    </tr>
                  );
                })}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={4} className="py-6 px-4 text-center text-sm text-[#94A3B8]">
                      No tool categories match "{search}".
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <aside className="xl:col-span-5 p-5 rounded-lg bg-[#121923] border border-[#1E293B] space-y-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-xs text-[#94A3B8]">Tool Contract Detail</div>
              <h3 className="font-display text-base font-semibold text-[#F1F5F9] mt-0.5">
                {selectedTool.category}
              </h3>
            </div>
            <StatusText status={selectedTool.implementationStatus} />
          </div>

          <p className="text-xs text-[#94A3B8] leading-relaxed">{selectedTool.description}</p>

          <div className="space-y-2 text-xs pt-2 border-t border-[#1E293B]">
            <div className="flex justify-between gap-2">
              <span className="text-[#94A3B8]">Contract ID</span>
              <span className="font-mono text-[#F1F5F9]">{selectedTool.id}</span>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-[#94A3B8]">Execution Context</span>
              <span className="font-mono text-[#F1F5F9]">{selectedTool.executionContext}</span>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-[#94A3B8]">Required Permissions</span>
              <span className="font-mono text-[#3987F5] text-right">
                {selectedTool.requiredPermissions.join(', ')}
              </span>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-[#94A3B8]">Error Policy</span>
              <span className="text-[#94A3B8] text-right max-w-[230px]">
                {selectedTool.errorHandling}
              </span>
            </div>
          </div>

          <div className="space-y-1.5">
            <div className="text-xs text-[#94A3B8]">Input & Output JSON Schema</div>
            <pre className="p-3 rounded-md bg-[#0B0F14] border border-[#1E293B] text-xs font-mono text-[#94A3B8] overflow-x-auto">
              {JSON.stringify(
                {
                  inputSchema: selectedTool.inputSchema,
                  outputSchema: selectedTool.outputSchema,
                },
                null,
                2
              )}
            </pre>
          </div>
        </aside>
      </div>
    </div>
  );
}
