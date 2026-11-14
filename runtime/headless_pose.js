/* Headless, host-neutral pose-frame protocol v0: no DOM, graphics API or filesystem.
 * Consumes a manifest already validated by the Python isolated archive reader.
 * A frame is computed by the very same evaluator/IK solver as browser playback.
 */
'use strict';
const Evaluator=require('./evaluator.js');
const Rig=require('./rig.js');
const hasOwn=(obj,key)=>Object.prototype.hasOwnProperty.call(obj,key);
const finite=(value,label)=>{
 if(typeof value!=='number'||!Number.isFinite(value))throw new RangeError('invalid '+label);
 return value;
};
const affine=(n)=>{
 const r=finite(n.rotation??0,'rotation')*Math.PI/180;
 const scale=finite(n.scale??1,'scale');
 const cos=Math.cos(r)*scale,sin=Math.sin(r)*scale;
 return [cos,sin,-sin,cos,finite(n.x??0,'x'),finite(n.y??0,'y')];
};
const multiply=(a,b)=>[
 a[0]*b[0]+a[2]*b[1],a[1]*b[0]+a[3]*b[1],
 a[0]*b[2]+a[2]*b[3],a[1]*b[2]+a[3]*b[3],
 a[0]*b[4]+a[2]*b[5]+a[4],a[1]*b[4]+a[3]*b[5]+a[5]
];
const identity=[1,0,0,1,0,0];
function sampleFrame(manifest,options={}){
 if(!manifest||typeof manifest!=='object'||Array.isArray(manifest))
   throw new TypeError('validated manifest required');
 const timeMs=finite(options.timeMs??0,'timeMs');
 if(timeMs<0)throw new RangeError('negative timeMs');
 const pose=Evaluator.sample(manifest,{clip:options.clip,variant:options.variant,
   timeMs,ikTargets:options.ikTargets},Rig);
 const world=new Map(),visiting=new Set();
 function resolve(id){
  if(world.has(id))return world.get(id);
  if(visiting.has(id))throw new RangeError('cyclic node parenting');
  const n=pose.nodes.get(id);
  if(!n)throw new RangeError('unknown parent node');
  visiting.add(id);
  const parent=n.parent?resolve(n.parent):identity;
  const transform=multiply(parent,affine(n));
  visiting.delete(id);
  for(const v of transform)finite(v,'world transform');
  world.set(id,transform);
  return transform;
 }
 const nodes=[...pose.nodes.values()].map(n=>{
  const matrix=resolve(n.id);
  const width=finite(n.width??0,'width'),height=finite(n.height??0,'height');
  const anchor=n.anchor??[0.5,0.5];
  if(!Array.isArray(anchor)||anchor.length!==2)throw new RangeError('invalid node anchor');
  const local={x:finite(n.x??0,'x'),y:finite(n.y??0,'y'),
   rotation:finite(n.rotation??0,'rotation'),scale:finite(n.scale??1,'scale'),
   opacity:finite(n.opacity??1,'opacity')};
  return {id:n.id,parent:n.parent??null,asset:n.asset??null,
   z:finite(n.z??0,'z'),width,height,
   anchor:[finite(anchor[0],'anchor x'),finite(anchor[1],'anchor y')],
   local,world:matrix};
 }).sort((a,b)=>a.z-b.z);
 return {protocol:'motionpack-pose',version:1,clip:pose.clip,variant:pose.variant,
  time_ms:pose.timeMs,canvas:{width:manifest.canvas.width,
   height:manifest.canvas.height,background:manifest.canvas.background??null},
  nodes,effects:pose.effects.map(fx=>({...fx}))};
}
function parseInput(text){
 const command=JSON.parse(text);
 if(!command||typeof command!=='object'||Array.isArray(command)||
    !command.manifest||!command.options)throw new TypeError('invalid command');
 return sampleFrame(command.manifest,command.options);
}
if(require.main===module){
 // Never permit an archive to choose scripts. This fixed entrypoint accepts data only.
 const chunks=[];let size=0;
 process.stdin.on('data',chunk=>{
  size+=chunk.length;
  if(size>2*1024*1024){
   process.stderr.write('pose request exceeds 2 MiB\n');process.exit(2);
  }
  chunks.push(chunk);
 });
 process.stdin.on('end',()=>{
  try{process.stdout.write(JSON.stringify(parseInput(Buffer.concat(chunks).toString('utf8')))+'\n');}
  catch(error){process.stderr.write('invalid or unsupported pose request\n');process.exitCode=1;}
 });
}
module.exports=Object.freeze({sampleFrame,parseInput});
