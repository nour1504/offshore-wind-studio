/**
 * Home page background, WebGL 2 on one canvas: green gas behind fluted glass (noise from the table
 * of gasGrid.ts, the same on every graphics card) and grains moved on the GPU, stirred by the
 * pointer. Before the projects open, grains sometimes build a wind turbine over waves; once open,
 * they form the project orbs. Loops stop while hidden; reduced motion draws still pictures.
 */
import { clamp, smoothstep, watchVisible } from "../../motion";
import { GAS_GRID } from "./gasGrid";

export type Mode = "intro" | "orbs";

/** An orb as drawn now: centre and radius in canvas pixels, depth 0 (back) to 1 (front) */
interface OrbView { x: number; y: number; r: number; depth: number }

export interface Engine {
  setMode(mode: Mode): void;
  /** The matter blown apart from a point (client coordinates) */
  burst(clientX: number, clientY: number): void;
  /** How many orbs, and which of them hold a project */
  setOrbs(held: boolean[]): void;
  /** Where each orb is drawn now */
  orbs(): OrbView[];
  /** An orb under the pointer grows a little; null for none */
  setHover(index: number | null): void;
  /** Drag: the sphere turns with the pointer (pixels), then goes on with `fling` (pixels a second) */
  turn(dx: number, dy: number): void;
  fling(vx: number, vy: number): void;
  setDragging(on: boolean): void;
  size(): { width: number; height: number };
  onFrame(listener: () => void): () => void;
  onResize(listener: () => void): () => void;
  dispose(): void;
}

const TAU = Math.PI * 2;
const isDark =() => document.documentElement.dataset.mantineColorScheme === "dark";
/** Any CSS colour as red, green and blue from 0 to 1: the build writes #ffffff as #fff (and may write
    a name), so the browser reads it first and gives it back as #rrggbb */
let probe: CanvasRenderingContext2D | null | undefined;
function rgb(colour: string) {
  probe ??= document.createElement("canvas").getContext("2d");
  let hex = colour;
  if (probe) {
    probe.fillStyle = "#808080";
    probe.fillStyle = colour;
    hex = String(probe.fillStyle);
  }
  if (!/^#[0-9a-f]{6}$/i.test(hex)) hex = "#808080";
  return [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
}

/** Seeded random numbers: the same nebula at every visit. */
function seeded(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const hash = (x: number, y: number) => {
  const s = Math.sin(x * 127.1 + y * 311.7) * 43758.5453;
  return s - Math.floor(s);
};
function vnoise(x: number, y: number) {
  const ix = Math.floor(x), iy = Math.floor(y);
  let fx = x - ix, fy = y - iy;
  fx = fx * fx * (3 - 2 * fx);
  fy = fy * fy * (3 - 2 * fy);
  const a = hash(ix, iy), b = hash(ix + 1, iy), c = hash(ix, iy + 1), d = hash(ix + 1, iy + 1);
  return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy;
}
function fbm(x: number, y: number) {
  let v = 0, a = 0.5;
  for (let o = 0; o < 4; o++) {
    v += a * vnoise(x, y);
    x = x * 2.03 + 1.7;
    y = y * 2.03 + 9.2;
    a *= 0.5;
  }
  return v;
}

/* ----------------------------------------------------------------------------- shaders */
const FULL = `#version 300 es
void main(){vec2 p=vec2(float((gl_VertexID<<1)&2),float(gl_VertexID&2));gl_Position=vec4(p*2.-1.,0.,1.);}`;

const GAS = `#version 300 es
precision highp float;
uniform vec2 r; uniform float t,k,o,flash,base,dark,zs;
uniform vec3 bg,c1,c2,c3; uniform vec2 pan;
uniform highp sampler2D grid;
out vec4 colour;
// The noise between four points of the grid: their numbers are read together in the table
float n(vec2 p){vec2 l=floor(p),f=p-l;vec4 c=texelFetch(grid,(ivec2(l)+ivec2(${-GAS_GRID.x0},${-GAS_GRID.y0}))&${GAS_GRID.size - 1},0);f=f*f*(3.-2.*f);return mix(mix(c.x,c.y,f.x),mix(c.z,c.w,f.x),f.y);}
float fbm(vec2 p){float v=0.,a=.5;for(int j=0;j<5;j++){v+=a*n(p);p=p*2.02+vec2(1.7,9.2);a*=.5;}return v;}
void main(){
  vec2 uv=gl_FragCoord.xy/r;
  vec2 p=(gl_FragCoord.xy-.5*r)/r.y;
  float s=dot(p,vec2(.7071,.7071))*13.;
  float f=fract(s);
  vec2 q=p+vec2(.7071,.7071)*(f-.5)*.16;
  float tt=t*.045;
  vec2 b=(q+pan)*(1.3/zs)+vec2(tt*.7,-tt*.4);
  vec2 w=vec2(fbm(b*1.1+vec2(0.,tt)),fbm(b*1.1+vec2(5.2,1.3)-tt));
  float v=fbm(b+1.9*w);
  float v2=fbm((q+pan*1.5)*(3.4/zs)+2.6*w+vec2(-tt*1.4,tt*.9));
  float dens=smoothstep(.26,.76,v);
  float fil=smoothstep(.5,.85,v2)*smoothstep(.28,.66,v);
  float body=base+(1.-base)*dens;
  vec3 c=mix(c1,c2,smoothstep(.42,.86,v));
  c=mix(c,c3,fil*.8);
  float shade=.74+.42*f-.3*smoothstep(.88,1.,f);
  float m=clamp(body*k*(1.-o*.15)+flash*.3,0.,1.);
  vec3 outc=mix(bg,c*shade,m);
  float vg=pow(clamp(length((uv-.5)*vec2(1.1,1.))*1.35,0.,1.),2.2);
  outc=mix(outc,bg,vg*mix(.12,.5,dark));
  colour=vec4(outc,1.);
}`;

const BLIT = `#version 300 es
precision mediump float;
uniform sampler2D tex; uniform vec2 r;
out vec4 colour;
float h(vec2 p){return fract(sin(dot(p,vec2(12.9898,78.233)))*43758.5453);}
void main(){vec2 uv=gl_FragCoord.xy/r;colour=vec4(texture(tex,uv).rgb+(h(gl_FragCoord.xy)-.5)/255.,1.);}`;

const POINT_VS = `#version 300 es
layout(location=0) in vec2 pos;
layout(location=1) in vec4 look;
uniform vec2 view; uniform float dpr;
out float va; out float vt; out float vg;
void main(){vec2 c=pos/view*2.-1.;gl_Position=vec4(c.x,-c.y,0.,1.);gl_PointSize=max(look.x*dpr,1.6);va=look.y;vt=look.z;vg=look.w;}`;

const POINT_FS = `#version 300 es
precision mediump float;
in float va; in float vt; in float vg;
uniform vec3 p0,p1,p2,p3; uniform float add;
out vec4 colour;
void main(){
  vec2 d=gl_PointCoord-.5; float r=dot(d,d)*4.;
  if(r>1.)discard;
  float core=1.-smoothstep(.2,1.,r);
  float a=mix(core,exp(-r*2.6),vg)*va;
  vec3 c=vt<1.?mix(p0,p1,vt):vt<2.?mix(p1,p2,vt-1.):mix(p2,p3,min(vt-2.,1.));
  colour=vec4(c*a,a*(1.-add));
}`;

/* ----------------------------------------------------------------------------- palettes */
interface Palette { bg: number[]; c1: number[]; c2: number[]; c3: number[]; k: number; base: number; p: number[][]; add: number; dark: number }
/** The colours from the theme shown (styles.css, --ows-nebula-*): ground, gas, then dust. */
function palette(): Palette {
  const tokens = getComputedStyle(document.documentElement);
  const read = (name: string) => rgb(tokens.getPropertyValue(`--ows-nebula-${name}`).trim() || "#808080");
  const colours = { bg: read("bg"), c1: read("gas-1"), c2: read("gas-2"), c3: read("gas-3"), p: [0, 1, 2, 3].map((k) => read(`dust-${k}`)) };
  return isDark() ? { ...colours, k: 1.1, base: 0.27, add: 0.5, dark: 1 } : { ...colours, k: 0.96, base: 0.14, add: 0, dark: 0 };
}

/* ----------------------------------------------------------------------------- the cycle */
const FIRST = 1.6; // seconds before the first turbine
const CYCLE = 34;
const FORM_END = 10;
const HOLD_END = 22;
const DECON_END = 31;
const FORM_DUR = 2.6;
const OMEGA = 0.62; // blade turn, rad/s

const ROLE_DUST = 0, ROLE_TURBINE = 1, ROLE_WAVE = 2;
// Turbine parts
const TOWER = 0, FOUNDATION = 1, NACELLE = 2, HUB = 3, BLADE = 4; // blades 4, 5, 6

/** Side of a cell of the velocity field stirred by the pointer, in pixels */
const CELL = 22;
/** Orbs at most on the sphere */
const ORBS = 64;

/* ----------------------------------------------------------------------------- the grains' step
   One grain per vertex. In and out, kept between images: s0 = place and velocity (x, y, vx, vy;
   on a shape, its shift from its place there); s1 = drawn place (x, y) and orb place at the last
   image (x, y); s2 = 1 when fixed, + 2 once flung off the turbine this cycle; o3 = look (size,
   opacity, tint, glow).
   Constant: a0 = home (x, y in 0..1), phase, depth; a1 = size, opacity, tint, glow; a2 =
   gathering offset (x, y), turn, scatter; a3 = role, part, start, release; a4 = place in the
   turbine or the waves (u, v). Set by the orbs: b0 = orb, place in it (u, v); b1 = gathering
   start, duration. */
const glsl = (value: number) => (Number.isInteger(value) ? `${value}.` : `${value}`);
const STEP_VS = `#version 300 es
precision highp float;
precision highp int;
layout(location=0) in vec4 s0;
layout(location=1) in vec4 s1;
layout(location=2) in float s2;
layout(location=3) in vec4 a0;
layout(location=4) in vec4 a1;
layout(location=5) in vec4 a2;
layout(location=6) in vec4 a3;
layout(location=7) in vec4 b0;
layout(location=8) in vec2 b1;
layout(location=9) in vec2 a4;
uniform vec2 uView,uScale,uPar,uSway,uHold;
uniform float uDt,uTime,uBefore,uCt,uGlint;
uniform vec4 uPhase,uWave,uOrbT;
uniform vec3 uCycle,uBc,uBs,uFlow,uFluid;
uniform highp sampler2D uField;
uniform vec4 uOrbA[${ORBS}];
uniform vec4 uOrbB[${ORBS}];
out vec4 o0;
out vec4 o1;
out float o2;
out vec4 o3;
const float TAU=6.283185307179586,OMEGA=${glsl(OMEGA)},FORM_DUR=${glsl(FORM_DUR)},CELL=${glsl(CELL)};
const float DEPTHPAR[3]=float[3](.2,.35,.5),COUPLE[3]=float[3](2.4,5.,7.),FLOW[3]=float[3](6.,10.,14.);
float chord(float u){return u<.2?.55+(.45*u)/.2:1.-(.8*(u-.2))/.8;}
float sstep(float a,float b,float v){float t=clamp((v-a)/(b-a),0.,1.);return t*t*(3.-2.*t);}
void main(){
  float W=uView.x,H=uView.y,dt=uDt,time=uTime;
  bool orbs=uPhase.x>.5,settle=uPhase.y>.5,reduced=uPhase.z>.5,intro=!orbs;
  float X=s0.x,Y=s0.y,VX=s0.z,VY=s0.w,RX=s1.x,RY=s1.y,TPX=s1.z,TPY=s1.w;
  // A new cycle of the turbine: nothing has been flung off it yet
  bool lock=mod(s2,2.)>=1.,released=s2>=2.&&uPhase.w<.5;
  float HX=a0.x,HY=a0.y,PHASE=a0.z;int depth=int(a0.w+.5);
  float SIZE=a1.x,ALPHA=a1.y,TINT=a1.z,GLOW=a1.w,OFFX=a2.x,OFFY=a2.y,SWIRL=a2.z,SCAT=a2.w;
  int role=int(a3.x+.5),part=int(a3.y+.5);float START=a3.z,REL=a3.w;
  bool kind=b0.x>.5;int orb=int(b0.y+.5);float OU=b0.z,OV=b0.w,ASTART=b1.x,ADUR=b1.y,PU=a4.x,PV=a4.y;
  // The orb of the grain: x, y, radius, depth; hover, move since the last image (x, y), held by a project
  vec4 oa=vec4(0.),ob=vec4(0.);
  if(kind){oa=uOrbA[orb];ob=uOrbB[orb];}

  // The free grains keep their place in the page as it changes size (a window maximised): moved at
  // once with it, they do not drift towards their new homes. A grain fixed to a shape holds only its
  // shift from it and follows the shape; a grain gathering into an orb is carried by the orb's own move.
  if(uScale!=vec2(1.)&&!lock&&!(orbs&&kind&&uBefore>ASTART)){X*=uScale.x;Y*=uScale.y;}

  // Turbine frame
  float L=min(H,W*.62);
  float bx=W*.8,by=H*.8,towerH=.42*L,hubX=bx,hubY=by-towerH,R=.22*L;
  float centreX=hubX,centreY=(hubY+by)/2.;
  float form=uCycle.x,decon=uCycle.y;bool holding=uCycle.z>.5;
  float span=W+120.,spanY=H+120.;
  float dampLocked=exp(-5.5*dt),dampHome=exp(-1.4*dt);

  // Home in the nebula
  float hx,hy;
  if(orbs){
    float k=DEPTHPAR[depth];
    hx=mod(HX*span+uPar.x*k,span)-60.;
    hy=mod(HY*spanY+uPar.y*k,spanY)-60.;
    if(!lock&&!kind){
      if(X-hx>span/2.)X-=span;else if(hx-X>span/2.)X+=span;
      if(Y-hy>spanY/2.)Y-=spanY;else if(hy-Y>spanY/2.)Y+=spanY;
    }
  }else{hx=HX*W;hy=HY*H;}
  hx+=12.*sin(uSway.x+PHASE*TAU);
  hy+=10.*cos(uSway.y+PHASE*TAU*1.3);

  // Shape: where the grain belongs in the turbine, the waves or an orb, and how far it got
  float p=0.,kHome=1.,sx=0.,sy=0.,tvx=0.,tvy=0.,shapeAlpha=.74,shapeSize=SIZE,shapeTint=TINT,shapeGlow=GLOW;
  float gatherX=0.,gatherY=0.,wrapFade=1.;
  // The sea forms once and stays under the turbine; the turbine comes and goes
  bool sea=role==${ROLE_WAVE}&&intro;
  if(sea||(intro&&role!=${ROLE_DUST}&&(form>=0.||holding||decon>=0.))){
    if(sea)p=reduced?1.:sstep(START,START+FORM_DUR,uCt);
    else if(form>=0.)p=sstep(START,START+FORM_DUR,form);
    else if(holding)p=1.;
    else if(decon<REL)p=1.;
    else{
      if(!released){
        released=true;
        if(lock){lock=false;X=RX;Y=RY;}
        // Flung along the blade's turn; blown off the tower; spray from the waves
        if(role==${ROLE_TURBINE}&&part>=${BLADE}){
          VX+=-OMEGA*(RY-hubY)*1.15+SCAT*20.;
          VY+=OMEGA*(RX-hubX)*1.15+SWIRL*16.;
        }else if(role==${ROLE_TURBINE}){
          VX+=40.+PHASE*70.;
          VY+=-12.-PHASE*26.+SCAT*12.;
        }else{
          VX+=20.+SCAT*30.;
          VY+=-18.-PHASE*30.;
        }
      }
      kHome=sstep(REL,REL+4.5,decon);
    }
    if(p>0.){
      if(role==${ROLE_TURBINE}){
        float u=PU,v=PV;
        if(part==${TOWER}){
          float w=(.024+(.014-.024)*u)*L;
          sx=bx+(v-.5)*w;
          sy=by-.03*L-u*(towerH-.03*L);
        }else if(part==${FOUNDATION}){
          sx=bx+(v-.5)*.036*L;
          sy=by+.006*L-u*.036*L;
        }else if(part==${NACELLE}){
          sx=hubX-.006*L+u*.072*L;
          sy=hubY-.017*L+v*.03*L;
        }else if(part==${HUB}){
          float a=u*TAU,rr=sqrt(v)*.017*L;
          sx=hubX-.01*L+cos(a)*rr*.75;
          sy=hubY+sin(a)*rr;
        }else{
          int b=part-${BLADE};
          float along=.016*L+u*(R-.016*L);
          float across=(v-.35)*.036*L*chord(u);
          sx=hubX+uBc[b]*along-uBs[b]*across;
          sy=hubY+uBs[b]*along+uBc[b]*across;
          tvx=-OMEGA*(sy-hubY);
          tvy=OMEGA*(sx-hubX);
          // A light running out along each blade from time to time
          float d=u-(uGlint-float(b)*.12);
          shapeAlpha+=.3*exp(-(d*d)/.003);
        }
        gatherX=sx*.4+centreX*.6;
        gatherY=sy*.4+centreY*.6;
      }else{
        // A surface, not rows: crossing swells whose crests bend with the distance
        float z=PV;
        float speed=.003+z*.006;
        float f=fract(PU+time*speed);
        float xw=(-.06+f*1.12)*W;
        float horizon=by-.03*L;
        float yb=horizon+pow(z,1.5)*(H*1.02-horizon);
        float A=(.003+.03*z*z)*L;
        float k=TAU/((.12+.35*z)*L);
        float ph=xw*k+z*7.-uWave.x;
        float env=.6+.4*sin(xw*.0021-uWave.y+z*5.);
        float h=A*env*(.55*sin(ph)+.3*sin(xw*k*1.73-z*11.+uWave.z+1.3)+.25*sin(xw*k*.61+z*3.1-uWave.w+4.));
        sx=xw-.45*A*env*cos(ph);
        sy=yb-h;
        tvx=speed*1.12*W;
        float crest=clamp(h/(A*env*.9+1e-6),0.,1.);
        shapeTint=1.25+crest*1.5+z*.3;
        shapeAlpha=(.62+.38*crest)*(.74+.26*z);
        shapeSize=SIZE*1.1;
        wrapFade=sstep(0.,.05,f)*(1.-sstep(.95,1.,f));
        gatherX=sx;
        gatherY=sy-40.-PHASE*60.;
      }
      if(holding||p>=1.){
        sx+=sin(uHold.x+PHASE*40.)*.5;
        sy+=cos(uHold.y+PHASE*31.)*.5;
      }
    }
  }else if(orbs&&kind){
    // A drop: its edge ripples, its inside turns, faster near the middle; lit from the upper left
    float kf=float(orb),r=oa.z;
    p=settle?1.:sstep(ASTART,ASTART+ADUR,time);
    float v=sqrt(OV);
    float turn=(orb%2==1?1.:-1.)*time*(.22+.55*(1.-v));
    float a=OU*TAU+turn;
    float ripple=1.+.07*sin(3.*a+uOrbT.x+kf)+.05*sin(5.*a-uOrbT.y+kf*2.3)+.035*sin(2.*a+uOrbT.z+kf*.7);
    float rr=(PHASE<.07?v*.55:v>.93?.97+(v-.93):v)*r*ripple;
    float ca=cos(a),sa=sin(a);
    sx=oa.x+ca*rr;
    sy=oa.y+sa*rr*(.94+.06*sin(uOrbT.w+kf));
    tvx=settle?0.:(sx-TPX)/max(dt,1e-3);
    tvy=settle?0.:(sy-TPY)/max(dt,1e-3);
    TPX=sx;
    TPY=sy;
    gatherX=oa.x;
    gatherY=oa.y;
    // Lit from the upper left: lighter there, a bright spot, a darker lower right
    float lit=clamp(.5-.5*(ca*.6+sa*.8)*v,0.,1.);
    float sxo=ca*v+.38,syo=sa*v+.42;
    float spot=exp(-(sxo*sxo+syo*syo)/.035);
    float rim=sstep(.82,1.,v);
    float depthLook=.35+.65*oa.w;
    float glow=ob.x;
    bool taken=ob.w>.5;
    float tone=taken?1.7+.75*lit+.35*rim+.3*glow+.6*spot:.2+.6*lit+.3*rim+.6*glow+.5*spot;
    if(PHASE<.07){
      // The body: a few broad soft grains filling the drop like a liquid
      shapeTint=tone-.3;
      shapeAlpha=(taken?.17:.15)*depthLook*(1.+.6*glow);
      shapeSize=r*(.55+.25*(1.-v));
      shapeGlow=1.;
    }else{
      shapeTint=tone;
      shapeAlpha=((taken?.68:.42)+.28*rim+.25*spot+.2*glow)*depthLook;
      shapeSize=(1.5+.6*rim+1.2*spot)*(.75+.5*oa.w);
      shapeGlow=.2;
    }
  }

  if(settle){
    // Still pictures: every grain where it belongs
    lock=false;
    X=p>=1.?sx:hx;
    Y=p>=1.?sy:hy;
    VX=0.;
    VY=0.;
  }

  // The fluid stirred by the pointer
  float fx=0.,fy=0.,act=0.;
  if(uFluid.x>.5){
    float px=lock?sx+X:X,py=lock?sy+Y:Y;
    float gx=clamp(px/CELL,0.,uFluid.y-1.001),gy=clamp(py/CELL,0.,uFluid.z-1.001);
    float c=floor(gx),r=floor(gy),wx=gx-c,wy=gy-r;
    ivec2 cell=ivec2(int(c),int(r));
    vec2 g=(texelFetch(uField,cell,0).xy*(1.-wx)+texelFetch(uField,cell+ivec2(1,0),0).xy*wx)*(1.-wy)
      +(texelFetch(uField,cell+ivec2(0,1),0).xy*(1.-wx)+texelFetch(uField,cell+ivec2(1,1),0).xy*wx)*wy;
    float speed=abs(g.x)+abs(g.y);
    if(speed>2.){
      act=min(1.,speed/60.)*min(1.,COUPLE[depth]*dt);
      fx=g.x;
      fy=g.y;
    }
  }

  if(lock){
    if(p<1.){
      lock=false;
      X=RX;
      Y=RY;
    }else{
      // Fixed to its place: only the displacement moves, and comes back
      float dvx=VX,dvy=VY;
      // An orb barely gives way under the pointer and comes back quickly
      bool onOrb=orbs&&kind;
      float spring=onOrb?22.:14.;
      dvx+=-spring*X*dt;
      dvy+=-spring*Y*dt;
      if(onOrb)act*=.45;
      if(act!=0.){
        dvx+=(fx-tvx-dvx)*act+(-fy*SCAT*.35)*act;
        dvy+=(fy-tvy-dvy)*act+(fx*SCAT*.35)*act;
      }
      VX=dvx*dampLocked;
      VY=dvy*dampLocked;
      X+=VX*dt;
      Y+=VY*dt;
      RX=sx+X;
      RY=sy+Y;
    }
  }
  if(!lock){
    float tx=hx,ty=hy,k=.5*kHome,c=1.4+(1.-kHome)*-.6;
    float flow=1.;
    if(p>0.){
      // A loose cloud first, then the silhouette in a haze that tightens, turning
      float q=1.-p;
      float a=q*1.4*SWIRL,ca=cos(a),sa=sin(a);
      float offx=OFFX*ca-OFFY*sa,offy=OFFX*sa+OFFY*ca;
      float haze=pow(q,1.7);
      float ax=gatherX+offx*2.3,ay=gatherY+offy*2.3;
      float bxx=sx+offx*haze,byy=sy+offy*haze;
      float m=sstep(.18,.6,p);
      float sxp=ax+(bxx-ax)*m,syp=ay+(byy-ay)*m;
      float w=sstep(0.,.2,p);
      tx=hx+(sxp-hx)*w;
      ty=hy+(syp-hy)*w;
      if(orbs){
        k=1.5+38.*p*p;
        c=2.2+7.5*p;
      }else{
        k=.7+22.*pow(p,2.2);
        c=1.5+5.5*p;
      }
      flow=(1.-p)*(1.-p);
    }
    // An orb carries its grains along: the spring only brings each one to its place in the drop, so
    // nothing trails behind an orb that is dragged or flung
    bool carried=!settle&&orbs&&kind&&p>0.;
    if(carried){
      float w=sstep(0.,.2,p);
      X+=ob.y*w;
      Y+=ob.z*w;
    }
    float vx=VX,vy=VY;
    vx+=(tx-X)*k*dt;
    vy+=(ty-Y)*k*dt;
    if(flow>.01){
      float ang=2.2*sin(X*.0032+uFlow.x)+2.*cos(Y*.0041-uFlow.y)+1.3*sin((X-Y)*.0019+uFlow.z);
      float F=FLOW[depth]*flow*(kHome<1.?2.2:1.);
      vx+=(cos(ang)*F+3.*flow)*dt;
      vy+=sin(ang)*F*dt;
    }
    if(act!=0.){
      vx+=(fx-vx)*act+(-fy*SCAT*.35)*act;
      vy+=(fy-vy)*act+(fx*SCAT*.35)*act;
    }
    float d=p>0.||kHome<1.?exp(-c*dt):dampHome;
    vx*=d;
    vy*=d;
    X+=vx*dt;
    Y+=vy*dt;
    VX=vx;
    VY=vy;
    RX=X;
    RY=Y;
    // Arrived and at rest: from now on fixed to its place
    // (an orb grain near its place: its velocity is already relative to the orb)
    float reach=carried?max(1.5,.2*oa.z):1.5;
    if(p>=1.&&abs(X-sx)<reach&&abs(Y-sy)<reach&&(carried?abs(vx)+abs(vy)<80.:abs(vx-tvx)+abs(vy-tvy)<40.)){
      lock=true;
      X-=sx;
      Y-=sy;
      VX=carried?0.:vx-tvx;
      VY=carried?0.:vy-tvy;
    }
  }

  // Look
  float alpha=ALPHA,size=SIZE,tint=TINT;
  if(GLOW>=1.)alpha*=.65+.35*sin(time*(.6+PHASE)+PHASE*TAU);
  if(p>0.){
    alpha+=(shapeAlpha-alpha)*p;
    size+=(shapeSize-size)*p;
    tint+=(shapeTint-tint)*p;
    alpha*=1.-(1.-wrapFade)*p;
  }
  // Around the orbs, the free nebula steps back
  if(orbs&&!kind)alpha*=.5;
  o0=vec4(X,Y,VX,VY);
  o1=vec4(RX,RY,TPX,TPY);
  o2=(lock?1.:0.)+(released?2.:0.);
  o3=vec4(size,min(1.,alpha),tint,GLOW+(shapeGlow-GLOW)*p);
  gl_Position=vec4(0.,0.,0.,1.);
}`;
const STEP_FS = `#version 300 es
precision mediump float;
void main(){}`;

/** A program handed to the graphics card, which compiles it on its side. */
function build(gl: WebGL2RenderingContext, vs: string, fs: string, kept?: string[]): WebGLProgram {
  const program = gl.createProgram();
  for (const [type, source] of [[gl.VERTEX_SHADER, vs], [gl.FRAGMENT_SHADER, fs]] as const) {
    const shader = gl.createShader(type)!;
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    gl.attachShader(program, shader);
  }
  // What the vertex shader gives out for each grain is kept in a buffer, in this order
  if (kept) gl.transformFeedbackVaryings(program, kept, gl.INTERLEAVED_ATTRIBS);
  gl.linkProgram(program);
  return program;
}
/** A program compiled, waited for; null when the card refuses it. */
function compile(gl: WebGL2RenderingContext, vs: string, fs: string): WebGLProgram | null {
  const program = build(gl, vs, fs);
  return gl.getProgramParameter(program, gl.LINK_STATUS) ? program : null;
}

/** The gas's table as the shader reads it: for each point of the grid, its number and those of the
    points on its right, above it and above right (read once, kept for the next visits of the page). */
let gridCorners: Float32Array | undefined;
function corners(): Float32Array {
  if (gridCorners) return gridCorners;
  const { size, values } = GAS_GRID;
  const text = atob(values);
  const at = (x: number, y: number) => {
    const k = ((y & (size - 1)) * size + (x & (size - 1))) * 2;
    return (text.charCodeAt(k) | (text.charCodeAt(k + 1) << 8)) / 65536;
  };
  const out = new Float32Array(size * size * 4);
  for (let y = 0, k = 0; y < size; y++) {
    for (let x = 0; x < size; x++, k += 4) {
      out[k] = at(x, y);
      out[k + 1] = at(x + 1, y);
      out[k + 2] = at(x, y + 1);
      out[k + 3] = at(x + 1, y + 1);
    }
  }
  return (gridCorners = out);
}

/** The grains of a page that holds `N` of them: for each, the numbers that never change (a0 to a4 of
    STEP_VS). Drawn from seeded numbers, the same at every visit: kept for the next one. */
const FIXED = 18;
let scattered: { count: number; fixed: Float32Array } | undefined;
function scatter(N: number) {
  if (scattered?.count === N) return scattered;
  const rand = seeded(20251104);
  const HX = new Float32Array(N), HY = new Float32Array(N);
  const SIZE = new Float32Array(N), ALPHA = new Float32Array(N), TINT = new Float32Array(N), GLOW = new Float32Array(N), PHASE = new Float32Array(N);
  const DEPTH = new Uint8Array(N), ROLE = new Uint8Array(N), PART = new Uint8Array(N);
  const PU = new Float32Array(N), PV = new Float32Array(N), START = new Float32Array(N), REL = new Float32Array(N);
  const OFFX = new Float32Array(N), OFFY = new Float32Array(N), SWIRL = new Float32Array(N), SCAT = new Float32Array(N);

  // Homes: filaments of a noise field over the whole page, and a thinner veil everywhere
  for (let i = 0; i < N; i++) {
    let x = 0, y = 0;
    if (rand() < 0.7) {
      for (let tries = 0; tries < 30; tries++) {
        x = rand() * 1.08 - 0.04;
        y = rand() * 1.08 - 0.04;
        const d = fbm(x * 3.1 + 4, y * 2.1 + 1.3);
        const w = fbm(x * 6.3 + d * 2.5, y * 4.2 - d * 1.5);
        if (rand() < smoothstep(0.36, 0.7, d) * (0.5 + 0.7 * w)) break;
      }
    } else {
      x = rand() * 1.08 - 0.04;
      y = rand() * 1.08 - 0.04;
    }
    HX[i] = x;
    HY[i] = y;
    PHASE[i] = rand();
    const depth = rand();
    DEPTH[i] = depth < 0.42 ? 0 : depth < 0.86 ? 1 : 2;
    const star = rand() < 0.015;
    SIZE[i] = star ? 4 + rand() * 3 : DEPTH[i] === 0 ? 1.1 + rand() * 0.7 : DEPTH[i] === 1 ? 1.5 + rand() * 1.1 : 2.3 + rand() * 1.6;
    ALPHA[i] = star ? 0.75 + rand() * 0.25 : DEPTH[i] === 0 ? 0.22 + rand() * 0.2 : DEPTH[i] === 1 ? 0.36 + rand() * 0.28 : 0.48 + rand() * 0.32;
    TINT[i] = star ? 2 + rand() * 0.6 : DEPTH[i] === 0 ? rand() * 0.8 : rand() * 1.4;
    GLOW[i] = star ? 1 : DEPTH[i] === 2 ? 0.35 : 0;
    const angle = rand() * TAU, length = 50 + rand() * 140;
    OFFX[i] = Math.cos(angle) * length;
    OFFY[i] = Math.sin(angle) * length;
    SWIRL[i] = rand() < 0.5 ? -1 : 1;
    SCAT[i] = rand() * 2 - 1;
  }

  // The turbine and the waves take grains of the middle and near depths
  const nTurbine = Math.round(N * 0.22), nWave = Math.round(N * 0.2);
  const shapeGrains: number[] = [];
  for (let i = 0; i < N && shapeGrains.length < nTurbine + nWave; i++) if (DEPTH[i] > 0 && GLOW[i] < 1) shapeGrains.push(i);
  const chord = (u: number) => (u < 0.2 ? 0.55 + (0.45 * u) / 0.2 : 1 - (0.8 * (u - 0.2)) / 0.8);
  shapeGrains.forEach((i, j) => {
    if (j < nTurbine) {
      ROLE[i] = ROLE_TURBINE;
      const share = j / nTurbine;
      const edge = rand() < 0.4;
      let v = edge ? (rand() < 0.5 ? rand() * 0.06 : 0.94 + rand() * 0.06) : rand();
      let u = rand();
      let part: number;
      if (share < 0.26) part = TOWER;
      else if (share < 0.31) part = FOUNDATION;
      else if (share < 0.4) part = NACELLE;
      else if (share < 0.44) part = HUB;
      else part = BLADE + (Math.floor(((share - 0.44) / 0.56) * 3) % 3);
      if (part >= BLADE) {
        // Along the blade as much as its width
        while (rand() > chord(u)) u = rand();
      }
      if (part === HUB) v = rand();
      PART[i] = part;
      PU[i] = u;
      PV[i] = v;
      TINT[i] = edge ? 2.05 + rand() * 0.3 : 1.3 + rand() * 0.5;
      SIZE[i] = edge ? 1.6 + rand() * 0.45 : 1.4 + rand() * 0.55;
      START[i] = part === FOUNDATION ? 1 + rand() * 0.6
        : part === TOWER ? 1.4 + u * 2.4 + rand() * 0.7
        : part === NACELLE ? 3.6 + rand() * 0.8
        : part === HUB ? 3.9 + rand() * 0.6
        : 4.2 + u * 1.9 + rand() * 0.7 + (part - BLADE) * 0.15;
      REL[i] = part >= BLADE ? (1 - u) * 1.8 + rand() * 0.8 + (part - BLADE) * 0.1
        : part === HUB ? 2.2 + rand() * 0.5
        : part === NACELLE ? 2.4 + rand() * 0.6
        : part === TOWER ? 2.8 + (1 - u) * 2.6 + rand() * 0.6
        : 5.2 + rand() * 0.6;
    } else {
      ROLE[i] = ROLE_WAVE;
      // A place on the sea: across (u) and from the horizon to the front (v)
      PU[i] = rand();
      PV[i] = Math.pow(rand(), 0.85);
      SIZE[i] = 1.4 + PV[i] * 1.7 + rand() * 0.4;
      START[i] = 0.2 + Math.abs(PU[i] * 1.12 - 0.06 - 0.8) * 2 + PV[i] * 0.8 + rand() * 0.8;
      REL[i] = 3 + rand() * 3.2;
    }
  });

  const fixed = new Float32Array(N * FIXED);
  for (let i = 0, at = 0; i < N; i++, at += FIXED) {
    fixed[at] = HX[i]; fixed[at + 1] = HY[i]; fixed[at + 2] = PHASE[i]; fixed[at + 3] = DEPTH[i];
    fixed[at + 4] = SIZE[i]; fixed[at + 5] = ALPHA[i]; fixed[at + 6] = TINT[i]; fixed[at + 7] = GLOW[i];
    fixed[at + 8] = OFFX[i]; fixed[at + 9] = OFFY[i]; fixed[at + 10] = SWIRL[i]; fixed[at + 11] = SCAT[i];
    fixed[at + 12] = ROLE[i]; fixed[at + 13] = PART[i]; fixed[at + 14] = START[i]; fixed[at + 15] = REL[i];
    fixed[at + 16] = PU[i]; fixed[at + 17] = PV[i];
  }
  return (scattered = { count: N, fixed });
}

/** What the graphics card keeps for each grain, in numbers: its place and velocity (4), where it is
    drawn and where its place in an orb was (4), its flags (1), its look (4) */
const KEPT = 13;
const DRAWN = 4, TARGET = 6, FLAGS = 8, LOOK = 9;

export function createEngine(canvas: HTMLCanvasElement, options: { reduced: boolean; mode: Mode }): Engine | null {
  const gl = canvas.getContext("webgl2", { antialias: false, alpha: false, premultipliedAlpha: true, powerPreference: "low-power" });
  if (!gl) return null;
  // The grains' step is the longest to compile, the first time: the card starts on it at once and
  // goes on while the page does the rest; nothing is drawn before it is ready
  const waiting = gl.getExtension("KHR_parallel_shader_compile");
  const stepper = build(gl, STEP_VS, STEP_FS, ["o0", "o1", "o2", "o3"]);
  const gas = compile(gl, FULL, GAS), blit = compile(gl, FULL, BLIT), points = compile(gl, POINT_VS, POINT_FS);
  if (!gas || !blit || !points) return null;
  const uniforms = (program: WebGLProgram, names: string[]) => Object.fromEntries(names.map((n) => [n, gl.getUniformLocation(program, n)]));
  const ug = uniforms(gas, ["r", "t", "k", "o", "flash", "base", "dark", "zs", "bg", "c1", "c2", "c3", "pan", "grid"]);
  const ub = uniforms(blit, ["tex", "r"]);
  const up = uniforms(points, ["view", "dpr", "p0", "p1", "p2", "p3", "add"]);
  let us: Record<string, WebGLUniformLocation | null> | null = null;
  let refused = false;
  /** True once the grains' step can run. */
  const ready = () => {
    if (us) return true;
    if (refused || (waiting && !gl.getProgramParameter(stepper, waiting.COMPLETION_STATUS_KHR))) return false;
    if (!gl.getProgramParameter(stepper, gl.LINK_STATUS)) {
      refused = true;
      return false;
    }
    us = uniforms(stepper, ["uView", "uScale", "uPar", "uSway", "uHold", "uDt", "uTime", "uBefore", "uCt", "uGlint", "uPhase", "uWave", "uOrbT", "uCycle", "uBc", "uBs", "uFlow", "uFluid", "uField", "uOrbA", "uOrbB"]);
    return true;
  };
  if (!waiting && !ready()) return null;
  // The canvas shows nothing before its first picture (an empty one would be black)
  let drawn = false;
  canvas.style.visibility = "hidden";
  const reduced = options.reduced;
  let mode: Mode = options.mode;
  let colours = palette();
  // Textures: 0 the gas drawn small, 1 the gas's table, 2 the velocity field
  const texture = (unit: number, smooth: boolean) => {
    const made = gl.createTexture();
    gl.activeTexture(gl.TEXTURE0 + unit);
    gl.bindTexture(gl.TEXTURE_2D, made);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, smooth ? gl.LINEAR : gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, smooth ? gl.LINEAR : gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    return made;
  };

  /* ------------------------------------------------------------------- size */
  let W = 2, H = 2, dpr = 1, bw = 2, bh = 2;
  const target = texture(0, true);
  const frame = gl.createFramebuffer();
  texture(1, false);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA32F, GAS_GRID.size, GAS_GRID.size, 0, gl.RGBA, gl.FLOAT, corners());

  /* ------------------------------------------------------------------- fluid */
  let gw = 2, gh = 2;
  let fu = new Float32Array(4), fv = new Float32Array(4), su = new Float32Array(4), sv = new Float32Array(4);
  // The field as the grains' step reads it: both velocities of each cell, side by side
  let field = new Float32Array(8);
  texture(2, false);
  const fluidResize = () => {
    gw = Math.ceil(W / CELL) + 2;
    gh = Math.ceil(H / CELL) + 2;
    const n = gw * gh;
    fu = new Float32Array(n); fv = new Float32Array(n); su = new Float32Array(n); sv = new Float32Array(n);
    field = new Float32Array(n * 2);
    gl.activeTexture(gl.TEXTURE2);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RG32F, gw, gh, 0, gl.RG, gl.FLOAT, field);
  };
  let fluidActive = false;
  const inject = (x: number, y: number, vx: number, vy: number, radius: number) => {
    const c0 = Math.max(0, Math.floor((x - radius) / CELL)), c1 = Math.min(gw - 1, Math.ceil((x + radius) / CELL));
    const r0 = Math.max(0, Math.floor((y - radius) / CELL)), r1 = Math.min(gh - 1, Math.ceil((y + radius) / CELL));
    const speed = Math.hypot(vx, vy);
    for (let r = r0; r <= r1; r++) {
      for (let c = c0; c <= c1; c++) {
        const dx = c * CELL - x, dy = r * CELL - y, d = Math.hypot(dx, dy);
        if (d >= radius) continue;
        let f = 1 - d / radius;
        f *= f;
        const i = r * gw + c;
        // Carried along the stroke, and pushed aside from it
        const out = d > 1 ? speed * 0.2 * f / d : 0;
        fu[i] = clamp(fu[i] + vx * 0.5 * f + dx * out, -1600, 1600);
        fv[i] = clamp(fv[i] + vy * 0.5 * f + dy * out, -1600, 1600);
      }
    }
    fluidActive = true;
  };
  const radial = (x: number, y: number, radius: number, speed: number) => {
    for (let r = 0; r < gh; r++) {
      for (let c = 0; c < gw; c++) {
        const dx = c * CELL - x, dy = r * CELL - y, d = Math.hypot(dx, dy);
        if (d >= radius || d < 1) continue;
        const f = Math.pow(1 - d / radius, 1.5) * speed / d;
        fu[r * gw + c] += dx * f;
        fv[r * gw + c] += dy * f;
      }
    }
    fluidActive = true;
  };
  const fluidStep = (dt: number) => {
    if (!fluidActive) return;
    const decay = Math.exp(-2.1 * dt);
    let energy = 0;
    for (let r = 0; r < gh; r++) {
      for (let c = 0; c < gw; c++) {
        const i = r * gw + c;
        const l = c > 0 ? i - 1 : i, rr = c < gw - 1 ? i + 1 : i, t = r > 0 ? i - gw : i, b = r < gh - 1 ? i + gw : i;
        su[i] = (fu[i] * 0.78 + (fu[l] + fu[rr] + fu[t] + fu[b]) * 0.055) * decay;
        sv[i] = (fv[i] * 0.78 + (fv[l] + fv[rr] + fv[t] + fv[b]) * 0.055) * decay;
      }
    }
    for (let i = 0; i < fu.length; i++) {
      fu[i] = Math.abs(su[i]) < 0.5 ? 0 : su[i];
      fv[i] = Math.abs(sv[i]) < 0.5 ? 0 : sv[i];
      energy += Math.abs(fu[i]) + Math.abs(fv[i]);
    }
    if (energy < fu.length * 0.05) fluidActive = false;
  };
  /* ------------------------------------------------------------------- grains */
  const area = Math.max(1, canvas.clientWidth * canvas.clientHeight || window.innerWidth * window.innerHeight);
  const N = Math.round(clamp(area / 44, 10000, 30000));
  const { fixed } = scatter(N);
  // In an orb (1) or free (0), which orb, its place in it, when it starts gathering and for how long
  const KIND = new Uint8Array(N), ORB = new Uint16Array(N), OU = new Float32Array(N), OV = new Float32Array(N);
  const ASTART = new Float32Array(N), ADUR = new Float32Array(N).fill(1);

  /* ------------------------------------------------------------------- the grains on the graphics card */
  // What the card keeps for each grain, as the page holds it only when the orbs form or dissolve
  // (the one moment its own code chooses and frees grains). Start in the nebula.
  const S = new Float32Array(N * KEPT);
  // What the orbs set
  const set = new Float32Array(N * 6);
  for (let i = 0; i < N; i++) {
    S[i * KEPT] = S[i * KEPT + DRAWN] = fixed[i * FIXED] * (canvas.clientWidth || window.innerWidth);
    S[i * KEPT + 1] = S[i * KEPT + DRAWN + 1] = fixed[i * FIXED + 1] * (canvas.clientHeight || window.innerHeight);
  }
  const buffer = (data: Float32Array, usage: number) => {
    const made = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, made);
    gl.bufferData(gl.ARRAY_BUFFER, data, usage);
    return made;
  };
  // Two buffers by turns: each step reads the grains in one and writes them in the other
  const kept = [buffer(S, gl.DYNAMIC_COPY), buffer(S, gl.DYNAMIC_COPY)];
  const fixedBuffer = buffer(fixed, gl.STATIC_DRAW), setBuffer = buffer(set, gl.DYNAMIC_DRAW);
  const attribute = (location: number, size: number, stride: number, offset: number) => {
    gl.enableVertexAttribArray(location);
    gl.vertexAttribPointer(location, size, gl.FLOAT, false, stride * 4, offset * 4);
  };
  const stepArrays = kept.map((grains) => {
    const array = gl.createVertexArray();
    gl.bindVertexArray(array);
    gl.bindBuffer(gl.ARRAY_BUFFER, grains);
    attribute(0, 4, KEPT, 0);
    attribute(1, 4, KEPT, DRAWN);
    attribute(2, 1, KEPT, FLAGS);
    gl.bindBuffer(gl.ARRAY_BUFFER, fixedBuffer);
    for (let k = 0; k < 4; k++) attribute(3 + k, 4, FIXED, k * 4);
    attribute(9, 2, FIXED, 16);
    gl.bindBuffer(gl.ARRAY_BUFFER, setBuffer);
    attribute(7, 4, 6, 0);
    attribute(8, 2, 6, 4);
    return array;
  });
  // For the drawing: where each grain is, and its look
  const drawArrays = kept.map((grains) => {
    const array = gl.createVertexArray();
    gl.bindVertexArray(array);
    gl.bindBuffer(gl.ARRAY_BUFFER, grains);
    attribute(0, 2, KEPT, DRAWN);
    attribute(1, 4, KEPT, LOOK);
    return array;
  });
  gl.bindVertexArray(null);
  gl.bindBuffer(gl.ARRAY_BUFFER, null);
  const feedback = gl.createTransformFeedback();
  // The buffer that holds the grains now
  let current = 0;
  const pull = () => {
    gl.bindBuffer(gl.ARRAY_BUFFER, kept[current]);
    gl.getBufferSubData(gl.ARRAY_BUFFER, 0, S);
    gl.bindBuffer(gl.ARRAY_BUFFER, null);
  };
  const push = () => {
    gl.bindBuffer(gl.ARRAY_BUFFER, kept[current]);
    gl.bufferSubData(gl.ARRAY_BUFFER, 0, S);
    for (let i = 0, at = 0; i < N; i++, at += 6) {
      set[at] = KIND[i]; set[at + 1] = ORB[i]; set[at + 2] = OU[i]; set[at + 3] = OV[i]; set[at + 4] = ASTART[i]; set[at + 5] = ADUR[i];
    }
    gl.bindBuffer(gl.ARRAY_BUFFER, setBuffer);
    gl.bufferSubData(gl.ARRAY_BUFFER, 0, set);
    gl.bindBuffer(gl.ARRAY_BUFFER, null);
  };
  push();

  /* ------------------------------------------------------------------- the sphere */
  // Orbs evenly over a sphere (golden spiral); it turns on its own, faster for a while after a drag
  let held: boolean[] = [];
  let hover = -1;
  const HOVER = new Float32Array(64);
  let dirX = new Float32Array(0), dirY = new Float32Array(0), dirZ = new Float32Array(0);
  const OX = new Float32Array(64), OY = new Float32Array(64), OR = new Float32Array(64), OD = new Float32Array(64);
  // How far each orb moved since the last image: its grains are carried by as much
  const DOX = new Float32Array(64), DOY = new Float32Array(64);
  let yaw = 0.4, pitch = -0.32, yawSpeed = 0, pitchSpeed = 0, dragging = false;
  const SPIN = reduced ? 0 : 0.085;
  let parX = 0, parY = 0;
  const sphere = () => {
    const radius = Math.min(W * 0.34, H * 0.36);
    return { cx: W * 0.5, cy: H * 0.55, radius, orb: clamp(Math.min(W, H) * 0.04, 16, 44) };
  };
  /** Each orb's place on the screen now */
  const placeOrbs = (dt: number) => {
    const n = held.length;
    const { cx, cy, radius, orb } = sphere();
    const cyw = Math.cos(yaw), syw = Math.sin(yaw), cp = Math.cos(pitch), sp = Math.sin(pitch);
    for (let k = 0; k < n; k++) {
      const x = dirX[k] * cyw + dirZ[k] * syw, z0 = -dirX[k] * syw + dirZ[k] * cyw;
      const y = dirY[k] * cp - z0 * sp, z = dirY[k] * sp + z0 * cp;
      const near = 3.4 / (3.4 - z);
      HOVER[k] += ((k === hover ? 1 : 0) - HOVER[k]) * (1 - Math.exp(-10 * dt));
      const ox = cx + x * radius * near, oy = cy + y * radius * near;
      DOX[k] = dt > 0 ? ox - OX[k] : 0;
      DOY[k] = dt > 0 ? oy - OY[k] : 0;
      OX[k] = ox;
      OY[k] = oy;
      OR[k] = orb * near * (held[k] ? 1.12 : 1) * (1 + 0.14 * HOVER[k]);
      OD[k] = (z + 1) / 2;
    }
  };
  const stepSpin = (dt: number) => {
    if (!dragging) {
      yaw += (SPIN + yawSpeed) * dt;
      pitch = clamp(pitch + pitchSpeed * dt, -1.1, 1.1);
      const f = Math.exp(-1.6 * dt);
      yawSpeed *= f;
      pitchSpeed *= f;
      // The tilt eases back to its rest
      pitch += (-0.32 - pitch) * (1 - Math.exp(-0.5 * dt)) * (Math.abs(pitchSpeed) < 0.05 ? 1 : 0);
    }
  };

  /* ------------------------------------------------------------------- orbs */
  let burstAt: { x: number; y: number; time: number } | null = null;
  // A grain fixed to its place is free again, where it is drawn
  const unlock = (i: number) => {
    const at = i * KEPT;
    if (!(S[at + FLAGS] & 1)) return;
    S[at + FLAGS] -= 1;
    S[at] = S[at + DRAWN];
    S[at + 1] = S[at + DRAWN + 1];
  };
  const release = (i: number) => {
    unlock(i);
    KIND[i] = 0;
  };
  const clearOrbs = () => {
    pull();
    for (let i = 0; i < N; i++) release(i);
    push();
  };
  /* The grains of each orb are taken from the nebula nearest to it, the front orbs first; each grain
     gets a place in the drop (an angle and a distance from the middle) and a start in the gathering. */
  const formOrbs = () => {
    pull();
    for (let i = 0; i < N; i++) release(i);
    const n = held.length;
    if (n) gather(n);
    push();
  };
  const gather = (n: number) => {
    const pick = seeded(31 + n);
    placeOrbs(0);
    const per = Math.min(1100, Math.floor((N * 0.6) / n));
    const order = Array.from({ length: n }, (_, k) => k).sort((a, b) => OD[b] - OD[a]);
    const taken = new Uint8Array(N);
    const from = burstAt && performance.now() / 1000 - burstAt.time < 4 ? burstAt : { x: W / 2, y: H / 2 };
    const diagonal = Math.hypot(W, H);
    // The free grains by distance, coarse: a grid of cells
    const cell = 40, cols = Math.ceil(W / cell) + 1, rows = Math.ceil(H / cell) + 1;
    const buckets: number[][] = Array.from({ length: cols * rows }, () => []);
    for (let i = 0; i < N; i++) {
      if (fixed[i * FIXED + 7] >= 1) continue;
      const c = clamp(Math.floor(S[i * KEPT + DRAWN] / cell), 0, cols - 1), r = clamp(Math.floor(S[i * KEPT + DRAWN + 1] / cell), 0, rows - 1);
      buckets[r * cols + c].push(i);
    }
    order.forEach((k, rank) => {
      const bc = clamp(Math.floor(OX[k] / cell), 0, cols - 1), br = clamp(Math.floor(OY[k] / cell), 0, rows - 1);
      let got = 0;
      for (let ring = 0; ring < Math.max(cols, rows) && got < per; ring++) {
        for (let dy = -ring; dy <= ring && got < per; dy++) {
          for (let dx = -ring; dx <= ring && got < per; dx++) {
            if (Math.max(Math.abs(dx), Math.abs(dy)) !== ring) continue;
            const c = bc + dx, r = br + dy;
            if (c < 0 || r < 0 || c >= cols || r >= rows) continue;
            for (const i of buckets[r * cols + c]) {
              if (taken[i]) continue;
              taken[i] = 1;
              unlock(i);
              KIND[i] = 1;
              ORB[i] = k;
              OU[i] = pick();
              OV[i] = pick();
              ASTART[i] = time + 0.1 + rank * 0.035 + (Math.hypot(OX[k] - from.x, OY[k] - from.y) / diagonal) * 0.6 + pick() * 0.5;
              ADUR[i] = 1.5 + pick() * 0.7;
              S[i * KEPT + TARGET] = S[i * KEPT + DRAWN];
              S[i * KEPT + TARGET + 1] = S[i * KEPT + DRAWN + 1];
              if (++got >= per) break;
            }
          }
        }
      }
    });
  };

  /* ------------------------------------------------------------------- where the canvas sits */
  let rect = canvas.getBoundingClientRect();
  let rectAt = -1;
  const readRect = () => {
    rect = canvas.getBoundingClientRect();
  };

  /* ------------------------------------------------------------------- pointer */
  const pointer = { x: 0, y: 0, lx: 0, ly: 0, known: false, moved: false };
  const onPointer = (event: PointerEvent) => {
    pointer.x = event.clientX - rect.left;
    pointer.y = event.clientY - rect.top;
    pointer.moved = true;
  };
  window.addEventListener("pointermove", onPointer, { passive: true });

  /* ------------------------------------------------------------------- simulation */
  let time = 0;
  let cycleIndex = -1;
  let flash = 0;
  let openness = mode === "orbs" ? 1 : 0;
  // The page's change of size that the grains have not followed yet
  let scaleX = 1, scaleY = 1;
  const orbA = new Float32Array(ORBS * 4), orbB = new Float32Array(ORBS * 4);

  /** The grains one image further: `dt` seconds after `before`. With `settle`, every grain where it
      belongs, for a still picture. The graphics card computes each grain (STEP_VS). */
  const step = (dt: number, settle: boolean, before: number) => {
    if (!us) return;
    const orbs = mode === "orbs";
    if (orbs) placeOrbs(dt);
    // Where the turbine is in its cycle
    let form = -1, decon = -1, holding = false, renewed = false;
    if (!orbs && !reduced) {
      const ct = time - FIRST;
      if (ct >= 0) {
        const index = Math.floor(ct / CYCLE), c = ct - index * CYCLE;
        if (index !== cycleIndex) {
          cycleIndex = index;
          renewed = true;
        }
        if (c < FORM_END) form = c;
        else if (c < HOLD_END) holding = true;
        else if (c < DECON_END) decon = c - HOLD_END;
      }
    }
    for (let k = 0; k < held.length; k++) {
      orbA[k * 4] = OX[k]; orbA[k * 4 + 1] = OY[k]; orbA[k * 4 + 2] = OR[k]; orbA[k * 4 + 3] = OD[k];
      orbB[k * 4] = HOVER[k]; orbB[k * 4 + 1] = DOX[k]; orbB[k * 4 + 2] = DOY[k]; orbB[k * 4 + 3] = held[k] ? 1 : 0;
    }
    // An angle that grows with the time, kept within one turn for the card's numbers
    const angle = (rate: number) => (time * rate) % TAU;
    const theta = time * OMEGA;
    gl.useProgram(stepper);
    gl.uniform2f(us.uView, W, H);
    gl.uniform2f(us.uScale, scaleX, scaleY);
    scaleX = scaleY = 1;
    gl.uniform2f(us.uPar, parX, parY);
    gl.uniform1f(us.uDt, dt);
    gl.uniform1f(us.uTime, time);
    gl.uniform1f(us.uBefore, before);
    gl.uniform1f(us.uCt, time - FIRST);
    gl.uniform1f(us.uGlint, (time * 0.32) % 1.6);
    gl.uniform4f(us.uPhase, orbs ? 1 : 0, settle ? 1 : 0, reduced ? 1 : 0, renewed ? 1 : 0);
    gl.uniform3f(us.uCycle, form, decon, holding ? 1 : 0);
    gl.uniform3f(us.uBc, Math.cos(theta), Math.cos(theta + TAU / 3), Math.cos(theta + (2 * TAU) / 3));
    gl.uniform3f(us.uBs, Math.sin(theta), Math.sin(theta + TAU / 3), Math.sin(theta + (2 * TAU) / 3));
    gl.uniform2f(us.uSway, angle(0.11), angle(0.09));
    gl.uniform3f(us.uFlow, angle(0.07), angle(0.05), angle(0.031));
    gl.uniform2f(us.uHold, angle(1.3), angle(1.1));
    gl.uniform4f(us.uWave, angle(1.1), angle(0.19), angle(0.8), angle(0.55));
    gl.uniform4f(us.uOrbT, angle(1.6), angle(1.15), angle(0.7), angle(0.9));
    gl.uniform4fv(us.uOrbA, orbA);
    gl.uniform4fv(us.uOrbB, orbB);
    // The fluid stirred by the pointer, only while it moves
    gl.uniform3f(us.uFluid, fluidActive ? 1 : 0, gw, gh);
    gl.uniform1i(us.uField, 2);
    if (fluidActive) {
      for (let i = 0; i < fu.length; i++) {
        field[i * 2] = fu[i];
        field[i * 2 + 1] = fv[i];
      }
      gl.activeTexture(gl.TEXTURE2);
      gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, 0, gw, gh, gl.RG, gl.FLOAT, field);
    }
    // Every grain read in one buffer and written in the other; nothing is drawn here
    gl.bindVertexArray(stepArrays[current]);
    gl.bindTransformFeedback(gl.TRANSFORM_FEEDBACK, feedback);
    gl.bindBufferBase(gl.TRANSFORM_FEEDBACK_BUFFER, 0, kept[1 - current]);
    gl.enable(gl.RASTERIZER_DISCARD);
    gl.beginTransformFeedback(gl.POINTS);
    gl.drawArrays(gl.POINTS, 0, N);
    gl.endTransformFeedback();
    gl.disable(gl.RASTERIZER_DISCARD);
    gl.bindBufferBase(gl.TRANSFORM_FEEDBACK_BUFFER, 0, null);
    gl.bindTransformFeedback(gl.TRANSFORM_FEEDBACK, null);
    gl.bindVertexArray(null);
    current = 1 - current;
  };

  /* ------------------------------------------------------------------- drawing */
  const empty = gl.createVertexArray();

  const draw = () => {
    const p = colours;
    // The gas, at half resolution, at every image: drawn more seldom, it moved by jerks next to the grains
    gl.bindFramebuffer(gl.FRAMEBUFFER, frame);
    gl.viewport(0, 0, bw, bh);
    gl.useProgram(gas);
    gl.bindVertexArray(empty);
    gl.uniform1i(ug.grid, 1);
    gl.uniform2f(ug.r, bw, bh);
    gl.uniform1f(ug.t, time + 14);
    gl.uniform1f(ug.k, p.k);
    gl.uniform1f(ug.o, openness);
    gl.uniform1f(ug.flash, flash);
    gl.uniform1f(ug.base, p.base);
    gl.uniform1f(ug.dark, p.dark);
    gl.uniform1f(ug.zs, 1);
    gl.uniform2f(ug.pan, (-parX * 0.25) / H, (parY * 0.25) / H);
    gl.uniform3fv(ug.bg, p.bg);
    gl.uniform3fv(ug.c1, p.c1);
    gl.uniform3fv(ug.c2, p.c2);
    gl.uniform3fv(ug.c3, p.c3);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.useProgram(blit);
    gl.bindVertexArray(empty);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, target);
    gl.uniform1i(ub.tex, 0);
    gl.uniform2f(ub.r, canvas.width, canvas.height);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    // The grains, where their last step left them
    gl.useProgram(points);
    gl.bindVertexArray(drawArrays[current]);
    gl.uniform2f(up.view, W, H);
    gl.uniform1f(up.dpr, dpr);
    gl.uniform3fv(up.p0, p.p[0]);
    gl.uniform3fv(up.p1, p.p[1]);
    gl.uniform3fv(up.p2, p.p[2]);
    gl.uniform3fv(up.p3, p.p[3]);
    gl.uniform1f(up.add, p.add);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    gl.drawArrays(gl.POINTS, 0, N);
    gl.disable(gl.BLEND);
    gl.bindVertexArray(null);
    if (!drawn) {
      drawn = true;
      canvas.style.visibility = "";
    }
  };

  let sized = false;
  const resize = () => {
    const box = canvas.getBoundingClientRect();
    const w = Math.max(2, Math.round(box.width)), h = Math.max(2, Math.round(box.height));
    dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    if (w === W && h === H && canvas.width === Math.round(w * dpr)) return false;
    // The grains follow the page at their next step
    if (sized) {
      scaleX *= w / W;
      scaleY *= h / H;
    }
    sized = true;
    W = w;
    H = h;
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    bw = Math.max(2, Math.round(W * 0.5));
    bh = Math.max(2, Math.round(H * 0.5));
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, target);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, bw, bh, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
    gl.bindFramebuffer(gl.FRAMEBUFFER, frame);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, target, 0);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    fluidResize();
    readRect();
    return true;
  };

  /* ------------------------------------------------------------------- loop */
  const frameListeners = new Set<() => void>(), resizeListeners = new Set<() => void>();
  let raf = 0, last = 0, visible = true, disposed = false;
  // The screen's own period (measured on its frames) and the frames counted, for a steady pace
  let seen = 0, period = 1000 / 60, count = 0;
  const emitFrame = () => frameListeners.forEach((listener) => listener());
  const tick = (now: number) => {
    const dt = Math.min(0.05, Math.max(0.001, (now - last) / 1000));
    const before = time;
    last = now;
    time += dt;
    if (now / 1000 - rectAt > 0.4) {
      rectAt = now / 1000;
      readRect();
    }
    stepSpin(dt);
    // The pointer's stroke since the last image, as a wake
    if (pointer.moved) {
      if (pointer.known && !dragging) {
        const dx = pointer.x - pointer.lx, dy = pointer.y - pointer.ly, d = Math.hypot(dx, dy);
        if (d > 0.5 && d < 400) {
          const vx = clamp(dx / dt, -3000, 3000), vy = clamp(dy / dt, -3000, 3000);
          const steps = Math.max(1, Math.ceil(d / 14));
          for (let k = 1; k <= steps; k++) inject(pointer.lx + (dx * k) / steps, pointer.ly + (dy * k) / steps, vx / steps, vy / steps, 76);
        }
      }
      pointer.lx = pointer.x;
      pointer.ly = pointer.y;
      pointer.known = true;
      pointer.moved = false;
    }
    fluidStep(dt);
    flash *= Math.exp(-3 * dt);
    openness += ((mode === "orbs" ? 1 : 0) - openness) * (1 - Math.exp(-2.5 * dt));
    step(dt, false, before);
    draw();
    emitFrame();
  };
  const loop = (now: number) => {
    raf = requestAnimationFrame(loop);
    if (!ready()) {
      last = seen = now;
      return;
    }
    // One image at every frame of the screen up to 90 Hz, at one frame in two or more above, always
    // the same count (a time threshold took one frame or the next by turns: the motion stumbled)
    const gap = now - seen;
    seen = now;
    if (gap > 3 && gap < 40) period += (gap - period) * 0.05;
    const every = Math.max(1, Math.round(1000 / period / 62));
    if (++count % every) return;
    tick(now);
  };
  const start = () => {
    if (raf || disposed || reduced || !visible) return;
    last = seen = performance.now();
    raf = requestAnimationFrame(loop);
  };
  const stop = () => {
    cancelAnimationFrame(raf);
    raf = 0;
  };
  // Reduced animations: one still picture after each change
  let pending = 0;
  const paintStill = () => {
    pending = 0;
    if (!ready()) {
      if (!refused && !disposed) pending = requestAnimationFrame(paintStill);
      return;
    }
    openness = mode === "orbs" ? 1 : 0;
    step(0, true, time);
    draw();
    emitFrame();
  };
  const still = () => {
    if (!reduced || pending) return;
    pending = requestAnimationFrame(paintStill);
  };

  resize();
  const sizeWatch = new ResizeObserver(() => {
    if (!resize()) return;
    resizeListeners.forEach((listener) => listener());
    // A canvas that changes size is emptied: drawn again before the page is shown, at its new
    // size, so that nothing is seen of the change
    if (raf) {
      if (ready()) tick(performance.now());
    } else if (reduced) {
      cancelAnimationFrame(pending);
      paintStill();
    }
  });
  sizeWatch.observe(canvas);
  const themeWatch = new MutationObserver(() => {
    colours = palette();
    still();
  });
  themeWatch.observe(document.documentElement, { attributes: true, attributeFilter: ["data-mantine-color-scheme"] });
  const stopVisible = watchVisible(canvas, (shown) => {
    visible = shown;
    if (visible) start();
    else stop();
  });
  const onLost = (event: Event) => {
    event.preventDefault();
    stop();
    disposed = true;
  };
  canvas.addEventListener("webglcontextlost", onLost);
  start();
  still();

  return {
    setMode(next) {
      if (next === mode) return;
      mode = next;
      if (mode === "orbs") formOrbs();
      else clearOrbs();
      still();
    },
    burst(clientX, clientY) {
      rect = canvas.getBoundingClientRect();
      const x = clientX - rect.left, y = clientY - rect.top;
      burstAt = { x, y, time: performance.now() / 1000 };
      flash = 1;
      if (!reduced) radial(x, y, Math.max(W, H) * 0.42, 950);
    },
    setOrbs(next) {
      const same = next.length === held.length;
      held = next.slice(0, 64);
      if (!same) {
        // Evenly over the sphere
        const n = held.length;
        dirX = new Float32Array(n);
        dirY = new Float32Array(n);
        dirZ = new Float32Array(n);
        for (let k = 0; k < n; k++) {
          const y = n === 1 ? 0 : 1 - (2 * (k + 0.5)) / n, r = Math.sqrt(Math.max(0, 1 - y * y)), a = k * 2.399963;
          dirX[k] = Math.cos(a) * r;
          dirY[k] = y;
          dirZ[k] = Math.sin(a) * r;
        }
        if (mode === "orbs") formOrbs();
      }
      still();
    },
    orbs: () => Array.from({ length: held.length }, (_, k) => ({ x: OX[k], y: OY[k], r: OR[k], depth: OD[k] })),
    setHover(index) {
      hover = index ?? -1;
      still();
    },
    turn(dx, dy) {
      const { radius } = sphere();
      yaw += dx / radius;
      pitch = clamp(pitch + dy / radius, -1.1, 1.1);
      parX += dx * 0.35;
      parY += dy * 0.35;
      still();
    },
    fling(vx, vy) {
      if (reduced) return;
      const { radius } = sphere();
      yawSpeed = clamp(vx / radius, -4, 4);
      pitchSpeed = clamp(vy / radius, -3, 3);
    },
    setDragging(on) {
      dragging = on;
      if (on) yawSpeed = pitchSpeed = 0;
    },
    size: () => ({ width: W, height: H }),
    onFrame(listener) {
      frameListeners.add(listener);
      return () => frameListeners.delete(listener);
    },
    onResize(listener) {
      resizeListeners.add(listener);
      return () => resizeListeners.delete(listener);
    },
    dispose() {
      disposed = true;
      stop();
      cancelAnimationFrame(pending);
      sizeWatch.disconnect();
      themeWatch.disconnect();
      stopVisible();
      window.removeEventListener("pointermove", onPointer);
      canvas.removeEventListener("webglcontextlost", onLost);
      gl.getExtension("WEBGL_lose_context")?.loseContext();
    },
  };
}
