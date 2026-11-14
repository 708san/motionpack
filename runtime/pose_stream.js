/* Persistent, data-only MotionPack pose sampler for trusted host processes.
 * Input: one JSON initialization line with {manifest}, followed by JSON command
 * lines. Output: {type:"ready"}, then one {type:"frame",frame} or generic error
 * per command. The package is validated separately by the isolated reader.
 */
'use strict';
const readline=require('node:readline');
const Core=require('./headless_pose.js');
const MAX_INIT_BYTES=2*1024*1024;
const MAX_COMMAND_BYTES=8192;
const MAX_FRAMES=100000;
let manifest=null,count=0,initialized=false;
const send=data=>{process.stdout.write(JSON.stringify(data)+'\n');};
const error=code=>send({type:'error',code});
const lines=readline.createInterface({input:process.stdin,crlfDelay:Infinity,terminal:false});
lines.on('line',line=>{
 try{
  if(Buffer.byteLength(line,'utf8')>(initialized?MAX_COMMAND_BYTES:MAX_INIT_BYTES)){
   error('INPUT_TOO_LARGE');lines.close();return;
  }
  const command=JSON.parse(line);
  if(!command||typeof command!=='object'||Array.isArray(command))throw Error('object required');
  if(!initialized){
   if(!command.manifest||typeof command.manifest!=='object'||Array.isArray(command.manifest))throw Error('manifest required');
   manifest=command.manifest;initialized=true;
   send({type:'ready',protocol:'motionpack-pose',version:1});
   return;
  }
  if(++count>MAX_FRAMES){error('SESSION_LIMIT');lines.close();return;}
  if(command.type!=='sample')throw Error('unsupported command');
  const keys=Object.keys(command);
  if(keys.some(k=>!['type','timeMs','clip','variant','ikTargets'].includes(k)))throw Error('unsupported request field');
  const frame=Core.sampleFrame(manifest,{
   timeMs:command.timeMs,clip:command.clip,variant:command.variant,ikTargets:command.ikTargets
  });
  send({type:'frame',frame});
 }catch(_){
  error('INVALID_REQUEST');
  if(!initialized)lines.close();
 }
});
