// Experimental Unity pose-frame adapter. No HTML, Canvas or JavaScript evaluation
// inside Unity. Feed it JSON frames produced by tools/sample_pose.py.
// Tested syntax by inspection only; Unity import/runtime tests are still needed.
using System;
using System.Collections.Generic;
using UnityEngine;

namespace MotionPack.Experimental
{
    [Serializable]
    public class PoseFrame
    {
        public string protocol;
        public int version;
        public string clip;
        public string variant;
        public float time_ms;
        public PoseNode[] nodes;
    }

    [Serializable]
    public class PoseLocal
    {
        public float x;
        public float y;
        public float rotation;
        public float scale;
        public float opacity = 1f;
    }

    [Serializable]
    public class PoseNode
    {
        public string id;
        public string parent;
        public string asset;
        public float z;
        public float width;
        public float height;
        public float[] anchor;
        public PoseLocal local;
        // World transform: [a, b, c, d, tx, ty] in MotionPack canvas pixels.
        public float[] world;
    }

    [Serializable]
    public class SpriteBinding
    {
        public string nodeId;
        // Assign a Unity SpriteRenderer and separately imported sprite.
        // This adapter does NOT extract archives or rasterize SVG assets.
        public SpriteRenderer renderer;
    }

    public sealed class MotionPackPoseAdapter : MonoBehaviour
    {
        [SerializeField] private TextAsset sampleFrame;
        [SerializeField] private SpriteBinding[] bindings = new SpriteBinding[0];
        [SerializeField] private float pixelsPerUnit = 100f;
        [SerializeField] private bool flipYAxis = true;

        private Dictionary<string, SpriteRenderer> map;

        private void Awake()
        {
            map = new Dictionary<string, SpriteRenderer>(StringComparer.Ordinal);
            if (bindings == null) return;
            foreach (var binding in bindings)
                if (binding != null && !string.IsNullOrEmpty(binding.nodeId) &&
                    binding.renderer != null)
                    map[binding.nodeId] = binding.renderer;
        }

        private void Start()
        {
            if (sampleFrame != null) ApplyFrame(sampleFrame.text);
        }

        public void ApplyFrame(string json)
        {
            if (string.IsNullOrEmpty(json))
                throw new ArgumentException("MotionPack pose JSON is required.");
            PoseFrame frame = JsonUtility.FromJson<PoseFrame>(json);
            if (frame == null || frame.protocol != "motionpack-pose" ||
                frame.version != 1 || frame.nodes == null)
                throw new ArgumentException("Unsupported MotionPack pose protocol.");
            if (pixelsPerUnit <= 0 || float.IsNaN(pixelsPerUnit) ||
                float.IsInfinity(pixelsPerUnit))
                throw new ArgumentException("pixelsPerUnit must be positive and finite.");

            int drawOrder = 0;
            foreach (PoseNode node in frame.nodes)
            {
                if (node == null || node.world == null || node.world.Length != 6)
                    throw new ArgumentException("Invalid MotionPack node transform.");
                SpriteRenderer target;
                if (!map.TryGetValue(node.id, out target)) { drawOrder++; continue; }
                var matrix = node.world;
                foreach (float value in matrix)
                    if (float.IsNaN(value) || float.IsInfinity(value))
                        throw new ArgumentException("Nonfinite MotionPack world transform.");
                float direction = flipYAxis ? -1f : 1f;
                float a = matrix[0], b = matrix[1], c = matrix[2], d = matrix[3];
                float scaleX = Mathf.Sqrt(a * a + b * b);
                float scaleY = Mathf.Sqrt(c * c + d * d);
                if (scaleX <= 0 || scaleY <= 0)
                    throw new ArgumentException("Degenerate pose matrix.");

                // IMPORTANT: sprite pivot must match the source node anchor;
                // renderers are root objects because transforms are already world-space.
                target.transform.position = new Vector3(
                    matrix[4] / pixelsPerUnit,
                    direction * matrix[5] / pixelsPerUnit,
                    -node.z * 0.001f);
                target.transform.rotation = Quaternion.Euler(
                    0f, 0f, direction * Mathf.Atan2(b, a) * Mathf.Rad2Deg);
                // SpriteRenderer dimensions are in Unity units and may differ
                // from the MotionPack node's declared logical width and height.
                Sprite sprite = target.sprite;
                if (sprite == null || sprite.rect.width <= 0 || sprite.rect.height <= 0)
                    throw new ArgumentException("Assign a sprite for every bound MotionPack node.");
                float spritePixelsPerUnit = sprite.pixelsPerUnit;
                float widthFactor = (node.width / pixelsPerUnit) /
                    (sprite.rect.width / spritePixelsPerUnit);
                float heightFactor = (node.height / pixelsPerUnit) /
                    (sprite.rect.height / spritePixelsPerUnit);
                target.transform.localScale = new Vector3(
                    scaleX * widthFactor, scaleY * heightFactor, 1f);
                // Use the frame's canonical z-order for overlapping layers.
                target.sortingOrder = drawOrder;
                float opacity = node.local == null ? 1f : node.local.opacity;
                Color color = target.color;
                color.a = Mathf.Clamp01(opacity);
                target.color = color;
                drawOrder++;
            }
        }
    }
}
