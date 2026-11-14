const {test,expect}=require('@playwright/test');
const {execFileSync}=require('node:child_process');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const root=path.resolve(__dirname,'..');
const preview=path.join(root,'test-results','visual','director-demo','preview.html');
test.beforeAll(()=>{
 execFileSync('python3',['tools/package.py','examples/layered_plant_demo','--out',path.dirname(preview)],
   {cwd:root,stdio:'inherit'});
});
test('host config adds independent procedural motion to a static clip offline',async({page})=>{
 const external=[],errors=[];
 page.on('request',r=>{if(/^https?:/i.test(r.url()))external.push(r.url());});
 page.on('pageerror',e=>errors.push(e.message));
 await page.route(/^https?:\/\//i,r=>r.abort());
 await page.clock.install({time:new Date('2026-01-01T00:00:00Z')});
 await page.goto(pathToFileURL(preview).href);
 await page.locator('#stage').waitFor({state:'visible'});
 await page.waitForFunction(()=>window.MotionPackPlayer &&
   [...document.images].every(img=>img.complete&&img.naturalWidth>0));
 await page.clock.pauseAt(new Date('2026-01-01T00:01:00Z'));
 await page.clock.runFor(16);
 const base=await page.locator('#stage').screenshot();
 await page.evaluate(()=>window.MotionPackPlayer.configureMotion({channels:[
   {id:'sway',node:'foliage',property:'x',amplitude:60,periodMs:1000}
 ]}));
 await page.clock.runFor(250);
 const moved=await page.locator('#stage').screenshot();
 expect(Buffer.compare(base,moved)).not.toBe(0);
 await page.evaluate(()=>window.MotionPackPlayer.configureMotion(null));
 await page.clock.runFor(16);
 const restored=await page.locator('#stage').screenshot();
 expect(Buffer.compare(base,restored)).toBe(0);
 expect(external).toEqual([]);
 expect(errors).toEqual([]);
});
