// Deterministic full-resolution export using Playwright and FFmpeg.
import { spawn } from 'node:child_process';
import { writeFile, mkdir } from 'node:fs/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
export async function renderWithPage(page, {ffmpeg='ffmpeg'}={}) {
  const out=path.join(root,'renders');
  await mkdir(out,{recursive:true});
  await page.setViewportSize({width:1080,height:1920});
  await page.goto(pathToFileURL(path.join(out,'player.html')).href+'?render=1');
  await page.waitForFunction(()=>window.filmReady===true);
  await page.evaluate(()=>document.fonts.ready);
  const target=path.join(out,'codex-task-router-terminal.mp4');
  const proc=spawn(ffmpeg,['-y','-loglevel','error','-f','image2pipe','-framerate','30','-vcodec','png','-i','pipe:0','-an','-c:v','libx264','-preset','slow','-crf','17','-pix_fmt','yuv420p','-movflags','+faststart',target],{stdio:['pipe','ignore','pipe']});
  let errors='';proc.stderr.on('data',data=>errors+=data.toString());
  let processError;
  proc.on('error',error=>{processError=error;});
  proc.stdin.on('error',error=>{processError=error;});
  const completion=new Promise((resolve,reject)=>{proc.on('close',code=>code===0?resolve():reject(new Error(errors||`FFmpeg exit ${code}`)));});
  // Observe failures immediately so rejection is never unhandled during capture.
  completion.catch(error=>{processError=error;});
  try {
    for(let frame=0;frame<1050;frame++) {
      if(processError)throw processError;
      const actual=await page.evaluate(t=>window.renderAt(t),frame/30);
      if(actual!==frame)throw new Error(`Seek mismatch: ${frame} / ${actual}`);
      const png=await page.screenshot({type:'png',animations:'disabled',scale:'css'});
      await new Promise((resolve,reject)=>proc.stdin.write(png,error=>error?reject(error):resolve()));
      if(frame%30===0)await writeFile(path.join(out,'render-progress.json'),JSON.stringify({status:'rendering',frame,total:1050}));
    }
    proc.stdin.end();await completion;
    await writeFile(path.join(out,'render-progress.json'),JSON.stringify({status:'complete',frames:1050,file:path.basename(target)}));
    return {target,frames:1050};
  } catch(error) {
    proc.kill('SIGTERM');await completion.catch(()=>{});
    await writeFile(path.join(out,'render-progress.json'),JSON.stringify({status:'failed',error:String(error)}));
    throw error;
  }
}

if(process.argv[1] && path.resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  const {chromium}=await import('playwright');
  const browser=await chromium.launch({headless:true});
  try {const page=await browser.newPage({viewport:{width:1080,height:1920},deviceScaleFactor:1});console.log(await renderWithPage(page,{ffmpeg:process.env.FFMPEG||'ffmpeg'}));}
  finally {await browser.close();}
}
