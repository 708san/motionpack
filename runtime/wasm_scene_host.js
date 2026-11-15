/* Dependency-free WebAssembly scene bridge for trusted, validated manifests.
 * The Wasm binary performs numeric pose evaluation, NOT archive parsing or
 * image rendering. This module supplies frame metadata and effect descriptors.
 */
'use strict';
const PROPERTIES=['x','y','rotation','scale','opacity'];
const own=(obj,k)=>Object.prototype.hasOwnProperty.call(obj,k);
function numericManifest(manifest,clipName,variantName,timeMs,ikTargets){
 if(!manifest||!manifest.nodes||!manifest.clips||!manifest.variants)
   throw new TypeError('validated manifest required');
 const clip=manifest.clips[clipName],variant=manifest.variants[variantName];
 if(!clip||!variant)throw new RangeError('unknown clip or variant');
 if(!Number.isFinite(timeMs)||timeMs<0)throw new RangeError('invalid time');
 const nodes=manifest.nodes;
 const index=new Map(nodes.map((n,i)=>[n.id,i]));
 const chains=manifest.iks||[];
 const chainIndex=new Map(chains.map((chain,i)=>[chain.id,i]));
 const overrides=Object.entries(variant.nodes||{})
   .filter(([,values])=>PROPERTIES.some(k=>own(values,k)));
 const keys=[],tracks=[],ikTracks=[];
 for(const track of clip.tracks||[]){
  const start=keys.length;
  for(const key of track.keys)keys.push(key.time_ms,key.value);
  tracks.push(index.get(track.node),PROPERTIES.indexOf(track.property),
   start/2,track.keys.length);
 }
 for(const track of clip.ik_tracks||[]){
  const start=keys.length;
  for(const key of track.keys)keys.push(key.time_ms,key.value);
  ikTracks.push(chainIndex.get(track.ik),track.axis==='x'?0:1,start/2,track.keys.length);
 }
 const targets=Object.entries(ikTargets||{});
 const data=[1,timeMs,clip.duration_ms,clip.loop===true?1:0,
   nodes.length,overrides.length,tracks.length/4,keys.length/2,
   chains.length,ikTracks.length/4,targets.length];
 for(const node of nodes)data.push(
   node.parent==null?-1:index.get(node.parent),
   ...PROPERTIES.map(p=>node[p]??(p==='scale'||p==='opacity'?1:0)));
 for(const [id,values] of overrides){
  const mask=PROPERTIES.reduce((mask,p,i)=>mask|(own(values,p)?(1<<i):0),0);
  data.push(index.get(id),mask,...PROPERTIES.map(p=>values[p]??0));
 }
 data.push(...tracks,...keys);
 for(const chain of chains)data.push(index.get(chain.upper),index.get(chain.lower),
   chain.lengths[0],chain.lengths[1],chain.target[0],chain.target[1],
   chain.bend??1,chain.weight??1);
 data.push(...ikTracks);
 for(const [id,xy] of targets){
  if(!chainIndex.has(id)||!Array.isArray(xy)||xy.length!==2)
   throw new RangeError('invalid IK target');
  data.push(chainIndex.get(id),xy[0],xy[1]);
 }
 if(data.length>65536 || !data.every(Number.isFinite))
   throw new RangeError('scene request exceeds bounded numeric protocol');
 return {data,clip,variant,nodes};
}
function createWasmSceneSampler(exports){
 if(!exports||!exports.memory||
   !['mp_wasm_alloc_f64_v1','mp_wasm_free_f64_v1','mp_wasm_sample_scene_v1']
    .every(k=>typeof exports[k]==='function'))
  throw new TypeError('MotionPack Wasm scene v1 exports required');
 return function sample(manifest,{clip,variant,timeMs=0,ikTargets=null}={}){
  const clipName=clip??manifest.defaults?.clip;
  const variantName=variant??manifest.defaults?.variant;
  const spec=numericManifest(manifest,clipName,variantName,timeMs,ikTargets);
  const count=1+11*spec.nodes.length;
  const inPtr=exports.mp_wasm_alloc_f64_v1(spec.data.length);
  if(!inPtr)throw new RangeError('Wasm input allocation rejected');
  let outPtr=0;
  try{
   outPtr=exports.mp_wasm_alloc_f64_v1(count);
   if(!outPtr)throw new RangeError('Wasm output allocation rejected');
   new Float64Array(exports.memory.buffer,inPtr,spec.data.length).set(spec.data);
   const status=exports.mp_wasm_sample_scene_v1(
     inPtr,spec.data.length,outPtr,count);
   if(status!==0)throw new RangeError('Wasm scene evaluation rejected: '+status);
   const buffer=Array.from(new Float64Array(exports.memory.buffer,outPtr,count));
   const sampled=buffer[0];
   const nodeRecords=spec.nodes.map((n,i)=>{
    const values=buffer.slice(1+11*i,1+11*(i+1));
    const visual={...n,...(spec.variant.nodes||{})[n.id]};
    const local=Object.fromEntries(PROPERTIES.map((p,j)=>[p,values[j]]));
    return {id:n.id,parent:visual.parent??null,asset:visual.asset??null,
      z:visual.z??0,width:visual.width??0,height:visual.height??0,
      anchor:visual.anchor??[0.5,0.5],local,world:values.slice(5)};
   }).sort((a,b)=>a.z-b.z);
   const effects=(spec.clip.effects||[]).filter(f=>
      sampled>=f.start_ms && sampled<=f.start_ms+f.duration_ms
    ).map(f=>({...f,age_ms:sampled-f.start_ms,
      progress:(sampled-f.start_ms)/f.duration_ms}));
   return {protocol:'motionpack-pose',version:1,clip:clipName,variant:variantName,
     time_ms:sampled,canvas:{width:manifest.canvas.width,
      height:manifest.canvas.height,background:manifest.canvas.background??null},
     nodes:nodeRecords,effects};
  }finally{
   if(outPtr)exports.mp_wasm_free_f64_v1(outPtr,count);
   exports.mp_wasm_free_f64_v1(inPtr,spec.data.length);
  }
 };
}
module.exports=Object.freeze({createWasmSceneSampler});
