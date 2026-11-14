const { test, expect } = require('@playwright/test');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

const root = path.resolve(__dirname, '..');
const output = path.join(root, 'test-results', 'visual', 'standalone-export');
const snapshots = path.join(root, 'test-results', 'visual', 'candidate-screenshots');
const html = path.join(output, 'robot-playable.html');

test.beforeAll(() => {
  fs.mkdirSync(output, { recursive: true });
  fs.mkdirSync(snapshots, { recursive: true });
  execFileSync('python3', [
    'tools/package.py', 'examples/robot_ik_demo', '--out', output
  ], { cwd: root, stdio: 'inherit' });
  execFileSync('python3', [
    'tools/export_html.py', path.join(output, 'robot_ik_demo.motionpack'), '--out', html
  ], { cwd: root, stdio: 'inherit' });
});

test('exported archive runs offline with the original MotionPack runtime', async ({ browser }, info) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  const externalRequests = [];
  const runtimeErrors = [];
  page.on('request', request => {
    if (/^https?:/i.test(request.url())) externalRequests.push(request.url());
  });
  page.on('pageerror', error => runtimeErrors.push(error.message));
  await page.route(/^https?:\/\//i, route => route.abort());
  await page.goto(pathToFileURL(html).href);
  await page.locator('#stage').waitFor({ state: 'visible' });
  await page.waitForFunction(() => window.MotionPackPlayer &&
    [...document.images].every(image => image.complete && image.naturalWidth > 0));
  await page.locator('#fire').click();
  await expect.poll(() => page.evaluate(() => window.MotionPackPlayer.getState().clip)).toBe('fire');
  await page.waitForTimeout(170);
  const screenshot = path.join(snapshots, 'archive-export-viewport-390x844.png');
  await page.screenshot({ path: screenshot, fullPage: false });
  const bytes = fs.readFileSync(screenshot);
  expect([bytes.readUInt32BE(16), bytes.readUInt32BE(20)]).toEqual([390, 844]);
  await info.attach('archive-export-viewport', { path: screenshot, contentType: 'image/png' });
  expect(externalRequests).toEqual([]);
  expect(runtimeErrors).toEqual([]);
  await context.close();
});
