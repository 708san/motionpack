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
    'examples/interactive_seal_demo/build_preview.py', '--out', output
  ], { cwd: root, stdio: 'inherit' });
});

async function openDemo(page) {
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
  await page.goto(pathToFileURL(preview).href);
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

test('touch tap only activates the seal and returns to idle', async ({ page }, testInfo) => {
  const { externalRequests, pageErrors } = await openDemo(page);
  const geometry = await page.locator('#stage').evaluate(canvas => {
    const rect = canvas.getBoundingClientRect();
    return { x: rect.x, y: rect.y, width: rect.width, height: rect.height,
      ratio: rect.width / rect.height, bitmapWidth: canvas.width, bitmapHeight: canvas.height };
  });
  expect(geometry.ratio).toBeCloseTo(910 / 550, 2);
  await captureCandidate(page, testInfo, 'idle');

  await page.evaluate(() => {
    const canvas = document.querySelector('#stage');
    const rect = canvas.getBoundingClientRect();
    const x = rect.left + rect.width * 0.5;
    const y = rect.top + rect.height * 0.12;
    canvas.dispatchEvent(new PointerEvent('pointerdown', {
      bubbles: true, pointerId: 31, pointerType: 'touch', isPrimary: true,
      clientX: x, clientY: y
    }));
    window.dispatchEvent(new PointerEvent('pointerup', {
      bubbles: true, pointerId: 31, pointerType: 'touch', isPrimary: true,
      clientX: x, clientY: y
    }));
  });
  await expect.poll(() => page.evaluate(() => window.__sealActivations)).toBe(0);

  await page.evaluate(() => {
    const canvas = document.querySelector('#stage');
    const rect = canvas.getBoundingClientRect();
    const x = rect.left + rect.width * 0.5;
    const y = rect.top + rect.height * 0.64;
    canvas.dispatchEvent(new PointerEvent('pointerdown', {
      bubbles: true, pointerId: 32, pointerType: 'touch', isPrimary: true,
      clientX: x, clientY: y
    }));
    window.dispatchEvent(new PointerEvent('pointerup', {
      bubbles: true, pointerId: 32, pointerType: 'touch', isPrimary: true,
      clientX: x, clientY: y
    }));
  });
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
});

test('mouse click and host keyboard activation use the same opt-in node', async ({ page }) => {
  const { externalRequests, pageErrors } = await openDemo(page);
  const canvas = page.locator('#stage');
  const rect = await canvas.boundingBox();
  await page.mouse.click(rect.x + rect.width * 0.5, rect.y + rect.height * 0.64);
  await expect.poll(() => page.evaluate(() => window.__sealActivations)).toBe(1);
  await page.waitForTimeout(700);
  await page.getByRole('button', { name: 'Activate the seal' }).focus();
  await page.keyboard.press('Enter');
  await expect.poll(() => page.evaluate(() => window.__sealActivations)).toBe(2);
  await expect.poll(() => page.evaluate(() => window.MotionPackPlayer.getState().clip))
    .toBe('squish');
  expect(externalRequests).toEqual([]);
  expect(pageErrors).toEqual([]);
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
