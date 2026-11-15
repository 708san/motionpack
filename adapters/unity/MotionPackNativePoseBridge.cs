// Experimental native MotionPack pose calculation bridge for Unity/C#.
// Source-only, not tested in Unity Editor. Native plugin must be built for
// the target Unity platform and registered in Unity's Plugin Inspector.
using System;
using System.Runtime.InteropServices;

namespace MotionPack.Experimental
{
    [StructLayout(LayoutKind.Sequential)]
    public struct NativeNode
    {
        public int Parent;
        public double X, Y, Rotation, Scale, Opacity;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct NativeVariant
    {
        public uint Node, Mask;
        public double X, Y, Rotation, Scale, Opacity;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct NativeKey
    {
        public double TimeMs, Value;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct NativeTrack
    {
        public uint Node, Property, KeyStart, KeyCount;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct NativeChain
    {
        public uint Upper, Lower;
        public double Length1, Length2, TargetX, TargetY, Bend, Weight;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct NativeIkTrack
    {
        public uint Chain, Axis, KeyStart, KeyCount;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct NativeTarget
    {
        public uint Chain;
        public double X, Y;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct NativeOutput
    {
        public double X, Y, Rotation, Scale, Opacity;
        public double A, B, C, D, Tx, Ty;
    }

    public static class MotionPackNativePoseBridge
    {
        // ABI: source is core/include/motionpack_core.h.
        // Supports trusted numeric scene data only; does NOT load .motionpack.
        [DllImport("motionpack_core", CallingConvention = CallingConvention.Cdecl,
            EntryPoint = "mp_scene_sample_v1")]
        private static extern int Evaluate(
            [In] NativeNode[] nodes, UIntPtr nodeCount,
            [In] NativeVariant[] variants, UIntPtr variantCount,
            [In] NativeTrack[] tracks, UIntPtr trackCount,
            [In] NativeKey[] keys, UIntPtr keyCount,
            [In] NativeChain[] chains, UIntPtr chainCount,
            [In] NativeIkTrack[] ikTracks, UIntPtr ikTrackCount,
            [In] NativeTarget[] targets, UIntPtr targetCount,
            double durationMs, uint loopFlag, double timeMs,
            [Out] NativeOutput[] output, UIntPtr outputCapacity,
            out double sampledMs);

        private static UIntPtr Size(int count)
        {
            return new UIntPtr(checked((uint)count));
        }

        public static int Sample(
            NativeNode[] nodes, NativeVariant[] variants,
            NativeTrack[] tracks, NativeKey[] keys, NativeChain[] chains,
            NativeIkTrack[] ikTracks, NativeTarget[] targets,
            double durationMs, bool loop, double timeMs,
            out NativeOutput[] output, out double sampledMs)
        {
            if (nodes == null) throw new ArgumentNullException(nameof(nodes));
            variants = variants ?? Array.Empty<NativeVariant>();
            tracks = tracks ?? Array.Empty<NativeTrack>();
            keys = keys ?? Array.Empty<NativeKey>();
            chains = chains ?? Array.Empty<NativeChain>();
            ikTracks = ikTracks ?? Array.Empty<NativeIkTrack>();
            targets = targets ?? Array.Empty<NativeTarget>();
            output = new NativeOutput[nodes.Length];
            return Evaluate(nodes, Size(nodes.Length),
                variants, Size(variants.Length),
                tracks, Size(tracks.Length),
                keys, Size(keys.Length),
                chains, Size(chains.Length),
                ikTracks, Size(ikTracks.Length),
                targets, Size(targets.Length),
                durationMs, loop ? 1u : 0u, timeMs,
                output, Size(output.Length), out sampledMs);
        }
    }
}
