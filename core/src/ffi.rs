//! Versioned C ABI for trusted, prevalidated MotionPack numeric scene data.
//! All arrays are borrowed from the caller, all output buffers are caller-owned.
//! This is NOT a safe archive reader: valid mapped pointers remain a host duty.
use crate::pose::{sample_scene,Axis,IkChain,IkTrack,Node};
use crate::timeline::{Clip,Keyframe,Pose,PoseOverride,Property,Track,VariantNode};
use core::mem::align_of;
use core::slice;

pub const MP_OK:i32=0;
pub const MP_INVALID_INPUT:i32=1;
pub const MP_EVALUATION_FAILED:i32=2;

#[repr(C)]
#[derive(Clone,Copy)]
pub struct MpNode {
    pub parent:i32,
    pub x:f64,pub y:f64,pub rotation:f64,pub scale:f64,pub opacity:f64
}
#[repr(C)]
#[derive(Clone,Copy)]
pub struct MpVariant {
    pub node:u32,pub mask:u32,
    pub x:f64,pub y:f64,pub rotation:f64,pub scale:f64,pub opacity:f64
}
#[repr(C)]
#[derive(Clone,Copy)]
pub struct MpKey {pub time_ms:f64,pub value:f64}
#[repr(C)]
#[derive(Clone,Copy)]
pub struct MpTrack {pub node:u32,pub property:u32,pub key_start:u32,pub key_count:u32}
#[repr(C)]
#[derive(Clone,Copy)]
pub struct MpChain {
    pub upper:u32,pub lower:u32,
    pub length1:f64,pub length2:f64,pub target_x:f64,pub target_y:f64,
    pub bend:f64,pub weight:f64
}
#[repr(C)]
#[derive(Clone,Copy)]
pub struct MpIkTrack {pub chain:u32,pub axis:u32,pub key_start:u32,pub key_count:u32}
#[repr(C)]
#[derive(Clone,Copy)]
pub struct MpTarget {pub chain:u32,pub x:f64,pub y:f64}
#[repr(C)]
#[derive(Clone,Copy,Debug)]
pub struct MpOutput {
    pub x:f64,pub y:f64,pub rotation:f64,pub scale:f64,pub opacity:f64,
    pub a:f64,pub b:f64,pub c:f64,pub d:f64,pub tx:f64,pub ty:f64
}

unsafe fn read_array<'a,T>(ptr:*const T,len:usize,max:usize)->Result<&'a [T],()> {
    if len>max {return Err(());}
    if len==0{return Ok(&[]);}
    if ptr.is_null() || (ptr as usize)%align_of::<T>()!=0 ||
       len>isize::MAX as usize/core::mem::size_of::<T>() {return Err(());}
    // SAFETY: FFI contract requires caller-provided pointers to readable,
    // properly aligned, contiguous mapped memory for exactly len elements.
    Ok(unsafe {slice::from_raw_parts(ptr,len)})
}
fn key_slice(keys:&[MpKey],first:u32,count:u32)->Result<Vec<Keyframe>,()>{
    let start=first as usize;
    let end=start.checked_add(count as usize).ok_or(())?;
    let selected=keys.get(start..end).ok_or(())?;
    if selected.is_empty() || selected.len()>4096{return Err(());}
    Ok(selected.iter().map(|k|Keyframe{time_ms:k.time_ms,value:k.value}).collect())
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn evaluate(nodes:&[MpNode],variants:&[MpVariant],tracks:&[MpTrack],
    keys:&[MpKey],chains:&[MpChain],ik_tracks:&[MpIkTrack],targets:&[MpTarget],
    duration:f64,loop_flag:u32,time:f64)->Result<(f64,Vec<MpOutput>),i32>{
    if loop_flag>1 {return Err(MP_INVALID_INPUT);}
    let mut scene=Vec::with_capacity(nodes.len());
    for node in nodes{
        let parent=if node.parent==-1{None}else{
            if node.parent<0 || node.parent as usize>=nodes.len(){return Err(MP_INVALID_INPUT);}
            Some(node.parent as usize)
        };
        scene.push(Node{parent,pose:Pose{x:node.x,y:node.y,
            rotation:node.rotation,scale:node.scale,opacity:node.opacity}});
    }
    let mut overrides=Vec::with_capacity(variants.len());
    for v in variants {
        if v.mask & !31 != 0 {return Err(MP_INVALID_INPUT);}
        overrides.push(VariantNode{node_index:v.node as usize,values:PoseOverride{
            x:if v.mask&1!=0{Some(v.x)}else{None},
            y:if v.mask&2!=0{Some(v.y)}else{None},
            rotation:if v.mask&4!=0{Some(v.rotation)}else{None},
            scale:if v.mask&8!=0{Some(v.scale)}else{None},
            opacity:if v.mask&16!=0{Some(v.opacity)}else{None}
        }});
    }
    let mut animation=Vec::with_capacity(tracks.len());
    for t in tracks{
        let property=match t.property{
            0=>Property::X,1=>Property::Y,2=>Property::Rotation,
            3=>Property::Scale,4=>Property::Opacity,_=>return Err(MP_INVALID_INPUT)
        };
        animation.push(Track{node_index:t.node as usize,property,
            keys:key_slice(keys,t.key_start,t.key_count)
                .map_err(|_|MP_INVALID_INPUT)?});
    }
    let mut ik_chains=Vec::with_capacity(chains.len());
    for c in chains{
        ik_chains.push(IkChain{upper:c.upper as usize,lower:c.lower as usize,
            lengths:(c.length1,c.length2),target:(c.target_x,c.target_y),
            bend:c.bend,weight:c.weight});
    }
    let mut ik_animation=Vec::with_capacity(ik_tracks.len());
    for t in ik_tracks {
        let axis=match t.axis{0=>Axis::X,1=>Axis::Y,_=>return Err(MP_INVALID_INPUT)};
        ik_animation.push(IkTrack{chain_index:t.chain as usize,axis,
            keys:key_slice(keys,t.key_start,t.key_count).map_err(|_|MP_INVALID_INPUT)?});
    }
    let changes:Vec<_>=targets.iter().map(|t|(t.chain as usize,(t.x,t.y))).collect();
    let clip=Clip{duration_ms:duration,looping:loop_flag==1,tracks:animation};
    let result=sample_scene(&scene,&overrides,&clip,&ik_chains,&ik_animation,&changes,time)
        .map_err(|_|MP_EVALUATION_FAILED)?;
    let output=result.local.iter().zip(result.world.iter()).map(|(p,m)| MpOutput{
        x:p.x,y:p.y,rotation:p.rotation,scale:p.scale,opacity:p.opacity,
        a:m.a,b:m.b,c:m.c,d:m.d,tx:m.tx,ty:m.ty
    }).collect();
    Ok((result.time_ms,output))
}

/// Caller-owned native/C# and Wasm-compatible numeric scene API (version 1).
///
/// SAFETY: Input pointers must remain readable and non-overlapping with output,
/// and output pointers must remain writable for the declared lengths. This ABI
/// validates counts, alignment, indices and values but cannot validate whether
/// an arbitrary external pointer is mapped. Never pass untrusted raw pointers.
/// On failure output arrays and *out_time are unchanged.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn mp_scene_sample_v1(
    nodes:*const MpNode,node_count:usize,
    variants:*const MpVariant,variant_count:usize,
    tracks:*const MpTrack,track_count:usize,
    keys:*const MpKey,key_count:usize,
    chains:*const MpChain,chain_count:usize,
    ik_tracks:*const MpIkTrack,ik_track_count:usize,
    targets:*const MpTarget,target_count:usize,
    duration:f64,loop_flag:u32,time:f64,
    out:*mut MpOutput,out_capacity:usize,out_time:*mut f64
)->i32{
    if out_capacity<node_count || out.is_null() || out_time.is_null() ||
       (out as usize)%align_of::<MpOutput>()!=0 ||
       (out_time as usize)%align_of::<f64>()!=0 {return MP_INVALID_INPUT;}
    let arrays=unsafe{(
        read_array(nodes,node_count,4096),
        read_array(variants,variant_count,4096),
        read_array(tracks,track_count,4096),
        read_array(keys,key_count,65536),
        read_array(chains,chain_count,128),
        read_array(ik_tracks,ik_track_count,4096),
        read_array(targets,target_count,128)
    )};
    let (Ok(n),Ok(v),Ok(tr),Ok(k),Ok(c),Ok(it),Ok(tg))=arrays
        else{return MP_INVALID_INPUT;};
    let (sampled,frames)=match evaluate(n,v,tr,k,c,it,tg,duration,loop_flag,time){
        Ok(value)=>value,Err(code)=>return code
    };
    // SAFETY: The trusted caller guarantees output writable for capacity.
    // All temporary data is fully evaluated before any memory is written.
    unsafe{
        core::ptr::copy_nonoverlapping(frames.as_ptr(),out,frames.len());
        *out_time=sampled;
    }
    MP_OK
}

#[cfg(test)]
mod tests{
    use super::*;
    #[test]
    fn stable_scene_ffi_and_error_output_atomicity(){
        let nodes=[MpNode{parent:-1,x:10.0,y:20.0,rotation:0.0,scale:1.0,opacity:1.0},
            MpNode{parent:0,x:5.0,y:3.0,rotation:0.0,scale:1.0,opacity:1.0}];
        let tracks=[MpTrack{node:0,property:1,key_start:0,key_count:2}];
        let keys=[MpKey{time_ms:0.0,value:20.0},MpKey{time_ms:1000.0,value:40.0}];
        let mut output=[MpOutput{x:-1.0,y:-1.0,rotation:-1.0,scale:-1.0,
            opacity:-1.0,a:-1.0,b:-1.0,c:-1.0,d:-1.0,tx:-1.0,ty:-1.0};2];
        let mut sampled=-1.0;
        let call=|loop_flag:u32,output:&mut [MpOutput;2],sampled:&mut f64|unsafe{
            mp_scene_sample_v1(nodes.as_ptr(),2,core::ptr::null(),0,
                tracks.as_ptr(),1,keys.as_ptr(),2,core::ptr::null(),0,
                core::ptr::null(),0,core::ptr::null(),0,
                1000.0,loop_flag,500.0,output.as_mut_ptr(),2,sampled)
        };
        assert_eq!(call(1,&mut output,&mut sampled),MP_OK);
        assert_eq!(sampled,500.0);
        assert_eq!(output[0].y,30.0);
        assert_eq!(output[1].ty,33.0);
        assert_eq!(call(2,&mut output,&mut sampled),MP_INVALID_INPUT);
        assert_eq!(sampled,500.0);
        assert_eq!(output[0].y,30.0);
    }
}
