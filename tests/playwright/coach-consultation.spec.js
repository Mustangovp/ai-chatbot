const {test,expect}=require('@playwright/test');
const cp=require('node:child_process');
const path=require('node:path');
const root=path.resolve(__dirname,'../..');
const cached=new Map();

function conversation(language){
  if(cached.has(language))return cached.get(language);
  const source=String.raw`
import os,sys,json,tempfile,socket
from contextlib import ExitStack
from types import SimpleNamespace as NS
sys.path.insert(0,sys.argv[1])
def denied(*a,**k): raise RuntimeError('provider_network_forbidden')
socket.socket.connect=denied;socket.create_connection=denied
with ExitStack() as resources:
    directory=resources.enter_context(tempfile.TemporaryDirectory(prefix='apex_consult_browser_',dir='C:/tmp'))
    os.environ.update(DATABASE_URL='sqlite:///'+directory.replace('\\','/')+'/fixture.db',
        OPENAI_API_KEY='offline-only',OPENAI_BASE_URL='http://127.0.0.1:9/v1',APEX_SECRET='synthetic-consult-browser',
        PAID_ACCESS_ENABLED='false',APEX_LIVE_VOICE_ENABLED='false',BRAIN_ENFORCE='true',BRAIN_SHADOW='false',
        TRAINING_ENGINE_ACTIVE='true',CONVERSATION_COMPOSER_ACTIVE='false')
    import app,db,nutrition_intent as ni
    resources.callback(db.engine.dispose)
    db.init_db();lang=sys.argv[2]
    messages=(['Обмислям да сваля 20+ кг за 1 месец. Не създавай план. Нека обсъдим по-безопасен срок.','какъв срок?','37г 120кг'] if lang=='bg' else
        ['I am considering losing 20+ kg in 1 month. Do not create a plan. Let us discuss a safer timeline.','What timeframe?','37 years old, 120 kg'])
    annotations={messages[0]:{'target_kg':20},messages[2]:{'age':37,'weight_kg':120}}
    def semantic(_client,prompt):
        data=json.loads(prompt[-1]['content']);facts={}
        turns=[*data['conversation'],{'role':'user','content':data['message']}]
        for index,turn in enumerate(turns):
            if turn['role']=='user':
                for key,value in annotations.get(turn['content'],{}).items(): facts[key]=[value,index]
        return NS(choices=[NS(finish_reason='stop',message=NS(content=json.dumps({
            'scope':'timeline_consultation','requested_goal':None,'consultation':facts})))])
    ni._request=semantic
    calls=[];learning=[]
    def forbidden(**kwargs): calls.append(True);raise RuntimeError('no_plan_or_coach_generation')
    app.client.chat.completions.create=forbidden
    app._update_learning_engine=lambda *args:learning.append(True)
    uid=db.get_or_create_user('synthetic-consult-browser@example.test');db.save_profile(uid,{'goal':'strength'})
    client=app.app.test_client();client.set_cookie(app.SESSION_COOKIE,db.create_session(uid))
    replies=[]
    for message in messages:
        response=client.post('/chat',json={'message':message,'lang':lang,'conversation_id':'browser-continuation'})
        assert response.status_code==200
        replies.append({'message':message,'sse':response.get_data(as_text=True)})
    print('APEX_CONSULT='+json.dumps({'replies':replies,'plans':len(db.list_nutrition_plans(uid)),
        'profile':db.get_profile(uid),'history':len(db.list_conversation(uid)),'provider_calls':len(calls),
        'learning_calls':len(learning)},ensure_ascii=True))
`;
  const output=cp.execFileSync(process.env.APEX_TEST_PYTHON||'python',['-c',source,root,language],
    {cwd:root,encoding:'utf8',env:{...process.env,PYTHONIOENCODING:'utf-8',PYTHONDONTWRITEBYTECODE:'1'}});
  const line=output.split(/\r?\n/).find(line=>line.startsWith('APEX_CONSULT='));
  const result=JSON.parse(line.slice('APEX_CONSULT='.length));cached.set(language,result);return result;
}

for(const language of ['bg','en'])for(const width of [1440,390,360])test(`${language} ${width}: persisted three-turn consultation stays useful and non-prescriptive`,async({page})=>{
  const fixture=conversation(language);
  expect(fixture).toMatchObject({plans:0,profile:{goal:'strength'},history:6,provider_calls:0,learning_calls:0});
  await page.setViewportSize({width,height:width===1440?900:844});
  await page.route('https://**/*',route=>route.abort());
  await page.route('**/auth/me',route=>route.fulfill({json:{authenticated:true,email:'synthetic-consult-browser@example.test',plan:'free',status:'free'}}));
  await page.route('**/api/profile',route=>route.fulfill({json:{profile:{goal:'strength',language,level:'intermediate',equipment:'home',frequency:'3'},training_constraint_records:[]}}));
  await page.route('**/api/history',route=>route.fulfill({json:{workouts:[],nutrition:[]}}));
  await page.route('**/api/conversations?*',route=>route.fulfill({json:{messages:[]}}));
  await page.route('**/api/athlete-model',route=>route.fulfill({json:{}}));
  let sent=0;
  await page.route('**/chat',route=>{
    const reply=fixture.replies[sent++];expect(route.request().postDataJSON().message).toBe(reply.message);
    return route.fulfill({contentType:'text/event-stream',body:reply.sse});
  });
  await page.goto('/app?lang='+language);
  await expect.poll(()=>page.evaluate(()=>DATA_OWNER.kind)).toBe('account');
  await page.evaluate(()=>{enterConsult('');document.getElementById('profile-modal').classList.remove('on');});
  for(let index=0;index<fixture.replies.length;index++){
    await page.locator('#user-in').fill(fixture.replies[index].message);await page.locator('.send-btn').click();
    await expect.poll(()=>page.evaluate(()=>ChatLifecycle.current?.state)).toBe('COMPLETED');
    const reply=page.locator('#feed .msg.a').last();
    if(index===1)await expect(reply).toContainText('20-40');
    if(index===2){
      await expect(reply).toContainText(language==='bg'?'37 г.':'37 years');
      await expect(reply).toContainText(language==='bg'?'120 кг':'120 kg');
      const pending=(await reply.textContent()).split(language==='bg'?'Остава да уточним:':'Still missing:')[1];
      expect(pending).not.toMatch(language==='bg'?/възраст|текущо тегло/:/age|current weight/);
    }
    await expect(reply.locator('.workout-protocol,.nutri,.start-workout')).toHaveCount(0);
    await expect(page.locator('#user-in')).toBeVisible();
  }
  expect(sent).toBe(3);expect(await page.evaluate(()=>pfLoad().goal)).toBe('strength');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
});
