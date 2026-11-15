//! Wasm32 host protocol: bounded packed f64 arrays, using the same Rust pose
//! evaluator as native FFI. Trusted host supplies validated manifest data.
//! Not a ZIP parser, asset renderer, or security sandbox.
use crate::ffi::{self, MpNode, MpVariant, MpKey, MpTrack, MpChain, MpIkTrack, MpTarget};
use core::slice;

const MAX_WORDS:usize=65536;
fn integer(value:f64,max:usize)->Result<usize,()>{
    if !value.is_finite() || value<0.0 || value>max as f64 || value.fract()!=0.0 {
        Err(())
    }else{ Ok(value as usize) }
}
struct Cursor<'a>{data:&'a [f64],position:usize}
impl<'a> Cursor<'a>{
    fn next(&mut self)->Result<f64,()>{
        let value=*self.data.get(self.position).ok_or(())?;
        self.position+=1;
        if value.is_finite(){Ok(value)}else{Err(())}
    }
    fn index(&mut self,max:usize)->Result<usize,()>{
        integer(self.next()?,max)
    }
    fn entry(&mut self,count:usize)->Result<&'a [f64],()>{
        let end=self.position.checked_add(count).ok_or(())?;
        let part=self.data.get(self.position..end).ok_or(())?;
        self.position=end;
        if part.iter().any(|v|!v.is_finite()){return Err(());}
        Ok(part)
    }
}
fn packed_scene(input:&[f64])->Result<Vec<f64>,()>{
    let mut r=Cursor{data:input,position:0};
    let version=r.index(1)?;
    if version!=1{return Err(());}
    let time=r.next()?;
    let duration=r.next()?;
    let looping=r.index(1)? as u32;
    let n=r.index(4096)?;
    let v=r.index(4096)?;
    let t=r.index(4096)?;
    let k=r.index(65536)?;
    let c=r.index(128)?;
    let it=r.index(4096)?;
    let tg=r.index(128)?;
    let mut nodes=Vec::with_capacity(n);
    for _ in 0..n{
        let p=r.entry(6)?;
        let parent=if p[0]==-1.0{-1}else{
            integer(p[0],n.saturating_sub(1))? as i32
        };
        nodes.push(MpNode{parent,x:p[1],y:p[2],rotation:p[3],scale:p[4],opacity:p[5]});
    }
    let mut variants=Vec::with_capacity(v);
    for _ in 0..v{
        let p=r.entry(7)?;
        variants.push(MpVariant{
            node:integer(p[0],n.saturating_sub(1))? as u32,
            mask:integer(p[1],31)? as u32,
            x:p[2],y:p[3],rotation:p[4],scale:p[5],opacity:p[6]
        });
    }
    let mut tracks=Vec::with_capacity(t);
    for _ in 0..t {
        let p=r.entry(4)?;
        tracks.push(MpTrack{
            node:integer(p[0],n.saturating_sub(1))? as u32,
            property:integer(p[1],4)? as u32,
            key_start:integer(p[2],k)? as u32,
            key_count:integer(p[3],4096)? as u32
        });
    }
    let mut keys=Vec::with_capacity(k);
    for _ in 0..k{
        let p=r.entry(2)?;
        keys.push(MpKey{time_ms:p[0],value:p[1]});
    }
    let mut chains=Vec::with_capacity(c);
    for _ in 0..c{
        let p=r.entry(8)?;
        chains.push(MpChain{
            upper:integer(p[0],n.saturating_sub(1))? as u32,
            lower:integer(p[1],n.saturating_sub(1))? as u32,
            length1:p[2],length2:p[3],target_x:p[4],target_y:p[5],
            bend:p[6],weight:p[7]
        });
    }
    let mut ik_tracks=Vec::with_capacity(it);
    for _ in 0..it{
        let p=r.entry(4)?;
        ik_tracks.push(MpIkTrack{
            chain:integer(p[0],c.saturating_sub(1))? as u32,
            axis:integer(p[1],1)? as u32,
            key_start:integer(p[2],k)? as u32,
            key_count:integer(p[3],4096)? as u32
        });
    }
    let mut targets=Vec::with_capacity(tg);
    for _ in 0..tg{
        let p=r.entry(3)?;
        targets.push(MpTarget{
            chain:integer(p[0],c.saturating_sub(1))? as u32,x:p[1],y:p[2]
        });
    }
    if r.position!=r.data.len(){return Err(());}
    let (time,poses)=ffi::evaluate(&nodes,&variants,&tracks,&keys,&chains,
        &ik_tracks,&targets,duration,looping,time).map_err(|_|())?;
    let mut out=Vec::with_capacity(1+poses.len()*11);
    out.push(time);
    for p in poses{
        out.extend_from_slice(&[p.x,p.y,p.rotation,p.scale,p.opacity,
            p.a,p.b,p.c,p.d,p.tx,p.ty]);
    }
    Ok(out)
}

/// Allocate a host-owned Float64 buffer in Wasm linear memory.
///
/// Only call with bounded counts and only release a pointer returned by this
/// exact module with its original length. The module is a trusted component.
#[no_mangle]
pub extern "C" fn mp_wasm_alloc_f64_v1(count:u32)->u32{
    let n=count as usize;
    if n==0 || n>MAX_WORDS{return 0;}
    let boxed=vec![0.0_f64;n].into_boxed_slice();
    let ptr=Box::into_raw(boxed) as *mut f64;
    ptr as u32
}

/// Release exactly one allocation from mp_wasm_alloc_f64_v1.
/// The caller must not use pointer after release.
#[no_mangle]
pub unsafe extern "C" fn mp_wasm_free_f64_v1(ptr:u32,count:u32){
    if ptr==0 || count==0 || count as usize>MAX_WORDS || ptr%8!=0{return;}
    // SAFETY: host contract guarantees this is a live allocation made with
    // mp_wasm_alloc_f64_v1 and the same original element count.
    let raw=core::ptr::slice_from_raw_parts_mut(ptr as *mut f64,count as usize);
    drop(unsafe{Box::from_raw(raw)});
}

/// Sample one scene. Returns 0 success, 1 invalid input, 2 evaluation failed.
/// Output: [sampledTime, x,y,rotation,scale,opacity,a,b,c,d,tx,ty ...].
///
/// SAFETY: Both pointers must refer to live module allocations of the stated
/// sizes, be non-overlapping, and remain allocated throughout this call.
#[no_mangle]
pub unsafe extern "C" fn mp_wasm_sample_scene_v1(
    input_ptr:u32,input_len:u32,out_ptr:u32,out_len:u32
)->i32{
    let a=input_len as usize;
    let b=out_len as usize;
    if input_ptr==0 || out_ptr==0 || input_ptr%8!=0 || out_ptr%8!=0 ||
        a<11 || a>MAX_WORDS || b==0 || b>MAX_WORDS{return 1;}
    let in_start=input_ptr as u64;
    let in_end=in_start+a as u64*8;
    let out_start=out_ptr as u64;
    let out_end=out_start+b as u64*8;
    if in_start<out_end && out_start<in_end{return 1;}
    // SAFETY: trusted host supplied live allocations, as specified above.
    let input=unsafe{slice::from_raw_parts(input_ptr as *const f64,a)};
    let nodes=match integer(input[4],4096){Ok(n)=>n,Err(_)=>return 1};
    if b!=1+11*nodes{return 1;}
    let output=match packed_scene(input){Ok(p)=>p,Err(_)=>return 2};
    if output.len()!=b{return 2;}
    // Only write after every validation and sample succeeds.
    unsafe{core::ptr::copy_nonoverlapping(output.as_ptr(),out_ptr as *mut f64,b);}
    0
}

#[cfg(test)]
mod tests{
    use super::*;
    #[test]
    fn trusted_packed_scene_and_rejected_lengths(){
        // version, t, duration, loop, counts: nodes variants tracks keys chains ikTracks targets
        let input=[1.0,500.0,1000.0,1.0,2.0,0.0,1.0,2.0,0.0,0.0,0.0,
            -1.0,10.0,20.0,0.0,1.0,1.0,
            0.0,5.0,3.0,0.0,1.0,1.0,
            0.0,1.0,0.0,2.0,
            0.0,20.0,1000.0,40.0];
        let frame=packed_scene(&input).unwrap();
        assert_eq!(frame.len(),23);
        assert_eq!(frame[0],500.0);
        assert_eq!(frame[2],30.0);
        assert_eq!(frame[1+11+10],33.0);
        assert!(packed_scene(&input[..input.len()-1]).is_err());
    }
}
