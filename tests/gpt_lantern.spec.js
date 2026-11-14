const { test, expect } = require('@playwright/test');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

const root = path.resolve(__dirname, '..');
const output = path.join(root, 'test-results', 'visual', 'gpt-lantern');
const screenshots = path.join(root, 'test-results', 'visual', 'candidate-screenshots');
const preview = path.join(output, 'preview.html');

test.beforeAll(() => {
  fs.mkdirSync(screenshots, { recursive: true });
  execFileSync('python3', ['tools/validate.py', 'examples/gpt_lantern_pilot'], {
    cwd: root, stdio: 'inherit'
  });
  execFileSync('python3', ['tools/package.py', 'examples/gpt_lantern_pilot', '--out', output], {
    cwd: root, stdio: 'inherit'
  });
});

test('offline playback, cycle captures, and mobile viewport evidence', async ({ browser }, testInfo) => {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 }, deviceScaleFactor: 1,
    recordVideo: { dir: output, size: { width: 390, height: 844 } }
  });
  const page = await context.newPage();
  const requests = [];
  const errors = [];
  page.on('request', req => { if (/^https?:/i.test(req.url())) requests.push(req.url()); });
  page.on('pageerror', err => errors.push(err.message));
  await page.route(/^https?:\/\//i, route => route.abort());
  await page.clock.install({ time: new Date('2026-01-01T00:00:00Z') });
  await page.goto(pathToFileURL(preview).href);
  const canvas = page.locator('#stage');
  await canvas.waitFor({ state: 'visible' });
  await page.waitForFunction(() => window.MotionPackPlayer &&
    [...document.images].every(img => img.complete && img.naturalWidth > 0));
  await page.clock.pauseAt(new Date('2026-01-01T00:01:00Z'));
  await page.clock.runFor(16);
  // The virtual clock was positioned one minute ahead while assets loaded.
  // Reset the player so evidence timestamps refer to the clip timeline.
  await page.evaluate(() => document.querySelector('#reset').click());
  await page.clock.runFor(16);
  expect(await page.evaluate(() => window.__MOTIONPACK__.defaults.clip)).toBe('float');
  const manifest = await page.evaluate(() => window.__MOTIONPACK__);
  const rotation = manifest.clips.float.tracks.find(
    track => track.node === 'lantern' && track.property === 'rotation'
  );
  expect(rotation.keys.map(key => key.value)).toEqual([-2.2, 0, 2.2, 0, -2.2]);
  const lanternY = manifest.clips.float.tracks.find(
    track => track.node === 'lantern' && track.property === 'y'
  );
  const glowY = manifest.clips.float.tracks.find(
    track => track.node === 'glow' && track.property === 'y'
  );
  expect(glowY.keys).toEqual(lanternY.keys);
  const frameBytes = [];
  const captures = [];
  for (const ms of [0, 800, 1600, 2400, 3200]) {
    if (ms) await page.clock.runFor(ms - (captures.length ? captures[captures.length - 1] : 0));
    const canvasPath = path.join(screenshots, `gpt-lantern-canvas-${ms}ms.png`);
    const viewportPath = path.join(screenshots, `gpt-lantern-viewport-390x844-${ms}ms.png`);
    await canvas.screenshot({ path: canvasPath, animations: 'disabled' });
    frameBytes.push(fs.readFileSync(canvasPath));
    await page.screenshot({ path: viewportPath, fullPage: false, animations: 'disabled' });
    const png = fs.readFileSync(viewportPath);
    expect([png.readUInt32BE(16), png.readUInt32BE(20)]).toEqual([390, 844]);
    await testInfo.attach(`gpt-lantern-viewport-${ms}ms`, {
      path: viewportPath, contentType: 'image/png'
    });
    const observedStatus = await page.locator('#status').textContent();
    const match = observedStatus.match(/[|] ([0-9]+) ms/);
    expect(match, `missing clip time at label ${ms}: ${observedStatus}`).not.toBeNull();
    const observed = Number(match[1]);
    const expected = ms % 3200;
    // Allow a single frame of scheduling slack around clip boundaries.
    const cycleError = Math.min(Math.abs(observed - expected),
      3200 - Math.abs(observed - expected));
    expect(cycleError, `incorrect phase at ${ms}ms: ${observedStatus}`).toBeLessThan(40);
    captures.push(ms);
  }
  expect(Buffer.compare(frameBytes[0], frameBytes[2])).not.toBe(0);
  expect(Buffer.compare(frameBytes[2], frameBytes[4])).not.toBe(0);
  const status = await page.locator('#status').textContent();
  expect(status).toContain('float');
  expect(requests).toEqual([]);
  expect(errors).toEqual([]);
  const video = page.video();
  await context.close();
  // Recordings are evidence only, not proof of frame-accurate playback or aesthetic approval.
  if (video) {
    const recorded = await video.path();
    const target = path.join(output, 'gpt-lantern-390x844.webm');
    fs.copyFileSync(recorded, target);
    await testInfo.attach('gpt-lantern-video', { path: target, contentType: 'video/webm' });
  }
  fs.appendFileSync(path.join(root, 'test-results', 'visual', 'capture-metadata.txt'),
    'gpt-lantern: 390x844 full viewport screenshot, canvas crop separately named; ' +
    '0/800/1600/2400/3200ms; playwright-emulated-mobile=true; visual-approved=false\n');
});
