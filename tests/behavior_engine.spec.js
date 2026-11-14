const {test,expect}=require('@playwright/test');
const {execFileSync}=require('node:child_process');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const root=path.resolve(__dirname,'..');
const output=path.join(root,'test-results','visual','semantic-behavior');
test.beforeAll(()=>{
 execFileSync('python3',['tools/package.py','examples/robot_demo','--out',output],
   {cwd:root,stdio:'inherit'});
});
test('semantic actions are host-owned, opt-in, and preserve ordinary clip control',async({page})=>{
 const requests=[],errors=[];
 page.on('request',r=>{if(/^https?:/i.test(r.url()))requests.push(r.url());});
 page.on('pageerror',e=>errors.push(e.message));
 await page.route(/^https?:\/\//i,r=>r.abort());
 await page.goto(pathToFileURL(path.join(output,'preview.html')).href);
 await page.waitForFunction(()=>!!window.MotionPackPlayer);
 const result=await page.evaluate(()=>{
  const player=window.MotionPackPlayer;
  const initiallyUnknown=player.act('greet');
  const initialClip=player.getState().clip;
  player.configureBehavior({
   actions:{greet:{clip:'fire'},rest:{clip:'idle'}},
   seed:43,
   ambient:{minIntervalMs:2000,maxIntervalMs:2400,
     choices:[{action:'greet'}]}
  });
  const greeted=player.act('greet');
  const clipAfterGreet=player.getState().clip;
  player.setAutonomy(false);
  player.playClip('idle');
  const normalClip=player.getState().clip;
  player.configureBehavior(null);
  const unknownAfterDisable=player.act('greet');
  return {initiallyUnknown,initialClip,greeted,clipAfterGreet,normalClip,unknownAfterDisable};
 });
 expect(result.initiallyUnknown).toBe(false);
 expect(result.initialClip).toBe('idle');
 expect(result.greeted).toBe(true);
 expect(result.clipAfterGreet).toBe('fire');
 expect(result.normalClip).toBe('idle');
 expect(result.unknownAfterDisable).toBe(false);
 expect(requests).toEqual([]);
 expect(errors).toEqual([]);
});
