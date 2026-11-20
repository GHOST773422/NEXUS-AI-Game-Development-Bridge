import { NEXUS_PROTOCOL_VERSION, WebSocketEventEnvelope, WebSocketEventType } from '../../sdk/ts';

export const WEBSOCKET_EVENT_TOPICS: WebSocketEventType[] = [
  'bridge.status',
  'engine.health',
  'engine.log',
  'engine.scene_changed',
  'task.step_updated',
  'error.diagnostic',
];

export function createWebSocketEvent<T>(
  type: WebSocketEventType,
  sequence: number,
  source: string,
  data: T
): WebSocketEventEnvelope<T> {
  return {
    type,
    protocolVersion: NEXUS_PROTOCOL_VERSION,
    sequence,
    timestamp: new Date().toISOString(),
    source,
    data,
  };
}
