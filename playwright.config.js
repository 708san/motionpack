const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests',
  testMatch: ['visual.spec.js', 'interactive_seal.spec.js', 'standalone_export.spec.js'],
  fullyParallel: false,
  workers: 1,
  timeout: 30_000,
  outputDir: 'test-results/visual',
  reporter: 'list',
  expect: {
    timeout: 5_000,
    toHaveScreenshot: {
      animations: 'disabled',
      scale: 'css',
      maxDiffPixelRatio: 0.002,
      threshold: 0.1
    }
  },
  use: {
    browserName: 'chromium',
    headless: true,
    viewport: { width: 1000, height: 1400 },
    deviceScaleFactor: 1
  }
});
