
/* Account-owned browser data. Bare legacy keys are claimed only by the current
   anonymous browser identity and are never uploaded into an account. */
const OWNED_STORAGE_KEYS=Object.freeze(['apexProfile','apexHistory','apexWorkoutLog','apexCoachMemory']);
const ACTIVE_OWNER_KEY='apexActiveDataOwnerV1',ANON_OWNER_KEY='apexAnonymousOwnerV1';
const newOwnerId=()=>{try{return crypto.randomUUID();}catch(e){return Date.now().toString(36)+Math.random().toString(36).slice(2);}};
function anonymousOwnerId(rotate=false){
  let id=rotate?'':localStorage.getItem(ANON_OWNER_KEY);
  if(!id){id=newOwnerId();localStorage.setItem(ANON_OWNER_KEY,id);}
  return id;
}
let DATA_OWNER={kind:'anonymous',id:anonymousOwnerId()};
function dataOwnerToken(owner=DATA_OWNER){return owner.kind+':'+owner.id;}
function ownedStorageKey(key,owner=DATA_OWNER){
  if(!OWNED_STORAGE_KEYS.includes(key))throw new Error('unowned_storage_key');
  return 'apexOwnedV1:'+dataOwnerToken(owner)+':'+key;
}
function ownedStorageGet(key,owner=DATA_OWNER){return localStorage.getItem(ownedStorageKey(key,owner));}
function ownedStorageSet(key,value,owner=DATA_OWNER){localStorage.setItem(ownedStorageKey(key,owner),value);}
function ownedStorageRemove(key){localStorage.removeItem(ownedStorageKey(key));}
function activateDataOwner(kind,id){
  DATA_OWNER={kind,id:String(id)};
  localStorage.setItem(ACTIVE_OWNER_KEY,dataOwnerToken());
}
function rotateAnonymousOwner(){
  const id=anonymousOwnerId(true);activateDataOwner('anonymous',id);return id;
}
function claimLegacyDataAsAnonymous(){
  const anonymous={kind:'anonymous',id:DATA_OWNER.id};
  OWNED_STORAGE_KEYS.forEach(key=>{
    const legacy=localStorage.getItem(key);
    if(legacy!==null&&ownedStorageGet(key,anonymous)===null)ownedStorageSet(key,legacy,anonymous);
    localStorage.removeItem(key);
  });
}
claimLegacyDataAsAnonymous();
window.addEventListener('storage',event=>{
  if(event.key===ACTIVE_OWNER_KEY&&event.newValue&&event.newValue!==dataOwnerToken())location.reload();
});
/* ═══════════════════════════════════════════════════════════════════
   LIVING ENERGY ORGANISM — volumetric plasma / nebula
   Smooth, soft, breathing. No particles. No flicker. No visible loop.
   Half-resolution accumulation buffer with smoke trails → Interstellar feel.
   ═══════════════════════════════════════════════════════════════════ */
const Noise=(()=>{const p=new Uint8Array(512),perm=[...Array(256).keys()];let s=1337;
  const rnd=()=>(s=(s*16807)%2147483647)/2147483647;
  for(let i=255;i>0;i--){const j=(rnd()*(i+1))|0;[perm[i],perm[j]]=[perm[j],perm[i]];}
  for(let i=0;i<512;i++)p[i]=perm[i&255];
  const fade=t=>t*t*t*(t*(t*6-15)+10),lerp=(a,b,t)=>a+(b-a)*t,grad=(h,x,y)=>{const u=h&1?x:-x,v=h&2?y:-y;return u+v;};
  return(x,y)=>{const X=Math.floor(x)&255,Y=Math.floor(y)&255;x-=Math.floor(x);y-=Math.floor(y);
    const u=fade(x),v=fade(y),A=p[X]+Y,B=p[X+1]+Y;
    return lerp(lerp(grad(p[A],x,y),grad(p[B],x-1,y),u),lerp(grad(p[A+1],x,y-1),grad(p[B+1],x-1,y-1),u),v);};})();
function fbm(x,y,t){let v=0,a=.5,f=1;for(let i=0;i<3;i++){v+=a*Noise(x*f+t*.4,y*f-t*.3);f*=2;a*=.5;}return v;}

/* ═══════════════════════════════════════════════════════════════════
   PRESENCE ENGINE — the organism's nervous system.
   Implements the frozen Behavioral Language: 12 behaviors, 6 dimensions,
   8 laws. Architecture:
     BreathEngine    — the one constant; ALL state transitions ride it
                       (a state may only begin on an exhale).
     AttentionEngine — orientation is a CONTINUOUS dimension, so the lean
                       responds within a frame while states wait for breath.
     PresenceEngine  — FSM (bases) + transient gestures + parameter physics.
   The canvas only renders; every behavioral decision lives here.
   ═══════════════════════════════════════════════════════════════════ */

class BreathEngine{
  // Asymmetric respiration: inhale 42% of the cycle, exhale 58%.
  // Base period 10.4s at rate=1 — matches the approved organism exactly.
  constructor(){
    this.phase=Math.random()*0.4;      // start mid-inhale, never at a boundary
    this.rate=1; this._rateT=1;
    this.depth=1; this._depthT=1;
    this.value=0.5; this.raw=0.5;
    this._impulse=0;                    // cadence micro-breaths (Answering)
    this._exhaleCbs=[];
    this.IN=0.42;                       // inhale→exhale boundary
  }
  onExhale(cb){this._exhaleCbs.push(cb);}
  target(rate,depth){this._rateT=rate;this._depthT=depth;}
  impulse(a){this._impulse=Math.min(this._impulse+a,0.06);}
  update(dt){
    // Law 2/3: rate & depth ease — the breath itself is never interrupted.
    const k=Math.min(dt*0.8,1);
    this.rate+=(this._rateT-this.rate)*k;
    this.depth+=(this._depthT-this.depth)*k;
    const period=10.4/Math.max(this.rate,0.05);
    const prev=this.phase;
    this.phase=(this.phase+dt/period)%1;
    // exhale begins at IN — the only moment a state change may execute.
    // Per-frame increments are tiny, so a simple crossing test is exact.
    if(prev<this.IN&&this.phase>=this.IN){for(const cb of this._exhaleCbs)cb();}
    const ss=t=>t*t*(3-2*t);
    this.raw=this.phase<this.IN?ss(this.phase/this.IN):1-ss((this.phase-this.IN)/(1-this.IN));
    this._impulse*=Math.max(0,1-dt*3.5);
    this.value=0.5+(this.raw-0.5)*this.depth+this._impulse;
  }
}

class AttentionEngine{
  // Where the organism's center drifts. Continuous — never gated on breath —
  // which is how the lean can answer a touch in one frame without breaking
  // the exhale rule (orientation is a dimension, not a state).
  constructor(){
    this.x=0;this.y=0;this.strength=0.25;
    this._tx=0;this._ty=0;this._sT=0;
    this._wander=Math.random()*100;this._idleAmplitude=1;
  }
  point(nx,ny,strength){this._tx=Math.max(-1,Math.min(1,nx));this._ty=Math.max(-1,Math.min(1,ny));this._sT=strength;}
  release(){this._sT=0;}
  setIdleAmplitude(value){this._idleAmplitude=Math.max(.7,Math.min(1,value));}
  update(dt){
    // idle wander: where the gaze rests when nothing calls it (Waiting)
    this._wander+=dt*0.045;
    const gx=this._sT>0.01?this._tx:fbm(this._wander,0.7,0)*0.5*this._idleAmplitude;
    const gy=this._sT>0.01?this._ty:fbm(0.3,this._wander,0)*0.35*this._idleAmplitude;
    const k=Math.min(dt*1.4,1);
    this.x+=(gx-this.x)*k; this.y+=(gy-this.y)*k;
    this.strength+=((this._sT>0.01?this._sT:0.25)-this.strength)*k;
    this._sT*=Math.max(0,1-dt*0.35);   // pointed attention relaxes on its own
  }
}

class AthleteModel{
  // ── THE NERVOUS SYSTEM ──────────────────────────────────────────────
  // Continuous internal state about the athlete and the dyad, derived from
  // witnessed FACTS. The interface reports what happened; the model decides
  // what it means; the body (PresenceEngine) reads state and nothing else.
  // Typing is not a cause — attention is. A finished workout is not a cause —
  // accomplishment is. Mouse movement is not a cause — curiosity is.
  constructor(){
    // somatic picture (from the profile — drives the palette)
    this.physiology={recovery:.6,fatigue:.35,stress:.3};
    // dyad state — real variables with real dynamics, not event flags
    this.presence=0.6;     // the human is here          (fades over ~100s of stillness)
    this.attention=0;      // the human is addressing us (fades over ~4s)
    this.curiosity=0;      // exploratory interest — the hand near the body (~6s)
    this.exchange='none';  // the coach's own mind: none | composing | speaking
    this.speechPulse=0;    // speech energy while answering (breath consumes it)
    this.away=false;       // the human left the room
    // physiological session state
    this.sessionLoad=0;    // accumulated effort, lingers (~10min half-life)
    this.restActive=false; this.recoveryFill=0;   // monotonic within an interval
    // internal shifts worth a gesture — monotonic counters the body consumes
    this.counters={salience:0,accomplishment:0,novelty:0,retrieval:0,reunion:0};
    this.reunionScale=0;
    // physical world state
    this.contacts=[];      // real touches on the body
    this.pointer=null;     // where the human's hand is (normalized)
    this._pointerAt=0;
  }
  setPhysiology(p){this.physiology={...this.physiology,...p};}
  // ── Facts in. Vocabulary is the world's, never the organism's.
  observe(fact,pl){
    const now=performance.now(); pl=pl||{};
    switch(fact){
      case 'pointer':      this.pointer={x:pl.x,y:pl.y}; this._pointerAt=now; this.presence=1;
                           this.curiosity=Math.min(1,this.curiosity+0.08); break;
      case 'contact':      this.contacts.push({x:pl.x,y:pl.y,t0:now});
                           if(this.contacts.length>4)this.contacts.shift();
                           this._pointerAt=now; this.curiosity=1; this.presence=1; break;
      case 'keystroke':    this.attention=1; this.presence=1; break;
      case 'exchangeOpened': this.exchange='composing'; this.presence=1; break;
      case 'replyToken':   this.exchange='speaking'; this.speechPulse=Math.min(this.speechPulse+0.25,1); break;
      case 'exchangeClosed': this.exchange='none'; this.speechPulse=0; break;
      case 'sessionBegan': this.counters.salience++; this.presence=1; break;
      case 'setCompleted': this.sessionLoad=Math.min(1,this.sessionLoad+0.15); this.counters.salience++; break;
      case 'restBegan':    this.restActive=true; this.recoveryFill=0; break;
      case 'restProgress': if(this.restActive)this.recoveryFill=Math.max(this.recoveryFill,Math.min(1,pl.p||0)); break;
      case 'restEnded':    this.restActive=false; break;
      case 'sessionCompleted': this.restActive=false; this.counters.accomplishment++; this.sessionLoad*=0.5; break;
      case 'modelChanged': this.counters.novelty++; break;      // the coach was changed by you
      case 'historyOpened':this.counters.retrieval++; break;    // shared past is being touched
      case 'consultOpened':this.counters.salience++; this.presence=1; break;
      case 'visibility':   this.away=!!pl.hidden; if(!pl.hidden)this.presence=1; break;
      case 'returned':     this.counters.reunion++; this.reunionScale=Math.min(1,(pl.days||0)/30); this.presence=1; break;
    }
  }
  update(dt,now){
    now=now||performance.now();
    // State persists and fades like state — never like an event. Attention
    // memory (~8s) deliberately outlasts a thinking-pause while composing, and
    // spans the breath gate — a single stray keystroke still under-reacts.
    this.attention*=Math.max(0,1-dt/8);
    this.curiosity*=Math.max(0,1-dt/6);
    this.speechPulse*=Math.max(0,1-dt*2.2);
    this.sessionLoad*=Math.max(0,1-dt/600);
    if(!this.away)this.presence*=Math.max(0,1-dt/35);   // ~100s of stillness → resting
    this.contacts=this.contacts.filter(c=>now-c.t0<1900);
  }
}

class PresenceEngine{
  constructor(athlete){
    this.athlete=athlete;   // the body reads the nervous system — nothing else
    this.breath=new BreathEngine();
    this.attention=new AttentionEngine();
    this.serverProjection=null;
    this.reduced=(typeof matchMedia!=='undefined')&&matchMedia('(prefers-reduced-motion: reduce)').matches;
    // ── Base states: the 6-dimension configurations (Behavioral Language §III).
    // waiting is calibrated to reproduce the approved organism exactly.
    this.S={
      waiting:   {rate:1.00,depth:1.00,density:0.45,tempo:1.00,coherence:0.00,warmth:0.55},
      listening: {rate:0.90,depth:0.55,density:0.55,tempo:0.40,coherence:0.55,warmth:0.55},
      thinking:  {rate:0.80,depth:0.85,density:0.78,tempo:0.55,coherence:0.80,warmth:0.50},
      answering: {rate:0.95,depth:0.75,density:0.52,tempo:0.75,coherence:0.45,warmth:0.48},
      resting:   {rate:0.70,depth:0.80,density:0.32,tempo:0.25,coherence:0.20,warmth:0.44},
      recovering:{rate:1.50,depth:0.45,density:0.85,tempo:0.45,coherence:0.60,warmth:0.38},
      goodbye:   {rate:0.75,depth:0.95,density:0.40,tempo:0.30,coherence:0.40,warmth:0.44},
    };
    // No precedence table: the canon's precedence IS the derivation order in
    // _derive() — a single if/else chain over real internal state.
    // ── Transient gestures: envelopes blended over the base, exhale-gated,
    // with expiry (a stale notice is no notice) and cooldowns (never twice).
    this.T={
      noticing:   {dur:1.8,expiry:6, cooldown:2.5,mods:{depth:0.35,density:0.10}},
      celebrating:{dur:3.4,expiry:99,cooldown:8,  mods:{depth:0.45,warmth:0.18,tempo:-0.25}},
      learning:   {dur:2.6,expiry:10,cooldown:5,  mods:{density:0.22,coherence:0.30},rearrange:true},
      remembering:{dur:4.0,expiry:10,cooldown:6,  mods:{tempo:-0.35,warmth:0.08,coherence:0.20},gaze:'off'},
      welcome:    {dur:3.2,expiry:20,cooldown:30, mods:{depth:0.35,warmth:0.15},gaze:'user'},
    };
    this.base='waiting'; this.pending=null;
    this.transient=null; this.pendingTransient=null;
    this._cool={};                       // per-gesture cooldown clocks
    // gesture consumption ledger — the body notices each internal shift once
    this._consumed={salience:0,accomplishment:0,novelty:0,retrieval:0,reunion:0};
    this._now=performance.now();
    // 6D eased parameters (breath rate/depth live in BreathEngine)
    this.p={density:0.45,tempo:1.0,coherence:0.0,warmth:0.55,attX:0,attY:0,attStrength:0.25};
    // All transitions ride the breath (Behavioral Language §IV)
    this.breath.onExhale(()=>this._onExhale());
    this._rearrangeCb=null;
  }
  onRearrange(cb){this._rearrangeCb=cb;}     // Learning's permanent imprint
  setServerProjection(projection){
    if(!projection||typeof projection!=='object')return false;
    const next={};
    if(projection.recovery_bias==='protective')next.recovery_bias='protective';
    if(projection.attention_bias==='focused')next.attention_bias='focused';
    if(!Object.keys(next).length)return false;
    const current=this.serverProjection||{};
    if(current.recovery_bias===next.recovery_bias&&current.attention_bias===next.attention_bias&&
      Object.keys(current).length===Object.keys(next).length)return false;
    this.serverProjection=next;
    return true;
  }

  // ── DERIVATION — the body perceives the nervous system. No events arrive
  // here, ever: every behavior below is a reading of real internal state.
  // The canon's precedence is not a table; it is the order of this chain.
  _derive(){
    const A=this.athlete;
    // Base state: a pure function of the dyad's condition.
    let want;
    if(A.away)                          want='goodbye';    // the human left the room
    else if(A.attention>0.5)            want='listening';  // we are being addressed
    else if(A.exchange==='composing')   want='thinking';   // our own mind is working
    else if(A.exchange==='speaking')    want='answering';  // our own voice is out
    else if(A.restActive)               want='recovering'; // the body is refilling
    else if(A.presence<0.05)            want='resting';    // long stillness — no one here
    else                                want='waiting';
    // Because this is re-derived every frame from truth, stale pendings are
    // impossible by construction: a cancelled departure simply stops deriving.
    this.pending = want===this.base ? null : want;
    // Gestures: internal SHIFTS in the model, each consumed exactly once.
    const C=A.counters, seen=this._consumed;
    if(C.accomplishment>seen.accomplishment){seen.accomplishment=C.accomplishment;this._gesture('celebrating');}
    if(C.novelty>seen.novelty)          {seen.novelty=C.novelty;          this._gesture('learning');}
    if(C.retrieval>seen.retrieval)      {seen.retrieval=C.retrieval;      this._gesture('remembering');}
    if(C.reunion>seen.reunion)          {seen.reunion=C.reunion; this._welcomeScale=A.reunionScale; this._gesture('welcome');}
    if(C.salience>seen.salience)        {seen.salience=C.salience;        this._gesture('noticing');}
    // Orientation: derived from what the dyad is doing, not from any event.
    if(A.attention>0.4)                 this.attention.point(0,0.8,0.4+A.attention*0.2);   // toward the human's words
    else if(A.exchange==='composing')   this.attention.point(0,0.05,0.5);                  // inward — thought is private
    else if(A.curiosity>0.25&&A.pointer)this.attention.point(A.pointer.x,A.pointer.y,0.3+A.curiosity*0.35); // curiosity follows the hand
    // else: the idle wander — where the gaze rests when nothing calls it
    // Speech: the chest movement of answering derives from speech energy.
    if(A.speechPulse>0.05)this.breath.impulse(A.speechPulse*0.012);
  }
  _gesture(name){
    const now=performance.now(), def=this.T[name];
    if(!def)return;
    if(this._cool[name]&&now-this._cool[name]<def.cooldown*1000)return;   // never twice
    if(this.transient&&this.transient.name===name)return;
    this.pendingTransient={name,queuedAt:now};
    // the fractional turn may happen now — orientation is continuous
    if(def.gaze==='off')this.attention.point(-0.45,-0.2,0.4);
    if(def.gaze==='user')this.attention.point(0,0.25,0.5);
  }
  _onExhale(){
    // The only moment state may change (Behavioral Language: the Breath Rule).
    if(this.pending){this.base=this.pending;this.pending=null;}
    if(this.pendingTransient){
      const q=this.pendingTransient, def=this.T[q.name];
      this.pendingTransient=null;
      if(performance.now()-q.queuedAt<=def.expiry*1000){
        this.transient={name:q.name,t0:performance.now(),def};
        this._cool[q.name]=performance.now();
        if(def.rearrange&&this._rearrangeCb)this._rearrangeCb();
      }
    }
  }
  update(dt){
    const now=performance.now(); this._now=now;
    // The body perceives the nervous system, continuously. Listening ends when
    // attention fades; resting begins when presence fades; answering resumes
    // after an interruption — all for free, because state is re-derived from
    // truth every frame instead of being commanded by events.
    this._derive();
    this.breath.update(dt);
    this.attention.update(dt);
    // ── compose targets: base pose, recovery interpolation, transient blend
    let s=this.S[this.base];
    let tgt={rate:s.rate,depth:s.depth,density:s.density,tempo:s.tempo,coherence:s.coherence,warmth:s.warmth};
    if(this.base==='recovering'){
      // the only state with a direction: compressed+dim → refilled — driven by
      // the model's recovery fill (monotonic in the nervous system, by law)
      const rec=this.athlete.recoveryFill;
      const q=rec*rec*(3-2*rec);
      tgt.rate=1.5-q*0.5; tgt.depth=0.45+q*0.45; tgt.density=0.85-q*0.35; tgt.warmth=0.38+q*0.24;
    }
    if(this.base==='thinking'&&this._thinkT0){
      // long thoughts deepen rather than loop (honest "hard question")
      tgt.density=Math.min(0.86,tgt.density+Math.min((now-this._thinkT0)/10000,1)*0.08);
    }
    this._thinkT0=this.base==='thinking'?(this._thinkT0||now):null;
    if(this.transient){
      const tr=this.transient, age=(now-tr.t0)/1000, u=age/tr.def.dur;
      if(u>=1){this.transient=null;}
      else{
        const env=Math.sin(Math.min(u,1)*Math.PI);            // smooth in-out
        const m=tr.def.mods, scale=this.transient.name==='welcome'?(0.8+(this._welcomeScale||0)*0.4):1;
        if(m.depth)tgt.depth+=m.depth*env*scale;
        if(m.density)tgt.density+=m.density*env;
        if(m.warmth)tgt.warmth+=m.warmth*env*scale;
        if(m.tempo)tgt.tempo=Math.max(0.1,tgt.tempo+m.tempo*env);
        if(m.coherence)tgt.coherence=Math.min(1,tgt.coherence+m.coherence*env);
      }
    }
    // The server may only bias continuous expression. It cannot select a base
    // state, bypass the exhale gate, or create a gesture.
    if(!this.reduced&&this.serverProjection){
      if(this.serverProjection.recovery_bias==='protective'){
        tgt.rate*=.94;tgt.depth*=.92;tgt.tempo*=.90;
      }
      this.attention.setIdleAmplitude(this.serverProjection.attention_bias==='focused'?.82:1);
    }else this.attention.setIdleAmplitude(1);
    if(this.reduced){tgt.tempo*=0.5;}
    // warmth floor — it never goes dark (Law 5 / §V)
    tgt.warmth=Math.max(0.34,tgt.warmth);
    this.breath.target(tgt.rate,tgt.depth);
    const k=Math.min(dt*0.9,1);
    this.p.density+=(tgt.density-this.p.density)*k;
    this.p.tempo+=(tgt.tempo-this.p.tempo)*k;
    this.p.coherence+=(tgt.coherence-this.p.coherence)*k;
    this.p.warmth+=(tgt.warmth-this.p.warmth)*k;
    this.p.attX=this.attention.x; this.p.attY=this.attention.y; this.p.attStrength=this.attention.strength;
  }
  get touches(){return this.athlete.contacts;}   // physical facts live in the model
  pointerFresh(now){return this.athlete._pointerAt&&now-this.athlete._pointerAt<1200;}
  // Touch physics: yield first (the field parts), then the lean-in (it gathers
  // toward the finger). Signed magnitude: negative = away, positive = toward.
  touchInfluence(age){
    if(this.reduced)return 0;
    const a=age/1000;
    if(a<0.10)return -(a/0.10)*1.0;             // ramp into the yield — no snap
    if(a<0.38)return -1.0;                       // parted
    if(a<0.62)return -1.0+((a-0.38)/0.24)*1.9;   // crossfade: yield → approach
    if(a<1.15)return 0.9;                        // gathered toward the finger
    return Math.max(0,0.9*(1-(a-1.15)/0.75));    // release, fade to stillness
  }
}

class LivingCore{
  constructor(canvas){
    this.cv=canvas; this.ctx=canvas.getContext('2d');
    this.dpr=Math.min(window.devicePixelRatio||1,2);
    this.off=document.createElement('canvas'); this.octx=this.off.getContext('2d');
    this.t=0; this.last=performance.now();
    this.cur={recovery:.6,fatigue:.35,stress:.3};
    // Nervous system first; the body is built around it and only reads it.
    this.athlete=new AthleteModel();
    this.presence=new PresenceEngine(this.athlete);
    this.presence.onRearrange(()=>this.rearrange());
    // flow lobes — the organism's drifting body (no discrete particles).
    // Angle & noise-time are ACCUMULATED per lobe so speed changes (tempo,
    // coherence) are continuous — the body can never teleport (Law 1).
    this.lobes=[]; const N=9;
    for(let i=0;i<N;i++){
      const seed=i*7.3+Math.random()*3;
      this.lobes.push({seed, seedT:seed, phase:seed, nt:seed, rad:.30+Math.random()*.20, sz:.7+Math.random()*.5, sp:.18+Math.random()*.22});
    }
    // Learning's permanent imprint persists across sessions (deterministic drift)
    this.drift=0;
    try{this.drift=parseInt(localStorage.getItem('apexOrganismDrift')||'0',10)||0;}catch(e){}
    for(let d=1;d<=Math.min(this.drift,200);d++)
      for(let i=0;i<this.lobes.length;i++){
        this.lobes[i].seed+=Math.sin(i*7.31+d*13.7)*0.35;
        this.lobes[i].seedT=this.lobes[i].seed;
      }
    this.resize(); window.addEventListener('resize',()=>this.resize());
  }
  // Learning: a subtle, PERMANENT rearrangement of the internal flow —
  // eased in over seconds (continuous), persisted across sessions.
  rearrange(){
    this.drift=Math.min(this.drift+1,200);
    try{localStorage.setItem('apexOrganismDrift',String(this.drift));}catch(e){}
    for(let i=0;i<this.lobes.length;i++)
      this.lobes[i].seedT=this.lobes[i].seed+Math.sin(i*7.31+this.drift*13.7)*0.35;
  }
  resize(){
    this.w=this.cv.clientWidth; this.h=this.cv.clientHeight;
    this.cv.width=this.w*this.dpr; this.cv.height=this.h*this.dpr;
    this.ctx.setTransform(this.dpr,0,0,this.dpr,0,0);
    // accumulation buffer at half-res → natural softness + performance
    this.ow=Math.max(2,Math.round(this.w*.5)); this.oh=Math.max(2,Math.round(this.h*.5));
    this.off.width=this.ow; this.off.height=this.oh;
    this.octx.fillStyle='#070910'; this.octx.fillRect(0,0,this.ow,this.oh);
    this.cx=this.ow/2; this.cy=this.oh*.46; this.R=Math.min(this.ow,this.oh)*.34;
  }
  setPhysiology(p){this.athlete.setPhysiology(p);}   // somatic state lives in the model
  setServerProjection(p){return this.presence.setServerProjection(p);}
  palette(){
    const{recovery:r,fatigue:f,stress:st}=this.cur;
    const mix=(a,b,t)=>a.map((v,i)=>v+(b[i]-v)*t);
    const cool=[[56,224,255],[140,235,120]], mid=[[255,177,60],[255,106,60]], warm=[[245,33,45],[255,90,50]];
    let c1,c2;
    if(r>.55){c1=mix(cool[0],mid[0],(1-r)*1.1);c2=mix(cool[1],mid[1],(1-r)*1.1);}
    else if(f>.55){c1=mix(warm[0],mid[0],(1-f));c2=mix(warm[1],mid[1],(1-f));}
    else{c1=mid[0].slice();c2=mid[1].slice();}
    if(st>.4)c1=mix(c1,warm[0],(st-.4)*.7);
    return{c1,c2};
  }
  step(now){
    const dt=Math.min(Math.max((now-this.last)/1000,0),.05); this.last=now;
    // nervous system advances first; the body then perceives and expresses it
    this.athlete.update(dt,now);
    for(const k in this.cur)this.cur[k]+=(this.athlete.physiology[k]-this.cur[k])*Math.min(dt*.7,1);
    this.presence.update(dt);
    const{recovery:r,fatigue:f}=this.cur, ps=this.presence.p;
    // 5× time-scale = the approved "visibly alive" pace; presence tempo scales it
    // per state (waiting tempo = 1.0 reproduces the approved organism exactly).
    const dtT=dt*(.10+r*.10-f*.05)*5.0*ps.tempo;
    this.t+=dtT;
    // Per-lobe accumulation: coherence blends individual speeds toward the mean
    // WITHOUT ever moving a lobe discontinuously — speed changes, position flows.
    const mean=0.29; // midpoint of the lobe speed range
    for(const L of this.lobes){
      const eff=L.sp+(mean-L.sp)*ps.coherence;
      L.nt+=dtT*eff; L.phase+=dtT*eff*0.45;
      // Learning's rearrangement eases in — a slow, permanent change of flow
      L.seed+=(L.seedT-L.seed)*Math.min(dt*0.3,1);
    }
  }
  render(){
    const g=this.octx,{recovery:r,fatigue:f,stress:st}=this.cur,{c1,c2}=this.palette();
    const ps=this.presence.p, now=this.presence._now;
    // smoke persistence — fade previous frame instead of clearing → volumetric trails
    g.globalCompositeOperation='source-over';
    g.fillStyle='rgba(7,9,16,'+(0.10+st*0.04)+')'; g.fillRect(0,0,this.ow,this.oh);
    const breath=this.presence.breath.value;                 // the one constant
    const compress=1-f*.26, expand=1+r*.14;
    // density: gathered ↔ diffuse (waiting 0.45 = scale 1.0, the approved look)
    const gather=1-(ps.density-0.45)*0.55;
    // warmth: luminance envelope; floored upstream — the organism never goes dark
    const lum=0.55+ps.warmth*0.82;
    // orientation: the lean — attention offsets the body's center, smoothly
    const acx=this.cx+ps.attX*this.R*0.14*ps.attStrength;
    const acy=this.cy+ps.attY*this.R*0.10*ps.attStrength;
    g.globalCompositeOperation='lighter';
    // faint ambient nebula — wide, soft, never a spotlight
    const neb=g.createRadialGradient(acx,acy,this.R*0.3,acx,acy,this.R*2.8);
    neb.addColorStop(0,`rgba(${c1[0]},${c1[1]},${c1[2]},${(0.030+r*0.018)*lum})`);
    neb.addColorStop(.55,`rgba(${c2[0]},${c2[1]},${c2[2]},${0.014*lum})`);
    neb.addColorStop(1,'rgba(0,0,0,0)');
    g.fillStyle=neb; g.fillRect(0,0,this.ow,this.oh);
    // plasma lobes — distributed soft smoke orbiting a ring, NOT piled at centre
    const touches=this.presence.touches;
    for(let i=0;i<this.lobes.length;i++){
      const L=this.lobes[i];
      const n1=fbm(Math.cos(L.seed)*1.1, Math.sin(L.seed)*1.1, L.nt);
      const n2=fbm(L.seed*.6+5, L.nt*0.8, L.nt);
      const turb=st*0.8;
      const ang=L.phase + n1*1.1 + n2*turb;
      const orbit=this.R*(0.55+L.rad)*expand*compress*gather*(0.9+breath*0.12);
      const drift=this.R*(0.18+Math.abs(n1)*0.30)*gather;
      let x=acx+Math.cos(ang)*orbit + Math.cos(ang*1.7+n2*3)*drift*(1+turb*0.4);
      let y=acy+Math.sin(ang)*orbit + Math.sin(ang*1.7+n1*3)*drift*(1+turb*0.4);
      // Touch physics: the field parts around contact, then gathers toward it —
      // the signature reversal. A displacement of the SAME body, never particles.
      for(const tp of touches){
        const tx=this.cx+tp.x*this.R, ty=this.cy+tp.y*this.R;
        const dx=x-tx, dy=y-ty, d=Math.hypot(dx,dy), reach=this.R*0.95;
        if(d<reach&&d>0.001){
          const inf=this.presence.touchInfluence(now-tp.t0)*(1-d/reach);
          x-=(dx/d)*inf*this.R*0.055; y-=(dy/d)*inf*this.R*0.055;
        }
      }
      const size=this.R*(L.sz*0.95)*(0.7+breath*0.25)*expand*compress*(1+(ps.density-0.45)*0.18);
      const alpha=(0.034+r*0.020-f*0.010)*lum;               // soft; no blown highlights
      const rg=g.createRadialGradient(x,y,0,x,y,Math.max(size,1));
      rg.addColorStop(0,`rgba(${c1[0]},${c1[1]},${c1[2]},${alpha})`);
      rg.addColorStop(.5,`rgba(${c2[0]},${c2[1]},${c2[2]},${alpha*0.45})`);
      rg.addColorStop(1,'rgba(0,0,0,0)');
      g.fillStyle=rg; g.beginPath(); g.arc(x,y,Math.max(size,1),0,6.2832); g.fill();
    }
    // NO white nucleus — the organism is plasma/smoke, never a spotlight
    g.globalCompositeOperation='source-over';
    // upscale to main canvas — smoothing gives the final soft, cinematic blur
    const c=this.ctx; c.imageSmoothingEnabled=true; c.imageSmoothingQuality='high';
    c.clearRect(0,0,this.w,this.h);
    c.drawImage(this.off,0,0,this.ow,this.oh,0,0,this.w,this.h);
  }
  // Step runs every frame (cheap). Render budget is adaptive: ~45fps at rest for
  // battery headroom, 60fps while the user is in physical contact — the one
  // moment that earns it (Presence decision memo).
  frame=(now)=>{this.step(now);const budget=this.presence.pointerFresh(now)?15:22;
    if(now-(this._lr||0)>=budget){this.render();this._lr=now;}requestAnimationFrame(this.frame);};
  start(){requestAnimationFrame(this.frame);}
}

/* HumanCoreView is a presentation adapter. It never computes physiology and
   never sends commands to the organism. It reads LivingCore's rendered canvas,
   breath and already-derived state, then composes that living material into a
   neutral human form. */
class HumanCoreView{
  constructor(canvas,source,livingCore){
    this.cv=canvas;this.source=source;this.core=livingCore;this.ctx=canvas.getContext('2d');
    this.dpr=Math.min(window.devicePixelRatio||1,2);this.mask=document.createElement('canvas');
    this.texture=document.createElement('canvas');this.mctx=this.mask.getContext('2d');this.tctx=this.texture.getContext('2d');
    this.figure=new Image();this.figureReady=false;
    this.figure.onload=()=>{this.figureReady=true;};
    this.figure.src='/static/apex-human-energy-neutral.png';
    this.color=[255,177,60];this.color2=[255,106,60];this.lastCss=0;this.resize();
    window.addEventListener('resize',()=>this.resize());
  }
  resize(){
    this.w=Math.max(2,this.cv.clientWidth);this.h=Math.max(2,this.cv.clientHeight);
    for(const c of [this.cv,this.mask,this.texture]){c.width=Math.round(this.w*this.dpr);c.height=Math.round(this.h*this.dpr);}
    for(const g of [this.ctx,this.mctx,this.tctx])g.setTransform(this.dpr,0,0,this.dpr,0,0);
  }
  targetPalette(){
    const key=readoutKey(this.core.cur);
    if(key==='strained'||key==='recover')return[[242,31,43],[255,90,50]];
    if(key==='peak')return[[200,255,61],[76,220,138]];
    return[[255,177,60],[255,106,60]];
  }
  body(g,cx,top,H,breath,paint='#fff'){
    const s=H/720,lean=(this.core.presence.p.attX||0)*9*s,b=1+breath*.018;
    g.save();g.translate(cx+lean,top+H*.48);g.scale(b,1+(b-1)*.65);g.translate(-cx,-(top+H*.48));
    g.fillStyle=paint;g.strokeStyle=paint;g.lineCap='round';g.lineJoin='round';
    // Head and neck: a quiet three-quarter orientation, never a portrait.
    g.beginPath();g.ellipse(cx+18*s,top+58*s,39*s,51*s,-.12,0,Math.PI*2);g.fill();
    g.lineWidth=36*s;g.beginPath();g.moveTo(cx+5*s,top+103*s);g.lineTo(cx-2*s,top+143*s);g.stroke();
    // Torso and pelvis.
    g.beginPath();g.moveTo(cx-7*s,top+132*s);
    g.bezierCurveTo(cx-72*s,top+127*s,cx-102*s,top+158*s,cx-92*s,top+226*s);
    g.bezierCurveTo(cx-84*s,top+282*s,cx-65*s,top+326*s,cx-64*s,top+374*s);
    g.bezierCurveTo(cx-28*s,top+398*s,cx+27*s,top+398*s,cx+65*s,top+370*s);
    g.bezierCurveTo(cx+62*s,top+317*s,cx+89*s,top+274*s,cx+93*s,top+214*s);
    g.bezierCurveTo(cx+99*s,top+157*s,cx+66*s,top+132*s,cx-7*s,top+132*s);g.closePath();g.fill();
    // Arms, built in tapering segments for an anatomically neutral silhouette.
    g.lineWidth=43*s;g.beginPath();g.moveTo(cx-76*s,top+164*s);g.quadraticCurveTo(cx-126*s,top+233*s,cx-115*s,top+302*s);g.stroke();
    g.lineWidth=31*s;g.beginPath();g.moveTo(cx-115*s,top+294*s);g.quadraticCurveTo(cx-103*s,top+357*s,cx-88*s,top+405*s);g.stroke();
    g.lineWidth=44*s;g.beginPath();g.moveTo(cx+75*s,top+166*s);g.quadraticCurveTo(cx+127*s,top+224*s,cx+116*s,top+294*s);g.stroke();
    g.lineWidth=30*s;g.beginPath();g.moveTo(cx+116*s,top+286*s);g.quadraticCurveTo(cx+105*s,top+349*s,cx+91*s,top+402*s);g.stroke();
    // Legs.
    g.lineWidth=58*s;g.beginPath();g.moveTo(cx-35*s,top+371*s);g.quadraticCurveTo(cx-55*s,top+478*s,cx-47*s,top+548*s);g.stroke();
    g.lineWidth=42*s;g.beginPath();g.moveTo(cx-47*s,top+535*s);g.quadraticCurveTo(cx-55*s,top+623*s,cx-63*s,top+697*s);g.stroke();
    g.lineWidth=59*s;g.beginPath();g.moveTo(cx+34*s,top+371*s);g.quadraticCurveTo(cx+56*s,top+470*s,cx+48*s,top+544*s);g.stroke();
    g.lineWidth=42*s;g.beginPath();g.moveTo(cx+48*s,top+532*s);g.quadraticCurveTo(cx+57*s,top+620*s,cx+66*s,top+697*s);g.stroke();
    g.restore();
  }
  figureMask(g,cx,top,H,breath){
    if(!this.figureReady){this.body(g,cx,top,H,breath);return;}
    const lean=(this.core.presence.p.attX||0)*9*(H/720),b=1+breath*.018;
    const fw=H*(this.figure.naturalWidth/this.figure.naturalHeight);
    g.save();g.translate(cx+lean,top+H*.48);g.scale(b,1+(b-1)*.65);g.translate(-cx,-(top+H*.48));
    g.drawImage(this.figure,cx-fw*.5,top,fw,H);g.restore();
  }
  render(now){
    const target=this.targetPalette(),ease=.035;
    for(let i=0;i<3;i++){this.color[i]+=(target[0][i]-this.color[i])*ease;this.color2[i]+=(target[1][i]-this.color2[i])*ease;}
    const c1=this.color.map(Math.round),c2=this.color2.map(Math.round),p=this.core.cur;
    const breath=this.core.presence.breath.value,cx=this.w*(innerWidth<=560?.5:.53);
    const H=Math.min(this.h*(innerWidth<=560?.94:1.08),this.w*(innerWidth<=560?1.68:1.26));
    const top=Math.max(innerWidth<=560?8:-30,(this.h-H)*(innerWidth<=560?.34:.48));
    const mg=this.mctx,tg=this.tctx,c=this.ctx;
    mg.clearRect(0,0,this.w,this.h);this.figureMask(mg,cx,top,H,breath);
    tg.clearRect(0,0,this.w,this.h);
    const halo=tg.createRadialGradient(cx,top+H*.38,H*.04,cx,top+H*.4,H*.55);
    halo.addColorStop(0,`rgba(${c1.join(',')},${.34+p.recovery*.18})`);
    halo.addColorStop(.56,`rgba(${c2.join(',')},.16)`);halo.addColorStop(1,'rgba(0,0,0,0)');
    tg.fillStyle=halo;tg.fillRect(0,0,this.w,this.h);
    // A continuous tissue layer keeps the organism legible even while the
    // original core is in a quiet phase. Its colour still comes only from the
    // already-classified physiology state above.
    const tissue=tg.createLinearGradient(cx-H*.22,top,cx+H*.23,top+H);
    tissue.addColorStop(0,`rgba(${c2.join(',')},.58)`);
    tissue.addColorStop(.42,`rgba(${c1.join(',')},.94)`);
    tissue.addColorStop(.72,`rgba(${c2.join(',')},.68)`);
    tissue.addColorStop(1,`rgba(${c1.join(',')},.76)`);
    tg.fillStyle=tissue;tg.fillRect(cx-H*.24,top-H*.02,H*.48,H*1.04);
    tg.globalCompositeOperation='screen';tg.globalAlpha=.9;
    tg.drawImage(this.source,0,0,this.source.width,this.source.height,cx-H*.34,top-H*.02,H*.68,H*1.02);
    // Fine energy fibres move with the same living clock and remain inside the body.
    tg.globalAlpha=.34;tg.strokeStyle=`rgb(${c1.join(',')})`;tg.lineWidth=.7;
    for(let n=0;n<20;n++){
      const y=top+H*(.10+n*.039),phase=this.core.t*1.7+n*.71;
      tg.beginPath();tg.moveTo(cx-H*.16,y);
      tg.bezierCurveTo(cx-H*(.03+Math.sin(phase)*.07),y+H*.04,cx+H*(.04+Math.cos(phase*.8)*.08),y-H*.035,cx+H*.16,y+H*.02);tg.stroke();
    }
    tg.globalAlpha=1;tg.globalCompositeOperation='destination-in';tg.drawImage(this.mask,0,0,this.w,this.h);tg.globalCompositeOperation='source-over';
    c.clearRect(0,0,this.w,this.h);
    // Draw the state-coloured organism itself first, then layer the original
    // LivingCore material over it. This is deliberately independent of how
    // sparse the core becomes during a quiet/resting frame.
    const visibleTissue=c.createLinearGradient(cx-H*.18,top,cx+H*.2,top+H);
    visibleTissue.addColorStop(0,`rgb(${c2.join(',')})`);
    visibleTissue.addColorStop(.48,`rgb(${c1.join(',')})`);
    visibleTissue.addColorStop(1,`rgb(${c2.join(',')})`);
    c.save();c.globalAlpha=.95;c.shadowColor=`rgba(${c1.join(',')},.62)`;c.shadowBlur=30;
    if(this.figureReady){
      // Preserve the generated figure's anatomical fibres and light detail;
      // colour is blended over those pixels rather than replacing them.
      this.figureMask(c,cx,top,H,breath);c.globalCompositeOperation='source-atop';c.globalAlpha=.72;
      c.fillStyle=visibleTissue;c.fillRect(0,0,this.w,this.h);
    }else{
      c.drawImage(this.mask,0,0,this.w,this.h);c.globalCompositeOperation='source-in';
      c.fillStyle=visibleTissue;c.fillRect(0,0,this.w,this.h);
    }
    c.restore();
    c.save();c.globalCompositeOperation='screen';c.globalAlpha=.38;c.filter='blur(18px)';c.drawImage(this.texture,0,0,this.w,this.h);c.restore();
    c.save();c.globalCompositeOperation='screen';c.globalAlpha=.72;c.drawImage(this.texture,0,0,this.w,this.h);c.restore();
    if(now-this.lastCss>180){
      document.documentElement.style.setProperty('--apx-state',`rgb(${c1.join(',')})`);
      document.documentElement.style.setProperty('--apx-state-rgb',c1.join(','));this.lastCss=now;
    }
  }
  frame=(now)=>{this.render(now);requestAnimationFrame(this.frame);};
  start(){requestAnimationFrame(this.frame);}
}

// The interface never speaks to the organism. It reports FACTS to the nervous
// system — in the world's vocabulary, not the body's — and the body derives
// everything from state. A model failure must never break chat, workouts, or
// payments: the coach survives its body.
function witness(fact,payload){try{if(window.core&&core.athlete)core.athlete.observe(fact,payload);}catch(e){}}

/* ═══════════════════════════════════════════════════════════════════
   PHYSIOLOGY
   ═══════════════════════════════════════════════════════════════════ */
function computePhysiology(){
  let p={};try{p=JSON.parse(ownedStorageGet('apexProfile')||'{}');}catch(e){}
  const sleep=(p.sleepQuality||'average').toLowerCase(),stress=(p.stressLevel||'moderate').toLowerCase(),rec=(p.recoveryFeel||'ok').toLowerCase();
  let recovery=.55,fatigue=.38,str=.3;
  if(sleep==='good'){recovery+=.22;fatigue-=.15;} else if(sleep==='poor'){recovery-=.25;fatigue+=.25;}
  if(rec==='fresh'){recovery+=.12;fatigue-=.1;} else if(rec==='tired'){recovery-=.14;fatigue+=.14;}
  if(stress==='low'){str=.18;recovery+=.06;} else if(stress==='high'){str=.72;recovery-=.12;fatigue+=.12;} else str=.4;
  try{const log=JSON.parse(ownedStorageGet('apexWorkoutLog')||'[]');
    const recent=log.filter(s=>Date.now()-(s.ts||0)<2*864e5).length; fatigue+=Math.min(recent*.08,.24);}catch(e){}
  const cl=v=>Math.max(.05,Math.min(.97,v));
  return{recovery:cl(recovery),fatigue:cl(fatigue),stress:cl(str)};
}

/* ═══════════════════════════════════════════════════════════════════
   COACH MEMORY — persistent. APEX never meets the user for the first time.
   ═══════════════════════════════════════════════════════════════════ */
function memLoad(){try{return JSON.parse(ownedStorageGet('apexCoachMemory')||'{}');}catch(e){return{};}}
function memSave(m){ownedStorageSet('apexCoachMemory',JSON.stringify(m));}
function logWorkout(session,workoutCompletion=null){
  let log=[];try{log=JSON.parse(ownedStorageGet('apexWorkoutLog')||'[]');}catch(e){}
  log.push(session); ownedStorageSet('apexWorkoutLog',JSON.stringify(log.slice(-60)));
  accountLogWorkout(session,workoutCompletion); // → account timeline (server truth) when signed in
  const m=memLoad();
  m.lastWorkout=session; m.lastWorkoutAt=session.ts;
  m.totalWorkouts=(m.totalWorkouts||0)+1;
  m.exerciseHistory=m.exerciseHistory||{};
  (session.exercises||[]).forEach(ex=>{
    const k=ex.name; (m.exerciseHistory[k]=m.exerciseHistory[k]||[]).push({date:session.date,sets:ex.sets,reps:ex.reps,weight:ex.weight||''});
    m.exerciseHistory[k]=m.exerciseHistory[k].slice(-12);
  });
  memSave(m);
}
// Build the [WORKOUT MEMORY] block the backend coaching engine reads.
function buildWorkoutContext(en){
  let log=[];try{log=JSON.parse(ownedStorageGet('apexWorkoutLog')||'[]');}catch(e){}
  if(!log.length)return '';
  const m=memLoad(), last=log[log.length-1];
  const wkAgo=Date.now()-(last.ts||0), justDone=wkAgo<2*3600e3;
  const wk7=log.filter(s=>Date.now()-(s.ts||0)<7*864e5).length;
  const L=[];
  L.push(en?'[WORKOUT MEMORY]':'[ТРЕНИРОВЪЧНА ПАМЕТ]');
  L.push((en?'  Completed sessions: ':'  Завършени сесии: ')+log.length);
  L.push((en?'  Frequency (7d): ':'  Честота (7д): ')+wk7+(en?'/week':'/седмица'));
  if(last){
    const exs=(last.exercises||[]).map(e=>`${e.name} ${e.sets}×${e.reps}${e.weight?(' @'+e.weight+'kg'):''}`).join(', ');
    L.push((en?'  Last session: ':'  Последна сесия: ')+last.date+' — '+(last.type||'training')+(exs?(' ('+exs+')'):''));
  }
  if(justDone)L.push(en?'  ⚡ POST-WORKOUT — finished within the last 2 hours. Acknowledge it; do NOT prescribe a new workout.':'  ⚡ СЛЕД ТРЕНИРОВКА — завършена в последните 2 часа. Признай я; НЕ предлагай нова тренировка.');
  if(m.lastNutritionAt)L.push((en?'  Last nutrition plan: ':'  Последен хранителен план: ')+new Date(m.lastNutritionAt).toLocaleDateString());
  return L.join('\n');
}

/* ═══════════════════════════════════════════════════════════════════
   LOCALIZATION — complete EN / BG. Zero English in BG mode.
   ═══════════════════════════════════════════════════════════════════ */
const T={
  en:{eyebrow:'SYSTEM ONLINE',ctaTrain:'Start training',ctaConsult:'Consult',back:'Back',live:'LIVE',
    feedback:'Send feedback',profile:'Profile',chEngine:'APEX COACH ENGINE',placeholder:'Describe your goal…',
    recovery:'Recovery',fatigue:'Fatigue',stress:'Stress',assessmentTitle:'Profile assessment',assessmentPending:'Assessment pending',assessmentSupport:'Complete your profile to calculate these values.',coach:'APEX',typing:'CALIBRATING',
    greetHi:'I read your signals.',greetSub:'Goal on file:',
    chips:[{label:"Today's Workout",q:'Make me a workout for today'},{label:'Nutrition Plan',q:'Make me a nutrition plan'},{label:'Progress',q:'How am I progressing?'},{label:'Ask APEX',q:null}],
    states:{peak:{h:'Peak readiness',s:'Recovery is high. Your nervous system is primed — this is your window to push.'},
      ready:{h:'Ready to train',s:'Balanced signals. A solid, productive session is well within reach today.'},
      recover:{h:'Recovery mode',s:'Fatigue is elevated. The smart move today is volume down, quality up.'},
      strained:{h:'Running hot',s:'Stress is high and recovery is thin. Today is about restoration, not records.'}},
    wiz:{c1:'Identity',c2:'Biology',c3:'Lifestyle',
      t1:'Who you are',t2:'Your recovery signals',t3:'Context that shapes the plan',
      d1:'The coach builds every plan around these. Honest input, honest results.',
      d2:'These drive the living organism and how hard the coach pushes today.',
      d3:'All optional. The more the coach knows, the safer and sharper the plan.',
      goal:'Primary goal',age:'Age',weight:'Weight (kg)',height:'Height (cm)',gender:'Sex',level:'Experience',
      equip:'Available equipment',sleep:'Sleep quality',stress:'Stress level',recovery:'Recovery feel',
      activity:'Daily activity',freq:'Training frequency (per week)',smoking:'Smoking',alcohol:'Alcohol',
      nicotine:'Nicotine',caffeine:'Caffeine',meds:'Medications',supps:'Supplements',injuries:'Previous injuries',
      surgeries:'Surgeries',limits:'Physical limitations',notes:'Additional notes',cont:'Continue →',save:'Save & calibrate',
      safety:'This information is used only to personalize coaching. APEX does not diagnose, prescribe or replace medical professionals.',
      opt:{goal:{fat_loss:'Lose fat',muscle_gain:'Build muscle',strength:'Get stronger',endurance:'Endurance',general:'General fitness'},
        gender:{male:'Male',female:'Female'},level:{beginner:'Beginner',intermediate:'Intermediate',advanced:'Advanced'},
        equip:{gym:'Full gym',home:'Home (dumbbells / bar)',none:'Bodyweight only'},
        sleep:{good:'Good',average:'Average',poor:'Poor'},stress:{low:'Low',moderate:'Moderate',high:'High'},
        recovery:{fresh:'Fresh',ok:'Okay',tired:'Tired'},
        activity:{sedentary:'Sedentary',moderate:'Moderate',active:'Active',very_active:'Very active'},
        smoking:{'':'—',no:'No',occasional:'Occasional',yes:'Yes'},alcohol:{'':'—',none:'None',social:'Social',regular:'Regular'},
        nicotine:{'':'—',no:'No',yes:'Yes'},caffeine:{'':'—',none:'None',moderate:'Moderate',high:'High'},
        freq:{'2':'2 days','3':'3 days','4':'4 days','5':'5 days','6':'6 days'}}},
    saved:'Calibrated to your signals.',cancelSub:'Cancel subscription',
    limitTitle:"You've hit today's free limit",limitDesc:'Come back in about {h}h — or unlock unlimited coaching anytime.',unlock:'Unlock Unlimited →',
    auth:{signin:'Sign in',signout:'Sign out',title:'Sign in to APEX',desc:'Enter your email — we send a one-time sign-in link. No password.',
      email:'you@email.com',send:'Send link',sent:'Check your inbox — we sent a sign-in link to <strong>{email}</strong>. It expires in 20 minutes.',
      rate:'Too many requests. Try again in a few minutes.',err:'Something went wrong. Try again.',
      welcome:'Signed in ✓ Your coach remembers you.',loggedOut:'Signed out.',linkBad:'That sign-in link is invalid or expired.',
      haveAccount:'Already a member? Sign in'},
    fbTitle:'Send feedback',fbDesc:'Tell the team what would make APEX better.',fbSend:'Send',fbThanks:'Thank you — received.',
    woStart:'Start session',woEx:'Exercise',woRest:'Rest',woNext:'Next',woDone:'Complete set',woFinish:'Finish',
    woExit:'Exit',woSkip:'Skip rest',woResume:'Begin',woComplete:'Session complete',woGreat:'Logged. Recovery starts now.',
    woSummary:{ex:'Exercises',sets:'Sets',time:'Minutes'},todayWO:'Build me a workout for today',
    nutriTotal:'Daily totals',sec:'sec',jumpLatest:'Jump to latest',
    menu:{home:'Home',consult:'Consultation',workouts:'My Workouts',nutrition:'Nutrition',progress:'Progress',
      history:'History',profile:'Profile',feedback:'Feedback',subscription:'Subscription',language:'Language',
      settings:'Settings',privacy:'Privacy & Safety',about:'About APEX'},
    seed:{workouts:'Build me a workout for today',nutrition:'Build me a nutrition plan',progress:'How am I progressing? Analyze my training.'},
    sub:{title:'Subscription',plan:'Current plan',billing:'Next billing date',method:'Payment method',
      history:'Billing history',cancel:'Cancel subscription',free:'Free',card:'Card on file',none:'—',
      statusL:'Status',statuses:{active:'Active',grace:'Active (cancels at period end)',cancelled:'Cancelled',expired:'Expired',free:'Free'},
      freeDesc:'You are on the free plan. Premium access is temporarily unavailable while we prepare the next APEX release.',
      upgrade:'View plans →',upgradePro:'PRO — €14.99 / 30 days',upgradeCore:'CORE — €9.99 / 30 days',comingSoon:'Coming soon',comingSoonNote:'Premium access is temporarily unavailable while we prepare the next APEX release.',
      access:'Access until',oneTime:'One-time 30-day pass (not a recurring subscription)',
      eu:'Refund requests are handled under the Refund Policy and applicable consumer-law rules.',
      confirmCancel:'Cancel your subscription and request a refund? This cannot be undone.'},
    hist:{title:'History',desc:'Your completed sessions and coaching activity.',empty:'No completed workouts yet. Finish a session and it appears here.',
      sets:'sets',exercises:'exercises'},
    settings:{title:'Settings',lang:'Language',theme:'Theme',dark:'Dark (default)',reset:'Reset local data',
      resetDesc:'Clears profile, memory and history on this device.',resetConfirm:'Erase all local APEX data on this device?',reset2:'Local data cleared.'},
    priv:{title:'Privacy & Safety',b:'<h4>Your data</h4><p>Your profile, memory and history are stored locally in your browser. Coaching context is sent to the AI only to generate your plans.</p><h4>Medical safety</h4><p>APEX is a coaching tool. It does not diagnose, prescribe, or replace medical professionals. For pain, symptoms or medical conditions, consult a doctor.</p><h4>Never shared</h4><p>Your data is never sold or shared with third parties.</p>'},
    about:{title:'About APEX',b:'<p><strong>APEX PULSE PRO</strong> is a living AI biological operating system — a personal coach that reads your physiology and adapts every plan to you.</p><h4>What it does</h4><ul><li>Personalized training & nutrition</li><li>Recovery-aware coaching</li><li>Persistent coaching memory</li></ul><p style="color:var(--faint);margin-top:12px">Version 3.3 · Your peak. Your pulse.</p>'}},
  bg:{eyebrow:'СИСТЕМАТА Е АКТИВНА',ctaTrain:'Започни тренировка',ctaConsult:'Консултация',back:'Назад',live:'НА ЖИВО',
    feedback:'Изпрати обратна връзка',profile:'Профил',chEngine:'APEX ТРЕНЬОРСКО ЯДРО',placeholder:'Опиши целта си…',
    recovery:'Възстановяване',fatigue:'Умора',stress:'Стрес',assessmentTitle:'Оценка на профила',assessmentPending:'Очаква оценка',assessmentSupport:'Попълни профила си, за да изчислим стойностите.',coach:'APEX',typing:'ПРЕСМЯТАМ',
    greetHi:'Прочетох сигналите ти.',greetSub:'Цел във файла:',
    chips:[{label:'Тренировка за днес',q:'Направи ми тренировка за днес'},{label:'Хранителен план',q:'Направи ми хранителен план'},{label:'Прогрес',q:'Как напредвам?'},{label:'Попитай APEX',q:null}],
    states:{peak:{h:'Пиково състояние',s:'Възстановяването е високо. Нервната ти система е заредена — това е моментът да натиснеш.'},
      ready:{h:'Готов за тренировка',s:'Балансирани сигнали. Солидна, продуктивна сесия е напълно постижима днес.'},
      recover:{h:'Режим възстановяване',s:'Умората е повишена. Умното решение днес е по-малко обем, повече качество.'},
      strained:{h:'Системата е под напрежение',s:'Стресът е висок, възстановяването — слабо. Днес е за регенерация, не за рекорди.'}},
    wiz:{c1:'Идентичност',c2:'Биология',c3:'Начин на живот',
      t1:'Кой си ти',t2:'Сигналите ти за възстановяване',t3:'Контекст, който оформя плана',
      d1:'Треньорът гради всеки план около тези данни. Честни данни, честни резултати.',
      d2:'Те задвижват живия организъм и колко силно треньорът натиска днес.',
      d3:'Всичко е по избор. Колкото повече знае треньорът, толкова по-безопасен и точен е планът.',
      goal:'Основна цел',age:'Възраст',weight:'Тегло (кг)',height:'Височина (см)',gender:'Пол',level:'Опит',
      equip:'Налично оборудване',sleep:'Качество на съня',stress:'Ниво на стрес',recovery:'Усещане за възстановяване',
      activity:'Дневна активност',freq:'Тренировки седмично',smoking:'Пушене',alcohol:'Алкохол',
      nicotine:'Никотин',caffeine:'Кофеин',meds:'Лекарства',supps:'Добавки',injuries:'Предишни травми',
      surgeries:'Операции',limits:'Физически ограничения',notes:'Допълнителни бележки',cont:'Продължи →',save:'Запази и калибрирай',
      safety:'Тази информация се използва само за персонализиране на треньорството. APEX не диагностицира, не предписва и не замества медицински специалисти.',
      opt:{goal:{fat_loss:'Свали мазнини',muscle_gain:'Натрупай мускули',strength:'Стани по-силен',endurance:'Издръжливост',general:'Общ тонус'},
        gender:{male:'Мъж',female:'Жена'},level:{beginner:'Начинаещ',intermediate:'Среден',advanced:'Напреднал'},
        equip:{gym:'Пълна зала',home:'Вкъщи (дъмбели / турник)',none:'Само телесно тегло'},
        sleep:{good:'Добър',average:'Среден',poor:'Лош'},stress:{low:'Нисък',moderate:'Среден',high:'Висок'},
        recovery:{fresh:'Свеж',ok:'Нормално',tired:'Уморен'},
        activity:{sedentary:'Заседнала',moderate:'Умерена',active:'Активна',very_active:'Много активна'},
        smoking:{'':'—',no:'Не',occasional:'Понякога',yes:'Да'},alcohol:{'':'—',none:'Никакъв',social:'Социален',regular:'Редовен'},
        nicotine:{'':'—',no:'Не',yes:'Да'},caffeine:{'':'—',none:'Никакъв',moderate:'Умерен',high:'Висок'},
        freq:{'2':'2 дни','3':'3 дни','4':'4 дни','5':'5 дни','6':'6 дни'}}},
    saved:'Калибрирано спрямо сигналите ти.',cancelSub:'Откажи абонамента',
    limitTitle:'Достигна безплатния лимит за днес',limitDesc:'Върни се след около {h}ч — или отключи неограничен достъп по всяко време.',unlock:'Отключи неограничено →',
    auth:{signin:'Вход',signout:'Изход',title:'Вход в APEX',desc:'Въведи имейла си — изпращаме еднократна връзка за вход. Без парола.',
      email:'ти@имейл.com',send:'Изпрати връзка',sent:'Провери пощата си — изпратихме връзка за вход до <strong>{email}</strong>. Валидна е 20 минути.',
      rate:'Твърде много заявки. Опитай отново след няколко минути.',err:'Нещо се обърка. Опитай отново.',
      welcome:'Влезе ✓ Треньорът те помни.',loggedOut:'Излезе от профила.',linkBad:'Връзката за вход е невалидна или изтекла.',
      haveAccount:'Вече имаш профил? Влез'},
    fbTitle:'Обратна връзка',fbDesc:'Кажи на екипа какво би направило APEX по-добър.',fbSend:'Изпрати',fbThanks:'Благодаря — получено.',
    woStart:'Започни сесия',woEx:'Упражнение',woRest:'Почивка',woNext:'Следва',woDone:'Завърши серия',woFinish:'Завърши',
    woExit:'Изход',woSkip:'Пропусни почивката',woResume:'Започни',woComplete:'Сесията завърши',woGreat:'Записано. Възстановяването започва сега.',
    woSummary:{ex:'Упражнения',sets:'Серии',time:'Минути'},todayWO:'Направи ми тренировка за днес',
    nutriTotal:'Дневни общо',sec:'сек',jumpLatest:'Към последното',
    menu:{home:'Начало',consult:'Консултация',workouts:'Моите тренировки',nutrition:'Хранене',progress:'Прогрес',
      history:'История',profile:'Профил',feedback:'Обратна връзка',subscription:'Абонамент',language:'Език',
      settings:'Настройки',privacy:'Поверителност и безопасност',about:'За APEX'},
    seed:{workouts:'Направи ми тренировка за днес',nutrition:'Направи ми хранителен план',progress:'Как напредвам? Анализирай тренировките ми.'},
    sub:{title:'Абонамент',plan:'Текущ план',billing:'Следваща дата на плащане',method:'Метод на плащане',
      history:'История на плащанията',cancel:'Откажи абонамента',free:'Безплатен',card:'Записана карта',none:'—',
      statusL:'Статус',statuses:{active:'Активен',grace:'Активен (спира в края на периода)',cancelled:'Отказан',expired:'Изтекъл',free:'Безплатен'},
      freeDesc:'Ти си на безплатния план. Платеният достъп е временно спрян, докато подготвяме следващото издание на APEX.',
      upgrade:'Виж плановете →',upgradePro:'PRO — €14.99 / 30 дни',upgradeCore:'CORE — €9.99 / 30 дни',comingSoon:'Очаквайте скоро',comingSoonNote:'Платеният достъп е временно спрян, докато подготвяме следващото издание на APEX.',
      access:'Достъп до',oneTime:'Еднократен 30-дневен достъп (не е повтарящ се абонамент)',
      eu:'Исканията за възстановяване се разглеждат съгласно Политиката за възстановяване и приложимите правила за защита на потребителите.',
      confirmCancel:'Да откажа абонамента и да поискам възстановяване? Това е необратимо.'},
    hist:{title:'История',desc:'Твоите завършени сесии и треньорска активност.',empty:'Още няма завършени тренировки. Завърши сесия и тя ще се появи тук.',
      sets:'серии',exercises:'упражнения'},
    settings:{title:'Настройки',lang:'Език',theme:'Тема',dark:'Тъмна (по подразбиране)',reset:'Изчисти локалните данни',
      resetDesc:'Изтрива профил, памет и история на това устройство.',resetConfirm:'Да изтрия всички локални данни на APEX на това устройство?',reset2:'Локалните данни са изчистени.'},
    priv:{title:'Поверителност и безопасност',b:'<h4>Твоите данни</h4><p>Профилът, паметта и историята ти се съхраняват локално в браузъра ти. Треньорският контекст се изпраща до AI само за да генерира плановете ти.</p><h4>Медицинска безопасност</h4><p>APEX е треньорски инструмент. Не диагностицира, не предписва и не замества медицински специалисти. При болка, симптоми или заболявания се консултирай с лекар.</p><h4>Никога не се споделя</h4><p>Данните ти никога не се продават или споделят с трети страни.</p>'},
    about:{title:'За APEX',b:'<p><strong>APEX PULSE PRO</strong> е жива AI биологична операционна система — личен треньор, който чете физиологията ти и адаптира всеки план за теб.</p><h4>Какво прави</h4><ul><li>Персонализирани тренировки и хранене</li><li>Треньорство спрямо възстановяването</li><li>Постоянна треньорска памет</li></ul><p style="color:var(--faint);margin-top:12px">Версия 3.3 · Your peak. Your pulse.</p>'}}
};
let lang=(localStorage.getItem('apexLang')||'en').toLowerCase(); if(lang!=='bg'&&lang!=='en')lang='en';
function tr(){return T[lang];}

/* ═══════════════════════════════════════════════════════════════════
   STATE READOUT
   ═══════════════════════════════════════════════════════════════════ */
function readoutKey(ph){
  if(ph.stress>.6&&ph.recovery<.5)return'strained';
  if(ph.fatigue>.6)return'recover';
  if(ph.recovery>.7&&ph.fatigue<.45)return'peak';
  return'ready';
}
function hasCompletedProfileAssessment(){
  const p=pfLoad();
  return ['goal','age','weight','height','gender','level','equipment','sleepQuality','stressLevel','recoveryFeel','activityLevel','frequency']
    .every(key=>String(p[key]||'').trim()!=='');
}
function applyReadout(){
  if(!hasCompletedProfileAssessment()){
    const t=tr();
    document.getElementById('read-state').textContent=t.assessmentTitle;
    document.getElementById('read-sub').textContent=t.assessmentSupport;
    document.getElementById('m-rec').textContent=t.assessmentPending;
    document.getElementById('m-fat').textContent=t.assessmentPending;
    document.getElementById('m-str').textContent=t.assessmentPending;
    return;
  }
  const ph=computePhysiology(); core.setPhysiology(ph);
  const s=tr().states[readoutKey(ph)];
  document.getElementById('read-state').textContent=s.h;
  document.getElementById('read-sub').textContent=s.s;
  document.getElementById('m-rec').textContent=Math.round(ph.recovery*100)+'%';
  document.getElementById('m-fat').textContent=Math.round(ph.fatigue*100)+'%';
  document.getElementById('m-str').textContent=Math.round(ph.stress*100)+'%';
}

/* ═══════════════════════════════════════════════════════════════════
   APPLY LANGUAGE
   ═══════════════════════════════════════════════════════════════════ */
function setOpts(id,map){const el=document.getElementById(id);if(!el)return;[...el.options].forEach(o=>{if(map[o.value]!==undefined)o.textContent=map[o.value];});}
function txt(id,v){const e=document.getElementById(id);if(e)e.textContent=v;}

function syncV4Shell(){
  const bg=lang==='bg', labels=bg?{today:'ДНЕС',coach:'ТРЕНЬОР',history:'ИСТОРИЯ',sleep:'Сън',goal:'Цел',label:'APEX',state:'ГОТОВ',head:'Днес според сигналите ти',copy:'Планът ти се адаптира към тялото, с което идваш днес.'}:{today:'TODAY',coach:'COACH',history:'HISTORY',sleep:'Sleep',goal:'Goal',label:'APEX',state:'READY',head:'Reading your signals',copy:'Your plan will adapt to the body that shows up today.'};
  txt('nav-today',labels.today);txt('nav-coach',labels.coach);txt('nav-history',labels.history);txt('sl-sleep',labels.sleep);txt('sl-goal',labels.goal);txt('decision-label',labels.label);txt('decision-state',labels.state);
  txt('decision-head',labels.head);txt('decision-copy',labels.copy);
}
function applyLang(){
  const t=tr(),w=t.wiz; document.documentElement.lang=lang;
  txt('ov-eyebrow',t.eyebrow); txt('cta-train',t.ctaTrain); txt('cta-consult',t.ctaConsult);
  txt('back-label',t.back); document.getElementById('status-pill').childNodes[0].nodeValue=t.live;
  txt('ch-label',t.chEngine); txt('ml-rec',t.recovery); txt('ml-fat',t.fatigue); txt('ml-str',t.stress);
  txt('jump-label',t.jumpLatest);
  syncV4Shell();
  const _ui=document.getElementById('user-in'); _ui.placeholder=t.placeholder; _ui.setAttribute('aria-label',t.placeholder);
  buildMenu();
  // wizard chrome
  txt('w1-cat',w.c1);txt('w2-cat',w.c2);txt('w3-cat',w.c3);
  txt('w1-title',w.t1);txt('w2-title',w.t2);txt('w3-title',w.t3);
  txt('w1-desc',w.d1);txt('w2-desc',w.d2);txt('w3-desc',w.d3);
  txt('l-goal',w.goal);txt('l-age',w.age);txt('l-weight',w.weight);txt('l-height',w.height);txt('l-gender',w.gender);
  txt('l-level',w.level);txt('l-equip',w.equip);txt('l-sleep',w.sleep);txt('l-stress',w.stress);txt('l-recovery',w.recovery);
  txt('l-activity',w.activity);txt('l-freq',w.freq);txt('l-smoking',w.smoking);txt('l-alcohol',w.alcohol);txt('l-nicotine',w.nicotine);
  txt('l-caffeine',w.caffeine);txt('l-meds',w.meds);txt('l-supps',w.supps);txt('l-injuries',w.injuries);
  txt('l-surgeries',w.surgeries);txt('l-limits',w.limits);txt('l-notes',w.notes);
  txt('w1-next',w.cont);txt('w2-next',w.cont);txt('w3-save',w.save);txt('safety-note',w.safety);
  txt('cancel-sub',t.cancelSub);
  setOpts('pf-goal',w.opt.goal);setOpts('pf-gender',w.opt.gender);setOpts('pf-level',w.opt.level);setOpts('pf-equip',w.opt.equip);
  setOpts('pf-sleep',w.opt.sleep);setOpts('pf-stress',w.opt.stress);setOpts('pf-recovery',w.opt.recovery);setOpts('pf-activity',w.opt.activity);
  setOpts('pf-smoking',w.opt.smoking);setOpts('pf-alcohol',w.opt.alcohol);setOpts('pf-nicotine',w.opt.nicotine);setOpts('pf-caffeine',w.opt.caffeine);
  setOpts('pf-freq',w.opt.freq);
  applyReadout();
}
function toggleLang(){
  lang=lang==='en'?'bg':'en';localStorage.setItem('apexLang',lang);
  const profile=pfLoad();profile.language=lang;ownedStorageSet('apexProfile',JSON.stringify(profile));accountSaveProfile(profile);
  applyLang();renderTrainingConstraints(ACTIVE_TRAINING_CONSTRAINTS);if(consultOn)resetGreeting();
}

/* ═══════════════════════════════════════════════════════════════════
   PROFILE WIZARD
   ═══════════════════════════════════════════════════════════════════ */
let wizStep=0;
let ACTIVE_TRAINING_CONSTRAINTS=[];
const TRAINING_CONSTRAINT_LABELS={
  vertical_push:{en:'Avoid overhead pressing',bg:'Избягвай преси над глава'},
  horizontal_push:{en:'Avoid push-ups',bg:'Избягвай лицеви опори'},
  vertical_pull:{en:'Avoid pull-ups',bg:'Избягвай набирания'},
  squat:{en:'Avoid squats',bg:'Избягвай клекове'},
  lunge:{en:'Avoid lunges',bg:'Избягвай напади'},
  hinge:{en:'Avoid deadlifts',bg:'Избягвай мъртва тяга'}
};
function renderTrainingConstraints(records){
  ACTIVE_TRAINING_CONSTRAINTS=Array.isArray(records)?records.map(record=>{
    if(typeof record==='string')return {pattern:record,removable:false};
    if(!record||typeof record!=='object'||typeof record.pattern!=='string')return null;
    return {id:typeof record.id==='string'?record.id:'',pattern:record.pattern,removable:record.removable===true};
  }).filter(record=>record&&TRAINING_CONSTRAINT_LABELS[record.pattern]):[];
  const section=document.getElementById('training-constraints');
  const title=document.getElementById('training-constraints-title');
  const list=document.getElementById('training-constraints-list');
  if(!section||!title||!list)return;
  title.textContent=lang==='bg'?'Активни тренировъчни ограничения':'Active training constraints';
  section.hidden=!ACTIVE_TRAINING_CONSTRAINTS.length;
  list.innerHTML=ACTIVE_TRAINING_CONSTRAINTS.map(record=>{
    const label=TRAINING_CONSTRAINT_LABELS[record.pattern][lang];
    const action=record.removable&&record.id?'<button type="button" class="training-constraint-remove" aria-label="'+esc((lang==='bg'?'Премахни ограничението: ':'Remove restriction: ')+label)+'" title="'+esc(lang==='bg'?'Премахни':'Remove')+'" onclick="removeTrainingConstraint(\''+esc(record.id)+'\')">×</button>':'';
    return '<li><span>'+esc(label)+'</span>'+action+'</li>';
  }).join('');
}
async function removeTrainingConstraint(id){
  if(!SESSION.authenticated||typeof id!=='string'||!id)return;
  const record=ACTIVE_TRAINING_CONSTRAINTS.find(item=>item.id===id&&item.removable);
  if(!record)return;
  const label=TRAINING_CONSTRAINT_LABELS[record.pattern][lang];
  const question=lang==='bg'?'Премахваш ограничението: '+label+'?':'Remove restriction: '+label+'?';
  if(!window.confirm(question))return;
  try{
    const response=await fetch('/api/training-constraints/'+encodeURIComponent(id),{method:'DELETE',credentials:'same-origin'});
    if(!response.ok)return;
    const data=await response.json();
    renderTrainingConstraints(Array.isArray(data.training_constraint_records)?data.training_constraint_records:[]);
  }catch(e){}
}
function pfLoad(){try{return JSON.parse(ownedStorageGet('apexProfile')||'{}');}catch(e){return{};}}
function wizGo(n){
  wizStep=n;
  document.querySelectorAll('.wiz-card').forEach(c=>c.classList.toggle('on',+c.dataset.card===n));
  document.querySelectorAll('.wiz-dot').forEach(d=>d.classList.toggle('on',+d.dataset.s<=n));
  document.querySelector('#profile-modal .sheet').scrollTop=0;
}
function openProfile(jump){
  const p=pfLoad();
  const set=(id,v)=>{const e=document.getElementById(id);if(e&&v!=null&&v!=='')e.value=v;};
  set('pf-goal',p.goal);set('pf-age',p.age);set('pf-weight',p.weight);set('pf-height',p.height);set('pf-gender',p.gender);
  set('pf-level',p.level);set('pf-equip',p.equipment);set('pf-sleep',p.sleepQuality);set('pf-stress',p.stressLevel);
  set('pf-recovery',p.recoveryFeel);set('pf-activity',p.activityLevel);set('pf-freq',p.frequency);
  set('pf-smoking',p.smoking);set('pf-alcohol',p.alcohol);set('pf-nicotine',p.nicotine);set('pf-caffeine',p.caffeine);
  set('pf-meds',p.medications);set('pf-supps',p.supplements);set('pf-injuries',p.injuries);
  set('pf-surgeries',p.surgeries);set('pf-limits',p.limitations);set('pf-notes',p.notes);
  renderTrainingConstraints(ACTIVE_TRAINING_CONSTRAINTS);
  document.getElementById('cancel-sub').style.display=localStorage.getItem('apexToken')?'block':'none';
  wizGo(jump||0);
  document.getElementById('profile-modal').classList.add('on');
}
function saveProfile(){
  const v=id=>{const e=document.getElementById(id);return e?e.value.trim():'';};
  const goal=v('pf-goal'), injuries=v('pf-injuries'), meds=v('pf-meds'), supps=v('pf-supps'),
        surgeries=v('pf-surgeries'), limits=v('pf-limits'), notes=v('pf-notes');
  // Compose everything the coach must never violate into healthNotes (backend reads it)
  const hb=[]; if(injuries)hb.push((lang==='bg'?'Травми: ':'Injuries: ')+injuries);
  if(surgeries)hb.push((lang==='bg'?'Операции: ':'Surgeries: ')+surgeries);
  if(limits)hb.push((lang==='bg'?'Ограничения: ':'Limitations: ')+limits);
  if(meds)hb.push((lang==='bg'?'Лекарства: ':'Medications: ')+meds);
  if(notes)hb.push(notes);
  const p={
    goal, goalDetail:tr().wiz.opt.goal[goal]||goal, focus:T.en.wiz.opt.goal[goal]||goal,
    age:v('pf-age'),weight:v('pf-weight'),height:v('pf-height'),gender:v('pf-gender'),level:v('pf-level'),
    equipment:v('pf-equip'),sleepQuality:v('pf-sleep'),stressLevel:v('pf-stress'),recoveryFeel:v('pf-recovery'),
    activityLevel:v('pf-activity'),frequency:v('pf-freq'),smoking:v('pf-smoking'),alcohol:v('pf-alcohol'),
    nicotine:v('pf-nicotine'),caffeine:v('pf-caffeine'),medications:meds,supplements:supps,
    injuries,surgeries,limitations:limits,notes,language:lang,
    healthNotes:hb.join('. ')  // backend reads healthNotes for constraints
  };
  ownedStorageSet('apexProfile',JSON.stringify(p));
  accountSaveProfile(p);              // → account (server truth) when signed in
  const m=memLoad(); m.goals=p.goalDetail; memSave(m);
  document.getElementById('profile-modal').classList.remove('on');
  applyReadout(); toast(tr().saved); if(consultOn)resetGreeting();
  witness('modelChanged');   // fact: the coach's model of you changed
}
function cancelSub(){ doWithdraw(tr().sub.confirmCancel); }
function doWithdraw(confirmMsg){
  const token=localStorage.getItem('apexToken')||'';
  if(!token && !SESSION.authenticated){toast(tr().sub.free);return;}
  if(!confirm(confirmMsg))return;
  fetch('/withdraw',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({token,lang})})
    .then(r=>r.json()).then(d=>{toast(d.message||(lang==='bg'?'Заявката е приета.':'Request received.'));closePanel();loadSession();}).catch(()=>toast('—'));
}

/* ═══════════════════════════════════════════════════════════════════
   SLIDE-OUT MENU  (Hero stays minimal; everything lives here)
   ═══════════════════════════════════════════════════════════════════ */
const MENU=[
  {k:'home',ico:'🏠'},{k:'consult',ico:'💬'},{k:'workouts',ico:'💪'},{k:'nutrition',ico:'🍽'},
  {k:'progress',ico:'📈'},{k:'history',ico:'📝'},{k:'profile',ico:'👤'},{k:'feedback',ico:'⭐'},
  {sep:true},
  {k:'subscription',ico:'💳'},{k:'language',ico:'🌐',val:()=>lang.toUpperCase()},{k:'settings',ico:'⚙'},
  {k:'privacy',ico:'🔒'},{k:'about',ico:'ℹ️'}
];
function buildMenu(){
  const nav=document.getElementById('drawer-nav'); if(!nav)return; const m=tr().menu;
  let html=MENU.map(it=>it.sep?'<div class="drawer-sep"></div>':
    '<button class="mi" onclick="menuAction(\''+it.k+'\')"><span class="mi-ico">'+it.ico+'</span><span>'+m[it.k]+'</span>'+
    (it.val?'<span class="mi-val">'+it.val()+'</span>':'')+'</button>').join('');
  // Auth row reflects server-verified session state.
  html+='<div class="drawer-sep"></div>';
  if(SESSION.authenticated){
    html+='<button class="mi" onclick="menuAction(\'logout\')"><span class="mi-ico">🚪</span><span>'+tr().auth.signout+'</span>'+
      '<span class="mi-val" style="max-width:120px;overflow:hidden;text-overflow:ellipsis">'+esc(SESSION.email||'')+'</span></button>';
  } else {
    html+='<button class="mi accent" onclick="menuAction(\'login\')"><span class="mi-ico">✨</span><span>'+tr().auth.signin+'</span></button>';
  }
  nav.innerHTML=html;
}
function openMenu(){ buildMenu(); document.getElementById('drawer').classList.add('on'); document.getElementById('drawer-scrim').classList.add('on'); }
function closeMenu(){ document.getElementById('drawer').classList.remove('on'); document.getElementById('drawer-scrim').classList.remove('on'); }
function menuAction(k){
  closeMenu();
  const seed=tr().seed;
  switch(k){
    case 'home': exitConsult(); break;
    case 'consult': enterConsult(); break;
    case 'workouts': enterConsult(seed.workouts); break;
    case 'nutrition': enterConsult(seed.nutrition); break;
    case 'progress': enterConsult(seed.progress); break;
    case 'history': showHistory(); break;
    case 'profile': openProfile(0); break;
    case 'feedback': openFeedback(); break;
    case 'subscription': showSubscription(); break;
    case 'language': toggleLang(); break;
    case 'settings': showSettings(); break;
    case 'privacy': showPanel(tr().priv.title,'<div class="info-body">'+tr().priv.b+'</div>'); break;
    case 'about': showPanel(tr().about.title,'<div class="info-body">'+tr().about.b+'</div>'); break;
    case 'login': showLogin(); break;
    case 'logout': logout(); break;
  }
}

/* ═══════════════════════════════════════════════════════════════════
   PANELS  (subscription / history / settings / privacy / about)
   ═══════════════════════════════════════════════════════════════════ */
function showPanel(title,bodyHtml){
  document.getElementById('panel-title').textContent=title;
  document.getElementById('panel-desc').style.display='none';
  document.getElementById('panel-body').innerHTML=bodyHtml;
  document.getElementById('panel-close').textContent=(lang==='bg'?'Затвори':'Close');
  document.getElementById('panel-modal').classList.add('on');
}
function closePanel(){ document.getElementById('panel-modal').classList.remove('on'); }
function fmtDate(ts){ try{return new Date(ts*1000).toLocaleDateString(lang==='bg'?'bg-BG':'en-GB',{day:'numeric',month:'short',year:'numeric'});}catch(e){return '—';} }
async function showSubscription(){
  const s=tr().sub, a=tr().auth;
  // Always re-verify against the server before showing anything.
  await loadSession();
  const plan=SESSION.plan, status=SESSION.status, paid=isElite();
  const expiry=SESSION.current_period_end?Date.parse(SESSION.current_period_end)/1000:0;
  const badge=paid?'<span class="plan-badge '+plan+'">'+plan.toUpperCase()+'</span>':'<span class="plan-badge free">'+s.free+'</span>';
  let body='<div class="panel-row"><span class="pr-l">'+s.plan+'</span><span class="pr-v">'+badge+'</span></div>';
  if(paid){
    body+='<div class="panel-row"><span class="pr-l">'+s.statusL+'</span><span class="pr-v">'+(s.statuses[status]||status)+'</span></div>';
    body+='<div class="panel-row"><span class="pr-l">'+s.access+'</span><span class="pr-v">'+(expiry?fmtDate(expiry):s.none)+'</span></div>';
    body+='<div class="panel-row"><span class="pr-l">'+s.method+'</span><span class="pr-v">'+s.card+'</span></div>';
    body+='<div class="panel-row"><span class="pr-l">'+s.history+'</span><span class="pr-v">'+(expiry?fmtDate(expiry-30*86400):s.none)+' · '+(plan==='pro'?'€14.99':'€9.99')+'</span></div>';
    body+='<div class="eu-note">'+s.oneTime+'<br><br>'+s.eu+'</div>';
    if(status!=='cancelled') body+='<button class="cancel-btn" onclick="doWithdraw(tr().sub.confirmCancel)">'+s.cancel+'</button>';
  } else {
    body+='<div class="eu-note">'+s.freeDesc+'</div>';
    body+='<div class="panel-row"><span class="pr-l">'+s.upgradePro+'</span><span class="pr-v">'+s.comingSoon+'</span></div>';
    body+='<div class="panel-row"><span class="pr-l">'+s.upgradeCore+'</span><span class="pr-v">'+s.comingSoon+'</span></div>';
    if(!SESSION.authenticated) body+='<button class="mlink" onclick="showLogin()">'+a.haveAccount+'</button>';
  }
  showPanel(s.title,body);
}
function showHistory(){
  witness('historyOpened');   // fact: the shared past is being touched
  const h=tr().hist; let log=[];try{log=JSON.parse(ownedStorageGet('apexWorkoutLog')||'[]');}catch(e){}
  let body='<p class="sd" style="margin-bottom:16px">'+h.desc+'</p>';
  if(!log.length){ body+='<div class="hist-empty">'+h.empty+'</div>'; }
  else{
    body+=log.slice().reverse().map(s=>{
      const mu=inferMuscle((s.exercises&&s.exercises[0]&&s.exercises[0].name)||'');
      const nEx=(s.exercises||[]).length, nSets=(s.exercises||[]).reduce((a,e)=>a+(parseInt(e.sets)||0),0);
      return '<div class="hist-item"><div class="hist-ico">'+mu.e+'</div><div class="hist-b">'+
        '<div class="hist-t">'+esc(s.type||'training')+'</div>'+
        '<div class="hist-s">'+esc(s.date||'')+' · '+nEx+' '+h.exercises+' · '+nSets+' '+h.sets+'</div></div></div>';
    }).join('');
  }
  showPanel(h.title,body);
}
function showSettings(){
  const st=tr().settings;
  const vLabel=(lang==='bg'?'Глас на APEX':'APEX voice');
  const vOpts=VoiceReg.catalog.map(v=>'<option value="'+v.id+'"'+(v.id===VoiceReg.current()?' selected':'')+'>'+(v.label[lang]||v.label.en)+'</option>').join('');
  const body='<div class="panel-row"><span class="pr-l">'+st.lang+'</span><span class="pr-v">'+
    '<button class="pill" style="height:32px" onclick="toggleLang();closePanel();">'+lang.toUpperCase()+'</button></span></div>'+
    '<div class="panel-row"><span class="pr-l">'+vLabel+'</span><span class="pr-v">'+
      '<select id="voice-select" aria-label="'+vLabel+'" onchange="voicePick(this.value)" '+
      'style="height:40px;min-width:150px;background:var(--surface);color:var(--text);border:1px solid var(--border2);border-radius:10px;padding:0 10px;font-size:13px;font-weight:600;">'+
      vOpts+'</select></span></div>'+
    '<div class="panel-row"><span class="pr-l">'+st.theme+'</span><span class="pr-v">'+st.dark+'</span></div>'+
    '<div class="eu-note">'+st.resetDesc+'</div>'+
    '<button class="cancel-btn" onclick="resetLocal()">'+st.reset+'</button>';
  showPanel(st.title,body);
}
function voicePick(id){ VoiceReg.set(id); toast(lang==='bg'?'Гласът е запазен ✓':'Voice saved ✓'); }
function resetLocal(){
  const st=tr().settings; if(!confirm(st.resetConfirm))return;
  OWNED_STORAGE_KEYS.forEach(ownedStorageRemove);
  closePanel(); applyReadout(); toast(st.reset2); setTimeout(()=>openProfile(0),400);
}

/* ═══════════════════════════════════════════════════════════════════
   SESSION / IDENTITY — the server is the source of truth.
   Every load asks /auth/me. localStorage is only a UI cache.
   ═══════════════════════════════════════════════════════════════════ */
let SESSION={authenticated:false,plan:'free',status:'free',email:null,expiry:null};
let sendLocked=false;
async function verifyAccessToken(token){
  if(!token)return null;
  try{
    const r=await fetch('/verify-token',{method:'POST',headers:{'Content-Type':'application/json'},
      credentials:'same-origin',body:JSON.stringify({token})});
    if(!r.ok)return null;
    const access=await r.json();
    return access&&access.valid===true?access:null;
  }catch(e){return null;}
}
async function bootstrapAccessToken(){
  const q=new URLSearchParams(location.search);
  const urlToken=q.get('token');
  const storedToken=localStorage.getItem('apexToken')||'';
  const token=urlToken||storedToken;
  const access=await verifyAccessToken(token);
  if(access){
    localStorage.setItem('apexToken',token);
  }else if(!urlToken&&storedToken){
    localStorage.removeItem('apexToken');
  }
  if(urlToken!==null){
    q.delete('token');
    const search=q.toString();
    history.replaceState(null,'',location.pathname+(search?'?'+search:'')+location.hash);
  }
  return access;
}
async function loadSession(tokenAccess){
  if(tokenAccess===undefined){
    tokenAccess=await verifyAccessToken(localStorage.getItem('apexToken')||'');
  }
  try{
    const r=await fetch('/auth/me',{credentials:'same-origin'});
    SESSION=Object.assign({authenticated:false,plan:'free',status:'free'},await r.json());
  }catch(e){ SESSION={authenticated:false,plan:'free',status:'free',email:null}; }
  if(tokenAccess&&SESSION.plan==='free'){
    SESSION.plan=tokenAccess.plan==='pro'?'pro':'core';
    SESSION.status='active';
    SESSION.expiry=Number(tokenAccess.expiry)||0;
    SESSION.current_period_end=SESSION.expiry?new Date(SESSION.expiry*1000).toISOString():null;
    SESSION.isDev=tokenAccess.isDev===true;
  }
  if(SESSION.authenticated&&SESSION.email)activateDataOwner('account',SESSION.email.trim().toLowerCase());
  else activateDataOwner('anonymous',DATA_OWNER.kind==='anonymous'?DATA_OWNER.id:anonymousOwnerId());
  // If just signed in, pull the account's canonical data down (DB → cache) once.
  if(SESSION.authenticated){
    await syncFromAccount();
    const savedProfile=pfLoad();
    const savedLanguage=String((savedProfile.language||savedProfile.lang||'')).toLowerCase();
    if(savedLanguage==='bg'||savedLanguage==='en'){
      lang=savedLanguage;localStorage.setItem('apexLang',lang);applyLang();
    }
  }
  const restoredProfile=pfLoad();
  if(restoredProfile&&restoredProfile._medical_hold&&restoredProfile._medical_hold.status==='ACTIVE_MEDICAL_HOLD'){
    activateMedicalHold(false);
  }
  buildMenu();
  return SESSION;
}
function isElite(){ return SESSION.plan==='core'||SESSION.plan==='pro'; }
async function syncFromAccount(){
  // Read account truth without uploading anonymous/browser state. For fields
  // present in both places, the server copy is authoritative.
  try{
    const [profileResponse,historyResponse,conversationResponse]=await Promise.all([
      fetch('/api/profile',{credentials:'same-origin'}),
      fetch('/api/history',{credentials:'same-origin'}),
      fetch('/api/conversations?limit=60',{credentials:'same-origin'})
    ]);
    if(profileResponse.ok){
      const d=await profileResponse.json();
      renderTrainingConstraints(d&&Array.isArray(d.training_constraint_records)?d.training_constraint_records:(d&&Array.isArray(d.training_constraints)?d.training_constraints:[]));
      applyAthleteCoreProjection(d&&d.athlete_core);
      let local={};try{local=JSON.parse(ownedStorageGet('apexProfile')||'{}');}catch(e){}
      if(d&&d.profile&&typeof d.profile==='object'){
        const merged=Object.assign({},local,d.profile);
        if(Object.keys(merged).length)ownedStorageSet('apexProfile',JSON.stringify(merged));
      }
    }
    if(historyResponse.ok){
      const d=await historyResponse.json();
      if(d&&Array.isArray(d.workouts)){
        // Account timeline is newest-first; the browser cache is oldest-first.
        const serverLog=d.workouts.map(w=>({ts:Date.parse(w.occurred_at)||Date.now(),date:(w.occurred_at||'').slice(0,10),
          serverId:w.id,type:w.type,exercises:w.exercises||[],diff:w.difficulty,completion:w.completion})).reverse();
        let local=[];try{local=JSON.parse(ownedStorageGet('apexWorkoutLog')||'[]');}catch(e){}
        const key=w=>{
          const day=w.ts?new Date(w.ts).toISOString().slice(0,10):String(w.date||'');
          const exercises=(w.exercises||[]).map(e=>[e.name,e.sets,e.reps,e.weight||''].join(':')).join(',');
          return [day,w.type||'',w.completion||0,exercises].join('|');
        };
        const merged=Array.isArray(local)?local.slice():[];
        serverLog.forEach(serverWorkout=>{
          const match=merged.findIndex(localWorkout=>
            (serverWorkout.serverId&&localWorkout.serverId===serverWorkout.serverId)||
            (!localWorkout.serverId&&key(localWorkout)===key(serverWorkout)));
          if(match>=0)merged[match]=Object.assign({},merged[match],serverWorkout);
          else merged.push(serverWorkout);
        });
        merged.sort((a,b)=>(a.ts||0)-(b.ts||0));
        ownedStorageSet('apexWorkoutLog',JSON.stringify(merged.slice(-60)));
      }
    }
    if(conversationResponse.ok){
      const d=await conversationResponse.json();
      if(d&&Array.isArray(d.messages)&&d.messages.length){
        ownedStorageSet('apexHistory',JSON.stringify(d.messages.slice(-40)));
      }
    }
    applyReadout();
  }catch(e){ console.debug('sync failed',e); }
}
function applyAthleteCoreProjection(projection){
  try{return !!(core&&core.setServerProjection(projection));}catch(e){return false;}
}
async function refreshAthleteCoreProjection(){
  if(!SESSION.authenticated)return false;
  try{
    const response=await fetch('/api/profile',{credentials:'same-origin'});
    if(!response.ok)return false;
    const payload=await response.json();
    return applyAthleteCoreProjection(payload&&payload.athlete_core);
  }catch(e){return false;}
}
// Persist to the account whenever logged in. A successful AthleteModel-producing
// write refreshes the bounded Core projection once; there is no polling loop.
function accountSaveProfile(p){
  if(!SESSION.authenticated)return Promise.resolve(false);
  return fetch('/api/profile',{method:'PUT',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({profile:p})})
    .then(response=>response.ok?refreshAthleteCoreProjection():false).catch(()=>false);
}
function accountLogWorkout(s,workoutCompletion=null){
  if(!SESSION.authenticated)return Promise.resolve(false);
  const body={session:s};if(workoutCompletion)body.workout_completion=workoutCompletion;
  return fetch('/api/workout',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify(body)})
    .then(response=>response.ok?refreshAthleteCoreProjection():false).catch(()=>false);
}

/* ── Passwordless login (magic link) ── */
function showLogin(){
  const t=tr().auth;
  const body='<p class="sd">'+t.desc+'</p>'+
    '<div class="field"><input type="email" id="login-email" inputmode="email" autocomplete="email" placeholder="'+t.email+'"></div>'+
    '<button class="save" id="login-send" onclick="sendMagicLink()">'+t.send+'</button>';
  showPanel(t.title,body);
  setTimeout(()=>{const e=document.getElementById('login-email');if(e)e.focus();},150);
}
async function sendMagicLink(){
  const el=document.getElementById('login-email'); const email=el?el.value.trim():'';
  const t=tr().auth;
  if(!email||email.indexOf('@')<0){ el&&el.focus(); return; }
  const btn=document.getElementById('login-send'); if(btn){btn.disabled=true;btn.textContent='…';}
  try{
    const r=await fetch('/auth/request',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,lang})});
    if(r.ok){ document.getElementById('panel-body').innerHTML='<div class="info-body"><p>'+t.sent.replace('{email}',esc(email))+'</p></div>'; }
    else { const d=await r.json(); toast(d.error==='rate_limited'?t.rate:t.err); if(btn){btn.disabled=false;btn.textContent=t.send;} }
  }catch(e){ toast(t.err); if(btn){btn.disabled=false;btn.textContent=t.send;} }
}
async function logout(){
  try{ await fetch('/auth/logout',{method:'POST',credentials:'same-origin'}); }catch(e){}
  SESSION={authenticated:false,plan:'free',status:'free',email:null};
  localStorage.removeItem('apexToken'); rotateAnonymousOwner(); buildMenu(); closePanel(); toast(tr().auth.loggedOut);
}

/* ═══════════════════════════════════════════════════════════════════
   CONSULTATION
   ═══════════════════════════════════════════════════════════════════ */
let consultOn=false;
function enterConsult(seed){
  consultOn=true;
  witness('consultOpened');
  document.getElementById('consult').classList.add('on');
  const ov=document.getElementById('overview');
  ov.style.opacity='0';ov.style.transform='translateY(-30px) scale(.96)';ov.style.pointerEvents='none';
  document.getElementById('vignette').style.background='radial-gradient(ellipse 80% 70% at center 50%,transparent 16%,rgba(7,9,16,.8) 68%,rgba(7,9,16,.97) 100%)';
  if(!document.getElementById('feed').children.length)resetGreeting();
  if(seed){document.getElementById('user-in').value=seed;send();}
  else setTimeout(()=>document.getElementById('user-in').focus(),400);
}
function exitConsult(){
  consultOn=false;
  document.getElementById('consult').classList.remove('on');
  const ov=document.getElementById('overview');
  ov.style.opacity='1';ov.style.transform='none';ov.style.pointerEvents='auto';
  document.getElementById('vignette').style.background='';
  applyReadout();
}
function intentTrain(){ enterConsult(tr().todayWO); }
function resetGreeting(){
  const t=tr(),feed=document.getElementById('feed'),p=pfLoad();
  const goalTxt=p.goalDetail||(p.goal?tr().wiz.opt.goal[p.goal]:'');
  feed.innerHTML='<div class="greet"><h3><span class="grad">'+t.greetHi+'</span></h3>'+
    (goalTxt?'<p>'+t.greetSub+'</p><div class="goalrow">'+esc(goalTxt)+'</div>':'<p>'+t.greetSub+' —</p>')+
    '<div class="chips">'+t.chips.map((c,k)=>'<button class="chip" data-k="'+k+'" onclick="quickChip('+k+')">'+esc(c.label)+'</button>').join('')+'</div></div>';
}
function quickChip(k){
  const c=tr().chips[k]; if(!c)return;
  if(c.q){document.getElementById('user-in').value=c.q;send();}
  else{document.getElementById('user-in').focus();}   // "Ask APEX" → free question
}

/* ═══════════════════════════════════════════════════════════════════
   MARKDOWN RENDERER — full markdown → beautiful HTML
   ═══════════════════════════════════════════════════════════════════ */
function esc(s){return(s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function inlineMd(s){
  s=esc(s);
  s=s.replace(/`([^`]+)`/g,'<code>$1</code>');
  s=s.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
  s=s.replace(/(^|[^*])\*([^*]+)\*(?!\*)/g,'$1<em>$2</em>');
  s=s.replace(/__([^_]+)__/g,'<strong>$1</strong>');
  return s;
}
// Lightweight render used DURING streaming only — cheap, O(n), no table parsing
// or card building. Hides in-progress pipe-table rows so raw "|" never shows;
// the final renderMarkdown() call replaces this with Exercise/Nutrition cards.
function streamRender(s){
  return s.split('\n').filter(l=>!l.includes('|')).join('\n')
    .replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))
    .replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>')
    .replace(/\n{2,}/g,'<br><br>').replace(/\n/g,'<br>');
}
function parseTable(lines){
  const rows=lines.map(l=>l.trim().replace(/^\||\|$/g,'').split('|').map(c=>c.trim()));
  const header=rows[0]; const body=rows.slice(1).filter(r=>!/^[-:\s|]+$/.test(r.join('')));
  return{header,body};
}
function classifyTable(header){
  const h=header.join(' ').toLowerCase();
  if(/серии|повторения|sets|reps|упражнение|exercise/.test(h)&&/серии|sets|повторения|reps/.test(h))return'workout';
  if(/ккал|kcal|калории|protein|протеин|въглехидрати|carb|мазнини|fat/.test(h))return'nutrition';
  return'generic';
}
function pipeCells(line){return line.trim().replace(/^\||\|$/g,'').split('|').map(c=>c.trim());}
function isMealLabel(value){return /^(meal|breakfast|lunch|snack|dinner|хранене|закуска|обяд|междинно|вечеря)/i.test(value||'');}
function nutritionHeaderFor(columns){
  const base=columns===5?['Meal','Protein','Carbs','Fat','Kcal']:
    ['Meal','Quantity','Protein','Carbs','Fat','Kcal'];
  return base.slice(0,columns);
}
function separatorlessNutritionBlock(lines,start){
  const rows=[];let i=start;
  while(i<lines.length&&lines[i].includes('|')&&!collapsedNutritionBlock(lines[i])){rows.push(pipeCells(lines[i]));i++;}
  if(rows.length<2||rows[0].length<3||!rows.every(r=>r.length===rows[0].length))return null;
  const first=rows[0];
  const isHeader=classifyTable(first)==='nutrition';
  if(!isHeader&&!isMealLabel(first[0]))return null;
  return {header:isHeader?first:nutritionHeaderFor(first.length),body:isHeader?rows.slice(1):rows,next:i};
}
/* Collapsed single-line nutrition blocks — some LLM replies emit a whole meal
   (label + several foods) on ONE pipe line instead of one row per line, e.g.
   "| Lunch: | | | | Chicken | 200 g | 46 | 0 | 6 | 210 | | Rice | ... |".
   Detected safely: the line MUST start with a real meal label AND contain at
   least one numeric food row. Ordinary prose that merely contains "|" never
   matches (it has no numeric food rows), so it stays ordinary text. */
function collapsedMealLabel(v){
  return /^(breakfast|lunch|snack|dinner|закуска|обяд|следобедна|вечеря|допълнителни|междинно)/i.test((v||'').trim());
}
function collapsedNutritionBlock(line){
  if(!line||line.indexOf('|')<0) return null;
  const cells=pipeCells(line);
  if(cells.length<6) return null;                       // too small to be a collapsed meal
  const label=cells[0].replace(/[:：].*$/,'').trim();   // "Lunch:" → "Lunch"
  if(!collapsedMealLabel(label)) return null;
  const isNum=c=>/^\d+([.,]\d+)?$/.test(c);                                                        // macro / kcal
  const isServing=c=>/\d/.test(c)&&/^\d+([.,]\d+)?\s*(g|г|гр|ml|мл|kg|кг|oz|бр|pcs|порц\.?)$/i.test(c);
  const rest=cells.slice(1).filter(c=>c!=='');
  const body=[[label,'','','','']];                     // meal section row (name only)
  let k=0, foods=0;
  while(k<rest.length){
    if(isNum(rest[k])||isServing(rest[k])){ k++; continue; }     // stray value with no name → skip
    const name=rest[k]; k++;
    const vals=[];
    while(k<rest.length && (isServing(rest[k])||isNum(rest[k])) && vals.length<5){ vals.push(rest[k]); k++; }
    if(vals.length<4) continue;                          // need P,C,F,kcal at least → not a food row
    const m=vals.slice(vals.length-4);                   // last four = P,C,F,kcal (drop any leading qty)
    body.push([name, m[0], m[1], m[2], m[3]]);
    foods++;
  }
  if(foods<1) return null;                               // no real food row → leave as ordinary text
  return { header:['Meal','Protein','Carbs','Fat','Kcal'], body };
}
/* ═══════════════════════════════════════════════════════════════════════════
   NUTRITION V4 — format-tolerant scanner. One nutrition plan may mix markdown
   tables, separator-less tables, collapsed single-line meals, bold/plain meal
   headers, free-text foods and totals — in any order, BG or EN. We scan the
   whole region into ONE ordered model (meals → foods → total). It never leaves
   a raw pipe: a valid food row always becomes a card; a malformed row is dropped
   WITHOUT ending the meal; the region only stops at the next non-nutrition prose.
   ═══════════════════════════════════════════════════════════════════════════ */
function mdClean(v){return (v||'').replace(/\*\*|__|`/g,'').replace(/^\s*#{1,4}\s+/,'').replace(/^\s*[-*•]\s+/,'').trim();}
const MEAL_RE=/^(breakfast|lunch|dinner|snacks?|morning snack|afternoon snack|evening snack|pre[-\s]?workout|post[-\s]?workout|\u0437\u0430\u043a\u0443\u0441\u043a\u0430|\u043e\u0431\u044f\u0434|\u0432\u0435\u0447\u0435\u0440\u044f|\u0441\u043b\u0435\u0434\u043e\u0431\u0435\u0434\u043d\u0430(\s+\u0437\u0430\u043a\u0443\u0441\u043a\u0430)?|\u043c\u0435\u0436\u0434\u0438\u043d\u043d\u0430(\s+\u0437\u0430\u043a\u0443\u0441\u043a\u0430)?|\u043c\u0435\u0436\u0434\u0438\u043d\u043d\u043e(\s+\u0445\u0440\u0430\u043d\u0435\u043d\u0435)?|\u0434\u043e\u043f\u044a\u043b\u043d\u0438\u0442\u0435\u043b\u043d\u0438(\s+\u0437\u0430\u043a\u0443\u0441\u043a\w*)?|\u0441\u043d\u0430\u043a)$/i;
function mealHeaderName(line){
  let s=mdClean(line).replace(/\(.*?\)/g,'').replace(/[:：].*$/,'').trim();
  return MEAL_RE.test(s)?s.replace(/\s+/g,' '):'';
}
function isMealCell(v){ return MEAL_RE.test(mdClean(v).replace(/[:：]\s*$/,'').trim()); }
const _isPureNum=c=>/^\d+([.,]\d+)?$/.test((c||'').trim());
const _isServingValue=c=>{c=(c||'').trim();return /\d/.test(c)&&/^\d+([.,]\d+)?\s*(g|\u0433|\u0433\u0440|kg|\u043a\u0433|ml|\u043c\u043b|oz|\u0431\u0440|pcs|\u043f\u043e\u0440\u0446\.?|slices?|cup|\u0447\u0430\u0448\u0430|tbsp|tsp|eggs?|\u044f\u0439\u0446\w*)\.?$/i.test(c);};
const _isTotal=s=>/[\s(|:](total|totals|\u043e\u0431\u0449\u043e|\u0441\u0443\u043c\u0430\u0440\u043d\u043e|\u0441\u0443\u043c\u0430|\u0438\u0442\u043e\u0433\u043e|daily\s*total|\u0434\u043d\u0435\u0432\u043d\w*)/i.test(' '+mdClean(s));
function _nums(s){return (String(s).match(/\d+(?:[.,]\d+)?/g)||[]);}
const BG_NUTRITION_FIELDS=Object.freeze({
  '\u0445\u0440\u0430\u043d\u0435\u043d\u0435':'name',
  '\u043c\u0435\u043d\u044e':'title',
  'id \u043d\u0430 \u0445\u0440\u0430\u043d\u0435\u043d\u0435':'mealId',
  '\u0445\u0440\u0430\u043d\u0430':'food','\u0445\u0440\u0430\u043d\u0438':'food',
  '\u044f\u0441\u0442\u0438\u0435':'food','\u043f\u0440\u043e\u0434\u0443\u043a\u0442':'food','\u0438\u043c\u0435':'food',
  '\u043a\u043e\u043b\u0438\u0447\u0435\u0441\u0442\u0432\u043e':'qty','\u043f\u043e\u0440\u0446\u0438\u044f':'qty','\u0433\u0440\u0430\u043c\u0430\u0436':'qty',
  '\u043f\u0440\u043e\u0442\u0435\u0438\u043d':'p','\u0431\u0435\u043b\u0442\u044a\u0447\u0438\u043d\u0438':'p',
  '\u0432\u044a\u0433\u043b\u0435\u0445\u0438\u0434\u0440\u0430\u0442\u0438':'c','\u043c\u0430\u0437\u043d\u0438\u043d\u0438':'f',
  '\u043a\u043a\u0430\u043b':'k','\u043a\u0430\u043b\u043e\u0440\u0438\u0438':'k',
  '\u0437\u0430\u0449\u043e \u0442\u043e\u0432\u0430 \u0445\u0440\u0430\u043d\u0435\u043d\u0435':'reason','\u043f\u0440\u0438\u0447\u0438\u043d\u0430':'reason',
  '\u0440\u0435\u0446\u0435\u043f\u0442\u0430':'recipe'
});
function nutritionField(v){
  const h=mdClean(v).toLowerCase().replace(/\s*\([^)]*\)\s*$/,'').trim();
  if(BG_NUTRITION_FIELDS[h])return BG_NUTRITION_FIELDS[h];
  if(/^(meal)$/.test(h))return'name';
  if(/^(menu|menu title)$/.test(h))return'title';
  if(/^(meal id)$/.test(h))return'mealId';
  if(/^(food|dish|product|name)$/.test(h))return'food';
  if(/^(quantity|qty|amount|serving|serving size|portion|grams?)$/.test(h))return'qty';
  if(/^(protein)$/.test(h))return'p';
  if(/^(carbs?|carbohydrates)$/.test(h))return'c';
  if(/^(fat|fats)$/.test(h))return'f';
  if(/^(kcal|calories|calorie)$/.test(h))return'k';
  if(/^(why this meal|meal reason|reason)$/.test(h))return'reason';
  if(/^(recipe)$/.test(h))return'recipe';
  return null;
}
function nutritionSchema(cells){
  const schema={name:-1,title:-1,mealId:-1,food:-1,qty:-1,p:-1,c:-1,f:-1,k:-1,reason:-1,recipe:-1,width:(cells||[]).length};
  (cells||[]).forEach((cell,index)=>{const field=nutritionField(cell);if(field&&schema[field]===-1)schema[field]=index;});
  return (schema.name>=0||schema.food>=0)&&[schema.p,schema.c,schema.f,schema.k].filter(index=>index>=0).length>=3?schema:null;
}
function isNutritionTableHeader(cells){
  const h=(cells||[]).join(' ').toLowerCase();
  if(/серии|sets|повторения|reps|упражнение|exercise/.test(h)) return false;
  return !!nutritionSchema(cells);
}
/* one pipe/collapsed row → ordered items (meal titles / foods / totals) */
function itemFromSchema(cells,schema){
  const value=field=>schema[field]>=0?mdClean(cells[schema[field]]||''):'';
  const meal=value('name'); const food=value('food'); const name=food||meal; if(!name)return [];
  const item={title:value('title'),mealId:value('mealId'),p:value('p'),c:value('c'),f:value('f'),k:value('k'),reason:value('reason'),recipe:value('recipe')};
  if(_isTotal(meal||food))return[{type:'total',...item}];
  if(isMealCell(meal)&&!food&&!item.p&&!item.c&&!item.f&&!item.k)return[{type:'meal',name:mealHeaderName(meal)||meal}];
  const items=[];
  if(isMealCell(meal)&&food)items.push({type:'meal',name:mealHeaderName(meal)||meal});
  items.push({type:'food',name,qty:value('qty'),mealSummary:isMealCell(meal)&&!food,...item});
  return items;
}
function itemsFromCells(cells,schema=null){
  cells=(cells||[]).map(mdClean);
  if(schema&&cells.length===schema.width)return itemFromSchema(cells,schema);
  const items=[]; let k=0;
  while(k<cells.length){
    const c=cells[k];
    if(!c||_isPureNum(c)||_isServingValue(c)){k++;continue;}
    const name=c; k++;
    while(k<cells.length && cells[k]==='') k++;              // skip padding empties, e.g. "Total | | | 13 | 1 | 11 | 155"
    const vals=[];
    while(k<cells.length && (_isPureNum(cells[k])||_isServingValue(cells[k]))){ vals.push(cells[k]); k++; }
    const nums=vals.filter(_isPureNum);
    if(nums.length>=3){
      const qty=vals.length===5&&_isServingValue(vals[0])?vals[0]:'';
      const m=nums.slice(-4);
      if(_isTotal(name)) items.push({type:'total',p:m[0]||'',c:m[1]||'',f:m[2]||'',k:m.length>=4?m[3]:''});
      else items.push({type:'food',name,qty,mealSummary:isMealCell(name),p:m[0]||'',c:m[1]||'',f:m[2]||'',k:m.length>=4?m[3]:''});
    } else if(isMealCell(name)){
      items.push({type:'meal',name:mealHeaderName(name)||mdClean(name).replace(/[:：]\s*$/,'')});
    }
  }
  return items;
}
/* a free-text food line, e.g. "Oatmeal — 80 g, 12 g protein, 54 carbs, 7 fat, 320 kcal" */
function foodFromText(t){
  if(t.includes('|')) return null;
  const s=mdClean(t); const nums=_nums(s);
  if(nums.length<3 || !/(g\b|г\b|kcal|ккал|cal\b|калори)/i.test(s)) return null;
  if(_isTotal(s)){ const m=nums.slice(-4); return {type:'total',p:m[0]||'',c:m[1]||'',f:m[2]||'',k:m.length>=4?m[3]:''}; }
  const idx=s.search(/\d/); if(idx<=0) return null;
  let name=s.slice(0,idx).replace(/[-—:,>·\s]+$/,'').trim();
  if(!name||name.length>48||isMealCell(name)) return null;
  const m=nums.slice(-4);
  return {type:'food',name,qty:'',p:m[0]||'',c:m[1]||'',f:m[2]||'',k:m.length>=4?m[3]:''};
}
function _nutritionLine(t){
  if(!t) return false;
  if(mealHeaderName(t)) return true;
  if(_isTotal(t)&&_nums(t).length>=3) return true;
  if(t.includes('|')){ const c=pipeCells(t); return isNutritionTableHeader(c)||itemsFromCells(c).some(x=>x.type!=='meal'); }
  return !!foodFromText(t);
}
function nutritionStarts(lines,i){
  const t=(lines[i]||'').trim(); if(!t) return false;
  if(mealHeaderName(t)) return true;
  if(t.includes('|')){
    const cells=pipeCells(t);
    if(isNutritionTableHeader(cells)) return true;
    if(/\b(sets?|reps?|серии|повторения)\b/i.test(t)) return false;
    if(itemsFromCells(cells).some(x=>x.type==='food'||x.type==='total')) return true;
  }
  return false;
}
function nutritionScan(lines,start){
  if(!nutritionStarts(lines,start)) return null;
  const model=[]; let i=start, schema=null;
  while(i<lines.length){
    const t=(lines[i]||'').trim();
    if(t===''){ let j=i+1; while(j<lines.length&&lines[j].trim()==='')j++;
      if(j>=lines.length||!_nutritionLine(lines[j].trim())) break; i=j; continue; }
    if(t.includes('-')&&/^[\s|:\-]+$/.test(t)){ i++; continue; }                 // markdown separator row
    const mh=mealHeaderName(t);
    if(mh){ model.push({type:'meal',name:mh}); schema=null; i++; continue; }
    if(!t.includes('|')&&_isTotal(t)&&_nums(t).length>=3){ const m=_nums(t).slice(-4);
      model.push({type:'total',p:m[0]||'',c:m[1]||'',f:m[2]||'',k:m.length>=4?m[3]:''}); i++; continue; }
    if(t.includes('|')){
      const cells=pipeCells(t);
      const rowSchema=nutritionSchema(cells);
      if(rowSchema){ schema=rowSchema; i++; continue; }                          // column header → retain semantics
      const its=itemsFromCells(cells,schema);
      if(its.length){ its.forEach(x=>model.push(x)); i++; continue; }
      if(model.length){ i++; continue; }                                         // malformed pipe row → drop (no raw pipes)
      break;
    }
    const ft=foodFromText(t);
    if(ft){ model.push(ft); i++; continue; }
    break;                                                                       // prose boundary → region ends
  }
  if(!model.some(x=>x.type==='food'||x.type==='total')) return null;
  return { html: renderNutritionModel(model), next:i };
}
function renderNutritionModel(model){
  const L=(lang==='bg')
    ?{p:'Белтъчини',c:'Въглехидрати',f:'Мазнини',k:'Калории',u:'г',cap:'Хранителна стойност'}
    :{p:'Protein',c:'Carbs',f:'Fat',k:'Calories',u:'g',cap:'Nutrition value'};
  const clip=v=>{
    const raw=(v||'').toString().replace(/[^\d.,-]/g,'').replace(',','.');
    const value=Number(raw);
    if(!Number.isFinite(value))return '';
    return String(Math.round(value));
  };
  const recipePayload=token=>{
    if(!token||!token.startsWith('recipe:'))return null;
    try{
      const base64=token.slice(7).replace(/-/g,'+').replace(/_/g,'/');
      const bytes=Uint8Array.from(atob(base64),c=>c.charCodeAt(0));
      const recipe=JSON.parse(new TextDecoder().decode(bytes));
      if(!recipe||typeof recipe.meal_id!=='string'||typeof recipe.title!=='string'||!Array.isArray(recipe.steps)||!Array.isArray(recipe.tips)||!Array.isArray(recipe.substitutions))return null;
      if(recipe.preparation_type!==undefined&&recipe.preparation_type!=='recipe'&&recipe.preparation_type!=='assembly')return null;
      return recipe;
    }catch(_){return null;}
  };
  const recipeCard=recipe=>{
    if(!recipe)return '';
    try{
      const labels=lang==='bg'
        ?{recipe:'Рецепта',assembly:'Как да го приготвиш',steps:'Стъпки за приготвяне',tips:'Съвети за здравословно готвене',storage:'Съхранение',subs:'Замени',minutes:'мин',prep:'Подходяща за meal prep'}
        :{recipe:'Recipe',assembly:'How to prepare',steps:'Preparation steps',tips:'Healthy cooking tips',storage:'Storage',subs:'Substitutions',minutes:'min',prep:'Suitable for meal prep'};
      const list=items=>'<ul>'+items.map(item=>'<li>'+esc(String(item))+'</li>').join('')+'</ul>';
      if(recipe.preparation_type==='assembly'){
        return '<details class="nm-recipe" open><summary>'+esc(labels.assembly)+'</summary><p>'+esc(recipe.steps.map(step=>String(step)).join(' '))+'</p></details>';
      }
      const title='<div class="nm-recipe-title">'+esc(labels.recipe+': '+recipe.title)+'</div>';
      const meta='<div class="nm-recipe-meta">'+esc(String(recipe.difficulty||'')+' · '+String(recipe.minutes||'')+' '+labels.minutes+(recipe.meal_prep?' · '+labels.prep:''))+'</div>';
      return title+meta+
        '<details class="nm-recipe"><summary>'+esc(labels.steps)+'</summary><ol>'+recipe.steps.map(step=>'<li>'+esc(String(step))+'</li>').join('')+'</ol></details>'+
        (recipe.tips.length?'<details class="nm-recipe"><summary>'+esc(labels.tips)+'</summary>'+list(recipe.tips)+'</details>':'')+
        (recipe.storage?'<details class="nm-recipe"><summary>'+esc(labels.storage)+'</summary><p>'+esc(String(recipe.storage))+'</p></details>':'')+
        (recipe.substitutions.length?'<details class="nm-recipe"><summary>'+esc(labels.subs)+'</summary>'+list(recipe.substitutions)+'</details>':'');
    }catch(_){return '';}
  };
  const macroBlock=it=>{
    const b=[];
    if(clip(it.p))b.push('<span class="macro p"><span class="mname">'+L.p+'</span><b>'+clip(it.p)+' '+L.u+'</b></span>');
    if(clip(it.c))b.push('<span class="macro c"><span class="mname">'+L.c+'</span><b>'+clip(it.c)+' '+L.u+'</b></span>');
    if(clip(it.f))b.push('<span class="macro f"><span class="mname">'+L.f+'</span><b>'+clip(it.f)+' '+L.u+'</b></span>');
    if(clip(it.k))b.push('<span class="macro k"><span class="mname">'+L.k+'</span><b>'+clip(it.k)+' kcal</b></span>');
    return b.length?'<div class="macros-cap">'+L.cap+'</div><div class="macros">'+b.join('')+'</div>':'';
  };
  const mealIcon=foods=>{
    const names=(foods||[]).map(food=>mdClean(food.name).toLowerCase()).join(' ');
    const icon=path=>'<span class="nm-meal-icon" aria-hidden="true"><svg viewBox="0 0 32 32">'+path+'</svg></span>';
    if(/whey|protein powder|суроват|протеин на прах/.test(names))return icon('<path d="M11 5h10M12 5l1 5h6l1-5M11 10h10l-1 16H12l-1-16ZM13 17h6"/>');
    if(/oats|oatmeal|овес|yogurt|мляко|извара/.test(names))return icon('<path d="M6 14h20M8 14c1 8 4 12 8 12s7-4 8-12M10 9c2-2 10-2 12 0"/>');
    if(/apple|banana|fruit|ябъл|банан|fruit|nuts|ядки|almond|бадем/.test(names))return icon('<path d="M16 12c-5-4-10 0-9 7 1 6 5 9 9 9s8-3 9-9c1-7-4-11-9-7ZM16 12c0-4 2-6 5-7M19 6c3-1 5 0 6 2"/>');
    return icon('<path d="M5 17h22M7 17c1 7 5 10 9 10s8-3 9-10M10 12h12M16 12V8M12 8h8"/>');
  };
  const numeric=v=>{const n=Number(String(v||'').replace(/[^\d.,-]/g,'').replace(',','.'));return Number.isFinite(n)?n:0;};
  const mealTotals=foods=>({p:foods.reduce((sum,food)=>sum+numeric(food.p),0),c:foods.reduce((sum,food)=>sum+numeric(food.c),0),f:foods.reduce((sum,food)=>sum+numeric(food.f),0),k:foods.reduce((sum,food)=>sum+numeric(food.k),0)});
  const mealCard=group=>{
    const foods=group.foods;
    const rows=group.summary?'':foods.map(food=>'<div class="nm-food-row"><span class="nm-food-name">'+esc(mdClean(food.name))+'</span>'+(food.qty?'<span class="nm-food-qty">'+esc(mdClean(food.qty))+'</span>':'')+'</div>').join('');
    const reason=group.reason?'<div class="nm-reason">'+esc(mdClean(group.reason))+'</div>':'';
    const menuTitle=mdClean(group.menuTitle);
    const showMenuTitle=menuTitle&&menuTitle.toLocaleLowerCase()!==mdClean(group.name).toLocaleLowerCase();
    return '<div class="nutri-meal nutri-title"><div class="nm-head"><span class="nm-title-main">'+mealIcon(foods)+'<span class="nm-name">'+esc(group.name)+'</span></span></div>'+
      (showMenuTitle?'<div class="nm-menu-title">'+esc(menuTitle)+'</div>':'')+
      (rows?'<div class="nm-foods">'+rows+'</div>':'')+macroBlock(mealTotals(foods))+reason+recipeCard(group.recipe)+'</div>';
  };
  const groups=[]; let active=null; let total=null;
  for(const it of model){
    if(it.type==='total'){ if(clip(it.p)||clip(it.c)||clip(it.f)||clip(it.k)) total=it; continue; }
    if(it.type==='meal'){
      const name=mdClean(it.name); if(!name) continue;
      active={name,menuTitle:'',mealId:'',foods:[],reason:'',recipe:null,canOwnRecipe:true}; groups.push(active); continue;
    }
    const name=mdClean(it.name); if(!name) continue;
    // Legacy meal-only tables have no separate Food column. Keep their one row
    // as a self-contained meal, but never let a recipe token float onto it.
    if(!active||it.mealSummary) { active={name,menuTitle:'',mealId:'',foods:[],reason:'',recipe:null,canOwnRecipe:false,summary:!!it.mealSummary}; groups.push(active); }
    const key=name.toLowerCase()+'~'+clip(it.p)+'~'+clip(it.c)+'~'+clip(it.f)+'~'+clip(it.k);
    if(active.foods.some(food=>food._key===key)) continue;
    active.foods.push({...it,_key:key});
    const mealId=mdClean(it.mealId);
    if(mealId&&(!active.mealId||active.mealId===mealId)) active.mealId=mealId;
    if(!active.menuTitle&&it.title) active.menuTitle=mdClean(it.title);
    if(!active.reason&&it.reason) active.reason=it.reason;
    if(active.canOwnRecipe&&!active.recipe&&it.recipe){
      const candidate=recipePayload(it.recipe);
      if(candidate&&candidate.meal_id===active.mealId) active.recipe=candidate;
    }
  }
  let html='<div class="nutri">';
  groups.forEach(group=>{html+=mealCard(group);});
  if(total){
    html+='<div class="nutri-total"><div class="nt-label">'+tr().nutriTotal+'</div><div class="nt-grid">'+
      (clip(total.p)?'<div class="nt-stat p"><div class="v">'+clip(total.p)+' '+L.u+'</div><div class="l">'+L.p+'</div></div>':'')+
      (clip(total.c)?'<div class="nt-stat c"><div class="v">'+clip(total.c)+' '+L.u+'</div><div class="l">'+L.c+'</div></div>':'')+
      (clip(total.f)?'<div class="nt-stat f"><div class="v">'+clip(total.f)+' '+L.u+'</div><div class="l">'+L.f+'</div></div>':'')+
      (clip(total.k)?'<div class="nt-stat k"><div class="v">'+clip(total.k)+'</div><div class="l">'+L.k+'</div></div>':'')+
      '</div></div>';
  }
  return html+'</div>';
}
function renderMarkdown(raw){
  const lines=raw.replace(/\r/g,'').split('\n');
  let html='',i=0,inCode=false,codeBuf=[];
  const flushP=[];
  while(i<lines.length){
    let ln=lines[i];
    // fenced code
    if(/^```/.test(ln.trim())){
      if(!inCode){inCode=true;codeBuf=[];}
      else{inCode=false;html+='<pre><code>'+esc(codeBuf.join('\n'))+'</code></pre>';}
      i++;continue;
    }
    if(inCode){codeBuf.push(ln);i++;continue;}
    const t=ln.trim();
    // NUTRITION V4 — greedy, format-tolerant nutrition region (mixed formats → one coherent UI)
    const nutriV4=nutritionStarts(lines,i)?nutritionScan(lines,i):null;
    if(nutriV4){html+=nutriV4.html;i=nutriV4.next;continue;}
    // table block (workout / generic; nutrition tables are handled by the scanner above)
    if(t.includes('|')&&i+1<lines.length&&/^[\s|:\-]+$/.test(lines[i+1].trim())&&lines[i+1].includes('-')){
      const tb=[]; while(i<lines.length&&lines[i].includes('|')){tb.push(lines[i]);i++;}
      const{header,body}=parseTable(tb); const kind=classifyTable(header);
      if(kind==='nutrition')html+=renderNutrition(header,body);
      else if(kind==='workout')html+=renderWorkout(header,body);
      else html+=renderGenericTable(header,body);
      continue;
    }
    // heading
    let mh=t.match(/^(#{1,4})\s+(.*)$/);
    if(mh){html+='<h'+mh[1].length+'>'+inlineMd(mh[2])+'</h'+mh[1].length+'>';i++;continue;}
    // blockquote
    if(/^>\s?/.test(t)){const q=[];while(i<lines.length&&/^>\s?/.test(lines[i].trim())){q.push(lines[i].trim().replace(/^>\s?/,''));i++;}html+='<blockquote>'+inlineMd(q.join(' '))+'</blockquote>';continue;}
    // horizontal rule
    if(/^(-{3,}|\*{3,}|_{3,})$/.test(t)){html+='<hr>';i++;continue;}
    // unordered list
    if(/^[-*•]\s+/.test(t)){const items=[];while(i<lines.length&&/^[-*•]\s+/.test(lines[i].trim())){items.push(lines[i].trim().replace(/^[-*•]\s+/,''));i++;}html+='<ul>'+items.map(x=>'<li>'+inlineMd(x)+'</li>').join('')+'</ul>';continue;}
    // ordered list
    if(/^\d+[.)]\s+/.test(t)){const items=[];while(i<lines.length&&/^\d+[.)]\s+/.test(lines[i].trim())){items.push(lines[i].trim().replace(/^\d+[.)]\s+/,''));i++;}html+='<ol>'+items.map(x=>'<li>'+inlineMd(x)+'</li>').join('')+'</ol>';continue;}
    // elite status footer
    if(/ELITE STATUS/i.test(t)){const buf=[];while(i<lines.length&&lines[i].trim()){buf.push(lines[i].trim());i++;}html+='<div class="elite-status">'+buf.map(x=>inlineMd(x.replace(/\*\*/g,''))).join('<br>').replace(/ELITE STATUS: ACTIVE/i,'<b>ELITE STATUS: ACTIVE</b>')+'</div>';continue;}
    // paragraph
    if(t){const buf=[];while(i<lines.length&&lines[i].trim()&&!/^(#{1,4}\s|[-*•]\s|\d+[.)]\s|>\s?|```)/.test(lines[i].trim())&&!(lines[i].includes('|')&&i+1<lines.length&&/^[\s|:\-]+$/.test((lines[i+1]||'').trim()))){buf.push(lines[i].trim());i++;}html+='<p>'+inlineMd(buf.join(' '))+'</p>';continue;}
    i++;
  }
  if(inCode&&codeBuf.length)html+='<pre><code>'+esc(codeBuf.join('\n'))+'</code></pre>';
  return html;
}
function renderGenericTable(header,body){
  let h='<div class="table-wrap"><table><thead><tr>'+header.map(c=>'<th>'+inlineMd(c)+'</th>').join('')+'</tr></thead><tbody>';
  h+=body.map(r=>'<tr>'+r.map(c=>'<td>'+inlineMd(c)+'</td>').join('')+'</tr>').join('');
  return h+'</tbody></table></div>';
}

/* ── NUTRITION RENDERER — meal cards + macro badges + totals ── */
function colIndex(header,res){return header.findIndex(c=>res.some(r=>r.test(c.toLowerCase())));}
/* Adapter: an already-parsed table (header+body) → the V4 model → cards.
   Column order is positional (name/food … P, C, F, kcal), same as the scanner. */
function renderNutrition(header,body){
  const model=[];
  const schema=nutritionSchema(header);
  (body||[]).forEach(r=>{ itemsFromCells(r,schema).forEach(x=>model.push(x)); });
  return renderNutritionModel(model);
}

/* ── WORKOUT RENDERER — exercise cards + start button ── */
const MUSCLE_MAP=[
  {re:/клек|squat|присед|лег прес|leg press|lunge|напад/i,m:'legs',e:'🦵',ic:'#38E0FF'},
  {re:/лицев|push.?up|пресов|bench|преса|гръд|chest|fly|разперв/i,m:'chest',e:'💪',ic:'#FF6A3C'},
  {re:/гръб|back|row|гребане|lat|набиран|pull.?up|pull.?down|тяга|deadlift|мъртва/i,m:'back',e:'🔙',ic:'#B6FF3C'},
  {re:/рамо|shoulder|press|overhead|латерал|raise|разтвар/i,m:'shoulders',e:'🏋️',ic:'#FFB13C'},
  {re:/бицепс|biceps|curl|сгъван/i,m:'arms',e:'💪',ic:'#F5212D'},
  {re:/трицепс|triceps|extension|разгъв/i,m:'arms',e:'💪',ic:'#F5212D'},
  {re:/корем|abs|core|планк|plank|crunch|коремн/i,m:'core',e:'🔥',ic:'#FFB13C'},
  {re:/кардио|cardio|run|бягане|cycle|колоездене|jump|скок/i,m:'cardio',e:'⚡',ic:'#38E0FF'}
];
const MUSCLE_LABELS={
  legs:{bg:'\u043a\u0440\u0430\u043a\u0430',en:'legs'}, chest:{bg:'\u0433\u044a\u0440\u0434\u0438',en:'chest'},
  back:{bg:'\u0433\u0440\u044a\u0431',en:'back'}, shoulders:{bg:'\u0440\u0430\u043c\u0435\u043d\u0435',en:'shoulders'},
  arms:{bg:'\u0440\u044a\u0446\u0435',en:'arms'}, core:{bg:'\u043a\u043e\u0440\u0435\u043c',en:'core'},
  cardio:{bg:'\u043a\u0430\u0440\u0434\u0438\u043e',en:'cardio'}
};
function inferMuscle(name){for(const x of MUSCLE_MAP)if(x.re.test(name)){const labels=MUSCLE_LABELS[x.m]||{};return{...x,m:labels[lang==='bg'?'bg':'en']||x.m};}return{m:lang==='bg'?'\u0446\u044f\u043b\u043e \u0442\u044f\u043b\u043e':'full body',e:'⚡',ic:'#8B93A7'};}
function inferDiff(reps,name){
  const r=parseInt((reps||'').replace(/[^\d]/g,''))||10;
  if(/начинаещ|beginner|лек|light/i.test(name))return'easy';
  if(r>=15)return'easy'; if(r<=6)return'hard'; return'med';
}
function localizedTime(value){
  const raw=String(value||'').trim();
  if(lang==='bg')return raw.replace(/\bseconds?\b|\bsecs?\b/ig,'сек').replace(/\bminutes?\b|\bmins?\b/ig,'минути');
  return raw.replace(/секунди?/ig,'seconds').replace(/минути?/ig,'minutes');
}
function workoutPrescription(exercise){
  const canonical=exercise.instruction_record||(window.ApexExerciseInstructions&&window.ApexExerciseInstructions.find(exercise.name));
  if(canonical){
    const type=canonical.prescription_type,raw=String(exercise.reps||'').trim();
    if(type==='duration'||type==='duration_per_side'){
      const hasUnit=/\b(?:sec(?:ond)?s?|minutes?|mins?)\b|\u0441\u0435\u043a|\u0441\u0435\u043a\u0443\u043d|\u043c\u0438\u043d/i.test(raw);
      return{type,value:(raw&&hasUnit)?localizedTime(raw):'20–40 '+(lang==='bg'?'секунди':'seconds')};
    }
    return{type,value:raw.replace(/\b(?:reps?|per side)\b|\u043f\u043e\u0432\u0442(?:\.|\u043e\u0440\u0435\u043d\u0438\u044f)?|\u043d\u0430 \u0441\u0442\u0440\u0430\u043d\u0430/ig,'').trim()||'8–12'};
  }
  const record=window.ApexExerciseInstructions&&window.ApexExerciseInstructions.find(exercise.name);
  if(record&&record.prescription_type==='duration'){
    const raw=String(exercise.reps||'');
    const valid=/\bsec(?:ond)?s?\b|\bseconds?\b|сек\b|секун/i.test(raw);
    return{type:'duration',value:valid?raw.replace(/\bsec(?:ond)?s?\b|\bseconds?\b|сек\.?|секунди?/ig,'').trim()||'20–40':'20–40'};
  }
  return{type:'repetitions',value:String(exercise.reps||'8–12')};
}
function parseExercises(header,body){
  const iName=0;
  const iSets=colIndex(header,[/серии|sets/]);
  const iReps=colIndex(header,[/повторения|reps|повтор/]);
  const iRest=colIndex(header,[/пауза|почивка|rest/]);
  const iNote=colIndex(header,[/бележка|note|защо|замяна/]);
  const ex=[];ex.unsupported=[];
  body.forEach(r=>{
    const name=(r[iName]||'').trim(); if(!name||/общо|total/i.test(name))return;
    const record=window.ApexExerciseInstructions&&window.ApexExerciseInstructions.find(name);
    if(!record){ex.unsupported.push(name);return;}
    const exercise={name:window.ApexExerciseInstructions.display(record,lang),contract_display_name:name,canonical_id:record.canonical_id,instruction_record:record,sets:iSets>-1?(r[iSets]||'3'):'3',reps:iReps>-1?(r[iReps]||'10'):'10',
      rest:iRest>-1?(r[iRest]||'60'):'60',note:iNote>-1?(r[iNote]||''):''};
    const prescription=workoutPrescription(exercise);
    if(prescription.type==='duration'||prescription.type==='duration_per_side')exercise.reps=prescription.value;
    ex.push(exercise);
  });
  return ex;
}
let pendingWorkout=null,pendingWorkouts={},pendingWorkoutContracts={},pendingTrainingCompletion=null,pendingCompletionSessions=[],medicalHoldActive=false;
function activeWorkoutConversationId(){
  const key='apexWorkoutConversationId';let value=sessionStorage.getItem(key)||'';
  if(!/^[A-Za-z0-9_-]{16,128}$/.test(value)){
    value=(crypto.randomUUID?crypto.randomUUID():String(Date.now())+'-'+Math.random()).replace(/[^A-Za-z0-9_-]/g,'');
    sessionStorage.setItem(key,value);
  }
  return value;
}
function activateMedicalHold(persist=true){
  medicalHoldActive=true;pendingWorkout=null;pendingWorkouts={};pendingWorkoutContracts={};
  document.querySelectorAll('.start-wo').forEach(b=>{b.disabled=true;b.style.display='none';});
  if(persist){
    const profile=pfLoad();
    if(!profile._medical_hold||profile._medical_hold.status!=='ACTIVE_MEDICAL_HOLD'){
      profile._medical_hold={status:'ACTIVE_MEDICAL_HOLD',workout_blocked:true,session_blocked:true};
      ownedStorageSet('apexProfile',JSON.stringify(profile));accountSaveProfile(profile);
    }
  }
}
const renderedWorkoutExercises={};
const WORKOUT_ALL_EXERCISE_INSTRUCTIONS='WORKOUT_ALL_EXERCISE_INSTRUCTIONS';
const WORKOUT_SINGLE_EXERCISE_EXPLANATION='WORKOUT_SINGLE_EXERCISE_EXPLANATION';
function normalizedInstructionIntent(value){return String(value||'').toLocaleLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g,'').replace(/[^\p{L}\p{N}]+/gu,' ').trim();}
function workoutFollowUpIntent(value){
  const q=normalizedInstructionIntent(value);
  const english=['how do i perform these exercises','explain the exercises','show exercise technique','how do i do them','explain each exercise','exercise instructions'];
  const bulgarian=[
    'как се правят тези упражнения','как се правят всички тези упражнения','как се изпълняват','покажи ми как се изпълняват',
    'обясни упражненията','обясни техниката','обясни ми техниката','покажи техниката','как да ги правя','техника на упражненията','обясни ми всяко упражнение'
  ];
  if(english.includes(q)||bulgarian.includes(q))return{type:WORKOUT_ALL_EXERCISE_INSTRUCTIONS};
  if(!/(?:what is|how (?:do|to)|explain|technique|какво е|как се|обясни|техника|изпълнява)/i.test(q))return null;
  const protocol=latestWorkoutProtocol();if(!protocol||!window.ApexExerciseInstructions)return null;
  const key=decodeURIComponent(protocol.dataset.workoutKey||''),current=renderedWorkoutExercises[key]||[];
  const record=window.ApexExerciseInstructions.records.find(item=>current.some(exercise=>exercise.canonical_id===item.canonical_id)&&item.aliases.some(alias=>{
    const aliasKey=normalizedInstructionIntent(alias);return q===aliasKey||q.includes(' '+aliasKey)||q.endsWith(aliasKey);
  }));
  return record?{type:WORKOUT_SINGLE_EXERCISE_EXPLANATION,record,key}:null;
}
function instructionList(items,ordered=false){const tag=ordered?'ol':'ul';return '<'+tag+'>'+items.map(item=>'<li>'+esc(item)+'</li>').join('')+'</'+tag+'>';}
function instructionContent(content){
  if(Array.isArray(content)){const values=content.filter(item=>typeof item==='string'&&item.trim()&&item.trim()!=='-');return values.length?values:null;}
  return typeof content==='string'&&content.trim()&&content.trim()!=='-'?content:null;
}
function instructionSection(label,content,ordered=false,open=false){
  const normalized=instructionContent(content);if(!normalized)return '';
  const value=Array.isArray(normalized)?instructionList(normalized,ordered):'<p class="ei-copy">'+esc(normalized)+'</p>';
  return '<details class="ei-section"'+(open?' open':'')+'><summary>'+esc(label)+'</summary>'+value+'</details>';
}
function instructionStaticSection(label,content,ordered=false){
  const normalized=instructionContent(content);if(!normalized)return '';
  const value=Array.isArray(normalized)?instructionList(normalized,ordered):'<p class="ei-copy">'+esc(normalized)+'</p>';
  return '<section class="ei-section"><div class="ei-static-label">'+esc(label)+'</div>'+value+'</section>';
}
function fallbackInstructionRecord(exercise){
  const bg=lang==='bg';return{ id:'unavailable',prescription_type:'repetitions',
    [bg?'bg':'en']:{starting:[bg?'Запази спокойна и контролирана начална позиция.':'Use a calm, controlled starting position.'],steps:[bg?'За това упражнение няма подготвена детайлна инструкция. Не променяй самостоятелно техниката или натоварването.':'A detailed instruction is not available for this exercise. Do not change technique or load on your own.'],breathing:bg?'Дишай спокойно и не задържай въздуха.':'Breathe calmly and do not hold your breath.',cues:[bg?'Изпълнявай само в безболезнен обхват.':'Work only through a pain-free range.'],mistakes:[bg?'Не ускорявай движението, за да компенсираш несигурност.':'Do not rush the movement to compensate for uncertainty.'],regression:bg?'Избери по-лесен вариант само след конкретна насока от треньора.':'Use an easier variation only with specific coaching guidance.',safety:bg?'Спри при остра болка.':'Stop for sharp pain.'}};
}
function instructionLabels(){
  return lang==='bg'?{start:'Начална позиция',steps:'Изпълнение',breathing:'Дишане',cues:'Ключови насоки',mistakes:'Чести грешки',regression:'По-лесен вариант',safety:'Безопасност'}:{start:'Starting position',steps:'Execution',breathing:'Breathing',cues:'Key cues',mistakes:'Common mistakes',regression:'Easier variation',safety:'Safety'};
}
function instructionRecordFor(exercise){
  const api=window.ApexExerciseInstructions;
  return exercise.instruction_record||(api&&api.find(exercise.name))||null;
}
function workoutInstructionSections(exercise,includeOverview=false){
  const labels=instructionLabels(),record=instructionRecordFor(exercise),copy=record[lang==='bg'?'bg':'en'];
  const overview=instructionContent(copy.overview);
  return (includeOverview&&overview?'<p class="ei-overview">'+esc(overview)+'</p>':'')+instructionStaticSection(labels.start,copy.starting)+instructionStaticSection(labels.steps,copy.execution,true)+
    instructionSection(labels.breathing,copy.breathing)+instructionSection(labels.cues,copy.cues)+
    instructionSection(labels.mistakes,copy.mistakes)+instructionSection(labels.regression,copy.regression)+instructionSection(labels.safety,copy.safety);
}
function workoutDisplayMeta(exercise){
  const note=String(exercise.note||''),tempo=(note.match(/(?:темпо|tempo)\s*([\d-]+)/i)||[])[1]||'2-0-2';
  const rpe=(note.match(/RPE\s*([\d.]+)/i)||[])[1]||'—',rir=(note.match(/RIR\s*([\d.]+)/i)||[])[1]||'—';
  return{tempo,rpe,rir,note};
}
function renderWorkoutExerciseCard(exercise,diffLabel,includeOverview=false){
  const api=window.ApexExerciseInstructions;
  const record=instructionRecordFor(exercise);if(!record)return '';
  const mu={...inferMuscle(exercise.name),m:lang==='bg'?record.muscle_group_bg:record.muscle_group_en},df=inferDiff(exercise.reps,exercise.name),prescription=workoutPrescription(exercise),meta=workoutDisplayMeta(exercise);
  const unit=prescription.type==='duration'?(lang==='bg'?'сек':'sec'):(lang==='bg'?'повт.':'reps');
  const labels=lang==='bg'?{sets:'Серии',target:'Повторения',rest:'Почивка',tempo:'Темпо',rpe:'RPE',rir:'RIR'}:{sets:'Sets',target:'Repetitions',rest:'Rest',tempo:'Tempo',rpe:'RPE',rir:'RIR'};
  if(prescription.type==='duration')labels.target=lang==='bg'?'Продължителност':'Duration';
  const displayUnit=(prescription.type==='duration'||prescription.type==='duration_per_side')?'':(prescription.type==='repetitions_per_side'?(lang==='bg'?' повторения на страна':' reps / side'):(' '+unit));
  const displayTarget=prescription.type==='duration'||prescription.type==='duration_per_side'?(lang==='bg'?'Продължителност':'Duration'):(prescription.type==='repetitions_per_side'?(lang==='bg'?'Повторения на страна':'Repetitions per side'):labels.target);
  return '<article class="ex-card ei-card workout-exercise-card" data-exercise-id="'+esc(record.canonical_id)+'" data-exercise-instruction-id="'+esc(record.id)+'"><div class="workout-card-hero"><div class="ex-glyph" style="background:radial-gradient(circle at 50% 35%,'+mu.ic+'33,rgba(18,23,36,.6))">'+mu.e+'</div><div class="workout-card-title"><div class="ex-top"><h3 class="ex-name">'+esc(exercise.name)+'</h3><span class="ex-diff '+df+'">'+diffLabel[df]+'</span></div><div class="ex-muscles"><span class="ex-muscle">'+mu.m+'</span></div></div></div><div class="workout-card-stats">'+
    '<span class="workout-card-stat"><b>'+esc(exercise.sets)+'</b>'+labels.sets+'</span><span class="workout-card-stat"><b>'+esc(prescription.value)+displayUnit+'</b>'+displayTarget+'</span><span class="workout-card-stat"><b>'+esc(localizedTime(exercise.rest))+'</b>'+labels.rest+'</span><span class="workout-card-stat meta"><b>'+esc(meta.tempo)+'</b>'+labels.tempo+'</span><span class="workout-card-stat meta"><b>'+esc(meta.rpe)+'</b>'+labels.rpe+'</span><span class="workout-card-stat meta"><b>'+esc(meta.rir)+'</b>'+labels.rir+'</span></div>'+
    (meta.note?'<div class="workout-card-note">'+esc(meta.note)+'</div>':'')+workoutInstructionSections(exercise,includeOverview)+'</article>';
}
function reopenWorkoutInstructions(){
  const protocol=latestWorkoutProtocol();if(!protocol)return false;
  const cards=protocol.querySelectorAll('.workout-exercise-card');if(!cards.length)return false;
  cards.forEach(card=>card.querySelectorAll('details').forEach(section=>{section.open=true;}));
  cards[0].scrollIntoView({behavior:'smooth',block:'start'});return true;
}
function latestWorkoutProtocol(){const protocols=document.querySelectorAll('.workout-protocol');return protocols[protocols.length-1]||null;}
function renderFocusedExerciseInstruction(record,key){
  const exercise=(renderedWorkoutExercises[key]||[]).find(item=>item.canonical_id===record.canonical_id);if(!exercise)return false;
  const label=lang==='bg'?'Техника на упражнението':'Exercise technique';
  const diffLbl={easy:lang==='bg'?'Лесно':'Easy',med:lang==='bg'?'Средно':'Medium',hard:lang==='bg'?'Трудно':'Hard'};
  const coach=appendCoach();coach.innerHTML='<section class="focused-exercise-instruction"><h3>'+label+'</h3>'+renderWorkoutExerciseCard(exercise,diffLbl,true)+'</section>';
  coach.querySelectorAll('details').forEach(section=>{section.open=true;});coach.scrollIntoView({behavior:'smooth',block:'start'});return true;
}
function completionSessionFor(exercises){
  const session=pendingCompletionSessions.shift();
  if(!session||!Array.isArray(session.exercises)||session.exercises.length!==exercises.length)return null;
  const valid=session.exercises.every((item,index)=>item&&item.display_name===exercises[index].contract_display_name&&
    typeof item.prescription_id==='string'&&typeof item.exercise_id==='string'&&typeof item.exercise_version==='string');
  if(!valid)return null;
  exercises.forEach((exercise,index)=>{exercise.completion=Object.assign({},session.exercises[index]);});
  return session;
}
function workoutRationale(raw){
  if(!raw||raw.version!=='training-rationale-v1'||!Array.isArray(raw.used)||!Array.isArray(raw.changed)||
    !raw.used.length||!raw.changed.length||raw.used.length>2||raw.changed.length>2||
    !['goal_and_capacity','progressed_from_previous_workout','progressed_within_constraints','protective_recovery','cross_session_progressed','cross_session_progressed_with_constraints','longitudinal_split_sequence','longitudinal_exercise_rotation'].includes(raw.reason_code))return null;
  const patterns={vertical_push:lang==='bg'?'преса над глава':'overhead pressing',horizontal_push:lang==='bg'?'лицеви опори и хоризонтални преси':'push-ups and horizontal pressing',vertical_pull:lang==='bg'?'набирания и вертикално дърпане':'pull-ups and vertical pulling',squat:lang==='bg'?'клекове':'squats',lunge:lang==='bg'?'напади':'lunges',hinge:lang==='bg'?'хиндж движения и тяги':'hinge movements and deadlifts',core_anti_extension:lang==='bg'?'планк и анти-екстензия за корем':'planks and anti-extension core work'};
  const goals={strength:lang==='bg'?'сила':'strength',muscle_gain:lang==='bg'?'мускулен растеж':'muscle gain',fat_loss:lang==='bg'?'намаляване на мазнини':'fat loss',maintenance:lang==='bg'?'поддържане':'maintenance',general_fitness:lang==='bg'?'обща физическа форма':'general fitness'};
  const levels={beginner:lang==='bg'?'начално':'beginner',intermediate:lang==='bg'?'средно':'intermediate',advanced:lang==='bg'?'напреднало':'advanced'};
  const valid=(item,used)=>item&&typeof item.kind==='string'&&typeof item.value==='string'&&Object.keys(item).length===2&&
    (used?{active_constraint:patterns,recent_workout:{previous_session:1},protective_recovery:{protective:1},training_goal:goals,experience_capacity:levels,comparable_session:{comfortable_completed:1},recent_training_exposure:{completed_session:1}}:{excluded_movement:patterns,difficulty_adjustment:{increased:1,decreased:1},protective_volume:{conservative:1},goal_structure:goals,capacity_prescription:levels,cross_session_progression:{load:1,repetitions:1,sets:1,eligible_alternative:1,conservative:1,mixed:1},split_sequence:{full_body:1,upper_lower:1,push_pull_legs:1},exercise_rotation:{safe_alternative:1}})[item.kind]&&
    (used?{active_constraint:patterns,recent_workout:{previous_session:1},protective_recovery:{protective:1},training_goal:goals,experience_capacity:levels,comparable_session:{comfortable_completed:1},recent_training_exposure:{completed_session:1}}:{excluded_movement:patterns,difficulty_adjustment:{increased:1,decreased:1},protective_volume:{conservative:1},goal_structure:goals,capacity_prescription:levels,cross_session_progression:{load:1,repetitions:1,sets:1,eligible_alternative:1,conservative:1,mixed:1},split_sequence:{full_body:1,upper_lower:1,push_pull_legs:1},exercise_rotation:{safe_alternative:1}})[item.kind][item.value];
  if(!raw.used.every(item=>valid(item,true))||!raw.changed.every(item=>valid(item,false)))return null;
  const usedLine=item=>({active_constraint:lang==='bg'?'Използвано: активно ограничение за '+patterns[item.value]+'.':'Used: your active restriction for '+patterns[item.value]+'.',recent_workout:lang==='bg'?'Използвана е предишната ти тренировка.':'Used: your previous workout.',protective_recovery:lang==='bg'?'Използван е защитен контекст за възстановяване.':'Used: a protective recovery context.',training_goal:lang==='bg'?'Използвана цел: '+goals[item.value]+'.':'Used: your '+goals[item.value]+' goal.',experience_capacity:lang==='bg'?'Използвано ниво: '+levels[item.value]+'.':'Used: your '+levels[item.value]+' training level.',recent_training_exposure:lang==='bg'?'Използвана е последната ти завършена тренировка.':'Used: your last completed workout.'})[item.kind];
  const changedLine=item=>({excluded_movement:lang==='bg'?'Промяна: '+patterns[item.value]+' остава изключено.':'Changed: '+patterns[item.value]+' remains excluded.',difficulty_adjustment:item.value==='increased'?(lang==='bg'?'Промяна: трудността е увеличена с допустими алтернативи.':'Changed: difficulty increased through eligible alternatives.'):(lang==='bg'?'Промяна: трудността е намалена в безопасни граници.':'Changed: difficulty reduced within safe limits.'),protective_volume:lang==='bg'?'Промяна: обемът е запазен по-консервативен.':'Changed: volume remains conservative.',goal_structure:lang==='bg'?'Промяна: структурата следва целта ти за '+goals[item.value]+'.':'Changed: the structure follows your '+goals[item.value]+' goal.',capacity_prescription:lang==='bg'?'Промяна: предписанието е съобразено с '+levels[item.value]+' ниво.':'Changed: the prescription matches your '+levels[item.value]+' level.',split_sequence:lang==='bg'?'Промяна: следващата сесия е избрана по реда на твоя сплит.':'Changed: the next session follows your split sequence.',exercise_rotation:lang==='bg'?'Промяна: избран е съвместим вариант вместо точно повторение.':'Changed: a compatible alternative replaced an exact recent repeat.'})[item.kind];
  const crossSessionUsed=lang==='bg'?'Използвана е последната ти сравнима тренировка, завършена комфортно.':'Used: your last comparable session, completed comfortably.';
  const crossSessionChanged=lang==='bg'?'Промяна: допустими упражнения са прогресирани от тази тренировка.':'Changed: eligible prescriptions progressed from that session.';
  const lines=[...raw.used.map(item=>item.kind==='comparable_session'?crossSessionUsed:usedLine(item)),...raw.changed.map(item=>item.kind==='cross_session_progression'?crossSessionChanged:changedLine(item))];
  return lines.every(Boolean)&&lines.length<=4?lines:null;
}
function renderWorkoutRationale(raw){
  const lines=workoutRationale(raw);if(!lines)return '';
  return '<details class="workout-rationale"><summary>'+(lang==='bg'?'Защо този план?':'Why this plan?')+'</summary><ul>'+lines.map(line=>'<li>'+esc(line)+'</li>').join('')+'</ul></details>';
}
function renderWorkout(header,body){
  const ex=parseExercises(header,body); if(ex.unsupported.length)return '<p>'+(lang==='bg'?'Тренировката не можа да бъде потвърдена безопасно. Опитай отново.':'The workout could not be safely verified. Please try again.')+'</p>';
  if(!ex.length)return renderGenericTable(header,body);
  const completionSession=completionSessionFor(ex);
  const workoutKey=completionSession?completionSession.session_id:('legacy-'+Date.now()+'-'+Math.random());
  pendingWorkout=ex;
  pendingWorkouts[workoutKey]=ex;
  renderedWorkoutExercises[workoutKey]=ex;
  pendingWorkoutContracts[workoutKey]=completionSession?{
    plan_id:pendingTrainingCompletion.plan_id,plan_version:pendingTrainingCompletion.plan_version,
    session_id:completionSession.session_id
  }:null;
  const diffLbl={easy:lang==='bg'?'Лесно':'Easy',med:lang==='bg'?'Средно':'Medium',hard:lang==='bg'?'Трудно':'Hard'};
  let html='<section class="workout-protocol" data-workout-key="'+encodeURIComponent(workoutKey)+'"><div class="wo-intro"><span class="wt">'+(lang==='bg'?'Тренировъчен протокол':'Training protocol')+'</span>'+
    '<button class="start-wo" data-workout-key="'+encodeURIComponent(workoutKey)+
    '" onclick="startWorkout(decodeURIComponent(this.dataset.workoutKey))">▶ '+tr().woStart+'</button></div>'+renderWorkoutRationale(pendingTrainingCompletion&&pendingTrainingCompletion.recommendation_rationale);
  ex.forEach(e=>{
    html+=renderWorkoutExerciseCard(e,diffLbl);
  });
  return html+'</section>';
}

/* ═══════════════════════════════════════════════════════════════════
   WORKOUT MODE — full protocol engine with rest timer & summary
   ═══════════════════════════════════════════════════════════════════ */
let WO=null,restTimer=null,sessionStart=0,lastWorkoutCompletion=null,lastWorkoutSummary=null;
function startWorkout(workoutKey=null){
  if(medicalHoldActive)return;
  const source=workoutKey?pendingWorkoutContracts[workoutKey]:null;
  const exercises=workoutKey?pendingWorkouts[workoutKey]:pendingWorkout;
  if(!exercises||!exercises.length)return;
  witness('sessionBegan');
  WO={ex:JSON.parse(JSON.stringify(exercises)),contract:source,i:0,set:0,phase:'work',startMs:Date.now()};
  sessionStart=Date.now();
  document.getElementById('workout').classList.add('on');
  document.getElementById('wo-quit-btn').textContent='✕ '+tr().woExit;
  renderWO();
}
function quitWorkout(){clearInterval(restTimer);witness('restEnded');document.getElementById('workout').classList.remove('on');WO=null;}
function woEstRemaining(){
  let sec=0; for(let k=WO.i;k<WO.ex.length;k++){const e=WO.ex[k];const sets=parseInt(e.sets)||3;const rest=parseInt((e.rest+'').replace(/[^\d]/g,''))||60;
    const remSets=k===WO.i?sets-WO.set:sets; sec+=remSets*(40+rest);} return Math.max(1,Math.round(sec/60));
}
function woProgress(){
  let total=0,done=0; WO.ex.forEach((e,k)=>{const s=parseInt(e.sets)||3;total+=s;done+=k<WO.i?s:(k===WO.i?WO.set:0);});
  return total?Math.round(done/total*100):0;
}
function boundedWorkoutEffort(value,min,max,integerOnly){
  if(value===''||value==null)return null;
  const number=Number(value);
  if(!Number.isFinite(number)||number<min||number>max||(integerOnly&&!Number.isInteger(number)))return null;
  return number;
}
function workoutEffortOptions(min,max,selected){
  let out='<option value="">—</option>';
  for(let value=min;value<=max;value++)out+='<option value="'+value+'"'+(selected===value?' selected':'')+'>'+value+'</option>';
  return out;
}
function captureExerciseEffort(){
  if(!WO||!WO.ex||!WO.ex[WO.i])return;
  const exercise=WO.ex[WO.i],rpe=document.getElementById('wo-rpe-in'),rir=document.getElementById('wo-rir-in'),effort=document.getElementById('wo-effort-in'),reps=document.getElementById('wo-reps-in');
  exercise.completedRpe=boundedWorkoutEffort(rpe&&rpe.value,1,10,false);
  exercise.completedRir=boundedWorkoutEffort(rir&&rir.value,0,10,true);
  exercise.completedEffort=['easy','productive','hard','incomplete'].includes(effort&&effort.value)?effort.value:null;
  exercise.completedRepetitions=boundedWorkoutEffort(reps&&reps.value,0,999,true);
}
function renderWO(){
  const t=tr(),e=WO.ex[WO.i],mu=inferMuscle(e.name),sets=parseInt(e.sets)||3,prescription=workoutPrescription(e);
  document.getElementById('wo-ptop-l').textContent=t.woEx+' '+(WO.i+1)+'/'+WO.ex.length;
  const pct=woProgress();
  document.getElementById('wo-ptop-r').textContent=pct+'%';
  document.getElementById('wo-fill').style.width=pct+'%';
  const stage=document.getElementById('wo-stage');
  if(WO.phase==='work'){
    let dots='';for(let s=0;s<sets;s++)dots+='<div class="set-dot '+(s<WO.set?'done':(s===WO.set?'current':''))+'">'+(s+1)+'</div>';
    const nextEx=WO.i+1<WO.ex.length?WO.ex[WO.i+1].name:(lang==='bg'?'Завършек':'Finish');
    stage.innerHTML='<div class="wo-step">'+(lang==='bg'?'Серия':'Set')+' '+(WO.set+1)+'/'+sets+' · ~'+woEstRemaining()+(lang==='bg'?'мин остават':'min left')+'</div>'+
      '<div class="wo-ex-glyph" style="background:radial-gradient(circle at 50% 35%,'+mu.ic+'44,rgba(18,23,36,.7))">'+mu.e+'</div>'+
      '<div class="wo-ex-name">'+esc(e.name)+'</div>'+
      '<div class="wo-ex-target">'+esc(prescription.value)+' '+(prescription.type==='duration'?(lang==='bg'?'секунди':'seconds'):(lang==='bg'?'повторения':'reps'))+'</div>'+
      '<div class="wo-ex-meta">'+mu.m+' · '+(lang==='bg'?'темп':'tempo')+' 2-0-2'+(e.note?(' · '+esc(e.note)):'')+'</div>'+
      '<div class="wo-weight"><input type="number" id="wo-reps-in" inputmode="numeric" min="0" placeholder="'+(lang==='bg'?'повторения':'reps')+'" value="'+(e.completedRepetitions==null?(parseInt(e.reps)||''):e.completedRepetitions)+'"><span>'+(lang==='bg'?'реално изпълнени':'completed reps')+'</span><input type="number" id="wo-weight-in" inputmode="decimal" placeholder="'+(lang==='bg'?'кг (по избор)':'kg (optional)')+'" value="'+(e.weight||'')+'" oninput="WO.ex[WO.i].weight=this.value"></div>'+
      '<div class="wo-effort"><span>'+(lang==='bg'?'Как се почувства упражнението?':'How did that exercise feel?')+'</span><select id="wo-effort-in" onchange="captureExerciseEffort()"><option value="">'+(lang==='bg'?'Избери':'Choose')+'</option><option value="easy"'+(e.completedEffort==='easy'?' selected':'')+'>'+(lang==='bg'?'Лесно':'Easy')+'</option><option value="productive"'+(e.completedEffort==='productive'?' selected':'')+'>'+(lang==='bg'?'Точно както трябва':'About right')+'</option><option value="hard"'+(e.completedEffort==='hard'?' selected':'')+'>'+(lang==='bg'?'Трудно':'Hard')+'</option><option value="incomplete"'+(e.completedEffort==='incomplete'?' selected':'')+'>'+(lang==='bg'?'Не успях да завърша':'Couldn’t finish')+'</option></select><details><summary>'+(lang==='bg'?'Разширено: RPE / RIR':'Advanced: RPE / RIR')+'</summary><small>'+(lang==='bg'?'RPE = колко трудно се усещаше. RIR = колко чисти повторения оставаха.':'RPE = how hard it felt. RIR = clean reps left.')+'</small><label>RPE <select id="wo-rpe-in" onchange="captureExerciseEffort()">'+workoutEffortOptions(1,10,boundedWorkoutEffort(e.completedRpe,1,10,false))+'</select></label><label>RIR <select id="wo-rir-in" onchange="captureExerciseEffort()">'+workoutEffortOptions(0,10,boundedWorkoutEffort(e.completedRir,0,10,true))+'</select></label></details></div>'+
      '<div class="set-dots">'+dots+'</div>'+
      '<div class="wo-controls"><button class="wo-btn primary" onclick="completeSet()">'+t.woDone+' →</button>'+
      (WO.i>0||WO.set>0?'<button class="wo-btn ghost" onclick="skipExercise()">'+(lang==='bg'?'Следващо':'Next')+' »</button>':'')+'</div>'+
      '<div class="wo-next"><b>'+t.woNext+':</b> '+esc(nextEx)+'</div>';
  } else {
    const rest=parseInt((e.rest+'').replace(/[^\d]/g,''))||60;
    stage.innerHTML='<div class="wo-step">'+t.woRest+'</div>'+
      '<div class="rest-ring"><svg width="200" height="200"><circle class="rt-track" cx="100" cy="100" r="92"/>'+
      '<circle class="rt-fill" id="rt-fill" cx="100" cy="100" r="92" stroke-dasharray="578" stroke-dashoffset="0"/></svg>'+
      '<div class="rt-num"><span class="n" id="rt-n">'+rest+'</span><span class="l">'+t.sec+'</span></div></div>'+
      '<div class="wo-controls"><button class="wo-btn ghost" onclick="endRest()">'+t.woSkip+' »</button></div>';
    runRest(rest);
  }
}
function completeSet(){
  captureExerciseEffort();
  witness('setCompleted');   // fact: effort happened (model accrues load + salience)
  const exercise=WO.ex[WO.i],sets=parseInt(exercise.sets)||3; exercise.completedSets=(exercise.completedSets||0)+1; WO.set++;
  if(WO.set>=sets){ // exercise done → advance or finish
    if(WO.i+1>=WO.ex.length){finishWorkout();return;}
    WO.i++;WO.set=0;WO.phase='rest';renderWO();
  } else {WO.phase='rest';renderWO();}
}
function skipExercise(){clearInterval(restTimer);witness('restEnded');if(WO.i+1>=WO.ex.length){finishWorkout();return;}WO.i++;WO.set=0;WO.phase='work';renderWO();}
function endRest(){clearInterval(restTimer);witness('restEnded');WO.phase='work';renderWO();}
function runRest(sec){
  clearInterval(restTimer); let left=sec; const C=578; const fill=document.getElementById('rt-fill'),numEl=document.getElementById('rt-n');
  witness('restBegan');   // fact: a rest interval opened
  restTimer=setInterval(()=>{
    left--; if(numEl)numEl.textContent=Math.max(0,left);
    if(fill)fill.style.strokeDashoffset=C*(1-left/sec);
    witness('restProgress',{p:1-left/sec});   // fact: interval elapsed (model keeps it monotonic)
    if(left<=0){clearInterval(restTimer);endRest();}
  },1000);
}
function finishWorkout(){
  clearInterval(restTimer);
  // Fact only: the session completed. Whether that becomes a celebration is the
  // model's judgment (accomplishment), not the interface's command.
  witness('sessionCompleted');
  const t=tr(),dur=Math.round((Date.now()-sessionStart)/60000);
  const totalSets=WO.ex.reduce((a,e)=>a+(parseInt(e.sets)||3),0);
  const session={ts:Date.now(),date:new Date().toLocaleDateString(),type:inferMuscle(WO.ex[0].name).m,
    exercises:WO.ex.map(e=>({name:e.name,sets:e.sets,reps:e.reps,weight:e.weight||''})),diff:'medium',completion:100};
  const workoutSummary={
    completed_at:new Date().toISOString(),type:session.type,completion:100,
    exercises:WO.ex.map(e=>({name:e.name,completed_sets:e.completedSets||0,
      completed_repetitions:(e.completedSets||0)?(e.completedRepetitions==null?(parseInt(e.reps)||0):e.completedRepetitions):0,
      completed_load:e.weight===''||e.weight==null?null:Number(e.weight)}))
  };
  const workoutCompletion=WO.contract&&WO.ex.every(e=>e.completion)?{
    workout_id:(window.crypto&&crypto.randomUUID?crypto.randomUUID():null),
    plan_id:WO.contract.plan_id,plan_version:WO.contract.plan_version,session_id:WO.contract.session_id,
    completion_timestamp:new Date().toISOString(),
    exercises:WO.ex.map(e=>({
      prescription_id:e.completion.prescription_id,exercise_id:e.completion.exercise_id,
      exercise_version:e.completion.exercise_version,completed_sets:e.completedSets||0,
      completed_repetitions:(e.completedSets||0)?(e.completedRepetitions==null?(parseInt(e.reps)||0):e.completedRepetitions):0,
      completed_load:e.weight===''||e.weight==null?null:Number(e.weight),
      completed_rir:boundedWorkoutEffort(e.completedRir,0,10,true),
      completed_rpe:boundedWorkoutEffort(e.completedRpe,1,10,false),
      completed_effort:['easy','productive','hard','incomplete'].includes(e.completedEffort)?e.completedEffort:null
    }))
  }:null;
  if(workoutCompletion&& !workoutCompletion.workout_id)workoutCompletion=null;
  lastWorkoutCompletion=workoutCompletion;
  lastWorkoutSummary=workoutSummary;
  logWorkout(session,workoutCompletion);
  document.getElementById('wo-stage').innerHTML='<div class="wo-summary"><div class="wo-step">✓ '+t.woComplete+'</div>'+
    '<div class="wo-ex-glyph" style="background:radial-gradient(circle at 50% 35%,#B6FF3C44,rgba(18,23,36,.7));margin:0 auto 20px">🏁</div>'+
    '<div class="wo-ex-name">'+t.woGreat+'</div>'+
    '<div class="sum-stats"><div class="sum-stat"><div class="v">'+WO.ex.length+'</div><div class="l">'+t.woSummary.ex+'</div></div>'+
    '<div class="sum-stat"><div class="v">'+totalSets+'</div><div class="l">'+t.woSummary.sets+'</div></div>'+
    '<div class="sum-stat"><div class="v">'+dur+'</div><div class="l">'+t.woSummary.time+'</div></div></div>'+
    '<div class="wo-controls"><button class="wo-btn primary" onclick="finishToCoach()">'+(lang==='bg'?'Към треньора →':'Back to coach →')+'</button></div></div>';
}
function finishToCoach(){
  document.getElementById('workout').classList.remove('on'); WO=null; applyReadout();
  if(!consultOn)enterConsult();
  const completion=lastWorkoutCompletion;
  const summary=lastWorkoutSummary;
  lastWorkoutCompletion=null;
  lastWorkoutSummary=null;
  if(completion){
    const recoveryFeel=(pfLoad().recoveryFeel||'ok').toLowerCase();
    const recovery={
      state:recoveryFeel==='fresh'?'fully_recovered':(recoveryFeel==='tired'?'fatigued':'normally_recovered'),
      accumulated_fatigue:recoveryFeel==='fresh'?'15':(recoveryFeel==='tired'?'65':'30'),
      source_version:'browser-recovery-v1'
    };
    setTimeout(()=>{
      document.getElementById('user-in').value=lang==='bg'?'Следваща тренировка.':'Build my next workout.';
      send({completedWorkout:completion,recovery});
    },300);
    return;
  }
  // Legacy cards cannot advance an immutable lifecycle, but their completed
  // exercises are still authoritative context for a post-workout acknowledgement.
  setTimeout(()=>{
    document.getElementById('user-in').value=lang==='bg'?'Завърших я.':'I finished it.';
    send({completedWorkout:summary,recovery:{source_version:'browser-recovery-v1'}});
  },300);
}

/* ═══════════════════════════════════════════════════════════════════
   CHAT MESSAGES + AI ENGINE
   Scroll ownership belongs to the USER. A request follows new content only while
   its owner was already at the bottom; scrolling away disarms follow immediately.
   ═══════════════════════════════════════════════════════════════════ */
function feedNearBottom(){const f=document.getElementById('feed');return f.scrollHeight-f.scrollTop-f.clientHeight<40;}
function showJump(){document.getElementById('jump-latest').classList.add('on');}
function hideJump(){document.getElementById('jump-latest').classList.remove('on');}
// Called during streaming: read-only. Only toggles the "Jump to latest" affordance
// when new content sits below the fold. Never moves the scroll position.
function smartScroll(){ feedNearBottom() ? hideJump() : showJump(); }
// One-time snap to bottom — user-initiated only (sending a message / pressing Jump).
function hardScroll(){ const f=document.getElementById('feed'); f.scrollTop=f.scrollHeight; hideJump(); }
function jumpToLatest(){if(ChatLifecycle.current&&!CHAT_TERMINAL.has(ChatLifecycle.current.state))ChatLifecycle.current.follow=true;hardScroll();}
function appendUser(text){const feed=document.getElementById('feed');const g=feed.querySelector('.greet');if(g)g.remove();
  const d=document.createElement('div');d.className='msg u';d.textContent=text;feed.appendChild(d);return d;}
function appendCoach(requestId=''){const feed=document.getElementById('feed'),d=document.createElement('div');d.className='msg a';
  if(requestId)d.dataset.requestId=requestId;
  d.innerHTML='<div class="who">'+tr().coach+'</div><div class="body md"></div>';feed.appendChild(d);smartScroll();return d.querySelector('.body');}
function getHistory(){try{return JSON.parse(ownedStorageGet('apexHistory')||'[]');}catch(e){return[];}}
function saveHistory(role,content){const h=getHistory();h.push({role,content});ownedStorageSet('apexHistory',JSON.stringify(h.slice(-40)));}

const CHAT_STATES=Object.freeze({
  IDLE:'IDLE',SENDING:'SENDING',WAITING_FIRST_TOKEN:'WAITING_FIRST_TOKEN',STREAMING:'STREAMING',
  COMPLETING:'COMPLETING',COMPLETED:'COMPLETED',FAILED:'FAILED',CANCELLED:'CANCELLED',INTERRUPTED:'INTERRUPTED'
});
const CHAT_TERMINAL=new Set([CHAT_STATES.COMPLETED,CHAT_STATES.FAILED,CHAT_STATES.CANCELLED,CHAT_STATES.INTERRUPTED]);
const STREAM_PAINT_BATCH=256;
const CHAT_TRANSITIONS=Object.freeze({
  IDLE:['SENDING'],SENDING:['WAITING_FIRST_TOKEN','FAILED','CANCELLED'],
  WAITING_FIRST_TOKEN:['STREAMING','FAILED','CANCELLED','INTERRUPTED'],
  STREAMING:['COMPLETING','FAILED','CANCELLED','INTERRUPTED'],COMPLETING:['COMPLETED','FAILED'],
  COMPLETED:[],FAILED:['SENDING'],CANCELLED:['SENDING'],INTERRUPTED:['SENDING']
});
const STOP_TURNS=new Set(['спри','стоп','млъкни','спри да говориш','stop','stop talking','be quiet','silence']);
function isStopTurn(text){return STOP_TURNS.has(String(text||'').trim().toLowerCase().replace(/[.!?…]+$/,'').trim());}

const ChatLifecycle={
  current:null,sequence:0,
  busy(){return !!this.current&&!CHAT_TERMINAL.has(this.current.state);},
  transition(x,next){
    if(!x||this.current!==x||!(CHAT_TRANSITIONS[x.state]||[]).includes(next))throw new Error('invalid_chat_transition');
    x.state=next;const c=document.getElementById('consult');if(c)c.dataset.chatState=next.toLowerCase();
  },
  begin(message,options,priorHistory){
    if(this.busy())return null;
    const retry=this.current&&this.current.message===message&&
      [CHAT_STATES.FAILED,CHAT_STATES.CANCELLED,CHAT_STATES.INTERRUPTED].includes(this.current.state);
    let x;
    if(retry){
      x=this.current;this.transition(x,CHAT_STATES.SENDING);x.attempt++;
      Object.assign(x,{options,controller:new AbortController(),typing:null,full:'',speechText:'',
        done:false,closed:false,follow:feedNearBottom(),watchdog:null,reader:null,pendingText:'',
        paintHandle:null,paintPromise:null,paintResolve:null,streamLineNode:null,streamSuppressed:false});
    }else{
      x={id:'chat-'+(++this.sequence),state:CHAT_STATES.IDLE,attempt:1,message,options,
        priorHistory,controller:new AbortController(),typing:null,assistantBody:null,full:'',speechText:'',
        done:false,closed:false,follow:feedNearBottom(),watchdog:null,reader:null,pendingText:'',
        paintHandle:null,paintPromise:null,paintResolve:null,streamLineNode:null,streamSuppressed:false};
      this.current=x;this.transition(x,CHAT_STATES.SENDING);
      if(!options.sessionStart){appendUser(message);saveHistory('user',message);}
    }
    const ty=document.createElement('div');ty.className='typing';ty.dataset.requestId=x.id;
    ty.innerHTML='<span class="tl">'+tr().typing+'</span><i></i><i></i><i></i>';
    document.getElementById('feed').appendChild(ty);x.typing=ty;
    if(x.follow)hardScroll();else smartScroll();
    witness('exchangeOpened');
    return x;
  },
  waiting(x){this.transition(x,CHAT_STATES.WAITING_FIRST_TOKEN);},
  removeTyping(x){if(x.typing&&x.typing.parentNode)x.typing.remove();x.typing=null;},
  content(x,text){
    if(!text||this.current!==x)return;
    if(x.state===CHAT_STATES.WAITING_FIRST_TOKEN){
      this.transition(x,CHAT_STATES.STREAMING);this.removeTyping(x);
      if(x.assistantBody)x.assistantBody.innerHTML='';
      else x.assistantBody=appendCoach(x.id);
      if(x.follow)hardScroll();
    }
    if(x.state!==CHAT_STATES.STREAMING)return;
    x.full+=text;x.pendingText+=text;witness('replyToken');this.schedulePaint(x);
  },
  appendStreamText(x,text){
    const fragment=document.createDocumentFragment();let start=0;
    const appendRun=end=>{
      if(end<=start||x.streamSuppressed)return;
      if(!x.streamLineNode){x.streamLineNode=document.createTextNode('');fragment.appendChild(x.streamLineNode);}
      x.streamLineNode.appendData(text.slice(start,end));
    };
    for(let i=0;i<text.length;i++){
      const ch=text[i];if(ch!=='\n'&&ch!=='|'&&ch!=='\r')continue;
      appendRun(i);start=i+1;
      if(ch==='|'){
        x.streamSuppressed=true;
        if(x.streamLineNode){x.streamLineNode.remove();x.streamLineNode=null;}
      }else if(ch==='\n'){
        if(!x.streamSuppressed)fragment.appendChild(document.createElement('br'));
        x.streamSuppressed=false;x.streamLineNode=null;
      }
    }
    appendRun(text.length);
    if(fragment.childNodes.length)x.assistantBody.appendChild(fragment);
  },
  flushPaint(x){
    if(this.current!==x||x.state!==CHAT_STATES.STREAMING||!x.pendingText)return;
    const delta=x.pendingText;x.pendingText='';this.appendStreamText(x,delta);
    if(x.follow)hardScroll();else smartScroll();
  },
  schedulePaint(x){
    if(x.paintPromise)return x.paintPromise;
    x.paintPromise=new Promise(resolve=>{
      x.paintResolve=resolve;x.paintHandle=requestAnimationFrame(()=>{
        x.paintHandle=null;x.paintPromise=null;x.paintResolve=null;
        this.flushPaint(x);resolve();
      });
    });
    return x.paintPromise;
  },
  cancelPaint(x){
    if(x.paintHandle!==null)cancelAnimationFrame(x.paintHandle);
    const resolve=x.paintResolve;
    x.paintHandle=null;x.paintPromise=null;x.paintResolve=null;x.pendingText='';
    if(resolve)resolve();
  },
  metadata(x,event){
    if(event.training_completion&&Array.isArray(event.training_completion.sessions)){
      pendingTrainingCompletion=event.training_completion;
      pendingCompletionSessions=event.training_completion.sessions.slice();
    }
    if(event.speech_text)x.speechText=event.speech_text;
  },
  complete(x){
    if(this.current!==x)return false;
    if(x.state!==CHAT_STATES.STREAMING||!x.full){this.fail(x,null,CHAT_STATES.FAILED);return false;}
    this.cancelPaint(x);
    this.transition(x,CHAT_STATES.COMPLETING);
    x.assistantBody.innerHTML=renderMarkdown(x.full);
    if(!x.options.sessionStart)saveHistory('assistant',x.full);
    afterReply(x.full,x.speechText);
    this.transition(x,CHAT_STATES.COMPLETED);this.finish(x);if(x.follow)hardScroll();else smartScroll();return true;
  },
  fail(x,message,state=CHAT_STATES.FAILED){
    if(!x||this.current!==x||CHAT_TERMINAL.has(x.state))return;
    this.cancelPaint(x);
    this.transition(x,state);this.removeTyping(x);
    if(!x.assistantBody)x.assistantBody=appendCoach(x.id);
    const terminalMessage=message||(state===CHAT_STATES.INTERRUPTED
      ?(lang==='bg'?'Отговорът беше прекъснат. Моля, опитай отново.':'The response was interrupted. Please try again.')
      :(lang==='bg'?'Връзката прекъсна. Моля, опитай отново.':'Connection interrupted. Please try again.'));
    x.assistantBody.innerHTML='<p>'+esc(terminalMessage)+'</p>';
    const inp=document.getElementById('user-in');if(inp&&!inp.value.trim())inp.value=x.message;
    if(typeof Voice!=='undefined'&&Voice.on)Voice.set('ERROR');
    this.finish(x);if(x.follow)hardScroll();else smartScroll();
  },
  cancel(x=this.current){
    if(!x||this.current!==x||CHAT_TERMINAL.has(x.state))return false;
    this.cancelPaint(x);
    this.transition(x,CHAT_STATES.CANCELLED);this.removeTyping(x);
    if(!x.assistantBody)x.assistantBody=appendCoach(x.id);
    x.assistantBody.innerHTML='<p>'+esc(lang==='bg'?'Заявката е отменена.':'Request cancelled.')+'</p>';
    try{x.controller.abort();}catch(_){}try{if(x.reader)x.reader.cancel();}catch(_){}
    const inp=document.getElementById('user-in');if(inp)inp.value=x.message;
    if(typeof Voice!=='undefined'&&Voice.on){Voice.set('LISTENING');Voice.listen();}
    this.finish(x);return true;
  },
  finish(x){
    if(x.closed)return;x.closed=true;if(x.watchdog)clearTimeout(x.watchdog);
    const inp=document.getElementById('user-in');if(inp)inp.focus();witness('exchangeClosed');
  },
  userScrolled(){
    const x=this.current;if(x&&!CHAT_TERMINAL.has(x.state))x.follow=feedNearBottom();
    feedNearBottom()?hideJump():showJump();
  }
};

async function send(options={}){
  if(sendLocked){ showLimit(); return; }   // limit reached → route to unlock, never a dead end
  const inp=document.getElementById('user-in');const val=inp.value.trim();if(!val)return;
  if(ChatLifecycle.busy()){
    if(isStopTurn(val)){inp.value='';ChatLifecycle.cancel();}
    return;
  }
  if(isStopTurn(val)){inp.value='';return;}
  const followUpIntent=workoutFollowUpIntent(val);
  if(followUpIntent&&followUpIntent.type===WORKOUT_ALL_EXERCISE_INSTRUCTIONS&&reopenWorkoutInstructions()){
    inp.value='';appendUser(val);saveHistory('user',val);hardScroll();return;
  }
  if(followUpIntent&&followUpIntent.type===WORKOUT_SINGLE_EXERCISE_EXPLANATION&&renderFocusedExerciseInstruction(followUpIntent.record,followUpIntent.key)){
    inp.value='';appendUser(val);saveHistory('user',val);saveHistory('assistant',lang==='bg'?'Техника на упражнението':'Exercise technique');hardScroll();return;
  }
  const priorHistory=getHistory(),x=ChatLifecycle.begin(val,options,priorHistory);if(!x)return;
  inp.value='';pendingTrainingCompletion=null;pendingCompletionSessions=[];
  const token=localStorage.getItem('apexToken')||'';
  const body={message:val,lang:lang};
  body.conversation_id=activeWorkoutConversationId();
  if(options.voice===true)body.voice=true;
  if(options.completedWorkout){
    body.completed_workout=options.completedWorkout;
    body.recovery=options.recovery;
  }
  const p=pfLoad();
  const wctx=buildWorkoutContext(lang==='en'); if(wctx)p.workoutContext=wctx;
  if(Object.keys(p).length)body.profile=p;
  if(token)body.token=token;
  body.history=x.priorHistory;
  return runChatExchange(x,body);
}

async function runChatExchange(x,body){
  // M-1: watchdog aborts a stalled request after 75s of inactivity so the UI is
  // never stuck. Each token resets it, so a long but active stream is never cut.
  const kick=()=>{if(x.watchdog)clearTimeout(x.watchdog);x.watchdog=setTimeout(()=>x.controller.abort(),75000);};
  // Account persistence and AthleteModel observation finish before the terminal
  // response. Refresh once after a meaningful content turn, never by polling.
  const refreshCoreAfterPersistedTurn=()=>{
    if(body.session_start!==true)void refreshAthleteCoreProjection();
  };
  ChatLifecycle.waiting(x);kick();
  try{
    const res=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',signal:x.controller.signal,body:JSON.stringify(body)});
    if(!res.ok)throw new Error('chat_http_'+res.status);
    const ct=res.headers.get('content-type')||'';
    if(ct.indexOf('text/event-stream')!==-1){
      const reader=res.body.getReader(),dec=new TextDecoder();x.reader=reader;let buf='',streamFailure=null,paintBatch=0;
      while(true){const{done,value}=await reader.read();if(done)break;
        buf=(buf+dec.decode(value,{stream:true})).replace(/\r\n/g,'\n');const parts=buf.split('\n\n');buf=parts.pop();
        for(const part of parts){const line=part.trim();if(!line.startsWith('data:'))continue;
          let o;try{o=JSON.parse(line.slice(5).trim());}catch(e){throw new Error('malformed_sse');}
          kick();
          if(o.medical_hold){activateMedicalHold();}
          if(o.t){
            ChatLifecycle.content(x,o.t);paintBatch++;
            if(paintBatch>=STREAM_PAINT_BATCH){await ChatLifecycle.schedulePaint(x);paintBatch=0;}
          }
          else if(o.training_completion||o.speech_text)ChatLifecycle.metadata(x,o);
          else if(o.limit_reached){showLimit(o.hours_left||24);ChatLifecycle.fail(x,tr().limitTitle,CHAT_STATES.FAILED);return;}
          else if(o.error){streamFailure=o.reply||null;break;}
          else if(o.done){x.done=true;break;}
        }
        if(streamFailure||x.done){try{await reader.cancel();}catch(_){}break;}
      }
      if(streamFailure)ChatLifecycle.fail(x,streamFailure,x.full?CHAT_STATES.INTERRUPTED:CHAT_STATES.FAILED);
      else if(x.done){ChatLifecycle.complete(x);refreshCoreAfterPersistedTurn();}
      else ChatLifecycle.fail(x,null,x.full?CHAT_STATES.INTERRUPTED:CHAT_STATES.FAILED);
    } else {
      const data=await res.json();
      if(data.limit_reached){showLimit(data.hours_left||24);ChatLifecycle.fail(x,tr().limitTitle,CHAT_STATES.FAILED);}
      else if(data.reply){ChatLifecycle.content(x,data.reply);ChatLifecycle.complete(x);refreshCoreAfterPersistedTurn();}
      else throw new Error('malformed_chat_response');
    }
  }catch(e){
    if(x.state!==CHAT_STATES.CANCELLED)
      ChatLifecycle.fail(x,null,x.full?CHAT_STATES.INTERRUPTED:CHAT_STATES.FAILED);
  }
  finally{if(x.watchdog)clearTimeout(x.watchdog);}
}
function afterReply(text,speechText=''){
  const m=memLoad();
  if(/ккал|kcal|калории|protein|протеин/i.test(text)&&/\|/.test(text)){m.lastNutritionAt=Date.now();witness('modelChanged');}
  m.lastConsultationAt=Date.now(); memSave(m);
  // Event-driven: the conversation pipeline announces a completed reply. The Voice
  // Controller (below) subscribes; nothing here knows or cares that voice exists.
  try{ if(window.VoiceBus) window.VoiceBus.emit('reply',{text:speechText||text}); }catch(_){}
}

/* ══════════════════════════════════════════════════════════════════════════
   VOICE CONTROLLER — one activation button → greeting → listen → Brain → speak.
   • STT: native browser SpeechRecognition (unchanged).
   • Reasoning: the EXISTING /chat pipeline (SESSION_START for the greeting; the
     existing send() for every turn). Brain / Athlete Model / Personality untouched.
   • Output: OpenAI TTS via the provider-independent /speak → voice adapter.
   • The frozen Living Core reacts only through facts it already consumes (witness()).
   ═══════════════════════════════════════════════════════════════════════════ */
window.VoiceBus = { _l:{}, on(e,f){(this._l[e]=this._l[e]||[]).push(f);}, emit(e,d){(this._l[e]||[]).forEach(f=>{try{f(d);}catch(_){}});} };

/* OUTPUT — provider-independent (talks to /speak). Exactly ONE active audio
   stream: every speak() supersedes any previous request AND playback via a
   generation counter, so responses are never queued or overlapped. Throws on
   TTS failure so the state machine can surface ERROR + retry. */
const VoiceOut = {
  _audio:null, _pulse:null, _gen:0, _res:null,
  get playing(){ return !!this._audio; },
  async speak(text){
    this.stop();                                   // cancel whatever was playing — never queue
    const gen=++this._gen;
    if(!text) return;
    const r=await fetch('/speak',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',
      body:JSON.stringify({text:text,lang:lang,voice:VoiceReg.ttsId()})});
    if(gen!==this._gen) return;                    // superseded while the request was in flight
    if(!r.ok) throw new Error('tts_'+r.status);
    const url=URL.createObjectURL(await r.blob());
    if(gen!==this._gen){ URL.revokeObjectURL(url); return; }
    await new Promise((res)=>{
      this._res=res;
      const a=new Audio(url); this._audio=a;
      this._pulse=setInterval(()=>witness('replyToken'),120);   // Core visibly SPEAKS while audio plays
      const done=()=>{ if(this._pulse){clearInterval(this._pulse);this._pulse=null;} URL.revokeObjectURL(url); if(this._audio===a)this._audio=null; this._res=null; res(); };
      a.onended=done; a.onerror=done; a.play().catch(done);
    });
  },
  /* Instant cancel — also resolves any pending speak() promise (pause() alone
     never fires onended), so an interrupted turn unwinds cleanly. */
  stop(){ this._gen++; if(this._pulse){clearInterval(this._pulse);this._pulse=null;} if(this._audio){try{this._audio.pause();}catch(_){}} this._audio=null; if(this._res){const r=this._res;this._res=null;r();} }
};

/* INPUT — native SpeechRecognition. interimResults let the machine detect the
   user starting to talk (barge-in); the final transcript is the user's turn.
   One recognizer instance at a time. Callbacks: {onInterim,onFinal,onError,onEnd}. */
const VoiceIn = {
  _rec:null,
  get supported(){ return !!(window.SpeechRecognition||window.webkitSpeechRecognition); },
  start(cb){
    const SR=window.SpeechRecognition||window.webkitSpeechRecognition; if(!SR){ cb.onError&&cb.onError('unsupported'); return false; }
    this.stop();
    const r=new SR(); this._rec=r;
    r.lang=(lang==='en')?'en-US':'bg-BG'; r.interimResults=true; r.maxAlternatives=1; r.continuous=false;
    witness('keystroke');       // the Core visibly LISTENS (attention rises), same as when typing
    r.onresult=(e)=>{
      let interim='', final='';
      for(let i=e.resultIndex;i<e.results.length;i++){ const res=e.results[i], t=(res[0]&&res[0].transcript)||''; if(res.isFinal)final+=t; else interim+=t; }
      if(interim.trim()&&cb.onInterim) cb.onInterim(interim.trim());
      if(final.trim()&&cb.onFinal) cb.onFinal(final.trim());
    };
    r.onerror=(e)=>{ if(cb.onError) cb.onError((e&&e.error)||'error'); };
    r.onend=()=>{ if(this._rec===r) this._rec=null; if(cb.onEnd) cb.onEnd(); };
    try{ r.start(); }catch(_){ if(cb.onError) cb.onError('start_failed'); return false; }
    return true;
  },
  get active(){ return !!this._rec; },
  stop(){ if(this._rec){ try{this._rec.onend=null;this._rec.onresult=null;this._rec.onerror=null;this._rec.stop();}catch(_){} this._rec=null; } }
};

/* ══════════════════════════════════════════════════════════════════════════
   VOICE STATE MACHINE — one deterministic machine, one source of truth.
   States: IDLE · LISTENING · THINKING · SPEAKING · INTERRUPTED · ERROR.
   `Voice.on` = session on/off; `Voice.state` = the ONLY state flag (no dup flags).
   Barge-in: while SPEAKING a recognizer is armed; the instant the user speaks we
   cancel TTS and drop to LISTENING — APEX never reads over the user.
   ══════════════════════════════════════════════════════════════════════════ */
function _helix(){ return document.getElementById('mic-btn'); }

/* Voice registry — selectable, persisted, extensible. Maps a coach name to a
   provider voice id passed to /speak (honoured once the backend reads it). */
const VoiceReg = {
  catalog:[
    {id:'alpha', tts:'ash',   label:{bg:'Coach Alpha — енергичен', en:'Coach Alpha — energetic'}},
    {id:'calm',  tts:'alloy', label:{bg:'Coach Calm — спокоен',    en:'Coach Calm — calm'}}
  ],
  current(){ const v=localStorage.getItem('apexVoice'); return this.catalog.some(x=>x.id===v)?v:this.catalog[0].id; },
  set(id){ if(this.catalog.some(x=>x.id===id)) localStorage.setItem('apexVoice',id); },
  ttsId(){ const c=this.catalog.find(x=>x.id===this.current()); return c?c.tts:'alloy'; }
};

const BARGE_GUARD_MS=650;   // ignore the mic for the first moment of playback (reduce self-trigger)
const MAX_RECOG_RETRY=3;    // bounded mic auto-recovery on silence / soft errors

const Voice = {
  on:false, state:'IDLE', _spokeAt:0, _retry:0,
  _labels(){ return (lang==='bg')
    ? {IDLE:'Говори с APEX',LISTENING:'Слушам те…',THINKING:'APEX мисли…',SPEAKING:'APEX говори — докосни за край',INTERRUPTED:'Слушам те…',ERROR:'Проблем с гласа — докосни за нов опит'}
    : {IDLE:'Talk to APEX',LISTENING:'Listening…',THINKING:'APEX is thinking…',SPEAKING:'APEX is speaking — tap to end',INTERRUPTED:'Listening…',ERROR:'Voice problem — tap to retry'}; },

  /* the ONLY place state changes — deterministic UI + a11y announcement (aria-live) */
  set(next){
    this.state=next;
    const b=_helix(); if(!b) return;
    b.setAttribute('data-state', next.toLowerCase());
    b.setAttribute('aria-pressed', next==='IDLE'?'false':'true');
    const lb=this._labels()[next]||''; b.setAttribute('aria-label', lb);
    const st=document.getElementById('mic-status'); if(st) st.textContent=(next==='IDLE')?'':lb;
  },

  /* ── session control (mic button) ── */
  start(){
    if(this.on) return; this.on=true; this._retry=0;
    try{ new Audio().play().catch(()=>{}); }catch(_){}   // unlock audio inside the user gesture
    if(!VoiceIn.supported) toast(lang==='bg'?'Разпознаването на реч не се поддържа тук — APEX ще говори, ти пиши.':'Speech recognition isn’t supported here — APEX will speak, you type.');
    this.greet();
  },
  stop(){ this.on=false; VoiceIn.stop(); VoiceOut.stop(); this.set('IDLE'); },
  toggle(){ this.on ? this.stop() : this.start(); },

  /* ── greeting via the SINGLE /chat entry point (SESSION_START) ── */
  async greet(){
    this.set('THINKING');
    const h=new Date().getHours();
    const daypart=h<5?'night':h<12?'morning':h<18?'afternoon':'evening';
    const body={session_start:true,lang:lang,daypart:daypart,history:(typeof getHistory==='function'?getHistory():[])};
    try{ const p=pfLoad(); if(p&&Object.keys(p).length)body.profile=p; }catch(_){}
    const token=localStorage.getItem('apexToken')||''; if(token)body.token=token;
    const x=ChatLifecycle.begin('',{voice:true,sessionStart:true},body.history);
    if(!x){this.set('ERROR');return;}
    await runChatExchange(x,body);
  },

  /* ── SPEAK one reply — single stream, barge-in armed from the first word ── */
  async say(text){
    if(!this.on) return;
    if(!text){ this.set('LISTENING'); this.listen(); return; }
    this.set('SPEAKING'); this._spokeAt=Date.now();
    this.listen();                       // arm recognizer NOW → barge-in possible immediately
    try{
      await VoiceOut.speak(text);        // exactly one active stream; a new say() cancels this
    }catch(e){
      if(this.on) this._ttsError(); return;
    }
    if(!this.on) return;
    if(this.state==='SPEAKING'){ this.set('LISTENING'); this.listen(); }   // natural end → keep listening
  },

  /* ── LISTEN (arm/keep exactly one recognizer) ── */
  listen(){
    if(!this.on || !VoiceIn.supported) return;
    if(VoiceIn.active) return;            // barge-in shares this recognizer; don't double-arm
    VoiceIn.start({
      onInterim:(t)=>this._onInterim(t),
      onFinal:(t)=>this._onFinal(t),
      onError:(err)=>this._onRecogError(err),
      onEnd:()=>this._onRecogEnd()
    });
  },

  /* user started talking → if APEX is speaking, cut it off this instant (barge-in) */
  _onInterim(t){
    if(!this.on) return;
    if(this.state==='SPEAKING' && (Date.now()-this._spokeAt)>BARGE_GUARD_MS){
      VoiceOut.stop();                   // stop TTS immediately
      this.set('INTERRUPTED');           // transient marker
      this.set('LISTENING');             // → straight back to listening (same recognizer keeps running)
    }
  },
  /* final user utterance → THINKING, then the existing /chat pipeline */
  _onFinal(t){
    if(!this.on || !t) return;
    if(this.state==='SPEAKING') VoiceOut.stop();   // barge-in caught only at the final result
    this._retry=0;
    VoiceIn.stop();
    this.set('THINKING');
    const inp=document.getElementById('user-in');
    if(inp){ inp.value=t; send({voice:true}); }      // EXISTING pipeline: Brain + Athlete + Personality + storage + Core facts
  },
  _onRecogError(err){
    if(!this.on) return;
    if(err==='not-allowed'||err==='service-not-allowed'){          // hard permission failure
      this.set('ERROR'); toast(lang==='bg'?'Няма достъп до микрофона.':'Microphone access is blocked.'); this.stop(); return;
    }
    // soft failure (no-speech / aborted / network) → recover, bounded; never lock the mic
    if(this.state==='LISTENING' && this._retry<MAX_RECOG_RETRY){ this._retry++; setTimeout(()=>{ if(this.on&&this.state==='LISTENING') this.listen(); },250); }
    else if(this.state==='LISTENING'){ this.set('IDLE'); }         // give up quietly; a tap restarts
  },
  _onRecogEnd(){
    // recognizer ended itself while we still want input → re-arm (bounded) so silence never locks the mic
    if(this.on && this.state==='LISTENING' && !VoiceIn.active && this._retry<MAX_RECOG_RETRY){ this._retry++; setTimeout(()=>{ if(this.on&&this.state==='LISTENING'&&!VoiceIn.active) this.listen(); },200); }
  },
  _ttsError(){
    this.set('ERROR');
    toast(lang==='bg'?'Гласът е временно недостъпен — докосни, за да опиташ пак.':'Voice is temporarily unavailable — tap to retry.');
    if(this.on) this.listen();           // never lock the mic — keep the conversation open
  }
};

/* thin global wrappers — the mic button + reply bus keep their existing hooks */
function voiceToggle(){ Voice.toggle(); }
window.VoiceBus.on('reply', ({text})=>{ if(Voice.on) Voice.say(text); });

/* ═══════════════════════════════════════════════════════════════════
   NOTICES + FEEDBACK
   ═══════════════════════════════════════════════════════════════════ */
function lockSending(on){
  sendLocked=on;
  const inp=document.getElementById('user-in'), btn=document.querySelector('.send-btn');
  if(inp){inp.disabled=on;inp.style.opacity=on?'0.5':'';}
  if(btn){btn.style.opacity=on?'0.5':'';}
}
function showLimit(h){const t=tr();
  lockSending(true);                    // disable sending only — nav, menu, profile, history stay live
  document.getElementById('nt-ico').textContent='⏳';
  document.getElementById('nt-title').textContent=t.limitTitle;
  document.getElementById('nt-desc').textContent=t.limitDesc.replace('{h}',h||24);
  // Primary action goes straight to the unlock path — never back to a dead chat.
  document.getElementById('nt-extra').innerHTML=
    '<button class="save" onclick="closeNotice();showSubscription();">'+t.unlock+'</button>';
  const ok=document.getElementById('nt-ok');ok.textContent=lang==='bg'?'Разгледай по-късно':'Maybe later';ok.onclick=closeNotice;
  document.getElementById('notice-modal').classList.add('on');}
let fbRating=0;
function openFeedback(){const t=tr();document.getElementById('nt-ico').textContent='✦';
  document.getElementById('nt-title').textContent=t.fbTitle;document.getElementById('nt-desc').textContent=t.fbDesc;
  fbRating=0;
  document.getElementById('nt-extra').innerHTML='<div class="fb-stars" id="fb-stars">'+[1,2,3,4,5].map(n=>'<span class="fb-star" data-n="'+n+'" onclick="setStars('+n+')">★</span>').join('')+'</div>'+
    '<div class="field"><textarea id="fb-text" rows="4" placeholder="…"></textarea></div>';
  const ok=document.getElementById('nt-ok');ok.textContent=t.fbSend;ok.onclick=sendFeedback;
  document.getElementById('notice-modal').classList.add('on');
  setTimeout(()=>{const f=document.getElementById('fb-text');if(f)f.focus();},200);}
function setStars(n){fbRating=n;document.querySelectorAll('#fb-stars .fb-star').forEach(s=>s.classList.toggle('on',+s.dataset.n<=n));}
async function sendFeedback(){const el=document.getElementById('fb-text');const txt=el?el.value.trim():'';
  if(!txt&&!fbRating){closeNotice();return;}
  try{
    const r=await fetch('/feedback',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({type:txt?'improvement':'positive',message:txt,rating:fbRating,lang})});
    if(!r.ok)throw new Error('feedback_'+r.status);
    closeNotice();toast(tr().fbThanks);
  }catch(e){toast('Feedback could not be sent.');}
}
function closeNotice(){document.getElementById('notice-modal').classList.remove('on');}
let toastTimer;function toast(msg){const el=document.getElementById('toast');el.textContent=msg;el.classList.add('on');clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.classList.remove('on'),2600);}

/* ═══════════════════════════════════════════════════════════════════
   INTENT ROUTING — landing → app continuity
   ═══════════════════════════════════════════════════════════════════ */
const GOAL_FROM_LANDING={burn:'fat_loss',zero:'general',growth:'muscle_gain',build:'strength'};
function applyIntent(){
  const q=new URLSearchParams(location.search);
  // language
  const ul=q.get('lang'); if(ul==='bg'||ul==='en'){lang=ul;localStorage.setItem('apexLang',lang);}
  // goal from landing goal-cards → pre-seed profile goal
  const g=q.get('goal'); if(g&&GOAL_FROM_LANDING[g]){const p=pfLoad();if(!p.goal){p.goal=GOAL_FROM_LANDING[g];ownedStorageSet('apexProfile',JSON.stringify(p));}}
  // Stripe return → poll for token (payment flow preserved)
  const ps=q.get('pending_session'); if(ps)pollToken(ps);
  // explicit intent
  const intent=q.get('intent')||'';
  const seedQ=q.get('q');
  // strip query so refresh doesn't replay
  if(location.search)history.replaceState(null,'',location.pathname);
  return{intent,seedQ,g};
}
function pollToken(sid){
  let tries=0;const iv=setInterval(()=>{tries++;
    fetch('/poll-token?session_id='+encodeURIComponent(sid)).then(r=>r.json()).then(d=>{
      if(d.ready&&d.token){localStorage.setItem('apexToken',d.token);clearInterval(iv);toast(lang==='bg'?'Достъпът е активиран ✓':'Access unlocked ✓');document.getElementById('cancel-sub').style.display='block';}
      else if(tries>20)clearInterval(iv);
    }).catch(()=>{if(tries>20)clearInterval(iv);});
  },1500);
}

/* ═══════════════════════════════════════════════════════════════════
   BOOT
   ═══════════════════════════════════════════════════════════════════ */
let core,humanCoreView,appStartupStarted=false;
async function startApp(){
  if(appStartupStarted)return;
  appStartupStarted=true;
  core=new LivingCore(document.getElementById('core'));
  core.setPhysiology(computePhysiology()); core.start();
  humanCoreView=new HumanCoreView(document.getElementById('human-core'),document.getElementById('core'),core);
  humanCoreView.start();

  // ── SENSES: the interface reports FACTS to the nervous system. It never
  // commands the body. Typing is not a cause — attention is. Movement is not
  // a cause — curiosity is. The model decides what everything means.
  const orgNorm=e=>{const rect=document.getElementById('human-core').getBoundingClientRect(),R=Math.min(rect.width,rect.height)*.34;
    return {x:(e.clientX-(rect.left+rect.width*.5))/R,y:(e.clientY-(rect.top+rect.height*.46))/R};};
  window.addEventListener('pointermove',e=>witness('pointer',orgNorm(e)),{passive:true});
  // Physical contact — a fact about the world touching the body. Never reported
  // from interactive surfaces or scroll containers: the body yields to the UI.
  window.addEventListener('pointerdown',e=>{
    if(e.target.closest('button,a,input,select,textarea,label,.modal,.sheet,#drawer,#drawer-scrim,.chip,.msg,.inputbar,#jump-latest,#workout,#feed,nav'))return;
    witness('contact',orgNorm(e));
  },{passive:true});
  // Absence and return are facts; goodbye and welcome are the model's readings.
  const seen=()=>{try{localStorage.setItem('apexLastSeen',String(Date.now()));}catch(e){}};
  document.addEventListener('visibilitychange',()=>{
    witness('visibility',{hidden:document.hidden});
    if(document.hidden)seen();
    else{const gap=Date.now()-(+localStorage.getItem('apexLastSeen')||Date.now());
      if(gap>30*60000)witness('returned',{days:gap/864e5});}
  });
  window.addEventListener('pagehide',seen);
  setInterval(seen,60000);
  try{ // arriving after a real absence: found resting, then the reunion registers
    const last=+localStorage.getItem('apexLastSeen')||0;
    if(last&&Date.now()-last>6*3600e3){
      core.athlete.presence=0.02;          // initial condition: no one was here
      core.presence.base='resting';
      setTimeout(()=>witness('returned',{days:(Date.now()-last)/864e5}),1200);
    }
  }catch(e){}
  seen();

  const tokenAccess=await bootstrapAccessToken();
  const intent=applyIntent();
  applyLang();
  const _uin=document.getElementById('user-in');
  _uin.addEventListener('keydown',e=>{witness('keystroke');if(e.key==='Enter'){e.preventDefault();send();}});
  _uin.addEventListener('focus',()=>witness('keystroke'));
  document.querySelectorAll('.modal').forEach(m=>m.addEventListener('click',e=>{if(e.target===m)m.classList.remove('on');}));
  // scroll ownership: user scrolling up releases auto-follow + offers "Jump to latest";
  // reaching the bottom re-arms auto-follow and hides the button.
  document.getElementById('feed').addEventListener('scroll',()=>ChatLifecycle.userScrolled(),{passive:true});
  // Esc closes drawer/panels
  document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeMenu();closePanel();}});
  // ── Server-authoritative session on every load ──
  const q=new URLSearchParams(location.search);
  if(q.get('auth')==='ok'){ toast(tr().auth.welcome); }
  else if(q.get('auth')==='invalid'){ toast(tr().auth.linkBad); }
  loadSession(tokenAccess).then(()=>{
    if(location.search.match(/auth=/)) history.replaceState(null,'',location.pathname);
    // First-run and landing intent decisions use the restored account state.
    const hasProfile=!!ownedStorageGet('apexProfile');
    if(!hasProfile){setTimeout(()=>{if(!ownedStorageGet('apexProfile'))openProfile(0);},900);}
    const planSeed={fat_loss:lang==='bg'?'Направи ми план за сваляне на мазнини':'Build me a fat-loss plan',
      muscle_gain:lang==='bg'?'Направи ми план за мускулна маса':'Build me a muscle-building plan',
      strength:lang==='bg'?'Направи ми силова програма':'Build me a strength program',
      general:lang==='bg'?'Направи ми план за начинаещ':'Build me a beginner plan'};
    const landingGoal=intent.g&&GOAL_FROM_LANDING[intent.g]?GOAL_FROM_LANDING[intent.g]:null;
    if(intent.intent==='profile'){setTimeout(()=>openProfile(0),300);}
    else if(intent.intent==='workout'||intent.intent==='train'){if(hasProfile)setTimeout(intentTrain,400);}
    else if(intent.intent==='nutrition'){if(hasProfile)setTimeout(()=>enterConsult(lang==='bg'?'Направи ми хранителен план':'Build me a nutrition plan'),400);}
    else if(intent.seedQ){if(hasProfile)setTimeout(()=>enterConsult(intent.seedQ),400);}
    else if(intent.intent==='consult'||landingGoal){if(hasProfile)setTimeout(()=>enterConsult(landingGoal?planSeed[landingGoal]:''),400);}
  });
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',startApp,{once:true});
else startApp();
