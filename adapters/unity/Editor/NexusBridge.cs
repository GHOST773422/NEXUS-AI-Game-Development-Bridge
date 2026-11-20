#if UNITY_EDITOR
using System.Collections.Generic;

namespace Nexus.Bridge.Editor
{
    /// <summary>
    /// Facade implementing INexusEditorAdapter delegating to NexusUnityBridgeEntrypoint.
    /// </summary>
    public sealed class NexusBridge : INexusEditorAdapter
    {
        public NexusEngineHealth CheckHealth()
        {
            return NexusUnityBridgeEntrypoint.CheckHealth();
        }

        public IReadOnlyList<NexusToolDescriptor> DiscoverTools()
        {
            return NexusUnityBridgeEntrypoint.DiscoverTools();
        }
    }
}
#endif
