import { memo } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  CircleDashed,
  Clock,
  Loader2,
  MinusCircle,
  Unplug,
} from 'lucide-react';
import { NexusStatus } from '../../types/nexus';

interface StatusTextProps {
  status: NexusStatus;
  className?: string;
}

const STATUS_STYLE: Record<NexusStatus, { color: string; Icon: typeof CheckCircle2 }> = {
  [NexusStatus.Connected]: {
    color: 'text-[#35D6C5]',
    Icon: CheckCircle2,
  },
  [NexusStatus.Available]: {
    color: 'text-[#35D6C5]',
    Icon: CheckCircle2,
  },
  [NexusStatus.Running]: {
    color: 'text-[#3987F5]',
    Icon: Loader2,
  },
  [NexusStatus.Disconnected]: {
    color: 'text-[#8B97A7]',
    Icon: Unplug,
  },
  [NexusStatus.Unavailable]: {
    color: 'text-[#D99B38]',
    Icon: MinusCircle,
  },
  [NexusStatus.Failed]: {
    color: 'text-[#E5534B]',
    Icon: AlertCircle,
  },
  [NexusStatus.Planned]: {
    color: 'text-[#7C8B9E]',
    Icon: Clock,
  },
};

export const StatusText = memo(function StatusText({ status, className = '' }: StatusTextProps) {
  const entry = STATUS_STYLE[status] ?? {
    color: 'text-[#8B97A7]',
    Icon: CircleDashed,
  };
  const { color, Icon } = entry;

  return (
    <span
      className={`inline-flex items-center gap-1.5 text-xs font-medium whitespace-nowrap shrink-0 ${color} ${className}`}
    >
      <Icon
        className={`h-3.5 w-3.5 shrink-0 ${status === NexusStatus.Running ? 'animate-spin' : ''}`}
        aria-hidden="true"
      />
      <span>{status}</span>
    </span>
  );
});
