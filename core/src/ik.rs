//! Deterministic two-bone inverse kinematics (IK) for MotionPack.
//! Numeric inputs only; the host resolves parent transforms and supplies a
//! validated target in the same coordinate system as the origin.
use core::f64::consts::PI;

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct IkSolution {
    pub upper_deg: f64,
    pub lower_deg: f64,
    pub elbow: (f64, f64),
    pub hand: (f64, f64),
    pub reached: bool,
    pub clamped_distance: f64,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum IkError {
    InvalidParameters,
    NumericOverflow,
}

/// Mirrors runtime/rig.js solveTwoBone's 1e-5 reach clamp and sign of bend.
/// For targets at the origin, direction defaults to zero degrees.
pub fn solve_two_bone(origin: (f64, f64), target: (f64, f64),
    length1: f64, length2: f64, bend: f64) -> Result<IkSolution, IkError> {
    if ![origin.0, origin.1, target.0, target.1, length1, length2, bend]
        .iter().all(|v| v.is_finite()) || length1 <= 0.0 || length2 <= 0.0 {
        return Err(IkError::InvalidParameters);
    }
    let dx = target.0 - origin.0;
    let dy = target.1 - origin.1;
    let raw = dx.hypot(dy);
    if ![dx, dy, raw].iter().all(|v| v.is_finite()) {
        return Err(IkError::NumericOverflow);
    }
    // The explicit max(min(...)) order is deliberate: match JavaScript clamp.
    let low = (length1 - length2).abs() + 1e-5;
    let high = length1 + length2 - 1e-5;
    let distance = raw.min(high).max(low);
    let dir = if raw > 1e-10 { dy.atan2(dx) } else { 0.0 };
    let numerator = length1.powi(2) + distance.powi(2) - length2.powi(2);
    let denominator = 2.0 * length1 * distance;
    if !numerator.is_finite() || !denominator.is_finite() || denominator == 0.0 {
        return Err(IkError::NumericOverflow);
    }
    let cosine = numerator / denominator;
    if !cosine.is_finite() {
        return Err(IkError::NumericOverflow);
    }
    let alpha = cosine.clamp(-1.0, 1.0).acos();
    let a = dir + if bend >= 0.0 { alpha } else { -alpha };
    let elbow = (origin.0 + length1 * a.cos(), origin.1 + length1 * a.sin());
    let b = (origin.1 + distance * dir.sin() - elbow.1)
        .atan2(origin.0 + distance * dir.cos() - elbow.0);
    let hand = (elbow.0 + length2 * b.cos(), elbow.1 + length2 * b.sin());
    let upper_deg = a * 180.0 / PI;
    let lower_deg = (b - a) * 180.0 / PI;
    if ![upper_deg, lower_deg, elbow.0, elbow.1, hand.0, hand.1, distance]
        .iter().all(|v| v.is_finite()) {
        return Err(IkError::NumericOverflow);
    }
    Ok(IkSolution {
        upper_deg, lower_deg, elbow, hand,
        reached: (raw - distance).abs() < 0.01,
        clamped_distance: distance,
    })
}

/// Applies the existing runtime's finite-weight blend to authored rotations.
pub fn weighted_rotations(solution: IkSolution, weight: f64,
    original_upper_deg: f64, original_lower_deg: f64) -> Result<(f64, f64), IkError> {
    if ![weight, original_upper_deg, original_lower_deg]
        .iter().all(|v| v.is_finite()) {
        return Err(IkError::InvalidParameters);
    }
    let w = weight.clamp(0.0, 1.0);
    let upper = original_upper_deg * (1.0 - w) + solution.upper_deg * w;
    let lower = original_lower_deg * (1.0 - w) + solution.lower_deg * w;
    if !upper.is_finite() || !lower.is_finite() {
        return Err(IkError::NumericOverflow);
    }
    Ok((upper, lower))
}

/// Minimal number-only ABI for native callers and WebAssembly.
#[no_mangle]
pub extern "C" fn mp_ik_upper_deg(ox: f64, oy: f64, tx: f64, ty: f64,
    length1: f64, length2: f64, bend: f64) -> f64 {
    solve_two_bone((ox, oy), (tx, ty), length1, length2, bend)
        .map(|solution| solution.upper_deg).unwrap_or(f64::NAN)
}

#[no_mangle]
pub extern "C" fn mp_ik_lower_deg(ox: f64, oy: f64, tx: f64, ty: f64,
    length1: f64, length2: f64, bend: f64) -> f64 {
    solve_two_bone((ox, oy), (tx, ty), length1, length2, bend)
        .map(|solution| solution.lower_deg).unwrap_or(f64::NAN)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn near(a: f64, b: f64) { assert!((a-b).abs() <= 1e-7, "{a} != {b}"); }

    #[test]
    fn reachable_and_clamped_targets() {
        let s = solve_two_bone((0.0, 0.0), (150.0, 20.0), 115.0, 105.0, -1.0).unwrap();
        assert!(s.reached);
        near(s.hand.0,150.0);
        near(s.hand.1,20.0);
        let far = solve_two_bone((0.0,0.0),(1000.0,0.0),115.0,105.0,-1.0).unwrap();
        assert!(!far.reached);
        near(far.clamped_distance, 219.99999);
    }

    #[test]
    fn bends_and_weighted_rotations() {
        let left = solve_two_bone((0.0,0.0),(120.0,0.0),100.0,90.0,1.0).unwrap();
        let right = solve_two_bone((0.0,0.0),(120.0,0.0),100.0,90.0,-1.0).unwrap();
        assert!(left.upper_deg > 0.0 && right.upper_deg < 0.0);
        let zero = weighted_rotations(left,0.0,30.0,-12.0).unwrap();
        near(zero.0,30.0);near(zero.1,-12.0);
        let full = weighted_rotations(left,2.0,30.0,-12.0).unwrap();
        near(full.0,left.upper_deg);near(full.1,left.lower_deg);
    }

    #[test]
    fn invalid_parameters_fail_closed() {
        assert_eq!(solve_two_bone((0.0,0.0),(1.0,1.0),0.0,1.0,1.0),
                   Err(IkError::InvalidParameters));
        assert!(mp_ik_upper_deg(f64::NAN,0.0,1.0,0.0,1.0,1.0,1.0).is_nan());
        assert_eq!(weighted_rotations(
            solve_two_bone((0.0,0.0),(1.0,0.0),1.0,1.0,1.0).unwrap(),
            f64::INFINITY,0.0,0.0),Err(IkError::InvalidParameters));
    }
}
