/* Optional host-owned semantic action mapping and bounded stochastic ambient events.
 * No manifest schema changes, timers, DOM, scripts or Math.random().
 * The host chooses whether to apply suggested actions to its timeline.
 */
(function(root,factory){
 const api=factory();
 if(typeof module==='object'&&module.exports)module.exports=api;
 else root.MotionPackBehavior=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
const own=(o,k)=>Object.prototype.hasOwnProperty.call(o,k);
const number=(v,min,max,name)=>{
 if(typeof v!=='number'||!Number.isFinite(v)||v<min||v>max)throw new RangeError('invalid '+name);
 return v;
};
const LABEL=/^[a-z][a-z0-9_-]{0,47}$/;
function create(profile,manifest){
 if(!profile||typeof profile!=='object'||Array.isArray(profile)||!manifest||typeof manifest!=='object')throw new TypeError('behavior profile and manifest required');
 if(Object.keys(profile).some(k=>!['actions','ambient','seed'].includes(k)))throw new TypeError('unknown behavior option');
 const actions=profile.actions;
 if(!actions||typeof actions!=='object'||Array.isArray(actions))throw new TypeError('actions object required');
 const names=Object.keys(actions);
 if(names.length>64)throw new RangeError('too many semantic actions');
 const definitions=new Map();
 for(const name of names){
  if(!LABEL.test(name))throw new RangeError('invalid action name');
  const d=actions[name];
  if(!d||typeof d!=='object'||Array.isArray(d)||Object.keys(d).some(k=>!['clip','variant'].includes(k)))throw new TypeError('invalid action definition');
  if(typeof d.clip!=='string'||!own(manifest.clips||{},d.clip))throw new RangeError('unknown action clip');
  if(d.variant!==undefined && (typeof d.variant!=='string'||!own(manifest.variants||{},d.variant)))throw new RangeError('unknown action variant');
  definitions.set(name,Object.freeze({clip:d.clip,variant:d.variant??null,action:name}));
 }
 const seed=number(profile.seed??1,0,4294967295,'seed')>>>0;
 let rng=seed||0x9e3779b9;
 function random(){
  rng^=rng<<13;rng^=rng>>>17;rng^=rng<<5;
  return (rng>>>0)/4294967296;
 }
 let ambient=null;
 if(profile.ambient!==undefined){
  const a=profile.ambient;
  if(!a||typeof a!=='object'||Array.isArray(a)||Object.keys(a).some(k=>!['minIntervalMs','maxIntervalMs','choices'].includes(k)))throw new TypeError('invalid ambient configuration');
  const min=number(a.minIntervalMs,1000,120000,'minimum interval');
  const max=number(a.maxIntervalMs,min,120000,'maximum interval');
  if(!Array.isArray(a.choices)||a.choices.length===0||a.choices.length>16)throw new RangeError('invalid ambient choices');
  let total=0;
  const choices=a.choices.map(item=>{
   if(!item||typeof item!=='object'||Array.isArray(item)||Object.keys(item).some(k=>!['action','weight'].includes(k)))throw new TypeError('invalid ambient choice');
   if(typeof item.action!=='string'||!definitions.has(item.action))throw new RangeError('unknown ambient action');
   const weight=number(item.weight??1,0.01,100,'choice weight');
   total+=weight;
   return Object.freeze({action:item.action,weight});
  });
  ambient={min,max,choices,total};
 }
 let now=0,enabled=!!ambient,nextAt=ambient?ambient.min+Math.floor(random()*(ambient.max-ambient.min+1)):Infinity;
 function resolve(action){
  if(typeof action!=='string'||!LABEL.test(action))return null;
  const found=definitions.get(action);
  return found?{...found}:null;
 }
 function advance(deltaMs){
  number(deltaMs,0,60000,'deltaMs');
  now+=deltaMs;
  const events=[];
  if(!ambient)return events;
  // Scheduler advances whether or not autonomy is enabled: disabling must not
  // accumulate events that fire all at once when re-enabled.
  let scanned=0;
  while(nextAt<=now){
   if(++scanned>64)throw new RangeError('ambient event budget exceeded');
   const target=random()*ambient.total;
   let cumulative=0,choice=ambient.choices[ambient.choices.length-1];
   for(const option of ambient.choices){cumulative+=option.weight;if(target<cumulative){choice=option;break;}}
   if(enabled)events.push({...definitions.get(choice.action),scheduledAtMs:nextAt});
   nextAt+=ambient.min+Math.floor(random()*(ambient.max-ambient.min+1));
  }
  return events;
 }
 return Object.freeze({
  resolve,advance,
  setAutonomy:value=>{if(typeof value!=='boolean')throw new TypeError('autonomy flag must be boolean');enabled=value&&!!ambient;},
  getState:()=>({enabled,elapsedMs:now,nextAmbientAtMs:ambient?nextAt:null,actions:names.slice()})
 });
}
return Object.freeze({create});
});
