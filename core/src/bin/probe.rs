//! Developer-only native executable to compare Rust and JavaScript math.
use motionpack_core::{mp_point_x, mp_point_y, mp_sample_segment};
use motionpack_core::timeline::{clip_time, sample_track, Keyframe};
use std::env;

fn parse(raw: &str) -> f64 {
    raw.parse::<f64>().expect("expected finite numeric argument")
}

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    match args.first().map(String::as_str) {
        Some("segment") if args.len() == 6 => {
            println!("{:.17}", mp_sample_segment(
                parse(&args[1]), parse(&args[2]), parse(&args[3]),
                parse(&args[4]), parse(&args[5])
            ));
        }
        Some("track") if args.len() >= 6 && args.len() % 2 == 0 => {
            // track timeMs durationMs loop(0|1) t0 v0 [t1 v1 ...]
            let looping = match args[3].as_str() {
                "0" => false, "1" => true,
                _ => { eprintln!("invalid loop"); std::process::exit(2); }
            };
            let mut keys = Vec::new();
            for pair in args[4..].chunks_exact(2) {
                keys.push(Keyframe { time_ms: parse(&pair[0]), value: parse(&pair[1]) });
            }
            let result = clip_time(parse(&args[2]), looping, parse(&args[1]))
                .and_then(|t| sample_track(&keys, t));
            match result {
                Ok(value) => println!("{value:.17}"),
                Err(err) => { eprintln!("invalid track: {err:?}"); std::process::exit(2); }
            }
        }
        Some("point") if args.len() == 7 => {
            let n: Vec<f64> = args[1..].iter().map(|s| parse(s)).collect();
            println!("{:.17} {:.17}",
                mp_point_x(n[0], n[1], n[2], n[3], n[4], n[5]),
                mp_point_y(n[0], n[1], n[2], n[3], n[4], n[5]));
        }
        _ => {
            eprintln!("usage: motionpack_core_probe segment t t0 v0 t1 v1 | point x y rotation_deg scale px py");
            std::process::exit(2);
        }
    }
}
