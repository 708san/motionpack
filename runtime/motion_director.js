/* Deterministic host-side procedural motion overlays for experimental MotionPack.
 * Data-only config. No timers, DOM, audio, random input, eval, or manifest schema changes.
 */
(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  else root.MotionPackMotionDirector=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
const PROPERTIES=Object.freeze({x:200,y:200,rotation:45,scale:1,opacity:1});
const hasOwn=(o,k)=>Object.prototype.hasOwnProperty.call(o,k);
function requireNumber(value,label,min,max){
 if(typeof value!=='number'||!Number.isFinite(value)||value<min||value>max)
   throw new RangeError('invalid '+label);
 return value;
}
function create(profile,manifest){
 if(!profile||typeof profile!=='object'||Array.isArray(profile)||
    !Array.isArray(profile.channels)||profile.channels.length>64)
   throw new TypeError('motion profile requires up to 64 channels');
 if(!manifest||!Array.isArray(manifest.nodes))
   throw new TypeError('a validated manifest with nodes is required');
 const nodeIds=new Set(manifest.nodes.map(node=>node.id));
 const ids=new Set();
 const channels=profile.channels.map((input,index)=>{
   if(!input||typeof input!=='object'||Array.isArray(input))
     throw new TypeError('invalid motion channel');
   const id=input.id;
   if(typeof id!=='string'||!id||id.length>64||ids.has(id))
     throw new RangeError('invalid or duplicate motion channel id');
   ids.add(id);
   if(typeof input.node!=='string'||!nodeIds.has(input.node))
     throw new RangeError('motion channel target is unknown');
   if(!hasOwn(PROPERTIES,input.property))
     throw new RangeError('unsupported motion channel property');
   const kind=input.kind??'sine';
   if(kind!=='sine'&&kind!=='pulse')
     throw new RangeError('unsupported motion channel waveform');
   const blend=input.blend??'add';
   if(blend!=='add'&&blend!=='multiply')
     throw new RangeError('unsupported motion channel blend');
   const amplitude=requireNumber(input.amplitude,'amplitude',-PROPERTIES[input.property],PROPERTIES[input.property]);
   const periodMs=requireNumber(input.periodMs,'periodMs',250,60000);
   const phase=requireNumber(input.phase??0,'phase',0,1);
   const weight=requireNumber(input.weight??1,'weight',0,1);
   const width=requireNumber(input.width??0.12,'pulse width',0.01,1);
   const priority=requireNumber(input.priority??0,'priority',-100,100);
   return Object.freeze({id,node:input.node,property:input.property,kind,blend,
     amplitude,periodMs,phase,weight,width,priority,index});
 });
 channels.sort((a,b)=>a.priority-b.priority||a.index-b.index);
 function sample(basePose,timeMs){
  requireNumber(timeMs,'motion time',0,Number.MAX_SAFE_INTEGER);
  if(!basePose||!(basePose.nodes instanceof Map))
    throw new TypeError('a sampled MotionPack pose is required');
  const nodes=new Map(basePose.nodes);
  for(const channel of channels){
   const source=nodes.get(channel.node);
   if(!source)throw new RangeError('missing pose node');
   const phase=((timeMs/channel.periodMs+channel.phase)%1+1)%1;
   const oscillation=channel.kind==='sine'?Math.sin(2*Math.PI*phase):
     (phase<channel.width?Math.sin(Math.PI*phase/channel.width)**2:0);
   const change=channel.amplitude*channel.weight*oscillation;
   const current=source[channel.property]??(channel.property==='scale'||channel.property==='opacity'?1:0);
   const result=channel.blend==='multiply'?current*(1+change):current+change;
   const value=channel.property==='opacity'?Math.max(0,Math.min(1,result)):
     channel.property==='scale'?Math.max(0.05,Math.min(10,result)):result;
   nodes.set(channel.node,{...source,[channel.property]:value});
  }
  return {...basePose,nodes};
 }
 return Object.freeze({sample,channelCount:channels.length});
}
return Object.freeze({create});
});
