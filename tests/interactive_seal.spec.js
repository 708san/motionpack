const { test, expect } = require('@playwright/test');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

const root = path.resolve(__dirname, '..');
const output = path.join(root, 'test-results', 'visual', 'interactive-seal');
const preview = path.join(output, 'interactive_seal_demo.html');
const candidates = path.join(root, 'test-results', 'visual', 'candidate-screenshots');

test.beforeAll(() => {
  fs.mkdirSync(output, { recursive: true });
  fs.mkdirSync(candidates, { recursive: true });
  execFileSync('python3', [
    'tools/validate.py', 'examples/interactive_seal_demo'
  ], { cwd: root, stdio: 'inherit' });
  execFileSync('python3', [
    'tools/package.py', 'examples/interactive_seal_demo', '--out', output
  ], { cwd: root, stdio: 'inherit' });
  execFileSync('python3', [
    'examples/interactive_seal_demo/build_preview.py', '--out', output
  ], { cwd: root, stdio: 'inherit' });
  const packagePath = path.join(output, 'interactive_seal_demo.motionpack');
  execFileSync('python3', [
    '-c',
    'import json,sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); m=json.loads(z.read("manifest.json")); expected={"manifest.json"}|set(m["assets"].values()); actual=set(z.namelist()); assert actual==expected, (actual, expected); assert not any(name.startswith("source/") for name in actual); assert "assets/static_fallback.svg" not in actual',
    packagePath
  ], { cwd: root, stdio: 'inherit' });
});

async function openDemo(page, target = preview) {
  const externalRequests = [];
  const pageErrors = [];
  page.on('request', request => {
    if (/^https?:/i.test(request.url())) externalRequests.push(request.url());
  });
  page.on('pageerror', error => pageErrors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') pageErrors.push(message.text());
  });
  await page.route(/^https?:\/\//i, route => route.abort());
  await page.goto(pathToFileURL(target).href);
  await page.locator('#stage').waitFor({ state: 'visible' });
  await page.waitForFunction(() => !!window.MotionPackPlayer);
  await page.waitForFunction(() =>
    document.querySelector('#static-fallback').hidden === true
  );
  return { externalRequests, pageErrors };
}

async function captureCandidate(page, testInfo, name) {
  const imagePath = path.join(candidates, 'interactive-seal-' + name + '.png');
  await page.locator('#stage').screenshot({ path: imagePath, animations: 'disabled' });
  await testInfo.attach('interactive-seal-' + name, {
    path: imagePath, contentType: 'image/png'
  });
}

test('invalid fallback SVG is rejected before package output', async () => {
  const invalidFallback = path.join(output, 'invalid-fallback.svg');
  const rejectedOutput = path.join(output, 'rejected-build');
  fs.rmSync(rejectedOutput, { recursive: true, force: true });
  fs.writeFileSync(invalidFallback,
    '<svg xmlns="http://www.w3.org/2000/svg" width="910" height="550" viewBox="0 0 910 550" onload="alert(1)"></svg>');
  const result = require('node:child_process').spawnSync('python3', [
    'examples/interactive_seal_demo/build_preview.py',
    '--out', rejectedOutput,
    '--fallback', invalidFallback
  ], { cwd: root, encoding: 'utf8' });
  expect(result.status).not.toBe(0);
  expect(fs.existsSync(path.join(rejectedOutput, 'interactive_seal_demo.motionpack'))).toBe(false);
});

test('touch tap only activates the seal and returns to idle', async ({ browser }, testInfo) => {
  const context = await browser.newContext({
    hasTouch: true, viewport: { width: 1000, height: 1400 }, deviceScaleFactor: 1
  });
  const page = await context.newPage();
  const { externalRequests, pageErrors } = await openDemo(page);
  const geometry = await page.locator('#stage').evaluate(canvas => {
    const rect = canvas.getBoundingClientRect();
    return { x: rect.x, y: rect.y, width: rect.width, height: rect.height,
      ratio: rect.width / rect.height, bitmapWidth: canvas.width, bitmapHeight: canvas.height };
  });
  expect(geometry.ratio).toBeCloseTo(910 / 550, 2);
  await captureCandidate(page, testInfo, 'idle');

  const canvasBox = await page.locator('#stage').boundingBox();
  await page.touchscreen.tap(canvasBox.x + canvasBox.width * 0.5,
    canvasBox.y + canvasBox.height * 0.12);
  await expect.poll(() => page.evaluate(() => window.__sealActivations)).toBe(0);

  await page.touchscreen.tap(canvasBox.x + canvasBox.width * 0.5,
    canvasBox.y + canvasBox.height * 0.64);
  await expect.poll(() => page.evaluate(() => window.__sealActivations)).toBe(1);
  await expect.poll(() => page.evaluate(() => window.MotionPackPlayer.getState().clip))
    .toBe('squish');
  await captureCandidate(page, testInfo, 'squish');
  await page.waitForTimeout(700);
  await expect.poll(() => page.evaluate(() => window.MotionPackPlayer.getState().clip))
    .toBe('idle');
  await expect.poll(() => page.evaluate(() => window.MotionPackPlayer.getState().variant))
    .toBe('rest');
  await captureCandidate(page, testInfo, 'rest');

  expect(externalRequests).toEqual([]);
  expect(pageErrors).toEqual([]);
  fs.appendFileSync(path.join(output, 'capture-metadata.txt'),
    'interactive-seal: chromium=' + page.context().browser().version() +
    '; viewport=' + geometry.width + 'x' + geometry.height +
    '; deviceScaleFactor=' + (await page.evaluate(() => window.devicePixelRatio)) +
    '; bitmap=' + geometry.bitmapWidth + 'x' + geometry.bitmapHeight +
    '; physical-device=false; visual-baseline=not-yet-reviewed\n');
  await context.close();
});

test('mouse click activates the opted-in seal node', async ({ page }) => {
  const { externalRequests, pageErrors } = await openDemo(page);
  const canvas = page.locator('#stage');
  await canvas.evaluate(element => {
    element.addEventListener('click', event => {
      window.__nativeSealClick = {
        constructor: event.constructor.name,
        pointerType: event.pointerType || '',
        x: event.clientX,
        y: event.clientY
      };
    }, { once: true });
  });
  const rect = await canvas.boundingBox();
  await page.mouse.click(rect.x + rect.width * 0.5, rect.y + rect.height * 0.64);
  const nativeClick = await page.evaluate(() => window.__nativeSealClick);
  const interaction = await page.evaluate(() => window.__lastInteraction);
  expect(nativeClick, 'capture the browser-generated mouse click event').toMatchObject({
    pointerType: 'mouse'
  });
  await expect.poll(() => page.evaluate(() => window.__sealActivations), { message: 'mouse interaction: ' + JSON.stringify({ nativeClick, interaction }) }).toBe(1);
  await page.waitForTimeout(700);
  await page.getByRole('button', { name: 'Activate the seal' }).focus();
  await page.keyboard.press('Enter');
  await expect.poll(() => page.evaluate(() => window.__sealActivations)).toBe(2);
  await expect.poll(() => page.evaluate(() => window.MotionPackPlayer.getState().clip))
    .toBe('squish');
  expect(externalRequests).toEqual([]);
  expect(pageErrors).toEqual([]);
});



test('host keyboard activation triggers the seal action', async ({ page }) => {
  const { externalRequests, pageErrors } = await openDemo(page);
  await page.getByRole('button', { name: 'Activate the seal' }).focus();
  await page.keyboard.press('Enter');
  await expect.poll(() => page.evaluate(() => window.__sealActivations)).toBe(1);
  await expect.poll(() => page.evaluate(() => window.MotionPackPlayer.getState().clip))
    .toBe('squish');
  await page.waitForTimeout(700);
  await expect.poll(() => page.evaluate(() => window.MotionPackPlayer.getState().clip))
    .toBe('idle');
  expect(externalRequests).toEqual([]);
  expect(pageErrors).toEqual([]);
});

test('static fallback remains visible when an embedded asset fails to decode', async ({ browser }) => {
  const html = fs.readFileSync(preview, 'utf8');
  const manifestOffset = html.indexOf('window.__MOTIONPACK__=');
  const prefix = 'data:image/svg+xml;base64,';
  const assetOffset = html.indexOf(prefix, manifestOffset);
  const valueStart = assetOffset + prefix.length;
  const valueEnd = html.indexOf('"', valueStart);
  expect(manifestOffset).toBeGreaterThanOrEqual(0);
  expect(assetOffset).toBeGreaterThan(manifestOffset);
  expect(valueEnd).toBeGreaterThan(valueStart);
  const broken = html.slice(0, valueStart) + Buffer.from('<svg><broken').toString('base64') + html.slice(valueEnd);
  const malformedPreview = path.join(output, 'malformed-asset.html');
  fs.writeFileSync(malformedPreview, broken);
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto(pathToFileURL(malformedPreview).href);
  await page.locator('#stage').waitFor({ state: 'visible' });
  await page.waitForFunction(() => !!window.MotionPackPlayer);
  await page.waitForTimeout(300);
  await expect(page.locator('#static-fallback')).toBeVisible();
  await expect(page.locator('#asset-error')).toBeVisible();
  await context.close();
});
test('static illustration remains available without JavaScript', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto(pathToFileURL(preview).href);
  const fallback = page.locator('#static-fallback');
  await expect(fallback).toBeVisible();
  await expect.poll(() => fallback.evaluate(image => image.naturalWidth)).toBe(910);
  await expect(page.locator('#stage')).toBeVisible();
  await context.close();
});
