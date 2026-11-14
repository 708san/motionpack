'use strict';
const assert=require('node:assert/strict');
const Behavior=require('../runtime/behavior_engine.js');
const manifest={clips:Object.create(null),variants:Object.create(null)};
manifest.clips.idle={};manifest.clips.wave={};manifest.clips.blink={};manifest.clips.celebrate={};
manifest.variants.default={};manifest.variants.happy={};
const profile={seed:123,actions:{
 greet:{clip:'wave'},happy:{clip:'celebrate',variant:'happy'},blink:{clip:'blink'}
},ambient:{minIntervalMs:1000,maxIntervalMs:3000,choices:[
 {action:'blink',weight:3},{action:'greet',weight:1}
]}};
const x=Behavior.create(profile,manifest);
assert.deepEqual(x.resolve('greet'),{clip:'wave',variant:null,action:'greet'});
assert.deepEqual(x.resolve('happy'),{clip:'celebrate',variant:'happy',action:'happy'});
assert.equal(x.resolve('unknown'),null);
assert.equal(x.resolve('__proto__'),null);
const a=Behavior.create(profile,manifest),b=Behavior.create(profile,manifest);
let eventsA=[],eventsB=[];
for(let i=0;i<180;i++){
 eventsA.push(...a.advance(200));
 eventsB.push(...b.advance(200));
}
assert.deepEqual(eventsA,eventsB,'same seed and same ticks must yield identical events');
assert(eventsA.length>5,'ambient scheduler produces gestures');
assert(eventsA.some(e=>e.action==='blink'));
assert(eventsA.every(e=>['wave','blink'].includes(e.clip)));
const intervals=eventsA.slice(1).map((e,i)=>e.scheduledAtMs-eventsA[i].scheduledAtMs);
assert(intervals.every(d=>d>=1000&&d<=3000),'nonperiodic intervals are bounded');
assert(new Set(intervals).size>1,'scheduled intervals are not a fixed repeating loop');
const frozen=Behavior.create(profile,manifest);
frozen.setAutonomy(false);
assert.deepEqual(frozen.advance(30000),[],'disabled autonomy cannot trigger ambient');
frozen.setAutonomy(true);
const resumed=frozen.advance(2000);
assert(resumed.length<=2,'re-enable does not dump previously suppressed gestures');
assert.deepEqual(profile.actions.greet,{clip:'wave'},'profile is unchanged');
const plain=Behavior.create({actions:{greet:{clip:'wave'}}},manifest);
assert.deepEqual(plain.advance(60000),[],'semantic actions do not automatically enable autonomy');
assert.deepEqual(plain.resolve('greet'),{clip:'wave',variant:null,action:'greet'});
for(const malformed of [
 {actions:{bad:{clip:'missing'}}},
 {actions:{'__proto__':{clip:'idle'}}},
 {actions:{greet:{clip:'wave',script:'evil'}}},
 {actions:{greet:{clip:'wave'}},ambient:{minIntervalMs:0,maxIntervalMs:2000,choices:[{action:'greet'}]}},
 {actions:{greet:{clip:'wave'}},ambient:{minIntervalMs:1000,maxIntervalMs:2000,choices:[{action:'bad'}]}}
]){
 if(Object.keys(malformed.actions).length===0)continue; // object-literal prototype key is not an own property
 assert.throws(()=>Behavior.create(malformed,manifest));
}
assert.throws(()=>plain.advance(Infinity),/deltaMs/);
assert.throws(()=>plain.setAutonomy('true'),/boolean/);
const prototypeAttempt=JSON.parse('{"actions":{"__proto__":{"clip":"idle"}}}');
assert.throws(()=>Behavior.create(prototypeAttempt,manifest),/invalid action/);
console.log('OK: safe semantic resolution, deterministic bounded nonperiodic ambient actions, explicit opt-in');
