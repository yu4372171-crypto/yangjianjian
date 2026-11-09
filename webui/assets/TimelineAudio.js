const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));

export function dbToGain(db){
  const value=Number(db);
  if(!Number.isFinite(value))throw Error('音量分贝值无效');
  if(value<=-60)return 0;
  return clamp(10**(clamp(value,-60,12)/20),0,4);
}

export function gainToDb(gain){
  const value=clamp(Number(gain)||0,0,4);
  return value<=1e-8?-60:clamp(20*Math.log10(value),-60,12);
}

export function waveformPeaks(samples,count=96){
  const array=samples instanceof Float32Array?samples:new Float32Array(samples||[]);
  const buckets=Math.max(8,Math.min(512,Math.trunc(count)||96));
  if(!array.length)return new Array(buckets).fill(0);
  const size=array.length/buckets,peaks=new Array(buckets);
  for(let bucket=0;bucket<buckets;bucket++){
    const start=Math.floor(bucket*size),end=Math.max(start+1,Math.floor((bucket+1)*size));
    let peak=0;
    for(let index=start;index<Math.min(array.length,end);index++)peak=Math.max(peak,Math.abs(array[index]));
    peaks[bucket]=clamp(peak,0,1);
  }
  const maximum=Math.max(1e-6,...peaks);
  return peaks.map(value=>clamp(value/maximum,0,1));
}

export async function decodeWaveform(url,count=96,AudioContextType){
  const Audio=AudioContextType||globalThis.AudioContext||globalThis.webkitAudioContext;
  if(!Audio)throw Error('当前浏览器不支持音频波形');
  const response=await fetch(url);
  if(!response.ok)throw Error('读取音频波形失败');
  const context=new Audio();
  try{
    const buffer=await context.decodeAudioData(await response.arrayBuffer());
    const samples=new Float32Array(buffer.length);
    for(let channel=0;channel<buffer.numberOfChannels;channel++){
      const source=buffer.getChannelData(channel);
      for(let index=0;index<samples.length;index++)samples[index]=Math.max(samples[index],Math.abs(source[index]));
    }
    return waveformPeaks(samples,count);
  }finally{
    context.close?.().catch?.(()=>{});
  }
}
