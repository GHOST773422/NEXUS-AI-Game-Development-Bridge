#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;

namespace Nexus.Bridge.Editor.Tests
{
    /// <summary>
    /// EditMode integration tests designed to run inside a real Unity Editor Test Runner on Windows 10/11.
    /// Verifies actual Unity scene, GameObject, Transform, Component, AssetDatabase, Build, and safety guard behavior.
    /// </summary>
    public sealed class NexusUnityIntegrationTests
    {
        private readonly List<GameObject> _createdObjects = new List<GameObject>();
        private readonly List<string> _createdAssets = new List<string>();

        [TearDown]
        public void TearDown()
        {
            foreach (GameObject go in _createdObjects)
            {
                if (go != null)
                {
                    Undo.DestroyObjectImmediate(go);
                }
            }
            _createdObjects.Clear();

            foreach (string assetPath in _createdAssets)
            {
                if (!string.IsNullOrEmpty(AssetDatabase.AssetPathToGUID(assetPath)))
                {
                    AssetDatabase.DeleteAsset(assetPath);
                }
            }
            _createdAssets.Clear();
        }

        [Test]
        public void CreateTransformManageComponentAndInspectObjectInRealScene()
        {
            var createResult = NexusUnityHandlers.CreateObject(new Dictionary<string, object>
            {
                { "name", "NexusVerificationCube" },
                { "primitiveType", "Cube" },
                { "position", new Dictionary<string, object> { { "x", 2.0 }, { "y", 3.0 }, { "z", 4.0 } } }
            });

            var goDict = createResult["gameObject"] as Dictionary<string, object>;
            Assert.IsNotNull(goDict);
            int instanceId = Convert.ToInt32(goDict["instanceId"]);

            GameObject liveObj = EditorUtility.InstanceIDToObject(instanceId) as GameObject;
            Assert.IsNotNull(liveObj);
            _createdObjects.Add(liveObj);

            NexusUnityHandlers.TransformObject(new Dictionary<string, object>
            {
                { "instanceId", instanceId },
                { "localScale", new Dictionary<string, object> { { "x", 2.0 }, { "y", 2.0 }, { "z", 2.0 } } }
            });
            Assert.AreEqual(2f, liveObj.transform.localScale.x, 0.001f);

            NexusUnityHandlers.ManageComponent(new Dictionary<string, object>
            {
                { "instanceId", instanceId },
                { "action", "add" },
                { "componentType", "Rigidbody" }
            });
            Assert.IsNotNull(liveObj.GetComponent<Rigidbody>());

            NexusUnityHandlers.ManageComponent(new Dictionary<string, object>
            {
                { "instanceId", instanceId },
                { "action", "set_property" },
                { "componentType", "Rigidbody" },
                { "propertyName", "m_UseGravity" },
                { "value", false }
            });
            Assert.IsFalse(liveObj.GetComponent<Rigidbody>().useGravity);
        }

        [Test]
        public void ScriptPathSandboxRejectsTraversalAndExternalPaths()
        {
            Assert.Throws<NexusRpcException>(() =>
                NexusUnityHandlers.CreateScript(new Dictionary<string, object>
                {
                    { "assetPath", "../OutsideAssets.cs" },
                    { "content", "public class Bad {}" }
                })
            );

            Assert.Throws<NexusRpcException>(() =>
                NexusUnityHandlers.CreateScript(new Dictionary<string, object>
                {
                    { "assetPath", "Assets/NotCSharp.txt" },
                    { "content", "plain text" }
                })
            );
        }

        [Test]
        public void CreateModifyAndInspectScriptInRealAssetDatabase()
        {
            string testFolder = "Assets/NexusTempVerification";
            if (!AssetDatabase.IsValidFolder(testFolder))
            {
                AssetDatabase.CreateFolder("Assets", "NexusTempVerification");
            }
            string scriptPath = $"{testFolder}/NexusSampleComponent.cs";
            _createdAssets.Add(scriptPath);
            _createdAssets.Add(testFolder);

            var created = NexusUnityHandlers.CreateScript(new Dictionary<string, object>
            {
                { "assetPath", scriptPath },
                { "content", "using UnityEngine;\npublic class NexusSampleComponent : MonoBehaviour { public int Value = 1; }\n" },
                { "overwrite", true }
            });
            Assert.AreEqual(true, created["created"]);
            Assert.IsTrue(File.Exists(Path.Combine(NexusUnityHandlers.GetProjectRootPath(), scriptPath)));

            var modified = NexusUnityHandlers.ModifyScript(new Dictionary<string, object>
            {
                { "assetPath", scriptPath },
                { "searchText", "public int Value = 1;" },
                { "replaceText", "public int Value = 42;" }
            });
            Assert.AreEqual(true, modified["modified"]);
        }

        [Test]
        public void BuildStatusCompilationAndEditorStateReportRealUnityState()
        {
            var editorState = NexusUnityHandlers.GetEditorState();
            Assert.AreEqual(Application.unityVersion, editorState["unityVersion"]);

            var buildStatus = NexusUnityHandlers.GetBuildStatus();
            Assert.IsTrue(buildStatus.ContainsKey("activeBuildTarget"));
            Assert.IsTrue(buildStatus.ContainsKey("buildScenes"));
        }
    }
}
#endif
