'use strict';
// Native and WebAssembly Rust two-bone IK numerical parity against the
// existing JavaScript solver. The Rust code is not yet wired into full poses.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {spawnSync}=require('node:child_process');
const Rig=require('../runtime/rig.js');
const root=path.resolve(__dirname,'..');
const native=path.join(root,'core','target','debug',
  'motionpack_core_probe'+(process.platform==='win32'?'.exe':''));
const wasm=path.join(root,'core','target','wasm32-unknown-unknown','release','motionpack_core.wasm');
const mode=process.argv[2];
assert(['native','wasm'].includes(mode),'native or wasm test mode required');
function near(a,b,label){
 assert(Number.isFinite(a)&&Number.isFinite(b),label+' finite');
 assert(Math.abs(a-b)<1e-7*Math.max(1,Math.abs(b)),
  label+': Rust '+a+' != JS '+b);
}
async function main(){
 let exports=null;
 if(mode==='wasm'){
  const instance=await WebAssembly.instantiate(fs.readFileSync(wasm),{});
  exports=instance.instance.exports;
  assert.equal(typeof exports.mp_ik_upper_deg,'function');
  assert.equal(typeof exports.mp_ik_lower_deg,'function');
 }
 const cases=[
  [0,0,150,20,115,105,-1],
  [0,0,150,20,115,105,1],
  [0,0,1000,0,115,105,-1],
  [0,0,0,0,115,105,1],
  [0,0,0,0,115,105,-1],
  [100,-88,805,410,115,105,-1],
  [100,-88,860,350,115,105,1],
  [20,30,35,50,40,30,1],
  [-20,-40,-35,-80,50,50,-1],
  [0,0,0.01,0.04,30,20,1],
 ];
 for(let i=0;i<25;i++){
  const ox=(i-12)*11,oy=(i%7)*-17;
  const tx=ox+Math.cos(i*0.49)*120;
  const ty=oy+Math.sin(i*0.49)*70;
  cases.push([ox,oy,tx,ty,115+(i%3)*8,105+(i%4)*5,i%2?1:-1]);
 }
 let tests=0;
 for(const values of cases){
  const [ox,oy,tx,ty,l1,l2,bend]=values;
  const expected=Rig.solveTwoBone([ox,oy],[tx,ty],l1,l2,bend);
  if(mode==='native'){
   const result=spawnSync(native,['ik',...values.map(String)],
      {encoding:'utf8',timeout:5000});
   assert.equal(result.status,0,result.stderr||'native IK probe failed');
   const parts=result.stdout.trim().split(/\s+/).map(Number);
   assert.equal(parts.length,8);
   for(const [k,index] of [
    ['upperDeg',0],['lowerDeg',1],['clampedDistance',6]
   ]) near(parts[index],expected[k],k);
   for(const [name,offset] of [['elbow',2],['hand',4]]){
    near(parts[offset],expected[name][0],name+'.x');
    near(parts[offset+1],expected[name][1],name+'.y');
   }
   assert.equal(parts[7],expected.reached?1:0,'reached flag');
  }else{
   near(exports.mp_ik_upper_deg(...values),expected.upperDeg,'Wasm upper');
   near(exports.mp_ik_lower_deg(...values),expected.lowerDeg,'Wasm lower');
  }
  tests++;
 }
 if(mode==='wasm'){
  assert(Number.isNaN(exports.mp_ik_upper_deg(0,0,0,0,0,1,1)),
    'reject zero-length arm');
  assert(Number.isNaN(exports.mp_ik_lower_deg(NaN,0,0,0,1,1,1)),
    'reject non-finite inputs');
 }
 console.log('PASS',mode,'IK numerical conformance',tests,'two-bone cases');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
