const assert=require('assert');
const R=require('../runtime/rig.js');
const near=(a,b,t=.02)=>assert(Math.abs(a-b)<t, 'expected '+a+' near '+b);
for(const bend of [-1,1]){
 const s=R.solveTwoBone([0,0],[120,30],100,80,bend);
 near(s.hand[0],120);near(s.hand[1],30);near(Math.hypot(...s.elbow),100);
 assert.deepStrictEqual(s,R.solveTwoBone([0,0],[120,30],100,80,bend));
}
const far=R.solveTwoBone([0,0],[1000,0],100,80,-1);
assert(!far.reached);near(Math.hypot(...far.hand),180);
const nodes=new Map([['root',{id:'root',x:50,y:40,rotation:0}],['upper',{id:'upper',parent:'root',x:20,y:30}],['lower',{id:'lower',parent:'upper',x:0,y:0}]]);
R.applyIK(nodes,[{id:'arm',upper:'upper',lower:'lower',lengths:[100,80],target:[160,100],bend:-1}]);
const a=nodes.get('upper').rotation*Math.PI/180,b=(nodes.get('upper').rotation+nodes.get('lower').rotation)*Math.PI/180;
near(70+100*Math.cos(a)+80*Math.cos(b),160);near(70+100*Math.sin(a)+80*Math.sin(b),100);
assert.throws(()=>R.solveTwoBone([0,0],[Infinity,0],100,80));
console.log('OK: two-bone IK, reach limits, determinism and parent transforms');
