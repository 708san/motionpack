'use strict';
const assert=require('node:assert/strict');
const Director=require('../runtime/motion_director.js');
const manifest={nodes:[{id:'body'},{id:'eye'}]};
const base={timeMs:300,nodes:new Map([
 ['body',{id:'body',x:20,y:40,rotation:3,scale:1,opacity:0.8}],
 ['eye',{id:'eye',opacity:1}]
]),effects:[]};
const director=Director.create({channels:[
 {id:'sway',node:'body',property:'rotation',amplitude:6,periodMs:1000},
 {id:'breath',node:'body',property:'scale',amplitude:0.04,periodMs:2000,phase:0},
 {id:'blink',node:'eye',property:'opacity',amplitude:-1,periodMs:4000,kind:'pulse',width:0.1}
]},manifest);
const a=director.sample(base,250);
assert.equal(a.nodes.get('body').rotation,9);
assert.ok(a.nodes.get('body').scale>1);
assert.equal(a.nodes.get('eye').opacity,1);
assert.equal(base.nodes.get('body').rotation,3,'source pose must remain unchanged');
assert.notEqual(a.nodes.get('body'),base.nodes.get('body'));
assert.equal(director.sample(base,250).nodes.get('body').rotation,9,'same input deterministic');
assert.ok(Math.abs(director.sample(base,1250).nodes.get('body').rotation-9)<1e-10,'periodicity');
const blink=director.sample(base,200).nodes.get('eye').opacity;
assert.ok(Math.abs(blink)<1e-10,'blink pulse closes eye at midpoint');
assert.equal(director.sample(base,500).nodes.get('eye').opacity,1,'blink recovers');
const capped=Director.create({channels:[
 {id:'fade',node:'body',property:'opacity',amplitude:1,periodMs:1000},
 {id:'grow',node:'body',property:'scale',amplitude:1,periodMs:1000,blend:'multiply'}
]},manifest).sample(base,250);
assert.equal(capped.nodes.get('body').opacity,1,'opacity clamped');
assert.equal(capped.nodes.get('body').scale,2);
for(const channel of [
 {id:'unknown',node:'bogus',property:'x',amplitude:2,periodMs:1000},
 {id:'bad',node:'body',property:'code',amplitude:1,periodMs:1000},
 {id:'bad',node:'body',property:'rotation',amplitude:100,periodMs:1000},
 {id:'bad',node:'body',property:'x',amplitude:1,periodMs:0},
 {id:'bad',node:'body',property:'x',amplitude:1,periodMs:1000,weight:2}
])assert.throws(()=>Director.create({channels:[channel]},manifest));
assert.throws(()=>Director.create({channels:Array.from({length:65},(_,i)=>({
 id:'c'+i,node:'body',property:'x',amplitude:1,periodMs:1000}))},manifest));
assert.throws(()=>director.sample(base,-1));
console.log('OK: bounded, layered, deterministic motion director');
