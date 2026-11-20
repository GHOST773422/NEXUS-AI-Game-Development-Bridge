import { memo, useMemo, useState } from 'react';
import { formatCachedLocalTime } from '../../services/formatCache';
import { SessionActivityEntry } from '../../types/nexus';
import { StatusText } from '../ui/StatusText';

interface ActivityViewProps {
  entries: SessionActivityEntry[];
  streamPaused: boolean;
  onToggleStreamPaused: () => void;
  onClearSessionLog: () => void;
}

const DEFAULT_ACTIVITY_PAGE_SIZE = 50;

export const ActivityView = memo(function ActivityView({
  entries,
  streamPaused,
  onToggleStreamPaused,
  onClearSessionLog,
}: ActivityViewProps) {
  const [categoryFilter, setCategoryFilter] = useState<'All' | SessionActivityEntry['category']>(
    'All'
  );
  const [severityFilter, setSeverityFilter] = useState<'All' | 'Warnings & Errors'>('All');
  const [search, setSearch] = useState('');
  const [showAllRows, setShowAllRows] = useState(false);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return entries.filter((e) => {
      if (categoryFilter !== 'All' && e.category !== categoryFilter) return false;
      if (severityFilter === 'Warnings & Errors' && e.severity === 'info') return false;
      if (!q) return true;
      return e.message.toLowerCase().includes(q) || (e.detail?.toLowerCase().includes(q) ?? false);
    });
  }, [entries, categoryFilter, severityFilter, search]);

  const visibleEntries = useMemo(
    () => (showAllRows ? filtered : filtered.slice(0, DEFAULT_ACTIVITY_PAGE_SIZE)),
    [filtered, showAllRows]
  );

  return (
    <div className="space-y-8">
      <section className="flex flex-col lg:flex-row lg:items-end justify-between gap-4 pb-6 border-b border-[#1E293B]">
        <div className="space-y-1.5">
          <h2 className="font-display text-xl font-semibold text-[#F1F5F9]">
            Activity & Real-Time Event Stream
          </h2>
          <p className="text-sm text-[#94A3B8]">
            Chronological log of observed runtime checks, bridge probes, project registrations, and
            task events.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3 shrink-0">
          <button
            type="button"
            onClick={onToggleStreamPaused}
            className={`px-3.5 py-1.5 text-xs font-medium rounded-md border transition-colors whitespace-nowrap shrink-0 ${
              streamPaused
                ? 'bg-[#2A2010] border-[#D99B38]/50 text-[#F4BF64]'
                : 'bg-[#121923] border-[#1E293B] text-[#F1F5F9] hover:border-[#35D6C5]'
            }`}
          >
            {streamPaused ? 'Resume Event Capture' : 'Pause Event Capture'}
          </button>
          <button
            type="button"
            onClick={onClearSessionLog}
            className="px-3.5 py-1.5 text-xs font-medium rounded-md border border-[#1E293B] text-[#94A3B8] hover:text-[#F1F5F9] hover:border-[#3987F5] transition-colors whitespace-nowrap shrink-0"
          >
            Clear Log
          </button>
        </div>
      </section>

      <section className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Filter event messages or details..."
          aria-label="Filter activity events"
          className="flex-1 px-3.5 py-2 rounded-md bg-[#121923] border border-[#1E293B] text-sm text-[#F1F5F9] placeholder:text-[#64748B] focus:outline-none focus:border-[#35D6C5]"
        />

        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <div className="flex items-center gap-1 p-1 rounded-md bg-[#121923] border border-[#1E293B]">
            {(['All', 'Runtime', 'Probe', 'Security', 'Project', 'Task'] as const).map((cat) => (
              <button
                key={cat}
                type="button"
                onClick={() => setCategoryFilter(cat)}
                className={`px-2.5 py-1 text-xs font-medium rounded transition-colors whitespace-nowrap shrink-0 ${
                  categoryFilter === cat
                    ? 'bg-[#1B2636] text-[#35D6C5]'
                    : 'text-[#94A3B8] hover:text-[#F1F5F9]'
                }`}
              >
                {cat}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-1 p-1 rounded-md bg-[#121923] border border-[#1E293B]">
            {(['All', 'Warnings & Errors'] as const).map((sev) => (
              <button
                key={sev}
                type="button"
                onClick={() => setSeverityFilter(sev)}
                className={`px-2.5 py-1 text-xs font-medium rounded transition-colors whitespace-nowrap shrink-0 ${
                  severityFilter === sev
                    ? 'bg-[#1B2636] text-[#3987F5]'
                    : 'text-[#94A3B8] hover:text-[#F1F5F9]'
                }`}
              >
                {sev}
              </button>
            ))}
          </div>
        </div>
      </section>

      <div className="overflow-x-auto rounded-lg border border-[#1E293B] bg-[#121923]">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-[#1E293B] text-xs font-medium text-[#94A3B8]">
              <th className="py-3 px-4">Timestamp</th>
              <th className="py-3 px-4">Category</th>
              <th className="py-3 px-4">Event</th>
              <th className="py-3 px-4">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#1E293B] text-sm">
            {visibleEntries.map((entry) => (
              <tr key={entry.id} className="hover:bg-[#161F2C]">
                <td className="py-3 px-4 font-mono text-xs tabular-nums text-[#94A3B8] whitespace-nowrap align-top">
                  {formatCachedLocalTime(entry.timestamp)}
                </td>
                <td className="py-3 px-4 text-xs text-[#94A3B8] whitespace-nowrap align-top">
                  {entry.category}
                </td>
                <td className="py-3 px-4 align-top">
                  <div className="text-[#F1F5F9] text-sm">{entry.message}</div>
                  {entry.detail && (
                    <div className="text-xs font-mono text-[#94A3B8] mt-1">{entry.detail}</div>
                  )}
                </td>
                <td className="py-3 px-4 whitespace-nowrap align-top">
                  <StatusText status={entry.status} />
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={4} className="py-8 px-4 text-center text-sm text-[#94A3B8]">
                  No activity entries recorded for this filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        {filtered.length > DEFAULT_ACTIVITY_PAGE_SIZE && (
          <div className="px-4 py-3 border-t border-[#1E293B] flex items-center justify-between text-xs text-[#94A3B8]">
            <span>
              Showing {visibleEntries.length} of {filtered.length} matching entries
            </span>
            <button
              type="button"
              onClick={() => setShowAllRows((prev) => !prev)}
              className="font-medium text-[#35D6C5] hover:underline whitespace-nowrap"
            >
              {showAllRows
                ? `Collapse to latest ${DEFAULT_ACTIVITY_PAGE_SIZE}`
                : `Show all ${filtered.length} entries`}
            </button>
          </div>
        )}
      </div>
    </div>
  );
});
