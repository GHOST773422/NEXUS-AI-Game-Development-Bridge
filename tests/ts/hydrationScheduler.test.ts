import { describe, expect, it } from 'vitest';
import { formatCachedLocalTime } from '../../src/services/formatCache';
import {
  ALL_HYDRATION_SCOPES,
  createHydrationCoalescer,
  HydrationScope,
  scopesForWebSocketEvent,
} from '../../src/services/hydrationScheduler';

describe('Hydration Scheduler & Format Cache', () => {
  it('routes WebSocket events strictly to affected REST scopes', () => {
    expect(scopesForWebSocketEvent('task.step_updated')).toEqual(['tasks']);
    expect(scopesForWebSocketEvent('bridge.status')).toEqual([
      'projects',
      'adapters',
      'engines',
      'tools',
      'mcp',
    ]);
    expect(scopesForWebSocketEvent('bridge.status')).not.toContain('diagnostics');
    expect(scopesForWebSocketEvent('engine.health')).toEqual(['engines', 'adapters']);
    expect(scopesForWebSocketEvent('engine.scene_changed')).toEqual(['engines', 'adapters']);
    expect(scopesForWebSocketEvent('error.diagnostic')).toEqual(['diagnostics']);
    expect(scopesForWebSocketEvent('engine.log')).toEqual([]);
    expect(scopesForWebSocketEvent(undefined)).toEqual([]);
    expect(ALL_HYDRATION_SCOPES).toHaveLength(8);
  });

  it('coalesces rapid burst triggers into a single deduplicated batch', async () => {
    const batches: HydrationScope[][] = [];
    const coalescer = createHydrationCoalescer(async (scopes) => {
      batches.push([...scopes]);
      return true;
    }, 20);

    const pending: Promise<boolean>[] = [];
    for (let i = 0; i < 15; i++) {
      pending.push(coalescer.schedule(['tasks']));
    }
    pending.push(coalescer.schedule(['engines', 'adapters', 'tasks']));

    const results = await Promise.all(pending);
    expect(results.every((ok) => ok === true)).toBe(true);
    expect(batches).toHaveLength(1);
    expect(batches[0].sort()).toEqual(['adapters', 'engines', 'tasks']);
  });

  it('serializes flushNow after an active in-flight batch and supports cancellation', async () => {
    const batches: HydrationScope[][] = [];
    let releaseFirst!: () => void;
    const firstGate = new Promise<void>((resolve) => {
      releaseFirst = resolve;
    });

    const coalescer = createHydrationCoalescer(async (scopes) => {
      batches.push([...scopes]);
      if (batches.length === 1) {
        await firstGate;
      }
      return true;
    }, 50);

    const first = coalescer.flushNow(['projects']);
    const second = coalescer.flushNow(['tasks']);

    await Promise.resolve();
    expect(batches).toHaveLength(1);

    releaseFirst();
    const [ok1, ok2] = await Promise.all([first, second]);
    expect(ok1).toBe(true);
    expect(ok2).toBe(true);
    expect(batches).toEqual([['projects'], ['tasks']]);

    const cancelledRun = coalescer.schedule(['diagnostics']);
    coalescer.cancel();
    expect(await cancelledRun).toBe(false);
  });

  it('caches formatted timestamps and stays bounded above 512 unique entries', () => {
    const sample = '2026-11-20T12:34:56.000Z';
    const first = formatCachedLocalTime(sample);
    expect(first).toBe(new Date(sample).toLocaleTimeString());
    expect(formatCachedLocalTime(sample)).toBe(first);

    for (let i = 0; i < 600; i++) {
      const iso = new Date(1700000000000 + i * 1000).toISOString();
      expect(formatCachedLocalTime(iso).length).toBeGreaterThan(0);
    }
    expect(formatCachedLocalTime(sample)).toBe(first);
  });
});
