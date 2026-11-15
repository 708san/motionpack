//! Integrated, data-only Rust pose evaluation for validated host inputs.
//! Reuses MotionPack timeline + IK and resolves hierarchical 2D transforms.
use crate::Affine;
use crate::ik::{solve_two_bone, weighted_rotations};
use crate::timeline::{sample_clip, sample_track, Clip, Pose, TimelineError, VariantNode};

#[derive(Clone, Copy, Debug)]
pub struct Node { pub parent: Option<usize>, pub pose: Pose }

#[derive(Clone, Copy, Debug)]
pub struct IkChain {
    pub upper: usize,
    pub lower: usize,
    pub lengths: (f64, f64),
    pub target: (f64, f64),
    pub bend: f64,
    pub weight: f64,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Axis { X, Y }

#[derive(Clone, Debug)]
pub struct IkTrack {
    pub chain_index: usize,
    pub axis: Axis,
    pub keys: Vec<crate::timeline::Keyframe>,
}

#[derive(Clone, Debug)]
pub struct SceneFrame {
    pub time_ms: f64,
    pub local: Vec<Pose>,
    pub world: Vec<Affine>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SceneError {
    InvalidInput,
    InvalidTopology,
    InvalidIk,
    Timeline(TimelineError),
}

impl From<TimelineError> for SceneError {
    fn from(value: TimelineError) -> Self { SceneError::Timeline(value) }
}

fn resolve_world(nodes: &[Node], local: &[Pose]) -> Result<Vec<Affine>, SceneError> {
    if nodes.len()!=local.len() || nodes.len()>4096 { return Err(SceneError::InvalidInput); }
    let mut world:Vec<Option<Affine>>=vec![None;nodes.len()];
    let mut visiting=vec![false;nodes.len()];
    fn visit(idx:usize,nodes:&[Node],local:&[Pose],world:&mut [Option<Affine>],
        visiting:&mut [bool],depth:usize)->Result<Affine,SceneError>{
        if depth>128 || idx>=nodes.len() || visiting[idx] { return Err(SceneError::InvalidTopology); }
        if let Some(m)=world[idx] { return Ok(m); }
        visiting[idx]=true;
        let p=local[idx];
        let own=Affine::from_pose(p.x,p.y,p.rotation,p.scale)
            .ok_or(SceneError::InvalidInput)?;
        let matrix=if let Some(parent)=nodes[idx].parent {
            visit(parent,nodes,local,world,visiting,depth+1)?
                .compose(&own).ok_or(SceneError::InvalidInput)?
        }else{own};
        visiting[idx]=false;
        world[idx]=Some(matrix);
        Ok(matrix)
    }
    for i in 0..nodes.len(){visit(i,nodes,local,&mut world,&mut visiting,0)?;}
    world.into_iter().map(|m|m.ok_or(SceneError::InvalidTopology)).collect()
}

fn inverse_point(matrix:Affine,target:(f64,f64))->Result<(f64,f64),SceneError>{
    let determinant=matrix.a*matrix.d-matrix.b*matrix.c;
    if !determinant.is_finite() || determinant.abs()<1e-10 ||
        !target.0.is_finite() || !target.1.is_finite() {
        return Err(SceneError::InvalidIk);
    }
    let x=target.0-matrix.tx;
    let y=target.1-matrix.ty;
    let point=((matrix.d*x-matrix.c*y)/determinant,
               (-matrix.b*x+matrix.a*y)/determinant);
    if point.0.is_finite() && point.1.is_finite(){Ok(point)}
    else{Err(SceneError::InvalidIk)}
}

/// This is a complete numeric node-pose frame for supplied host-parsed data.
/// Non-numeric asset IDs, effect descriptions, images and clip names remain
/// host-owned. No package content can be executed by this evaluator.
pub fn sample_scene(nodes:&[Node],variant:&[VariantNode],clip:&Clip,
    chains:&[IkChain],ik_tracks:&[IkTrack],target_overrides:&[(usize,(f64,f64))],
    requested_ms:f64)->Result<SceneFrame,SceneError>{
    if nodes.len()>4096 || chains.len()>128 || ik_tracks.len()>4096 ||
       target_overrides.len()>128 { return Err(SceneError::InvalidInput); }
    let base:Vec<Pose>=nodes.iter().map(|node|node.pose).collect();
    let (time_ms,mut local)=sample_clip(&base,variant,clip,requested_ms)?;
    let mut targets:Vec<(f64,f64)>=chains.iter().map(|chain|chain.target).collect();
    for tr in ik_tracks {
        let target=targets.get_mut(tr.chain_index).ok_or(SceneError::InvalidIk)?;
        let v=sample_track(&tr.keys,time_ms)?;
        match tr.axis {Axis::X=>target.0=v,Axis::Y=>target.1=v}
    }
    for &(index,position) in target_overrides {
        let target=targets.get_mut(index).ok_or(SceneError::InvalidIk)?;
        if !position.0.is_finite() || !position.1.is_finite(){return Err(SceneError::InvalidIk);}
        *target=position;
    }
    for (i,chain) in chains.iter().enumerate(){
        let upper=nodes.get(chain.upper).ok_or(SceneError::InvalidIk)?;
        let lower=nodes.get(chain.lower).ok_or(SceneError::InvalidIk)?;
        if lower.parent!=Some(chain.upper) || chain.upper==chain.lower ||
           !chain.weight.is_finite() {return Err(SceneError::InvalidIk);}
        // Recompute parent transforms per chain: prior IK updates must apply.
        let current=resolve_world(nodes,&local)?;
        let parent=upper.parent.map(|index|current[index]).unwrap_or(Affine::IDENTITY);
        let goal=inverse_point(parent,targets[i])?;
        let pose_upper=local[chain.upper];
        let pose_lower=local[chain.lower];
        let solution=solve_two_bone((pose_upper.x,pose_upper.y),goal,
            chain.lengths.0,chain.lengths.1,chain.bend)
            .map_err(|_|SceneError::InvalidIk)?;
        let (upper_deg,lower_deg)=weighted_rotations(solution,chain.weight,
            pose_upper.rotation,pose_lower.rotation).map_err(|_|SceneError::InvalidIk)?;
        local[chain.upper].rotation=upper_deg;
        local[chain.lower].x=chain.lengths.0;
        local[chain.lower].y=0.0;
        local[chain.lower].rotation=lower_deg;
    }
    let world=resolve_world(nodes,&local)?;
    Ok(SceneFrame{time_ms,local,world})
}

#[cfg(test)]
mod tests{
    use super::*;
    use crate::timeline::{Keyframe,Track,Property,PoseOverride};
    fn key(t:f64,v:f64)->Keyframe{Keyframe{time_ms:t,value:v}}
    #[test]
    fn parent_world_and_clip(){
        let nodes=[
            Node{parent:None,pose:Pose{x:10.0,y:20.0,..Pose::default()}},
            Node{parent:Some(0),pose:Pose{x:5.0,y:3.0,..Pose::default()}},
        ];
        let clip=Clip{duration_ms:1000.0,looping:true,tracks:vec![
            Track{node_index:0,property:Property::Y,keys:vec![key(0.0,20.0),key(1000.0,40.0)]}
        ]};
        let frame=sample_scene(&nodes,&[VariantNode{node_index:1,values:PoseOverride{
            rotation:Some(30.0),..PoseOverride::default()
        }}],&clip,&[],&[],&[],500.0).unwrap();
        assert!((frame.world[1].tx-15.0).abs()<1e-9);
        assert!((frame.world[1].ty-33.0).abs()<1e-9);
        assert!((frame.local[1].rotation-30.0).abs()<1e-9);
    }
    #[test]
    fn ik_and_override(){
        let nodes=[
            Node{parent:None,pose:Pose::default()},
            Node{parent:Some(0),pose:Pose::default()},
            Node{parent:Some(1),pose:Pose::default()},
        ];
        let clip=Clip{duration_ms:1000.0,looping:true,tracks:vec![]};
        let chain=IkChain{upper:1,lower:2,lengths:(100.0,80.0),
            target:(100.0,50.0),bend:-1.0,weight:1.0};
        let frame=sample_scene(&nodes,&[],&clip,&[chain],&[],&[],500.0).unwrap();
        assert!((frame.local[2].x-100.0).abs()<1e-9);
        assert_eq!(frame.local[2].y,0.0);
        let other=sample_scene(&nodes,&[],&clip,&[chain],&[],&[(0,(80.0,80.0))],500.0).unwrap();
        assert!((other.local[1].rotation-frame.local[1].rotation).abs()>1e-5);
    }
    #[test]
    fn cyclic_parent_and_bad_reference_rejected(){
        let nodes=[
            Node{parent:Some(1),pose:Pose::default()},
            Node{parent:Some(0),pose:Pose::default()}
        ];
        let clip=Clip{duration_ms:1000.0,looping:false,tracks:vec![]};
        assert_eq!(sample_scene(&nodes,&[],&clip,&[],&[],&[],0.0).unwrap_err(),
            SceneError::InvalidTopology);
    }
}
