const MAX_TIME_CACHE_ENTRIES = 512;
const localTimeCache = new Map<string, string>();

/**
 * Formats an ISO timestamp via toLocaleTimeString once per unique value,
 * preventing repeated Intl formatter calls across re-renders of long activity tables.
 */
export function formatCachedLocalTime(isoTimestamp: string): string {
  const existing = localTimeCache.get(isoTimestamp);
  if (existing !== undefined) {
    return existing;
  }
  const formatted = new Date(isoTimestamp).toLocaleTimeString();
  if (localTimeCache.size >= MAX_TIME_CACHE_ENTRIES) {
    localTimeCache.clear();
  }
  localTimeCache.set(isoTimestamp, formatted);
  return formatted;
}
