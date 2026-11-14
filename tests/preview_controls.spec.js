const { test, expect } = require('@playwright/test');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const root = path.resolve(__dirname, '..');
const out = path.join(root, 'test-results', 'visual', 'manifest-controls');

test.beforeAll(() => {
  fs.mkdirSync(out,{recursive:true});
  for (const project of ['layered_plant_demo', 'robot_ik_demo']) {
    execFileSync('python3',['tools/package.py','examples/'+project,'--out',out],
      {cwd:root,stdio:'inherit'});
  }
});
test('single-clip animation has no irrelevant robot controls in preview or export', async ({page}) => {
  const requests=[];
  page.on('request',request=>{if(/^https?:/i.test(request.url()))requests.push(request.url());});
  await page.route(/^https?:\/\//i,route=>route.abort());
  const archive=path.join(out,'layered_plant_demo.motionpack');
  const html=path.join(out,'plant-playable.html');
  execFileSync('python3',['tools/export_html.py',archive,'--out',html],
    {cwd:root,stdio:'inherit'});
  await page.goto(pathToFileURL(html).href);
  await page.waitForFunction(()=>!!window.MotionPackPlayer);
  await expect(page.locator('#controls')).toBeHidden();
  for(const id of ['idle','fire','transform','reset','aim'])
    await expect(page.locator('#'+id)).toBeHidden();
  await expect(page.locator('#stage')).toBeVisible();
  expect(await page.evaluate(()=>window.MotionPackPlayer.getState().clip)).toBe('static');
  expect(requests).toEqual([]);
});
test('robot retains only authored clips, variants and pointer IK controls', async ({page}) => {
  await page.goto(pathToFileURL(path.join(out,'preview.html')).href);
  await page.waitForFunction(()=>!!window.MotionPackPlayer);
  await expect(page.locator('#controls')).toBeVisible();
  for(const id of ['idle','fire','transform','reset','aim'])
    await expect(page.locator('#'+id)).toBeVisible();
  await page.locator('#fire').click();
  await expect.poll(()=>page.evaluate(()=>window.MotionPackPlayer.getState().clip)).toBe('fire');
});
