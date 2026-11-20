import { memo } from 'react';
import {
  Activity,
  Blocks,
  Cpu,
  FolderGit2,
  LayoutDashboard,
  ListChecks,
  Network,
  Puzzle,
  Settings,
  Stethoscope,
  X,
} from 'lucide-react';
import { NavSection, NexusStatus, RuntimeEnvironmentInfo } from '../../types/nexus';
import { StatusText } from '../ui/StatusText';

interface SidebarProps {
  activeSection: NavSection;
  onSelectSection: (section: NavSection) => void;
  runtime: RuntimeEnvironmentInfo;
  bridgeStatus: NexusStatus;
  demoMode: boolean;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}

const NAV_ITEMS: { section: NavSection; icon: typeof LayoutDashboard }[] = [
  { section: NavSection.Dashboard, icon: LayoutDashboard },
  { section: NavSection.Connections, icon: Network },
  { section: NavSection.Engines, icon: Cpu },
  { section: NavSection.Projects, icon: FolderGit2 },
  { section: NavSection.Tools, icon: Blocks },
  { section: NavSection.Tasks, icon: ListChecks },
  { section: NavSection.Activity, icon: Activity },
  { section: NavSection.Plugins, icon: Puzzle },
  { section: NavSection.Diagnostics, icon: Stethoscope },
  { section: NavSection.Settings, icon: Settings },
];

export const Sidebar = memo(function Sidebar({
  activeSection,
  onSelectSection,
  runtime,
  bridgeStatus,
  demoMode,
  mobileOpen,
  onCloseMobile,
}: SidebarProps) {
  const navContent = (
    <div className="flex h-full flex-col bg-[#0E141C] border-r border-[#1E293B]">
      <div className="flex items-center justify-between px-5 h-14 border-b border-[#1E293B]">
        <div className="flex items-baseline gap-2.5 min-w-0">
          <span className="font-display text-base font-bold tracking-tight text-[#F1F5F9] whitespace-nowrap shrink-0">
            NEXUS
          </span>
          <span className="text-xs text-[#94A3B8] truncate">Bridge Console</span>
        </div>
        <button
          type="button"
          onClick={onCloseMobile}
          className="lg:hidden p-1.5 text-[#94A3B8] hover:text-[#F1F5F9] focus-visible:outline-2 focus-visible:outline-[#35D6C5]"
          aria-label="Close navigation menu"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <nav aria-label="Primary navigation" className="flex-1 overflow-y-auto px-3 py-4 space-y-0.5">
        {NAV_ITEMS.map(({ section, icon: Icon }) => {
          const isActive = activeSection === section;
          return (
            <button
              key={section}
              type="button"
              onClick={() => {
                onSelectSection(section);
                onCloseMobile();
              }}
              aria-current={isActive ? 'page' : undefined}
              className={`w-full flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-md transition-colors duration-150 whitespace-nowrap focus-visible:outline-2 focus-visible:outline-[#35D6C5] ${
                isActive
                  ? 'bg-[#121923] text-[#35D6C5]'
                  : 'text-[#94A3B8] hover:text-[#F1F5F9] hover:bg-[#121923]/60'
              }`}
            >
              <Icon
                className={`h-4 w-4 shrink-0 ${isActive ? 'text-[#35D6C5]' : 'text-[#64748B]'}`}
                aria-hidden="true"
              />
              <span className="truncate">{section}</span>
            </button>
          );
        })}
      </nav>

      <div className="px-5 py-4 border-t border-[#1E293B] space-y-2.5 text-xs">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[#94A3B8]">Host</span>
          <span className="font-mono text-[#F1F5F9] whitespace-nowrap">
            {runtime.hostKind === 'TauriDesktop' ? 'Tauri Desktop' : 'Web Preview'}
          </span>
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-[#94A3B8]">Local Bridge</span>
          <StatusText status={bridgeStatus} />
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-[#94A3B8]">Data Mode</span>
          <span
            className={`font-mono whitespace-nowrap ${demoMode ? 'text-[#D99B38]' : 'text-[#35D6C5]'}`}
          >
            {demoMode ? 'Demo Fixture' : 'Live Runtime'}
          </span>
        </div>
      </div>
    </div>
  );

  return (
    <>
      <aside className="hidden lg:block w-60 shrink-0 h-screen sticky top-0">{navContent}</aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden flex">
          <div className="fixed inset-0 bg-black/60" onClick={onCloseMobile} aria-hidden="true" />
          <aside className="relative w-64 max-w-[80vw] h-full z-10">{navContent}</aside>
        </div>
      )}
    </>
  );
});
