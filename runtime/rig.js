/* MotionPack 0.2: deterministic two-bone inverse kinematics, no dependencies */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.MotionPackRig=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
function solveTwoBone(origin,target,length1,length2,bend=1){
 if(![...origin,...target,length1,length2,bend].every(Number.isFinite)||length1<=0||length2<=0)throw Error('Invalid IK parameters');
 const dx=target[0]-origin[0],dy=target[1]-origin[1],raw=Math.hypot(dx,dy);
 const distance=clamp(raw,Math.abs(length1-length2)+1e-5,length1+length2-1e-5),dir=raw>1e-10?Math.atan2(dy,dx):0;
 const alpha=Math.acos(clamp((length1**2+distance**2-length2**2)/(2*length1*distance),-1,1));
 const a=dir+(bend>=0?1:-1)*alpha,elbow=[origin[0]+length1*Math.cos(a),origin[1]+length1*Math.sin(a)];
 const b=Math.atan2(origin[1]+distance*Math.sin(dir)-elbow[1],origin[0]+distance*Math.cos(dir)-elbow[0]);
 const hand=[elbow[0]+length2*Math.cos(b),elbow[1]+length2*Math.sin(b)];
 return {upperDeg:a*180/Math.PI,lowerDeg:(b-a)*180/Math.PI,elbow,hand,reached:Math.abs(raw-distance)<.01,clampedDistance:distance};
}
const identity={a:1,b:0,c:0,d:1,e:0,f:0};
function matrix(n){const a=(n.rotation||0)*Math.PI/180,s=n.scale??1;return {a:Math.cos(a)*s,b:Math.sin(a)*s,c:-Math.sin(a)*s,d:Math.cos(a)*s,e:n.x||0,f:n.y||0};}
function multiply(a,b){return {a:a.a*b.a+a.c*b.b,b:a.b*b.a+a.d*b.b,c:a.a*b.c+a.c*b.d,d:a.b*b.c+a.d*b.d,e:a.a*b.e+a.c*b.f+a.e,f:a.b*b.e+a.d*b.f+a.f};}
function inversePoint(m,p){const det=m.a*m.d-m.b*m.c;if(Math.abs(det)<1e-10)throw Error('Noninvertible parent');const x=p[0]-m.e,y=p[1]-m.f;return [(m.d*x-m.c*y)/det,(-m.b*x+m.a*y)/det];}
function applyIK(nodes,iks,targets={}){
 const cache=new Map();
 function resolve(id){if(cache.has(id))return cache.get(id);const n=nodes.get(id);if(!n)throw Error('Missing node '+id);const m=multiply(n.parent?resolve(n.parent):identity,matrix(n));cache.set(id,m);return m;}
 for(const ik of iks){cache.clear();const upper=nodes.get(ik.upper),lower=nodes.get(ik.lower);if(!upper||!lower||lower.parent!==upper.id)throw Error('Invalid IK chain');
 const parent=upper.parent?resolve(upper.parent):identity,goal=inversePoint(parent,targets[ik.id]||ik.target);
 const s=solveTwoBone([upper.x||0,upper.y||0],goal,ik.lengths[0],ik.lengths[1],ik.bend||1),w=clamp(ik.weight??1,0,1);
 upper.rotation=(upper.rotation||0)*(1-w)+s.upperDeg*w;lower.x=ik.lengths[0];lower.y=0;lower.rotation=(lower.rotation||0)*(1-w)+s.lowerDeg*w;
 }
}
return {solveTwoBone,applyIK};
});