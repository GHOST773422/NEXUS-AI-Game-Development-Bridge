import { memo } from 'react';
import { Menu, RefreshCw } from 'lucide-react';
import { NavSection } from '../../types/nexus';

interface TopBarProps {
  activeSection: NavSection;
  probing: boolean;
  demoMode: boolean;
  onToggleDemoMode: () => void;
  onProbeBridge: () => void;
  onOpenMobileMenu: () => void;
}

export const TopBar = memo(function TopBar({
  activeSection,
  probing,
  demoMode,
  onToggleDemoMode,
  onProbeBridge,
  onOpenMobileMenu,
}: TopBarProps) {
  return (
    <header className="sticky top-0 z-30 h-14 px-5 lg:px-8 flex items-center justify-between gap-8 bg-[#0B0F14]/95 backdrop-blur-sm border-b border-[#1E293B]">
      <div className="flex items-center gap-3 min-w-0">
        <button
          type="button"
          onClick={onOpenMobileMenu}
          className="lg:hidden p-1.5 -ml-1.5 text-[#94A3B8] hover:text-[#F1F5F9] focus-visible:outline-2 focus-visible:outline-[#35D6C5]"
          aria-label="Open navigation menu"
        >
          <Menu className="h-5 w-5" />
        </button>
        <div className="flex items-center gap-2 text-sm min-w-0">
          <span className="text-[#94A3B8] whitespace-nowrap shrink-0">Control Center</span>
          <span className="text-[#475569]" aria-hidden="true">
            /
          </span>
          <h1 className="font-display font-semibold text-[#F1F5F9] truncate">{activeSection}</h1>
        </div>
      </div>

      <div className="flex items-center gap-3 shrink-0">
        <button
          type="button"
          onClick={onToggleDemoMode}
          className={`px-3 py-1.5 text-xs font-medium rounded-md border transition-colors whitespace-nowrap shrink-0 focus-visible:outline-2 focus-visible:outline-[#3987F5] ${
            demoMode
              ? 'bg-[#2A2010] border-[#D99B38]/60 text-[#F4BF64]'
              : 'bg-[#121923] border-[#1E293B] text-[#94A3B8] hover:text-[#F1F5F9] hover:border-[#3987F5]'
          }`}
        >
          {demoMode ? 'Unload Demo Fixture' : 'Load Demo Fixture'}
        </button>

        <button
          type="button"
          onClick={onProbeBridge}
          disabled={probing}
          className="inline-flex items-center gap-2 px-4 py-1.5 text-xs font-semibold rounded-md bg-[#35D6C5] text-[#081016] hover:bg-[#4BE0D0] disabled:opacity-60 transition-colors duration-150 whitespace-nowrap shrink-0 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#35D6C5]"
        >
          <RefreshCw
            className={`h-3.5 w-3.5 shrink-0 ${probing ? 'animate-spin' : ''}`}
            aria-hidden="true"
          />
          <span>{probing ? 'Probing Bridge...' : 'Probe Local Bridge'}</span>
        </button>
      </div>
    </header>
  );
});
