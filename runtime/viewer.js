/* MotionPack experimental offline Canvas2D renderer, animation player and visual effects */
(function(){
'use strict';
const S=window.__MOTIONPACK__,Rig=window.MotionPackRig,Evaluator=window.MotionPackEvaluator;
if(!S){document.body.textContent='Missing MotionPack asset';return;}
const canvas=document.getElementById('stage'),ctx=canvas.getContext('2d');canvas.width=S.canvas.width;canvas.height=S.canvas.height;
let assetDecodeFailed=false;
const reportAssetDecodeFailure=()=>{if(assetDecodeFailed)return;assetDecodeFailed=true;const status=document.getElementById('asset-error');if(status){status.textContent='Image decode failed';status.hidden=false;}};
const images={};for(const [id,src] of Object.entries(S.assets)){const im=new Image();im.onerror=reportAssetDecodeFailure;im.src=src;images[id]=im;}
let clip=S.defaults.clip,variant=S.defaults.variant,started=performance.now(),transition=null,pointerIK=false,pointer=null;
const clamp=(n,a,b)=>Math.max(a,Math.min(b,n)),mix=(a,b,t)=>a+(b-a)*t,identity={a:1,b:0,c:0,d:1,e:0,f:0};
function mm(a,b){return {a:a.a*b.a+a.c*b.b,b:a.b*b.a+a.d*b.b,c:a.a*b.c+a.c*b.d,d:a.b*b.c+a.d*b.d,e:a.a*b.e+a.c*b.f+a.e,f:a.b*b.e+a.d*b.f+a.f};}
function matrix(n){const r=(n.rotation||0)*Math.PI/180,s=n.scale??1;return {a:Math.cos(r)*s,b:Math.sin(r)*s,c:-Math.sin(r)*s,d:Math.cos(r)*s,e:n.x||0,f:n.y||0};}
function frame(time){
 let active=S.clips[clip],t=time-started;
 if(active.loop)t=((t%active.duration_ms)+active.duration_ms)%active.duration_ms;
 else if(t>active.duration_ms){if(transition){variant=transition;transition=null;}clip=S.defaults.clip;started=time;active=S.clips[clip];t=0;}
 const pose=Evaluator.sample(S,{clip,variant,timeMs:t,ikTargets:pointerIK&&pointer&&S.iks?.length?{[S.iks[0].id]:pointer}:{}},Rig);
 const nodes=pose.nodes;
 const world=new Map();
 function resolve(id){if(world.has(id))return world.get(id);const n=nodes.get(id);const m=mm(n.parent?resolve(n.parent):identity,matrix(n));world.set(id,m);return m;}
 function point(id,offset=[0,0]){const m=resolve(id);return [m.a*offset[0]+m.c*offset[1]+m.e,m.b*offset[0]+m.d*offset[1]+m.f];}
 ctx.clearRect(0,0,canvas.width,canvas.height);
 if(S.canvas.background){ctx.fillStyle=S.canvas.background;ctx.fillRect(0,0,canvas.width,canvas.height);}
 for(const n of [...nodes.values()].sort((a,b)=>(a.z||0)-(b.z||0))){if(!n.asset)continue;const im=images[n.asset];if(!im?.complete||!im.naturalWidth)continue;
 const m=resolve(n.id);ctx.save();ctx.transform(m.a,m.b,m.c,m.d,m.e,m.f);ctx.globalAlpha=clamp(n.opacity??1,0,1);
 ctx.drawImage(im,-(n.anchor?.[0]??.5)*(n.width||im.width),-(n.anchor?.[1]??.5)*(n.height||im.height),n.width||im.width,n.height||im.height);ctx.restore();}
 for(const fx of pose.effects){const age=fx.age_ms;
 const u=age/fx.duration_ms,pos=point(fx.node,fx.offset||[0,0]),color=fx.color||'#8ff1ff';
 ctx.save();ctx.strokeStyle=color;ctx.fillStyle=color;ctx.shadowColor=color;
 if(fx.kind==='beam'){const end=fx.target||[canvas.width-50,canvas.height/3],g=clamp(u*5,0,1),tip=[mix(pos[0],end[0],g),mix(pos[1],end[1],g)];ctx.lineCap='round';
 for(const width of [32,16,6]){ctx.globalAlpha=(1-u)*(.4+1/(width/3));ctx.lineWidth=width;ctx.shadowBlur=width;ctx.beginPath();ctx.moveTo(...pos);ctx.lineTo(...tip);ctx.stroke();}}
 else if(fx.kind==='ring'){ctx.globalAlpha=1-u;ctx.lineWidth=5;ctx.beginPath();ctx.arc(...pos,12+u*(fx.radius||180),0,2*Math.PI);ctx.stroke();}
 else if(fx.kind==='burst'){ctx.globalAlpha=1-u;const count=Math.min(fx.count||28,200);for(let i=0;i<count;i++){const a=i*2.399963+(fx.seed||0),r=u*(fx.radius||130)*(.45+(i*37%100)/160);ctx.beginPath();ctx.arc(pos[0]+r*Math.cos(a),pos[1]+r*Math.sin(a),2+i%4,0,2*Math.PI);ctx.fill();}}
 ctx.restore();}
 document.getElementById('status').textContent=clip+' | '+variant+' | '+Math.round(t)+' ms';requestAnimationFrame(frame);
}
function playClip(name,next){if(!S.clips[name])return;clip=name;started=performance.now();transition=next||null;}
document.getElementById('idle').onclick=()=>playClip('idle');
document.getElementById('fire').onclick=()=>playClip('fire');
document.getElementById('transform').onclick=()=>playClip('transform',variant==='form_a'?'form_b':'form_a');
document.getElementById('reset').onclick=()=>{variant=S.defaults.variant;playClip(S.defaults.clip);};
const aim=document.getElementById('aim');if(aim&&S.iks?.length)aim.onclick=()=>{pointerIK=!pointerIK;pointer=null;aim.textContent=pointerIK?'Pointer IK: ON':'Pointer IK: OFF';};
canvas.addEventListener?.('pointermove',e=>{if(!pointerIK)return;const r=canvas.getBoundingClientRect();pointer=[(e.clientX-r.left)*canvas.width/r.width,(e.clientY-r.top)*canvas.height/r.height];});
canvas.addEventListener?.('pointerleave',()=>{pointer=null;});
window.MotionPackPlayer=Object.freeze({playClip,setVariant:name=>{if(S.variants[name])variant=name;},playTransition:playClip,setPointerIK:v=>{pointerIK=!!v;pointer=null;},getState:()=>({clip,variant,pointerIK})});
requestAnimationFrame(frame);
})();
