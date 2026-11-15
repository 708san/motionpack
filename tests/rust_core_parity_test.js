'use strict';
// Numerical conformance of Rust native and Wasm primitives to the existing
// MotionPack JS evaluator/rig. This is NOT full-archive runtime parity.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const Evaluator = require('../runtime/evaluator.js');
const Rig = require('../runtime/rig.js');

const root=path.resolve(__dirname,'..');
const manifest=JSON.parse(fs.readFileSync(path.join(root,'examples/robot_ik_demo/manifest.json'),'utf8'));
const native=path.join(root,'core','target','debug',
  'motionpack_core_probe'+(process.platform==='win32'?'.exe':''));
const wasm=path.join(root,'core','target','wasm32-unknown-unknown','release','motionpack_core.wasm');
const mode=process.argv[2];
assert(['native','wasm'].includes(mode),'expected native or wasm mode');

function compare(actual,expected,label){
 assert(Number.isFinite(actual),label+' must be finite');
 assert(Math.abs(actual-expected)<1e-8,label+': '+actual+' != '+expected);
}
function runNative(command,values){
 const result=spawnSync(native,[command,...values.map(String)],{encoding:'utf8',timeout:5000});
 assert.equal(result.status,0,result.stderr || 'native probe failed');
 return result.stdout.trim().split(/\s+/).map(Number);
}
async function main(){
 let exports=null;
 if(mode==='wasm'){
  const binary=fs.readFileSync(wasm);
  const built=await WebAssembly.instantiate(binary,{});
  exports=built.instance.exports;
  assert.equal(typeof exports.mp_sample_segment,'function');
  assert.equal(typeof exports.mp_point_x,'function');
 }
 const segment=(...args)=>mode==='native'?runNative('segment',args)[0]:exports.mp_sample_segment(...args);
 const point=(...args)=>mode==='native'
   ?runNative('point',args)
   :[exports.mp_point_x(...args),exports.mp_point_y(...args)];
 let tests=0;
 for(const clipName of ['idle','fire','transform']){
  const clip=manifest.clips[clipName];
  // Every scalar keyframe track must match evaluator.sample at arbitrary
  // times. IK-related tracks use separate rig integration in the JS evaluator,
  // so we isolate a scalar track by sampling its identical keyframe curve.
  for(const track of clip.tracks||[]){
   const keys=track.keys;
   for(const t of [0,25,100,200,400,600,900,1200,1750,2200,2600]){
    const time=clip.loop?t%clip.duration_ms:Math.min(t,clip.duration_ms);
    const frame=Evaluator.sample(manifest,{clip:clipName,timeMs:t},Rig);
    const observed=frame.nodes.get(track.node)[track.property];
    let predicted;
    if(time<=keys[0].time_ms)predicted=keys[0].value;
    else if(time>=keys[keys.length-1].time_ms)predicted=keys[keys.length-1].value;
    else{
     let i=1;
     while(i<keys.length-1 && time>keys[i].time_ms)i++;
     predicted=segment(time,keys[i-1].time_ms,keys[i-1].value,
       keys[i].time_ms,keys[i].value);
    }
    // An IK solver can override upper/lower rotation or position after
    // interpolation. Validate only tracks without an IK-output override.
    if(manifest.iks?.some(ik=>(
      (ik.upper===track.node||ik.lower===track.node)&&
      ['rotation','x','y'].includes(track.property))))continue;
    compare(predicted,observed,clipName+'/'+track.node+'/'+track.property+'/'+t);
    tests++;
   }
  }
 }
 for(const [x,y,deg,scale,px,py] of [
  [0,0,0,1,0,0],[10,20,90,2,2,-3],
  [-40,10,-22.5,0.3,15,12],[2,-5,180,1,-99,17],
  [500,620,155,1,90,-88]
 ]){
  const m=Rig.matrix({x,y,rotation:deg,scale});
  const expected=[m.a*px+m.c*py+m.e,m.b*px+m.d*py+m.f];
  const observed=point(x,y,deg,scale,px,py);
  compare(observed[0],expected[0],'affine x');
  compare(observed[1],expected[1],'affine y');
  tests++;
 }
 assert(Number.isNaN(segment(0,1,2,1,3)),'degenerate segment must fail closed');
 console.log('PASS',mode,tests,'sampled JS/Rust interpolation and transform comparisons');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
