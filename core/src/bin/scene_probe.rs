//! Trusted developer-only fixture bridge; never reads archives or scripts.
//! Protocol: whitespace-delimited numeric fields, <=1 MiB, indexes by node order.
use motionpack_core::pose::{sample_scene,Axis,IkChain,IkTrack,Node};
use motionpack_core::timeline::{Clip,Keyframe,Pose,PoseOverride,Property,Track,VariantNode};
use std::io::{self,Read};

struct Reader<'a>{parts:std::str::SplitWhitespace<'a>}
impl Reader<'_>{
 fn number(&mut self)->Result<f64,String>{
  let text=self.parts.next().ok_or("missing number")?;
  let value=text.parse::<f64>().map_err(|_|"invalid number")?;
  if !value.is_finite(){return Err("nonfinite number".into());}
  Ok(value)
 }
 fn size(&mut self,max:usize)->Result<usize,String>{
  let v=self.number()?;
  if v<0.0 || v>max as f64 || v.fract()!=0.0{return Err("invalid count".into());}
  Ok(v as usize)
 }
 fn parent(&mut self,count:usize)->Result<Option<usize>,String>{
  let v=self.number()?;
  if v==-1.0 {return Ok(None);}
  if v<0.0 || v.fract()!=0.0 || v>=count as f64{return Err("invalid parent".into());}
  Ok(Some(v as usize))
 }
 fn keys(&mut self)->Result<Vec<Keyframe>,String>{
  let count=self.size(4096)?;
  let mut keys=Vec::with_capacity(count);
  for _ in 0..count{keys.push(Keyframe{time_ms:self.number()?,value:self.number()?});}
  Ok(keys)
 }
 fn end(&mut self)->Result<(),String>{
  if self.parts.next().is_some(){Err("trailing input".into())}else{Ok(())}
 }
}
fn execute(input:&str)->Result<(),String>{
 let mut r=Reader{parts:input.split_whitespace()};
 let time=r.number()?;
 let count=r.size(4096)?;
 let mut nodes=Vec::with_capacity(count);
 for _ in 0..count {
  let parent=r.parent(count)?;
  let pose=Pose{x:r.number()?,y:r.number()?,rotation:r.number()?,
   scale:r.number()?,opacity:r.number()?};
  nodes.push(Node{parent,pose});
 }
 let duration_ms=r.number()?;
 let looping=match r.size(1)?{0=>false,_=>true};
 let variants=r.size(4096)?;
 let mut variant=Vec::with_capacity(variants);
 for _ in 0..variants{
  let index=r.size(count.saturating_sub(1))?;
  let mut values=PoseOverride::default();
  let mask=r.size(31)?;
  for (bit,dest) in [(1,&mut values.x),(2,&mut values.y),
                     (4,&mut values.rotation),(8,&mut values.scale),
                     (16,&mut values.opacity)] {
   if mask&bit!=0 {*dest=Some(r.number()?);}
  }
  variant.push(VariantNode{node_index:index,values});
 }
 let track_count=r.size(4096)?;
 let mut tracks=Vec::with_capacity(track_count);
 for _ in 0..track_count {
  let node_index=r.size(count.saturating_sub(1))?;
  let property=match r.size(4)?{
   0=>Property::X,1=>Property::Y,2=>Property::Rotation,
   3=>Property::Scale,_=>Property::Opacity
  };
  tracks.push(Track{node_index,property,keys:r.keys()?});
 }
 let chain_count=r.size(128)?;
 let mut chains=Vec::with_capacity(chain_count);
 for _ in 0..chain_count{
  chains.push(IkChain{
   upper:r.size(count.saturating_sub(1))?,
   lower:r.size(count.saturating_sub(1))?,
   lengths:(r.number()?,r.number()?),
   target:(r.number()?,r.number()?),
   bend:r.number()?,
   weight:r.number()?,
  });
 }
 let ik_track_count=r.size(4096)?;
 let mut ik_tracks=Vec::with_capacity(ik_track_count);
 for _ in 0..ik_track_count{
  let chain_index=r.size(chain_count.saturating_sub(1))?;
  let axis=match r.size(1)?{0=>Axis::X,_=>Axis::Y};
  ik_tracks.push(IkTrack{chain_index,axis,keys:r.keys()?});
 }
 let override_count=r.size(128)?;
 let mut overrides=Vec::with_capacity(override_count);
 for _ in 0..override_count {
  overrides.push((r.size(chain_count.saturating_sub(1))?,(r.number()?,r.number()?)));
 }
 r.end()?;
 let clip=Clip{duration_ms,looping,tracks};
 let frame=sample_scene(&nodes,&variant,&clip,&chains,&ik_tracks,&overrides,time)
     .map_err(|e|format!("scene failed: {e:?}"))?;
 println!("{:.17}",frame.time_ms);
 for (local,m) in frame.local.iter().zip(frame.world.iter()){
  println!("{:.17} {:.17} {:.17} {:.17} {:.17} {:.17} {:.17} {:.17} {:.17} {:.17} {:.17}",
   local.x,local.y,local.rotation,local.scale,local.opacity,
   m.a,m.b,m.c,m.d,m.tx,m.ty);
 }
 Ok(())
}
fn main(){
 let mut input=String::new();
 if io::stdin().take(1024*1024+1).read_to_string(&mut input).is_err() ||
    input.len()>1024*1024 {eprintln!("invalid scene request");std::process::exit(2);}
 if let Err(err)=execute(&input){eprintln!("{err}");std::process::exit(2);}
}
