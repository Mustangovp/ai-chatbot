const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const cp=require('node:child_process');
const {project}=require('../static/holographic_hud.js');
for(const language of ['bg','en']){
  test('H1 '+language+': numbers come only from the supported profile frequency enum',()=>{
    for(const frequency of ['2','3','4','5','6',3]){
      const profile=Object.freeze({level:'intermediate',frequency,recovery:99,readiness:100,position:88});
      const value=project(profile,language,{authenticated:true});
      assert.equal(value.frequencyAvailable,true);assert.ok(value.frequencyValue.startsWith(String(frequency)+' '));
      assert.equal(value.levelAvailable,true);assert.doesNotMatch(JSON.stringify(value),/99|100|88/);
    }
  });
  test('H1 '+language+': missing, stale physiological and malformed inputs cannot manufacture values',()=>{
    for(const profile of [null,[],{}, {frequency:99,level:'ELITE'}, {frequency:'3.5'}, {frequency:true},
      {frequency:{value:3}}, {frequency:'<img src=x>',level:'<b>Advanced</b>'},
      {recoveryFeel:'fresh',readiness:100,updated_at:'2000-01-01T00:00:00Z'}]){
      const value=project(profile,language);assert.equal(value.frequencyAvailable,false);
      assert.equal(value.levelAvailable,false);assert.equal(value.frequencyValue,value.missing);
      assert.equal(value.levelValue,value.missing);assert.doesNotMatch(JSON.stringify(value),/2000|100|<img|ELITE/);
    }
  });
  test('H1 '+language+': provenance distinguishes demo, account and browser without changing inputs',()=>{
    const profile={frequency:'3',level:'beginner'},before=JSON.stringify(profile);
    const browser=project(profile,language),account=project(profile,language,{authenticated:true});
    const demo=project(profile,language,{authenticated:true,demo:true});
    assert.notEqual(account.source,browser.source);assert.match(demo.source,/DEMO/);
    assert.equal(JSON.stringify(profile),before);
  });
}
test('H1 original Core engines, renderer, pointer capture and canvas placement are frozen',()=>{
  const base=cp.execFileSync('git',['show','953869323ccac55d8f7f57eb17b05ef52df8561e:templates/apex.html'],{encoding:'utf8'}).replace(/\r\n/g,'\n');
  const current=fs.readFileSync(require('node:path').join(__dirname,'../templates/apex.html'),'utf8').replace(/\r\n/g,'\n');
  for(const [start,end]of [['class BreathEngine{','function witness('],['  const orgNorm=e=>','  // Absence and return'],['<div id="stage">','<div id="ui">'],['<style>','</style>'],["  core=new LivingCore(",'  const orgNorm=e=>']]){
    if(start==='<div id="stage">'){
      const original=base.slice(base.indexOf(start),base.indexOf('<div id="ui">'));
      const actual=current.slice(current.indexOf(start),current.indexOf(end));
      assert.equal(actual.trim(),original.trim());continue;
    }
    const section=text=>{const from=text.indexOf(start),to=text.indexOf(end,from);assert.ok(from>=0&&to>from);return text.slice(from,to);};
    assert.equal(section(current),section(base));
  }
});

test('HUD has no protected-layer overrides, visual filters, masks or fullscreen overlays',()=>{
  const css=fs.readFileSync(require('node:path').join(__dirname,'../static/holographic_hud.css'),'utf8');
  const html=fs.readFileSync(require('node:path').join(__dirname,'../templates/apex.html'),'utf8');
  assert.doesNotMatch(css,/#(?:stage|core|vignette|grain|grid)\b/);
  assert.doesNotMatch(css,/(?:backdrop-filter|filter|mask(?:-image)?|mix-blend-mode)\s*:|position\s*:\s*fixed/);
  assert.doesNotMatch(html,/id="holo-instrument"|class="holo-(?:scale|orbit|sweep)"/);
});
