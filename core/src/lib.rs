//! Portable data-only MotionPack mathematical primitives.
//!
//! Milestone 0: keyframe interpolation + 2D affine transforms only.
//! This library does NOT yet load archives, evaluate IK, blend clips or render.
//! No platform graphics APIs, timers, dynamic scripting or dependencies.
use core::f64::consts::PI;

#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Affine {
    pub a: f64,
    pub b: f64,
    pub c: f64,
    pub d: f64,
    pub tx: f64,
    pub ty: f64,
}

impl Affine {
    pub const IDENTITY: Self = Self {
        a: 1.0, b: 0.0, c: 0.0, d: 1.0, tx: 0.0, ty: 0.0,
    };

    pub fn from_pose(x: f64, y: f64, rotation_deg: f64, scale: f64) -> Option<Self> {
        if ![x, y, rotation_deg, scale].iter().all(|n| n.is_finite()) {
            return None;
        }
        let radians = rotation_deg * PI / 180.0;
        let cos = radians.cos() * scale;
        let sin = radians.sin() * scale;
        let m = Self { a: cos, b: sin, c: -sin, d: cos, tx: x, ty: y };
        m.is_finite().then_some(m)
    }

    pub fn is_finite(&self) -> bool {
        [self.a, self.b, self.c, self.d, self.tx, self.ty]
            .iter().all(|n| n.is_finite())
    }

    pub fn compose(&self, child: &Self) -> Option<Self> {
        if !self.is_finite() || !child.is_finite() {
            return None;
        }
        let m = Self {
            a: self.a * child.a + self.c * child.b,
            b: self.b * child.a + self.d * child.b,
            c: self.a * child.c + self.c * child.d,
            d: self.b * child.c + self.d * child.d,
            tx: self.a * child.tx + self.c * child.ty + self.tx,
            ty: self.b * child.tx + self.d * child.ty + self.ty,
        };
        m.is_finite().then_some(m)
    }

    pub fn point(&self, x: f64, y: f64) -> Option<(f64, f64)> {
        if !self.is_finite() || !x.is_finite() || !y.is_finite() {
            return None;
        }
        let result = (self.a * x + self.c * y + self.tx,
                      self.b * x + self.d * y + self.ty);
        (result.0.is_finite() && result.1.is_finite()).then_some(result)
    }
}

/// Exactly matches evaluator.js smoothstep interpolation and edge behavior.
/// Inputs are finite and key times strictly ordered.
pub fn sample_segment(time: f64, before_time: f64, before_value: f64,
                      after_time: f64, after_value: f64) -> Option<f64> {
    if ![time, before_time, before_value, after_time, after_value]
        .iter().all(|n| n.is_finite()) || before_time >= after_time {
        return None;
    }
    if time <= before_time {
        return Some(before_value);
    }
    if time >= after_time {
        return Some(after_value);
    }
    let amount = ((time - before_time) / (after_time - before_time)).clamp(0.0, 1.0);
    let eased = amount * amount * (3.0 - 2.0 * amount);
    let result = before_value + (after_value - before_value) * eased;
    result.is_finite().then_some(result)
}

/// Native and WebAssembly compatible primitive; invalid inputs yield NaN.
/// Calling this alone does not load or execute a MotionPack archive.
#[no_mangle]
pub extern "C" fn mp_sample_segment(time: f64, before_time: f64, before_value: f64,
                                    after_time: f64, after_value: f64) -> f64 {
    sample_segment(time, before_time, before_value, after_time, after_value)
        .unwrap_or(f64::NAN)
}

/// Transform a point by a MotionPack pose using degrees and uniform scale.
#[no_mangle]
pub extern "C" fn mp_point_x(x: f64, y: f64, rotation_deg: f64, scale: f64,
                             point_x: f64, point_y: f64) -> f64 {
    Affine::from_pose(x, y, rotation_deg, scale)
        .and_then(|m| m.point(point_x, point_y))
        .map(|v| v.0).unwrap_or(f64::NAN)
}

#[no_mangle]
pub extern "C" fn mp_point_y(x: f64, y: f64, rotation_deg: f64, scale: f64,
                             point_x: f64, point_y: f64) -> f64 {
    Affine::from_pose(x, y, rotation_deg, scale)
        .and_then(|m| m.point(point_x, point_y))
        .map(|v| v.1).unwrap_or(f64::NAN)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn close(a: f64, b: f64) {
        assert!((a - b).abs() < 1.0e-10, "{a} != {b}");
    }

    #[test]
    fn interpolation_edges_and_smoothstep() {
        close(mp_sample_segment(0.0, 0.0, -2.2, 800.0, 0.0), -2.2);
        close(mp_sample_segment(200.0, 0.0, -2.2, 800.0, 0.0), -1.85625);
        close(mp_sample_segment(400.0, 0.0, -2.2, 800.0, 0.0), -1.1);
        close(mp_sample_segment(800.0, 0.0, -2.2, 800.0, 0.0), 0.0);
        close(mp_sample_segment(900.0, 0.0, -2.2, 800.0, 0.0), 0.0);
    }

    #[test]
    fn rejects_bad_values() {
        assert!(mp_sample_segment(f64::NAN, 0.0, 0.0, 1.0, 1.0).is_nan());
        assert!(mp_sample_segment(0.0, 1.0, 0.0, 1.0, 1.0).is_nan());
        assert!(mp_point_x(0.0, 0.0, f64::INFINITY, 1.0, 1.0, 1.0).is_nan());
    }

    #[test]
    fn affine_parent_and_child() {
        let parent = Affine::from_pose(10.0, 20.0, 90.0, 2.0).unwrap();
        let child = Affine::from_pose(3.0, 4.0, -90.0, 0.5).unwrap();
        let world = parent.compose(&child).unwrap();
        let point = world.point(2.0, -1.0).unwrap();
        close(point.0, 3.0);
        close(point.1, 25.0);
        close(world.a, 1.0);
        close(world.d, 1.0);
        close(Affine::IDENTITY.point(2.0, -1.0).unwrap().0, 2.0);
    }
}
