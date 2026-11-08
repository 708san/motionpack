const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const root=path.resolve(__dirname,'..'),m=JSON.parse(fs.readFileSync(path.join(root,'examples/robot_demo/manifest.json'),'utf8'));
const ctx=new Proxy({}, {get(t,k){if(k==='canvas')return {width:800,height:1000};if(typeof t[k]==='function')return t[k];return ()=>{};},set(t,k,v){t[k]=v;return true;}});
const controls={stage:{getContext(){return ctx;},addEventListener(){},getBoundingClientRect(){return {left:0,top:0,width:800,height:1000};}},viewport:{style:{}},status:{textContent:''},idle:{},fire:{},transform:{},reset:{},aim:{textContent:''}};
const frames=[];let time=0;
const sandbox={window:{__MOTIONPACK__:m},document:{getElementById(id){return controls[id];},body:{}},performance:{now(){return time;}},requestAnimationFrame(f){frames.push(f);},Image:class {constructor(){this.complete=true;this.naturalWidth=100;this.width=100;this.height=100;}set src(x){this._src=x;}get src(){return this._src;}},Math,Map,Set,console};
sandbox.window.MotionPackRig=require(path.join(root,'runtime/rig.js'));
sandbox.window.MotionPackEvaluator=require(path.join(root,'runtime/evaluator.js'));
sandbox.window.MotionPackPlayerController=require(path.join(root,'runtime/player_controller.js'));
sandbox.window.MotionPackViewportAdapter=require(path.join(root,'runtime/viewport_adapter.js'));
vm.runInNewContext(fs.readFileSync(path.join(root,'runtime/viewer.js'),'utf8'),sandbox);
function frame(ms){time=ms;const fn=frames.shift();assert(fn,'no animation frame');fn(ms);}
frame(0);assert(controls.status.textContent.includes('idle'));
controls.fire.onclick();frame(650);assert(controls.status.textContent.includes('fire'));
controls.transform.onclick();frame(1600);assert(controls.status.textContent.includes('transform'));
frame(3000);assert(controls.status.textContent.includes('form_b'));
controls.reset.onclick();frame(5100);assert(controls.status.textContent.includes('form_a'));
assert(typeof sandbox.window.MotionPackPlayer.playClip==='function');
if(m.iks){controls.aim.onclick();assert(controls.aim.textContent.includes('ON'));}
console.log('OK: robot_demo runtime smoke');
