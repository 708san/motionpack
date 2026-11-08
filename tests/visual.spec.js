const { test, expect } = require('@playwright/test');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

const root = path.resolve(__dirname, '..');
const output = path.join(root, 'test-results', 'visual');
const preview = path.join(output, 'preview', 'preview.html');
const candidateDir = path.join(output, 'candidate-screenshots');

test.beforeAll(() => {
  fs.mkdirSync(output, { recursive: true });
  fs.rmSync(path.join(output, 'capture-metadata.txt'), { force: true });
  fs.writeFileSync(path.join(output, 'capture-metadata.txt'),
    'Capture started; environment metadata will follow after each scene.\n');
  fs.mkdirSync(candidateDir, { recursive: true });
  execFileSync('python3', [
    'tools/package.py', 'examples/robot_ik_demo', '--out', path.dirname(preview)
  ], { cwd: root, stdio: 'inherit' });
});

async function openReferencePreview(page) {
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

  await page.clock.install({ time: new Date('2024-01-01T00:00:00.000Z') });
  await page.goto(pathToFileURL(preview).href);
  await page.locator('#stage').waitFor({ state: 'visible' });
  await page.waitForFunction(() =>
    [...document.images].every(image => image.complete && image.naturalWidth > 0)
  );
  await page.clock.pauseAt(new Date('2024-01-01T00:01:00.000Z'));
  // Start the animation loop at a known virtual time after embedded images load.
  await page.clock.runFor(16);
  return { externalRequests, pageErrors };
}

async function capture(page, testInfo, name, advanceMs, expectedStatus, options = {}) {
  const { externalRequests, pageErrors } = await openReferencePreview(page);
  if (options.button || options.pointer) {
    const selector = options.button || '#idle';
    await page.evaluate(button => document.querySelector(button).click(), selector);
  }
  if (options.pointer) {
    await page.evaluate(({ x, y }) => {
      document.querySelector('#aim').click();
      const canvas = document.querySelector('#stage');
      const box = canvas.getBoundingClientRect();
      canvas.dispatchEvent(new PointerEvent('pointermove', {
        bubbles: true,
        clientX: box.x + box.width * x,
        clientY: box.y + box.height * y
      }));
    }, options.pointer);
  }
  await page.clock.runFor(advanceMs);

  const status = await page.locator('#status').textContent();
  expect(status).toBe(expectedStatus);
  const canvas = page.locator('#stage');
  const canvasSize = await canvas.evaluate(element => ({
    cssWidth: element.getBoundingClientRect().width,
    cssHeight: element.getBoundingClientRect().height,
    bitmapWidth: element.width,
    bitmapHeight: element.height
  }));
  const imagePath = path.join(candidateDir, `${name}.png`);
  await canvas.screenshot({ path: imagePath, animations: 'disabled', scale: 'css' });
  const screenshotBytes = fs.readFileSync(imagePath);
  const screenshotSize = {
    width: screenshotBytes.readUInt32BE(16),
    height: screenshotBytes.readUInt32BE(20)
  };
  await testInfo.attach(`${name}.png`, { path: imagePath, contentType: 'image/png' });

  const baselinePath = testInfo.snapshotPath(`${name}.png`);
  if (process.platform === 'linux' &&
      (fs.existsSync(baselinePath) || testInfo.config.updateSnapshots === 'all')) {
    await expect(canvas).toHaveScreenshot(`${name}.png`);
  } else if (process.env.VISUAL_BASELINE_BOOTSTRAP === '1') {
    console.warn(`No reviewed baseline for ${name}; captured candidate artifact only.`);
  } else if (process.platform !== 'linux') {
    console.info(`Pixel comparison for ${name} runs only on the pinned Linux reference platform.`);
  } else {
    throw new Error(`Missing reviewed screenshot baseline: ${baselinePath}`);
  }
  expect(externalRequests, 'preview must not make runtime network requests').toEqual([]);
  expect(pageErrors, 'preview must not raise uncaught browser errors').toEqual([]);
  if (options.pointer) {
    expect(await page.evaluate(() => window.MotionPackPlayer.getState().pointerIK)).toBe(true);
  }

  fs.appendFileSync(path.join(output, 'capture-metadata.txt'),
    `${name}: ${status}; viewport=1000x1400; deviceScaleFactor=1; ` +
    `canvasCss=${canvasSize.cssWidth}x${canvasSize.cssHeight}; ` +
    `canvasBitmap=${canvasSize.bitmapWidth}x${canvasSize.bitmapHeight}; ` +
    `canvasPng=${screenshotSize.width}x${screenshotSize.height}; ` +
    `platform=${process.platform}-${process.arch}; ` +
    `playwright=${require('@playwright/test/package.json').version}; ` +
    `chromium=${page.context().browser().version()}\n`);
}

test('idle pose at 800 ms', async ({ page }, testInfo) => {
  await capture(page, testInfo, 'idle', 800, 'idle | form_a | 800 ms', { button: '#idle' });
});

test('fire clip at 800 ms', async ({ page }, testInfo) => {
  await capture(page, testInfo, 'fire', 800, 'fire | form_a | 800 ms', { button: '#fire' });
});

test('transform clip at 1008 ms', async ({ page }, testInfo) => {
  await capture(page, testInfo, 'transform', 1008, 'transform | form_a | 1008 ms', { button: '#transform' });
});

test('completed form change', async ({ page }, testInfo) => {
  await capture(page, testInfo, 'form-change', 2912, 'idle | form_b | 800 ms', { button: '#transform' });
});

test('pointer IK at a fixed canvas coordinate', async ({ page }, testInfo) => {
  await capture(page, testInfo, 'pointer-ik', 800, 'idle | form_a | 800 ms', {
    pointer: { x: 0.724, y: 0.24 }
  });
});

test('collect report-only package, reader and browser performance measurements', async ({ page }, testInfo) => {
  test.setTimeout(120_000);
  const performanceDir = path.join(root, 'test-results', 'performance');
  execFileSync('python3', [
    'tests/run_performance_report.py', '--out', performanceDir
  ], { cwd: root, stdio: 'inherit', timeout: 65_000 });
  const reportPath = path.join(performanceDir, 'performance.json');
  const benchmarkPreview = path.join(performanceDir, 'package', 'preview.html');
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
  await page.addInitScript(() => {
    const NativeImage = window.Image;
    const images = [];
    Object.defineProperty(window, '__motionPackTrackedImages', { value: images });
    window.Image = function (...args) {
      const image = new NativeImage(...args);
      images.push(image);
      return image;
    };
    window.Image.prototype = NativeImage.prototype;
    Object.setPrototypeOf(window.Image, NativeImage);
  });

  const loadStarted = process.hrtime.bigint();
  await page.goto(pathToFileURL(benchmarkPreview).href);
  await page.locator('#stage').waitFor({ state: 'visible' });
  await page.waitForFunction(() =>
    (() => {
      const expectedCount = Object.keys(window.__MOTIONPACK__?.assets || {}).length;
      const images = window.__motionPackTrackedImages || [];
      return expectedCount > 0 && images.length === expectedCount &&
        images.every(image => image.complete && image.naturalWidth > 0);
    })()
  );
  const trackedImageCount = await page.evaluate(() => window.__motionPackTrackedImages.length);
  const loadReadyMs = Number(process.hrtime.bigint() - loadStarted) / 1e6;

  const frameStats = await page.evaluate(async () => {
    const warmupFrames = 30;
    const measuredFrames = 180;
    const timestamps = [];
    await new Promise(resolve => {
      function sample(timestamp) {
        timestamps.push(timestamp);
        if (timestamps.length < warmupFrames + measuredFrames + 1) {
          requestAnimationFrame(sample);
        } else {
          resolve();
        }
      }
      requestAnimationFrame(sample);
    });
    const intervals = [];
    for (let index = warmupFrames + 1; index < timestamps.length; index++) {
      intervals.push(timestamps[index] - timestamps[index - 1]);
    }
    const ordered = [...intervals].sort((a, b) => a - b);
    const median = ordered.length % 2
      ? ordered[(ordered.length - 1) / 2]
      : (ordered[ordered.length / 2 - 1] + ordered[ordered.length / 2]) / 2;
    const p95Index = Math.min(ordered.length - 1, Math.ceil(ordered.length * 0.95) - 1);
    return {
      sample_count: intervals.length,
      warmup_frames: warmupFrames,
      measured_duration_ms: intervals.reduce((sum, value) => sum + value, 0),
      median_ms: median,
      p95_ms: ordered[p95Index],
      max_ms: Math.max(...intervals),
      intervals_over_16_7ms: intervals.filter(value => value > 16.7).length,
      samples_ms: intervals
    };
  });
  expect(frameStats.sample_count).toBe(180);
  expect(frameStats.samples_ms.every(value => Number.isFinite(value) && value >= 0)).toBe(true);
  expect(Number.isFinite(loadReadyMs) && loadReadyMs >= 0).toBe(true);
  expect([frameStats.median_ms, frameStats.p95_ms, frameStats.max_ms,
    frameStats.measured_duration_ms].every(value => Number.isFinite(value) && value >= 0)).toBe(true);
  expect(externalRequests, 'preview must not make runtime network requests').toEqual([]);
  expect(pageErrors, 'preview must not raise uncaught browser errors').toEqual([]);

  const report = JSON.parse(fs.readFileSync(reportPath, 'utf8'));
  report.environment.playwright = require('@playwright/test/package.json').version;
  report.environment.chromium = page.context().browser().version();
  report.environment.viewport = '1000x1400';
  report.environment.device_scale_factor = 1;
  report.browser = {
    load_to_images_ready_ms: loadReadyMs,
    tracked_image_count: trackedImageCount,
    frame_interval_ms: frameStats,
    notes: 'Headless CI measurements are informational and include host scheduling noise.'
  };
  fs.writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`);
  await testInfo.attach('performance.json', { path: reportPath, contentType: 'application/json' });
});
