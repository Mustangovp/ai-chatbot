/* H1 presentation only: profile inputs are not physiological measurements. */
(function(root){
  'use strict';
  const copy={
    en:{title:'Training context',level:'Experience',frequency:'Planned frequency',week:'/ week',
      missing:'Not provided',account:'Account profile',browser:'This browser',demo:'DEMO profile',
      note:'Self-reported inputs. No verified readiness measurement.'},
    bg:{title:'Тренировъчен контекст',level:'Опит',frequency:'Планирана честота',week:'/ седмица',
      missing:'Непосочено',account:'Профил в акаунта',browser:'В този браузър',demo:'DEMO профил',
      note:'Въведени от теб данни. Няма проверено измерване за готовност.'}
  };
  const levels={en:{beginner:'Beginner',intermediate:'Intermediate',advanced:'Advanced'},
    bg:{beginner:'Начален',intermediate:'Среден',advanced:'Напреднал'}};
  function project(profile,language,options={}){
    const locale=language==='bg'?'bg':'en',c=copy[locale];
    const p=profile&&typeof profile==='object'&&!Array.isArray(profile)?profile:{};
    const frequency=(typeof p.frequency==='string'||typeof p.frequency==='number')?String(p.frequency):'';
    return{...c,source:options.demo?c.demo:options.authenticated?c.account:c.browser,
      levelValue:typeof p.level==='string'&&Object.hasOwn(levels[locale],p.level)?levels[locale][p.level]:c.missing,
      frequencyValue:/^[2-6]$/.test(frequency)?frequency+' '+c.week:c.missing,
      levelAvailable:typeof p.level==='string'&&Object.hasOwn(levels[locale],p.level),
      frequencyAvailable:/^[2-6]$/.test(frequency)};
  }
  function paint(profile,language,options){
    if(!root.document)return;
    const data=project(profile,language,options),text=(id,value)=>{const node=document.getElementById(id);if(node)node.textContent=value;};
    for(const [id,key]of Object.entries({'hud-context-label':'title','hud-level-label':'level','hud-frequency-label':'frequency',
      'hud-level':'levelValue','hud-frequency':'frequencyValue','hud-source':'source','hud-data-note':'note'}))text(id,data[key]);
    for(const key of ['level','frequency']){
      const node=document.getElementById('hud-'+key);
      if(node)node.dataset.available=String(data[key+'Available']);
    }
    document.getElementById('holo-readouts')?.setAttribute('aria-label',data.title);
  }
  const api={project,paint,clear:language=>paint({},language,{})};
  if(typeof module==='object'&&module.exports)module.exports=api;
  else{root.ApexHolographicHud=api;document.addEventListener('DOMContentLoaded',()=>root.paintOverviewHud?.(),{once:true});}
})(typeof window==='object'?window:globalThis);
