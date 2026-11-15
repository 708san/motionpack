'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Headless=require('../runtime/headless_pose.js');
const {createWasmSceneSampler}=require('../runtime/wasm_scene_host.js');
const root=path.resolve(__dirname,'..');
function compare(a,b,name){
 if(typeof b==='number'){
  assert(Number.isFinite(a)&&Math.abs(a-b)<=2e-7*Math.max(1,Math.abs(b)),
    name+' Wasm='+a+' JS='+b);
 }else assert.deepEqual(a,b,name);
}
async function main(){
 const wasm=fs.readFileSync(path.join(root,'core/target/wasm32-unknown-unknown/release/motionpack_core.wasm'));
 const instantiated=await WebAssembly.instantiate(wasm,{});
 const sample=createWasmSceneSampler(instantiated.instance.exports);
 let count=0;
 for(const example of ['robot_ik_demo','robot_demo','layered_plant_demo']){
  const manifest=JSON.parse(fs.readFileSync(path.join(root,'examples',example,'manifest.json'),'utf8'));
  for(const [clip,info] of Object.entries(manifest.clips)){
   for(const variant of Object.keys(manifest.variants)){
    for(const timeMs of [0,info.duration_ms*0.26,info.duration_ms,
      info.duration_ms+51]){
     const targets=[null];
     if(manifest.iks?.length)targets.push({[manifest.iks[0].id]:[760,320]});
     for(const ikTargets of targets){
      const a=sample(manifest,{clip,variant,timeMs,ikTargets});
      const b=Headless.sampleFrame(manifest,{clip,variant,timeMs,ikTargets});
      compare(a.protocol,b.protocol,'protocol');
      compare(a.version,b.version,'version');
      compare(a.clip,b.clip,'clip');compare(a.variant,b.variant,'variant');
      compare(a.time_ms,b.time_ms,'time');
      assert.deepEqual(a.canvas,b.canvas);
      assert.equal(a.nodes.length,b.nodes.length);
      for(let i=0;i<b.nodes.length;i++){
       const left=a.nodes[i],right=b.nodes[i];
       for(const key of ['id','parent','asset','z','width','height','anchor'])
        compare(left[key],right[key],key);
       for(const key of ['x','y','rotation','scale','opacity'])
        compare(left.local[key],right.local[key],left.id+' '+key);
       for(let j=0;j<6;j++)compare(left.world[j],right.world[j],left.id+' world '+j);
      }
      assert.equal(a.effects.length,b.effects.length);
      for(let j=0;j<a.effects.length;j++){
       const left=a.effects[j],right=b.effects[j];
       assert.deepEqual(Object.keys(left),Object.keys(right));
       for(const key of Object.keys(right))compare(left[key],right[key],'effect '+key);
      }
      count++;
     }
    }
   }
  }
 }
 assert(count>=50,'expected at least 50 frames from real assets');
 const manifest=JSON.parse(fs.readFileSync(
  path.join(root,'examples/robot_ik_demo/manifest.json'),'utf8'));
 assert.throws(()=>sample(manifest,{clip:'nonexistent'}),/unknown clip/);
 assert.throws(()=>sample(manifest,{timeMs:-1}),/invalid time/);
 assert.throws(()=>sample(manifest,{ikTargets:{bad:[0,0]}}),/invalid IK target/);
 // Confirm the same Wasm instance can sample again after invalid host input.
 assert.equal(sample(manifest,{clip:'idle',timeMs:123}).protocol,'motionpack-pose');
 console.log('PASS: Wasm full-node pose parity across',count,'frames and 3 reusable .motionpack sources');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
