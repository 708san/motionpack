'use strict';
// Full numeric scene parity: Rust integrated clip + variants + IK + parenting
// compared with the canonical headless JS renderer's pose-frame protocol.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {spawnSync}=require('node:child_process');
const Headless=require('../runtime/headless_pose.js');
const root=path.resolve(__dirname,'..');
const executable=path.join(root,'core','target','debug',
  'scene_probe'+(process.platform==='win32'?'.exe':''));
function compare(actual,reference,desc){
 assert(Number.isFinite(actual),desc+' must be finite');
 const tolerance=2e-7*Math.max(1,Math.abs(reference));
 assert(Math.abs(actual-reference)<=tolerance,
  desc+': Rust '+actual+' != JS '+reference);
}
function encode(manifest,clipName,variantName,time,overrides){
 const nodes=manifest.nodes;
 const index=new Map(nodes.map((node,i)=>[node.id,i]));
 const pieces=[time,nodes.length];
 for(const n of nodes){
  pieces.push(n.parent===undefined?-1:index.get(n.parent),
   n.x??0,n.y??0,n.rotation??0,n.scale??1,n.opacity??1);
 }
 const clip=manifest.clips[clipName];
 pieces.push(clip.duration_ms,clip.loop===true?1:0);
 const variant=manifest.variants[variantName];
 const entries=Object.entries(variant.nodes||{})
   .filter(([,v])=>['x','y','rotation','scale','opacity'].some(key=>Object.hasOwn(v,key)));
 pieces.push(entries.length);
 for(const [id,values] of entries){
  let mask=0;
  for(const [key,bit] of [['x',1],['y',2],['rotation',4],['scale',8],['opacity',16]]){
   if(Object.hasOwn(values,key))mask|=bit;
  }
  pieces.push(index.get(id),mask);
  for(const [key,bit] of [['x',1],['y',2],['rotation',4],['scale',8],['opacity',16]]){
   if(mask&bit)pieces.push(values[key]);
  }
 }
 const props=['x','y','rotation','scale','opacity'];
 pieces.push((clip.tracks||[]).length);
 for(const tr of clip.tracks||[]){
  pieces.push(index.get(tr.node),props.indexOf(tr.property),tr.keys.length);
  for(const key of tr.keys) pieces.push(key.time_ms,key.value);
 }
 const chains=manifest.iks||[];
 const ikIndex=new Map(chains.map((ik,i)=>[ik.id,i]));
 pieces.push(chains.length);
 for(const ik of chains){
  pieces.push(index.get(ik.upper),index.get(ik.lower),
   ik.lengths[0],ik.lengths[1],ik.target[0],ik.target[1],
   ik.bend??1,ik.weight??1);
 }
 pieces.push((clip.ik_tracks||[]).length);
 for(const tr of clip.ik_tracks||[]){
  pieces.push(ikIndex.get(tr.ik),tr.axis==='x'?0:1,tr.keys.length);
  for(const key of tr.keys)pieces.push(key.time_ms,key.value);
 }
 const overrideEntries=Object.entries(overrides||{});
 pieces.push(overrideEntries.length);
 for(const [id,p] of overrideEntries)pieces.push(ikIndex.get(id),p[0],p[1]);
 assert(pieces.every(x=>typeof x==='number'&&Number.isFinite(x)),
  'only finite numeric host fixture values allowed');
 return pieces.join(' ')+'\n';
}
let cases=0;
for(const example of ['robot_ik_demo','robot_demo','layered_plant_demo']){
 const manifest=JSON.parse(fs.readFileSync(
  path.join(root,'examples',example,'manifest.json'),'utf8'));
 for(const clipName of Object.keys(manifest.clips)){
  const clip=manifest.clips[clipName];
  for(const variantName of Object.keys(manifest.variants)){
   for(const t of [0,Math.floor(clip.duration_ms*0.23),
      Math.floor(clip.duration_ms*0.5),clip.duration_ms,
      clip.duration_ms+31]){
    const variations=[null];
    if(manifest.iks?.length)variations.push({
      [manifest.iks[0].id]:[760,320]
    });
    for(const targets of variations){
     const request=encode(manifest,clipName,variantName,t,targets);
     const run=spawnSync(executable,[],{encoding:'utf8',input:request,timeout:10000,
      maxBuffer:512*1024});
     assert.equal(run.status,0,example+'/'+clipName+': '+run.stderr);
     const lines=run.stdout.trim().split('\n');
     const expected=Headless.sampleFrame(manifest,{
      timeMs:t,clip:clipName,variant:variantName,ikTargets:targets
     });
     assert.equal(lines.length,expected.nodes.length+1);
     compare(Number(lines[0]),expected.time_ms,'clip time');
     // Headless output is z-sorted. Fixture keeps original manifest order.
     const byId=new Map(expected.nodes.map(n=>[n.id,n]));
     for(let i=0;i<manifest.nodes.length;i++){
      const actual=lines[i+1].trim().split(/\s+/).map(Number);
      assert.equal(actual.length,11);
      const node=byId.get(manifest.nodes[i].id);
      const reference=[node.local.x,node.local.y,node.local.rotation,
       node.local.scale,node.local.opacity,...node.world];
      reference.forEach((value,k)=>compare(actual[k],value,
       example+'/'+clipName+'/'+variantName+'/'+manifest.nodes[i].id+'/'+k+'@'+t));
     }
     cases++;
    }
   }
  }
 }
}
assert(cases>=50,'too few scene conformance cases: '+cases);
console.log('PASS integrated Rust scene versus JS reference:',cases,'frames');
