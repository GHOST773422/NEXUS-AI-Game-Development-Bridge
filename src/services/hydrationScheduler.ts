export type HydrationScope =
  'projects' | 'tasks' | 'tools' | 'adapters' | 'engines' | 'providers' | 'mcp' | 'diagnostics';

export const ALL_HYDRATION_SCOPES: readonly HydrationScope[] = [
  'projects',
  'tasks',
  'tools',
  'adapters',
  'engines',
  'providers',
  'mcp',
  'diagnostics',
];

/**
 * Maps a daemon WebSocket event type to only the REST slices actually affected,
 * eliminating redundant 8-way full hydrations (especially /diagnostics scans).
 */
export function scopesForWebSocketEvent(eventType: string | undefined): HydrationScope[] {
  if (!eventType) return [];
  switch (eventType) {
    case 'task.step_updated':
      return ['tasks'];
    case 'bridge.status':
      return ['projects', 'adapters', 'engines', 'tools', 'mcp'];
    case 'engine.health':
    case 'engine.scene_changed':
      return ['engines', 'adapters'];
    case 'error.diagnostic':
      return ['diagnostics'];
    default:
      return [];
  }
}

export interface HydrationCoalescer {
  schedule: (scopes: readonly HydrationScope[]) => Promise<boolean>;
  flushNow: (scopes: readonly HydrationScope[]) => Promise<boolean>;
  cancel: () => void;
}

/**
 * Coalesces rapid burst refresh triggers into minimal deduplicated network batches
 * and serializes overlapping in-flight refreshes.
 */
export function createHydrationCoalescer(
  runner: (scopes: readonly HydrationScope[]) => Promise<boolean>,
  coalesceMs = 120
): HydrationCoalescer {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let cancelled = false;
  let pendingScopes = new Set<HydrationScope>();
  let waiters: Array<(ok: boolean) => void> = [];
  let inFlight: Promise<boolean> | null = null;

  const resolveWaiters = (ok: boolean, batchWaiters: Array<(ok: boolean) => void>) => {
    for (const resolve of batchWaiters) {
      resolve(ok);
    }
  };

  const drain = async (): Promise<boolean> => {
    if (cancelled) {
      const stale = waiters;
      waiters = [];
      pendingScopes.clear();
      resolveWaiters(false, stale);
      return false;
    }

    let lastResult = true;
    while (pendingScopes.size > 0 && !cancelled) {
      const batchScopes = Array.from(pendingScopes);
      const batchWaiters = waiters;
      pendingScopes.clear();
      waiters = [];

      const runPromise = runner(batchScopes);
      inFlight = runPromise;
      try {
        lastResult = await runPromise;
      } finally {
        if (inFlight === runPromise) {
          inFlight = null;
        }
      }
      resolveWaiters(lastResult, batchWaiters);
    }
    return lastResult;
  };

  return {
    schedule(scopes) {
      if (cancelled || scopes.length === 0) {
        return Promise.resolve(false);
      }
      for (const s of scopes) {
        pendingScopes.add(s);
      }
      return new Promise<boolean>((resolve) => {
        waiters.push(resolve);
        if (timer !== null) return;
        timer = setTimeout(() => {
          timer = null;
          if (!inFlight) {
            void drain();
          }
        }, coalesceMs);
      });
    },

    flushNow(scopes) {
      if (cancelled || scopes.length === 0) {
        return Promise.resolve(false);
      }
      if (timer !== null) {
        clearTimeout(timer);
        timer = null;
      }
      for (const s of scopes) {
        pendingScopes.add(s);
      }
      if (inFlight) {
        return inFlight.then(() => drain());
      }
      return drain();
    },

    cancel() {
      cancelled = true;
      if (timer !== null) {
        clearTimeout(timer);
        timer = null;
      }
      const stale = waiters;
      waiters = [];
      pendingScopes.clear();
      resolveWaiters(false, stale);
    },
  };
}
