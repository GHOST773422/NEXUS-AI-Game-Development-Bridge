using System;
using System.Collections.Generic;

namespace Nexus.Bridge.Editor
{
    public sealed class NexusToolDescriptor
    {
        public string id = string.Empty;
        public string category = string.Empty;
        public string description = string.Empty;
        public string executionContext = "EditorMainThread";
        public string errorHandling = "JSON-RPC 2.0 error envelope with Unity state diagnostics";
        public string[] requiredPermissions = Array.Empty<string>();
        public Dictionary<string, object> inputSchema = new Dictionary<string, object>();
        public Dictionary<string, object> outputSchema = new Dictionary<string, object>();

        public Dictionary<string, object> ToDictionary()
        {
            return new Dictionary<string, object>
            {
                { "id", id },
                { "category", category },
                { "description", description },
                { "executionContext", executionContext },
                { "errorHandling", errorHandling },
                { "requiredPermissions", new List<object>(requiredPermissions) },
                { "inputSchema", inputSchema },
                { "outputSchema", outputSchema }
            };
        }
    }

    public sealed class NexusEngineHealth
    {
        public string engine = "Unity";
        public string unityVersion = string.Empty;
        public bool isCompiling;
        public bool isUpdating;
        public bool isPlaying;
        public bool mainThreadResponsive;
        public int listenerPort;
        public string timestamp = string.Empty;
    }

    public sealed class NexusRpcException : Exception
    {
        public int RpcCode { get; }
        public string ErrorCode { get; }
        public Dictionary<string, object> Details { get; }

        public NexusRpcException(
            int rpcCode,
            string errorCode,
            string message,
            Dictionary<string, object> details = null
        ) : base(message)
        {
            RpcCode = rpcCode;
            ErrorCode = errorCode;
            Details = details ?? new Dictionary<string, object>();
        }
    }

    public interface INexusEditorAdapter
    {
        NexusEngineHealth CheckHealth();
        IReadOnlyList<NexusToolDescriptor> DiscoverTools();
    }
}
