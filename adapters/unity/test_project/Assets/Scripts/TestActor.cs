using UnityEngine;

namespace Nexus.TestProject
{
    /// <summary>
    /// Verification actor used by NEXUS Unity Editor integration tests to validate
    /// transform mutation, script inspection, and Play Mode execution.
    /// </summary>
    public sealed class TestActor : MonoBehaviour
    {
        [SerializeField] private float rotationSpeed = 45f;
        [SerializeField] private int health = 100;

        public int Health => health;

        private void Update()
        {
            transform.Rotate(0f, rotationSpeed * Time.deltaTime, 0f);
        }

        public void ApplyDamage(int amount)
        {
            health = Mathf.Max(0, health - Mathf.Max(0, amount));
        }
    }
}
