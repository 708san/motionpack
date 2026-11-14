'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Headless=require('../runtime/headless_pose.js');
const Evaluator=require('../runtime/evaluator.js');
const Rig=require('../runtime/rig.js');
const ROOT=path.join(__dirname,'..');
function read(name){return JSON.parse(fs.readFileSync(path.join(ROOT,'examples',name,'manifest.json'),'utf8'));}
for(const name of ['robot_demo','robot_ik_demo','layered_plant_demo']){
 const manifest=read(name);
 for(const [clip,variant,timeMs] of [
  [manifest.defaults.clip,manifest.defaults.variant,0],
  [manifest.defaults.clip,manifest.defaults.variant,1234],
  [manifest.defaults.clip,manifest.defaults.variant,10000]
 ]){
  const raw=Evaluator.sample(manifest,{clip,variant,timeMs},Rig);
  const pose=Headless.sampleFrame(manifest,{clip,variant,timeMs});
  assert.equal(pose.protocol,'motionpack-pose');
  assert.equal(pose.version,1);
  assert.equal(pose.time_ms,raw.timeMs);
  assert.equal(pose.clip,raw.clip);
  assert.equal(pose.variant,raw.variant);
  assert.equal(pose.nodes.length,raw.nodes.size);
  assert.deepEqual(pose.effects,raw.effects);
  assert.equal(pose.nodes[0].z,Math.min(...[...raw.nodes.values()].map(n=>n.z??0)));
  for(const node of pose.nodes){
   const expected=raw.nodes.get(node.id);
   assert.equal(node.local.x,expected.x??0);
   assert.equal(node.local.y,expected.y??0);
   assert.equal(node.local.rotation,expected.rotation??0);
   assert.equal(node.asset,expected.asset??null);
   if(!expected.parent){
     assert.ok(Math.abs(node.world[4]-(expected.x??0))<1e-9);
     assert.ok(Math.abs(node.world[5]-(expected.y??0))<1e-9);
   }
  }
 }
}
const robot=read('robot_ik_demo');
const changed=Headless.sampleFrame(robot,{clip:'fire',variant:'form_b',timeMs:590});
assert.equal(changed.nodes.find(n=>n.id==='body').asset,'torso_power');
assert.ok(changed.effects.some(x=>x.kind==='beam'));
const original=JSON.stringify(robot);
const first=Headless.sampleFrame(robot,{timeMs:800});
const second=Headless.sampleFrame(robot,{timeMs:800});
assert.deepEqual(first,second);
assert.equal(JSON.stringify(robot),original,'manifest unchanged');
assert.throws(()=>Headless.sampleFrame(robot,{clip:'__proto__'}),/unknown clip/);
assert.throws(()=>Headless.sampleFrame(robot,{timeMs:-1}),/negative/);
const cycle=JSON.parse(JSON.stringify(robot));cycle.nodes.find(n=>n.id==='mech').parent='head';
assert.throws(()=>Headless.sampleFrame(cycle,{timeMs:0}),/cyclic/);
console.log('OK: browser-equivalent headless pose frames across clips, variants, IK and effects');
