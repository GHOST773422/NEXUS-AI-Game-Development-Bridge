#if UNITY_EDITOR
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEditor;

namespace Nexus.Bridge.Editor
{
    /// <summary>
    /// Loopback TCP NDJSON JSON-RPC 2.0 server implementing all 11 UniversalEngineAdapter operations.
    /// </summary>
    public sealed class NexusUnityTcpServer
    {
        private readonly int _port;
        private readonly ConcurrentDictionary<string, ClientSession> _clients = new ConcurrentDictionary<string, ClientSession>();
        private TcpListener _listener;
        private CancellationTokenSource _cts;

        public int Port => _port;
        public int ActiveClientCount => _clients.Count;
        public bool IsListening => _listener != null && _cts != null && !_cts.IsCancellationRequested;

        public NexusUnityTcpServer(int port)
        {
            _port = port;
        }

        public void Start()
        {
            if (IsListening) return;
            _cts = new CancellationTokenSource();
            _listener = new TcpListener(IPAddress.Loopback, _port);
            _listener.Start();
            NexusUnityStateTracker.OnEditorNotification += BroadcastNotification;
            _ = AcceptLoopAsync(_cts.Token);
        }

        public void Stop()
        {
            NexusUnityStateTracker.OnEditorNotification -= BroadcastNotification;
            try
            {
                _cts?.Cancel();
            }
            catch
            {
            }
            try
            {
                _listener?.Stop();
            }
            catch
            {
            }
            foreach (var kvp in _clients)
            {
                kvp.Value.Dispose();
            }
            _clients.Clear();
            _listener = null;
        }

        private async Task AcceptLoopAsync(CancellationToken token)
        {
            while (!token.IsCancellationRequested && _listener != null)
            {
                try
                {
                    TcpClient tcpClient = await _listener.AcceptTcpClientAsync().ConfigureAwait(false);
                    var session = new ClientSession(tcpClient, _port);
                    _clients[session.SessionId] = session;
                    _ = HandleClientAsync(session, token);
                }
                catch (ObjectDisposedException)
                {
                    break;
                }
                catch (SocketException)
                {
                    if (token.IsCancellationRequested) break;
                    await Task.Delay(100, token).ConfigureAwait(false);
                }
                catch
                {
                    if (token.IsCancellationRequested) break;
                }
            }
        }

        private async Task HandleClientAsync(ClientSession session, CancellationToken token)
        {
            try
            {
                using var reader = new StreamReader(session.Stream, Encoding.UTF8, detectEncodingFromByteOrderMarks: false, bufferSize: 8192, leaveOpen: true);
                while (!token.IsCancellationRequested && session.Tcp.Connected)
                {
                    string line = await reader.ReadLineAsync().ConfigureAwait(false);
                    if (line == null) break;
                    if (string.IsNullOrWhiteSpace(line)) continue;

                    object parsed = NexusSimpleJson.Deserialize(line);
                    if (!(parsed is Dictionary<string, object> msg)) continue;

                    object reqId = msg.TryGetValue("id", out object idObj) ? idObj : null;
                    string method = msg.TryGetValue("method", out object mObj) ? Convert.ToString(mObj, CultureInfo.InvariantCulture) : string.Empty;
                    Dictionary<string, object> rpcParams = msg.TryGetValue("params", out object pObj) && pObj is Dictionary<string, object> dict
                        ? dict
                        : new Dictionary<string, object>();

                    string responseJson = await DispatchRpcAsync(session, reqId, method, rpcParams).ConfigureAwait(false);
                    if (!string.IsNullOrEmpty(responseJson))
                    {
                        await session.SendLineAsync(responseJson).ConfigureAwait(false);
                    }
                }
            }
            catch
            {
                // Clean disconnect or socket cancellation.
            }
            finally
            {
                _clients.TryRemove(session.SessionId, out _);
                session.Dispose();
            }
        }

        private async Task<string> DispatchRpcAsync(
            ClientSession session,
            object reqId,
            string method,
            Dictionary<string, object> rpcParams
        )
        {
            try
            {
                Dictionary<string, object> result = await InvokeMethodOnMainThreadAsync(session, method, rpcParams).ConfigureAwait(false);
                if (reqId == null) return string.Empty;
                return NexusSimpleJson.Serialize(new Dictionary<string, object>
                {
                    { "jsonrpc", "2.0" },
                    { "id", reqId },
                    { "result", result }
                });
            }
            catch (NexusRpcException rpcEx)
            {
                if (reqId == null) return string.Empty;
                return NexusSimpleJson.Serialize(new Dictionary<string, object>
                {
                    { "jsonrpc", "2.0" },
                    { "id", reqId },
                    { "error", new Dictionary<string, object>
                        {
                            { "code", rpcEx.RpcCode },
                            { "message", rpcEx.Message },
                            { "data", new Dictionary<string, object>
                                {
                                    { "errorCode", rpcEx.ErrorCode },
                                    { "details", rpcEx.Details }
                                }
                            }
                        }
                    }
                });
            }
            catch (Exception ex)
            {
                if (reqId == null) return string.Empty;
                return NexusSimpleJson.Serialize(new Dictionary<string, object>
                {
                    { "jsonrpc", "2.0" },
                    { "id", reqId },
                    { "error", new Dictionary<string, object>
                        {
                            { "code", -32000 },
                            { "message", ex.Message },
                            { "data", new Dictionary<string, object>
                                {
                                    { "exceptionType", ex.GetType().FullName }
                                }
                            }
                        }
                    }
                });
            }
        }

        private Task<Dictionary<string, object>> InvokeMethodOnMainThreadAsync(
            ClientSession session,
            string method,
            Dictionary<string, object> rpcParams
        )
        {
            switch (method)
            {
                case "getEngineInfo":
                    return NexusMainThreadDispatcher.InvokeAsync(() => NexusUnityHandlers.GetEngineInfo(_port));

                case "discoverProjects":
                    return NexusMainThreadDispatcher.InvokeAsync(() => NexusUnityHandlers.DiscoverProjects(_port));

                case "connect":
                    session.Connected = true;
                    return NexusMainThreadDispatcher.InvokeAsync(() =>
                    {
                        var info = NexusUnityHandlers.GetEngineInfo(_port);
                        return new Dictionary<string, object>
                        {
                            { "connected", true },
                            { "isTestAdapter", false },
                            { "sessionId", session.SessionId },
                            { "protocolVersion", "1.0.0" },
                            { "projectId", info["projectId"] },
                            { "unityVersion", info["engineVersion"] },
                            { "timestamp", DateTime.UtcNow.ToString("O") }
                        };
                    });

                case "disconnect":
                    session.Connected = false;
                    session.SubscribedTopics.Clear();
                    return Task.FromResult(new Dictionary<string, object>
                    {
                        { "disconnected", true },
                        { "sessionId", session.SessionId }
                    });

                case "getCapabilities":
                    return Task.FromResult(new Dictionary<string, object>
                    {
                        { "isTestAdapter", false },
                        { "capabilities", new List<object>
                            {
                                "engine.info",
                                "project.discover",
                                "editor.state",
                                "scene.hierarchy",
                                "object.inspect",
                                "object.create",
                                "object.delete",
                                "object.transform",
                                "component.manage",
                                "script.create",
                                "script.modify",
                                "asset.database",
                                "asset.import",
                                "scene.save",
                                "compilation.monitor",
                                "console.logs",
                                "playmode.control",
                                "screenshot.capture",
                                "build.status"
                            }
                        }
                    });

                case "listTools":
                    var serializedTools = new List<object>();
                    foreach (NexusToolDescriptor tool in NexusUnityToolRegistry.BuildToolCatalog())
                    {
                        serializedTools.Add(tool.ToDictionary());
                    }
                    return Task.FromResult(new Dictionary<string, object>
                    {
                        { "isTestAdapter", false },
                        { "tools", serializedTools }
                    });

                case "executeTool":
                    string toolId = rpcParams.TryGetValue("toolId", out object tObj) ? Convert.ToString(tObj, CultureInfo.InvariantCulture) : string.Empty;
                    string projectId = rpcParams.TryGetValue("projectId", out object projObj) ? Convert.ToString(projObj, CultureInfo.InvariantCulture) : string.Empty;
                    string reqId = rpcParams.TryGetValue("requestId", out object ridObj) ? Convert.ToString(ridObj, CultureInfo.InvariantCulture) : string.Empty;
                    Dictionary<string, object> args = rpcParams.TryGetValue("arguments", out object aObj) && aObj is Dictionary<string, object> aDict
                        ? aDict
                        : new Dictionary<string, object>();

                    return NexusMainThreadDispatcher.InvokeAsync(() =>
                        NexusUnityToolRegistry.DispatchMainThreadTool(toolId, projectId, reqId, args));

                case "getProjectState":
                    return NexusMainThreadDispatcher.InvokeAsync(() => NexusUnityHandlers.GetEditorState());

                case "subscribeEvents":
                    var topics = new List<string>();
                    if (rpcParams.TryGetValue("topics", out object topicsObj) && topicsObj is List<object> tList)
                    {
                        foreach (object t in tList)
                        {
                            string s = Convert.ToString(t, CultureInfo.InvariantCulture);
                            if (!string.IsNullOrEmpty(s)) topics.Add(s);
                        }
                    }
                    session.SetSubscriptions(topics);
                    return Task.FromResult(new Dictionary<string, object>
                    {
                        { "subscribed", true },
                        { "topics", new List<object>(topics) },
                        { "isTestAdapter", false }
                    });

                case "captureScreenshot":
                    return NexusMainThreadDispatcher.InvokeAsync(() => NexusUnityHandlers.CaptureScreenshot(rpcParams));

                case "healthCheck":
                    return NexusMainThreadDispatcher.InvokeAsync(() => new Dictionary<string, object>
                    {
                        { "responsive", true },
                        { "connected", session.Connected },
                        { "isTestAdapter", false },
                        { "isCompiling", EditorApplication.isCompiling },
                        { "isUpdating", EditorApplication.isUpdating },
                        { "isPlaying", EditorApplication.isPlaying },
                        { "listenerPort", _port },
                        { "sessionId", session.SessionId },
                        { "timestamp", DateTime.UtcNow.ToString("O") }
                    });

                default:
                    throw new NexusRpcException(-32601, "NEXUS_METHOD_NOT_FOUND", $"Method '{method}' is not implemented.");
            }
        }

        private void BroadcastNotification(string rpcMethod, Dictionary<string, object> parameters)
        {
            if (_clients.IsEmpty) return;
            string frame = NexusSimpleJson.Serialize(new Dictionary<string, object>
            {
                { "jsonrpc", "2.0" },
                { "method", rpcMethod },
                { "params", parameters }
            });

            foreach (var kvp in _clients)
            {
                ClientSession session = kvp.Value;
                if (session.SubscribedTopics.Count > 0)
                {
                    _ = session.SendLineAsync(frame);
                }
            }
        }

        private sealed class ClientSession : IDisposable
        {
            private readonly SemaphoreSlim _writeLock = new SemaphoreSlim(1, 1);

            public string SessionId { get; } = $"unity-{Guid.NewGuid().ToString("N").Substring(0, 10)}";
            public TcpClient Tcp { get; }
            public NetworkStream Stream { get; }
            public int Port { get; }
            public bool Connected { get; set; }
            public HashSet<string> SubscribedTopics { get; } = new HashSet<string>(StringComparer.Ordinal);

            public ClientSession(TcpClient tcp, int port)
            {
                Tcp = tcp;
                Stream = tcp.GetStream();
                Port = port;
            }

            public void SetSubscriptions(IEnumerable<string> topics)
            {
                lock (SubscribedTopics)
                {
                    SubscribedTopics.Clear();
                    foreach (string topic in topics)
                    {
                        SubscribedTopics.Add(topic);
                    }
                }
            }

            public async Task SendLineAsync(string jsonLine)
            {
                byte[] bytes = Encoding.UTF8.GetBytes(jsonLine + "\n");
                await _writeLock.WaitAsync().ConfigureAwait(false);
                try
                {
                    if (Tcp.Connected)
                    {
                        await Stream.WriteAsync(bytes, 0, bytes.Length).ConfigureAwait(false);
                        await Stream.FlushAsync().ConfigureAwait(false);
                    }
                }
                catch
                {
                    // Drop dead client gracefully.
                }
                finally
                {
                    _writeLock.Release();
                }
            }

            public void Dispose()
            {
                try { Stream.Dispose(); } catch { }
                try { Tcp.Close(); } catch { }
                _writeLock.Dispose();
            }
        }
    }
}
#endif
