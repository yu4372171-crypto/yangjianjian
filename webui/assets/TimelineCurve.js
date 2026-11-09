const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));

export const BEZIER_EASING_OPTIONS=[
  'linear','hold','ease-in','ease-out','ease-in-out','bezier'
];

export function normalizeEasing(value){
  if(value===undefined||value===null)return 'linear';
  if(typeof value==='string'){
    if(value==='bezier')return {type:'bezier',x1:.25,y1:.1,x2:.25,y2:1};
    if(BEZIER_EASING_OPTIONS.includes(value))return value;
    throw Error('关键帧插值无效');
  }
  if(!value||typeof value!=='object'||value.type!=='bezier')throw Error('关键帧插值无效');
  const result={type:'bezier'};
  for(const key of ['x1','y1','x2','y2']){
    const number=Number(value[key]);
    if(!Number.isFinite(number)||number<0||number>1)throw Error('贝塞尔控制点需要在0到1之间');
    result[key]=number;
  }
  return result;
}

export function easingKey(value){
  const normalized=normalizeEasing(value);
  return typeof normalized==='string'?normalized:JSON.stringify(normalized);
}

function coordinate(t,a1,a2){
  const inv=1-t;
  return 3*inv*inv*t*a1+3*inv*t*t*a2+t*t*t;
}

function solveTime(x,x1,x2){
  let t=clamp(x,0,1);
  for(let i=0;i<8;i++){
    const current=coordinate(t,x1,x2)-x;
    if(Math.abs(current)<1e-7)return t;
    const inv=1-t;
    const derivative=3*inv*inv*x1+6*inv*t*(x2-x1)+3*t*t*(1-x2);
    if(Math.abs(derivative)<1e-7)break;
    t=clamp(t-current/derivative,0,1);
  }
  let low=0,high=1;
  for(let i=0;i<20;i++){
    const middle=(low+high)/2;
    if(coordinate(middle,x1,x2)<x)low=middle;
    else high=middle;
  }
  return (low+high)/2;
}

export function ease(progress,easing='linear'){
  const p=clamp(Number(progress)||0,0,1),value=normalizeEasing(easing);
  if(value==='hold')return 0;
  if(value==='ease-in')return p*p;
  if(value==='ease-out')return 1-(1-p)**2;
  if(value==='ease-in-out')return p<.5?2*p*p:1-(-2*p+2)**2/2;
  if(typeof value==='object'&&value?.type==='bezier'){
    const t=solveTime(p,value.x1,value.x2);
    return coordinate(t,value.y1,value.y2);
  }
  return p;
}

export function easingLabel(value){
  const normalized=normalizeEasing(value);
  if(typeof normalized==='string'){
    return {
      linear:'线性',
      hold:'保持',
      'ease-in':'缓入',
      'ease-out':'缓出',
      'ease-in-out':'缓入缓出'
    }[normalized];
  }
  return '贝塞尔曲线';
}
