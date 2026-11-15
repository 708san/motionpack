//! Pure, bounded, host-owned clip timeline evaluation.
//! Caller supplies already-validated animation data, never executable code.
//! This slice deliberately excludes IK, effects and graphical assets.
use crate::sample_segment;

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Keyframe {
    pub time_ms: f64,
    pub value: f64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Property {
    X,
    Y,
    Rotation,
    Scale,
    Opacity,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Pose {
    pub x: f64,
    pub y: f64,
    pub rotation: f64,
    pub scale: f64,
    pub opacity: f64,
}

impl Default for Pose {
    fn default() -> Self {
        Self { x: 0.0, y: 0.0, rotation: 0.0, scale: 1.0, opacity: 1.0 }
    }
}

impl Pose {
    fn valid(&self) -> bool {
        [self.x, self.y, self.rotation, self.scale, self.opacity]
            .iter().all(|v| v.is_finite())
    }

    fn assign(&mut self, property: Property, value: f64) {
        match property {
            Property::X => self.x = value,
            Property::Y => self.y = value,
            Property::Rotation => self.rotation = value,
            Property::Scale => self.scale = value,
            Property::Opacity => self.opacity = value,
        }
    }

    fn overlay(&mut self, other: &PoseOverride) {
        if let Some(v) = other.x { self.x = v; }
        if let Some(v) = other.y { self.y = v; }
        if let Some(v) = other.rotation { self.rotation = v; }
        if let Some(v) = other.scale { self.scale = v; }
        if let Some(v) = other.opacity { self.opacity = v; }
    }
}

#[derive(Debug, Clone, Copy, Default)]
pub struct PoseOverride {
    pub x: Option<f64>,
    pub y: Option<f64>,
    pub rotation: Option<f64>,
    pub scale: Option<f64>,
    pub opacity: Option<f64>,
}

#[derive(Debug, Clone)]
pub struct Track {
    pub node_index: usize,
    pub property: Property,
    pub keys: Vec<Keyframe>,
}

#[derive(Debug, Clone, Copy)]
pub struct VariantNode {
    pub node_index: usize,
    pub values: PoseOverride,
}

#[derive(Debug, Clone)]
pub struct Clip {
    pub duration_ms: f64,
    pub looping: bool,
    pub tracks: Vec<Track>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TimelineError {
    InvalidTime,
    InvalidDuration,
    InvalidKeyframes,
    TooManyItems,
    UnknownNode,
    NonFinitePose,
}

/// Consistent with runtime/evaluator.js: only a true explicit loop flag wraps.
/// Non-looping clips clamp to their duration.
pub fn clip_time(duration_ms: f64, looping: bool, requested_ms: f64) -> Result<f64, TimelineError> {
    if !duration_ms.is_finite() || duration_ms <= 0.0 {
        return Err(TimelineError::InvalidDuration);
    }
    if !requested_ms.is_finite() || requested_ms < 0.0 {
        return Err(TimelineError::InvalidTime);
    }
    Ok(if looping { requested_ms.rem_euclid(duration_ms) } else { requested_ms.min(duration_ms) })
}

/// Complete scalar timeline sampling from an arbitrary length, strictly ordered
/// track. The host must validate keys and input sizes before calling.
pub fn sample_track(keys: &[Keyframe], time_ms: f64) -> Result<f64, TimelineError> {
    if keys.is_empty() || keys.len() > 4096 || !time_ms.is_finite() {
        return Err(TimelineError::InvalidKeyframes);
    }
    let mut previous = &keys[0];
    if !previous.time_ms.is_finite() || !previous.value.is_finite() || previous.time_ms < 0.0 {
        return Err(TimelineError::InvalidKeyframes);
    }
    // Check the entire input first: reject a corrupt final key even if sampling
    // an earlier key, so no invalid manifest can silently sample successfully.
    for next in &keys[1..] {
        if !next.time_ms.is_finite() || !next.value.is_finite() ||
            next.time_ms <= previous.time_ms {
            return Err(TimelineError::InvalidKeyframes);
        }
        previous = next;
    }
    if time_ms <= keys[0].time_ms {
        return Ok(keys[0].value);
    }
    for pair in keys.windows(2) {
        if time_ms <= pair[1].time_ms {
            return sample_segment(time_ms, pair[0].time_ms, pair[0].value,
                pair[1].time_ms, pair[1].value)
                .ok_or(TimelineError::InvalidKeyframes);
        }
    }
    Ok(keys[keys.len() - 1].value)
}

/// Applies sparse variant overrides first, then tracks in source order,
/// mirroring JS evaluator semantics. It does not perform inverse kinematics (IK).
pub fn sample_clip(base_nodes: &[Pose], variant: &[VariantNode],
    clip: &Clip, requested_ms: f64) -> Result<(f64, Vec<Pose>), TimelineError> {
    if base_nodes.len() > 4096 || variant.len() > 4096 || clip.tracks.len() > 4096 {
        return Err(TimelineError::TooManyItems);
    }
    if base_nodes.iter().any(|p| !p.valid()) {
        return Err(TimelineError::NonFinitePose);
    }
    let time = clip_time(clip.duration_ms, clip.looping, requested_ms)?;
    // Do not mutate caller-provided base nodes, even on an invalid track.
    let mut nodes = base_nodes.to_vec();
    for overlay in variant {
        let node = nodes.get_mut(overlay.node_index).ok_or(TimelineError::UnknownNode)?;
        node.overlay(&overlay.values);
        if !node.valid() {
            return Err(TimelineError::NonFinitePose);
        }
    }
    for track in &clip.tracks {
        let node = nodes.get_mut(track.node_index).ok_or(TimelineError::UnknownNode)?;
        let value = sample_track(&track.keys, time)?;
        node.assign(track.property, value);
        if !node.valid() {
            return Err(TimelineError::NonFinitePose);
        }
    }
    Ok((time, nodes))
}

#[no_mangle]
pub extern "C" fn mp_clip_time(duration_ms: f64, looping_flag: i32, requested_ms: f64) -> f64 {
    if looping_flag != 0 && looping_flag != 1 {
        return f64::NAN;
    }
    clip_time(duration_ms, looping_flag == 1, requested_ms)
        .unwrap_or(f64::NAN)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn close(a: f64, b: f64) { assert!((a-b).abs() < 1e-9, "{a} != {b}"); }
    fn key(t: f64, v: f64) -> Keyframe { Keyframe {time_ms:t,value:v} }

    #[test]
    fn looping_and_clamped_time() {
        close(clip_time(1000.0, true, 1200.0).unwrap(),200.0);
        close(clip_time(1000.0, true, 1000.0).unwrap(),0.0);
        close(clip_time(1000.0, false, 1200.0).unwrap(),1000.0);
        assert_eq!(clip_time(0.0, true, 0.0),Err(TimelineError::InvalidDuration));
        assert_eq!(clip_time(1000.0, false, -1.0),Err(TimelineError::InvalidTime));
        assert!(mp_clip_time(1000.0, 2, 1.0).is_nan());
    }

    #[test]
    fn full_track_sampling_and_bad_keys() {
        let keys = [key(0.0,620.0),key(1200.0,608.0),key(2400.0,620.0)];
        close(sample_track(&keys,0.0).unwrap(),620.0);
        close(sample_track(&keys,600.0).unwrap(),614.0);
        close(sample_track(&keys,1800.0).unwrap(),614.0);
        close(sample_track(&keys,2500.0).unwrap(),620.0);
        assert_eq!(sample_track(&[key(0.0,0.0),key(0.0,1.0)],0.0),
                   Err(TimelineError::InvalidKeyframes));
        assert_eq!(sample_track(&[key(0.0,0.0),key(1.0,f64::NAN)],0.0),
                   Err(TimelineError::InvalidKeyframes));
        assert_eq!(sample_track(&[],0.0),Err(TimelineError::InvalidKeyframes));
    }

    #[test]
    fn sparse_variant_then_tracks_and_no_mutation() {
        let base = vec![Pose::default(),Pose { y:3.0, ..Pose::default() }];
        let variant = [VariantNode {node_index:0,values:PoseOverride {
            x:Some(33.0),rotation:Some(10.0), ..PoseOverride::default()
        }}];
        let clip = Clip {duration_ms:1000.0,looping:true,tracks:vec![
            Track {node_index:0,property:Property::Rotation,
                   keys:vec![key(0.0,0.0),key(1000.0,90.0)]},
            Track {node_index:1,property:Property::Opacity,
                   keys:vec![key(0.0,0.5),key(1000.0,1.0)]},
        ]};
        let (time, result) = sample_clip(&base,&variant,&clip,500.0).unwrap();
        close(time,500.0);
        close(result[0].x,33.0);
        close(result[0].rotation,45.0);
        close(result[1].y,3.0);
        close(result[1].opacity,0.75);
        close(base[0].x,0.0);
        assert_eq!(sample_clip(&base,&[VariantNode {
            node_index:9,values:PoseOverride::default()
        }],&clip,0.0).unwrap_err(),TimelineError::UnknownNode);
    }

    #[test]
    fn duplicate_tracks_follow_source_order() {
        let base=[Pose::default()];
        let clip=Clip {duration_ms:1000.0,looping:false,tracks:vec![
            Track {node_index:0,property:Property::X,
                   keys:vec![key(0.0,0.0),key(1000.0,100.0)]},
            Track {node_index:0,property:Property::X,
                   keys:vec![key(0.0,11.0),key(1000.0,11.0)]}
        ]};
        close(sample_clip(&base,&[],&clip,500.0).unwrap().1[0].x,11.0);
    }
}
