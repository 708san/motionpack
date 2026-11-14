/* Persistent, browser-free pose and opt-in semantic behavior sampler.
 * Trust boundary: init receives ONLY a manifest validated by Python's bounded
 * archive reader. The host may separately send a data-only behavior profile.
 * No scripts, DOM, arbitrary code, or external network access from archives.
 */
'use strict';
const readline=require('node:readline');
const Core=require('./headless_pose.js');
const Behavior=require('./behavior_engine.js');
const MAX_INIT_BYTES=2*1024*1024;
const MAX_COMMAND_BYTES=8192;
const MAX_FRAMES=100000;
let manifest=null,count=0,initialized=false,behavior=null;
const send=data=>{process.stdout.write(JSON.stringify(data)+'\n');};
const error=code=>send({type:'error',code});
const lines=readline.createInterface({input:process.stdin,crlfDelay:Infinity,terminal:false});
function exactKeys(command,allowed){
 if(Object.keys(command).some(key=>!allowed.includes(key)))
  throw new TypeError('unsupported request field');
}
function handle(command){
 if(++count>MAX_FRAMES){error('SESSION_LIMIT');lines.close();return;}
 switch(command.type){
  case 'sample': {
   exactKeys(command,['type','timeMs','clip','variant','ikTargets']);
   const frame=Core.sampleFrame(manifest,{
    timeMs:command.timeMs,clip:command.clip,variant:command.variant,
    ikTargets:command.ikTargets
   });
   send({type:'frame',frame});
   break;
  }
  case 'configureBehavior': {
   exactKeys(command,['type','profile']);
   // Profile is provided by the trusted host, not from the MotionPack asset.
   // Validate new instance before replacing the previous working configuration.
   const candidate=command.profile===null?null:Behavior.create(command.profile,manifest);
   behavior=candidate;
   send({type:'behaviorConfigured',enabled:!!behavior});
   break;
  }
  case 'act': {
   exactKeys(command,['type','action']);
   if(!behavior)throw new RangeError('behavior not configured');
   const action=behavior.resolve(command.action);
   send({type:'action',action});
   break;
  }
  case 'advanceBehavior': {
   exactKeys(command,['type','deltaMs']);
   if(!behavior)throw new RangeError('behavior not configured');
   const events=behavior.advance(command.deltaMs);
   send({type:'behaviorEvents',events});
   break;
  }
  case 'setAutonomy': {
   exactKeys(command,['type','enabled']);
   if(!behavior)throw new RangeError('behavior not configured');
   behavior.setAutonomy(command.enabled);
   send({type:'autonomy',enabled:behavior.getState().enabled});
   break;
  }
  default: throw new TypeError('unsupported command');
 }
}
lines.on('line',line=>{
 try{
  if(Buffer.byteLength(line,'utf8')>(initialized?MAX_COMMAND_BYTES:MAX_INIT_BYTES)){
   error('INPUT_TOO_LARGE');lines.close();return;
  }
  const command=JSON.parse(line);
  if(!command||typeof command!=='object'||Array.isArray(command))
   throw new TypeError('object required');
  if(!initialized){
   exactKeys(command,['manifest']);
   if(!command.manifest||typeof command.manifest!=='object'||
      Array.isArray(command.manifest))throw new TypeError('manifest required');
   manifest=command.manifest;initialized=true;
   send({type:'ready',protocol:'motionpack-pose',version:1});
   return;
  }
  handle(command);
 }catch(_){
  error('INVALID_REQUEST');
  if(!initialized)lines.close();
 }
});
