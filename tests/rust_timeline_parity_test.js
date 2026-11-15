'use strict';
// Native Rust clip timeline parity against JavaScript reference on all authored
// standard scalar tracks in repository fixtures. IK-owned output properties are
// excluded until the Rust IK solver is implemented.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {spawnSync}=require('node:child_process');
const Evaluator=require('../runtime/evaluator.js');
const Rig=require('../runtime/rig.js');
const root=path.resolve(__dirname,'..');
const executable=path.join(root,'core','target','debug',
  'motionpack_core_probe'+(process.platform==='win32'?'.exe':''));
function compare(a,b,label){
 assert(Number.isFinite(a)&&Number.isFinite(b),label+' finite');
 const tol=1e-8*Math.max(1,Math.abs(b));
 assert(Math.abs(a-b)<=tol,label+': Rust '+a+' vs JS '+b);
}
function rustTrack(clip,time,keys){
 const args=['track',String(time),String(clip.duration_ms),clip.loop?'1':'0'];
 for(const key of keys) args.push(String(key.time_ms),String(key.value));
 const result=spawnSync(executable,args,{encoding:'utf8',timeout:5000});
 assert.equal(result.status,0,'Rust probe failed: '+result.stderr);
 return Number(result.stdout.trim());
}
let total=0;
for(const example of ['robot_demo','robot_ik_demo','layered_plant_demo']){
 const manifest=JSON.parse(fs.readFileSync(
  path.join(root,'examples',example,'manifest.json'),'utf8'));
 const variant=manifest.defaults.variant;
 for(const [name,clip] of Object.entries(manifest.clips)){
  const duration=clip.duration_ms;
  const times=[0,1,duration*0.125,duration*0.5,duration*0.875,
    duration-1,duration,duration+1,duration*2+10];
  for(const t of times){
   const pose=Evaluator.sample(manifest,{clip:name,variant,timeMs:t},Rig);
   for(const track of clip.tracks||[]){
    const ikOwned=(manifest.iks||[]).some(ik=>
      [ik.upper,ik.lower].includes(track.node)&&
      ['x','y','rotation'].includes(track.property));
    if(ikOwned) continue;
    const value=rustTrack(clip,t,track.keys);
    compare(value,pose.nodes.get(track.node)[track.property],
      example+'/'+name+'/'+track.node+'/'+track.property+'@'+t);
    total++;
   }
  }
 }
}
assert(total>=65,'insufficient native Rust/JS clip comparisons: '+total);
console.log('PASS native Rust timeline against',total,'JS reference clip samples');
