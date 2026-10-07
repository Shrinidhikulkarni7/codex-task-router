#!/usr/bin/env node
/** Offline browser rendering. Run npm install, then npx playwright install chromium.
 * Reuses the supplied audio. Narration regeneration is a separate, explicit step.
 */
import { chromium } from 'playwright';
import { spawn } from 'node:child_process';
import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
await mkdir(path.join(root, 'renders'), { recursive: true });
const browser = await chromium.launch({ headless: true });
let encoder;
try {
  const page = await browser.newPage({
    viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1,
  });
  await page.goto(new URL('../renders/player.html?render=1', import.meta.url).href);
  await page.waitForFunction(() => window.filmReady);
  encoder = spawn('ffmpeg', [
    '-y', '-v', 'warning', '-f', 'image2pipe', '-framerate', '30', '-i', 'pipe:0',
    '-i', path.join(root, 'assets/audio/mix.m4a'),
    '-map', '0:v:0', '-map', '1:a:0', '-frames:v', '1440',
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '17', '-pix_fmt', 'yuv420p',
    '-c:a', 'copy', '-t', '48', '-movflags', '+faststart',
    path.join(root, 'renders/codex-task-router.mp4'),
  ], { stdio: ['pipe', 'inherit', 'inherit'] });

  // Handle early encoder failures before rendering or waiting for pipe drain.
  let failure;
  const completed = new Promise(resolve => {
    encoder.once('error', error => { failure = error; resolve(); });
    encoder.once('close', code => {
      if (code !== 0) failure ??= new Error(`FFmpeg exit ${code}`);
      resolve();
    });
  });
  encoder.stdin.on('error', error => { failure ??= error; });
  for (let frame = 0; frame < 1440; frame++) {
    if (failure) throw failure;
    const actual = await page.evaluate(t => window.renderAt(t), frame / 30);
    if (actual !== frame) throw new Error(`Seek mismatch: ${actual} != ${frame}`);
    const bytes = await page.screenshot({ type: 'png', animations: 'disabled' });
    await new Promise((resolve, reject) => {
      encoder.stdin.write(bytes, error => error ? reject(error) : resolve());
    });
    if (frame % 120 === 0) console.log(`Frame ${frame}/1440`);
  }
  encoder.stdin.end();
  await completed;
  if (failure) throw failure;
} finally {
  if (encoder?.pid && encoder.exitCode === null) {
    encoder.stdin.destroy();
    encoder.kill('SIGTERM');
  }
  await browser.close();
}
