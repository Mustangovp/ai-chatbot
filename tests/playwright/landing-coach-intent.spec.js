const {test,expect}=require('@playwright/test');
const cp=require('node:child_process');
const path=require('node:path');

const root=path.resolve(__dirname,'../..');
const profile={goal:'strength',age:'33',weight:'76',height:'178',gender:'male',
  level:'intermediate',equipment:'home',frequency:'3',activityLevel:'moderate',
  sleepQuality:'good',stressLevel:'low',recoveryFeel:'fresh'};
const fixtures=new Map();

function flaskFixture(language,timeline){
  const key=language+timeline;
  if(fixtures.has(key))return fixtures.get(key);
  const source=String.raw`
import os,sys,tempfile,json,socket
from types import SimpleNamespace as NS
from contextlib import ExitStack
sys.path.insert(0,sys.argv[1])
def denied(*a,**k): raise RuntimeError('provider_network_forbidden')
socket.socket.connect=denied
socket.create_connection=denied
with ExitStack() as resources:
    directory=resources.enter_context(tempfile.TemporaryDirectory(prefix='apex_landing_intent_'))
    os.environ.update(DATABASE_URL='sqlite:///'+directory.replace('\\','/')+'/fixture.db',
        OPENAI_API_KEY='offline-test-only',OPENAI_BASE_URL='http://127.0.0.1:9/v1',
        APEX_SECRET='isolated-browser-fixture',PAID_ACCESS_ENABLED='false',
        BRAIN_ENFORCE='false',BRAIN_SHADOW='false',CONVERSATION_COMPOSER_ACTIVE='false',
        APEX_NEXT_MOVE_ENABLED='false',APEX_LIVE_VOICE_ENABLED='false')
    import app as appmod,db as store,nutrition_intent as intent
    resources.callback(store.engine.dispose)
    store.init_db()
    language=sys.argv[2]; timeline=sys.argv[3]=='true'
    profile=json.loads(sys.argv[4])
    uid=store.get_or_create_user('synthetic-landing-browser@example.test')
    store.save_profile(uid,profile)
    appmod._update_learning_engine=lambda *a,**k:None
    def semantic(_client,messages):
        return NS(choices=[NS(finish_reason='stop',message=NS(content=json.dumps({
            'scope':'timeline_consultation' if timeline else 'daily_plan',
            'requested_goal':None if timeline else 'fat_loss'})))])
    intent._request=semantic
    calls=[]
    def no_generation(**kwargs):
        calls.append(True)
        raise RuntimeError('consultation_must_not_generate')
    appmod.client.chat.completions.create=no_generation
    if language=='bg':
        message=('Обмислям да сваля 20+ кг за 1 месец. Не създавай план за този срок. Нека обсъдим по-безопасен, персонален срок.' if timeline else
            'Искам да сваля 3 кг за 1 месец. Дай ми реалистичен план за хранене и движение, който се вписва в ежедневието ми.')
    else:
        message=('I am considering losing 20+ kg in 1 month. Do not create a plan for this timeline. Let us discuss a safer, personalized timeline.' if timeline else
            'I want to lose 3 kg in 1 month. Give me a realistic nutrition and movement plan that fits everyday life.')
    client=appmod.app.test_client()
    client.set_cookie(appmod.SESSION_COOKIE,store.create_session(uid))
    response=client.post('/chat',json={'message':message,'lang':language,'first_contact':True})
    print('APEX_FIXTURE='+json.dumps({'status':response.status_code,'sse':response.get_data(as_text=True),
        'message':message,'plans':len(store.list_nutrition_plans(uid)),
        'goal':store.get_profile(uid)['goal'],'generation_calls':len(calls)},ensure_ascii=True))
`;
  const stdout=cp.execFileSync(process.env.APEX_TEST_PYTHON||'python',
    ['-c',source,root,language,String(timeline),JSON.stringify(profile)],
    {cwd:root,encoding:'utf8',env:{...process.env,PYTHONIOENCODING:'utf-8',PYTHONDONTWRITEBYTECODE:'1'}});
  const line=stdout.split(/\r?\n/).find(line=>line.startsWith('APEX_FIXTURE='));
  const fixture=JSON.parse(line.slice('APEX_FIXTURE='.length));
  fixtures.set(key,fixture);return fixture;
}

for(const language of ['bg','en'])for(const width of [1440,390,360])for(const timeline of [false,true]){
  test(`${language} ${width}: real Flask ${timeline?'timeline consultation':'goal clarification'} renders without a prescription`,async({page})=>{
    const fixture=flaskFixture(language,timeline);
    expect(fixture).toMatchObject({status:200,plans:0,goal:'strength',generation_calls:0});
    await page.setViewportSize({width,height:width===1440?900:width===390?844:800});
    await page.route(/googletagmanager\.com|google-analytics\.com/,route=>route.abort());
    await page.route('**/auth/me',route=>route.fulfill({json:{authenticated:true,email:'synthetic-landing-browser@example.test',plan:'free',status:'free'}}));
    await page.route('**/api/profile',route=>route.fulfill({json:{profile:{...profile,language},training_constraint_records:[],training_constraint_load_state:'ready'}}));
    await page.route('**/api/history',route=>route.fulfill({json:{workouts:[],nutrition:[]}}));
    await page.route('**/api/conversations?*',route=>route.fulfill({json:{messages:[]}}));
    await page.route('**/api/athlete-model',route=>route.fulfill({json:{}}));
    let sent=0;
    await page.route('**/chat',route=>{
      expect(route.request().postDataJSON().message).toBe(fixture.message);sent++;
      return route.fulfill({contentType:'text/event-stream',body:fixture.sse});
    });
    await page.goto('/app?lang='+language);
    await expect.poll(()=>page.evaluate(()=>DATA_OWNER.kind)).toBe('account');
    await page.evaluate(()=>{enterConsult('');document.getElementById('profile-modal').classList.remove('on');});
    await page.locator('#user-in').fill(fixture.message);
    await page.locator('.send-btn').click();
    await expect.poll(()=>page.evaluate(()=>ChatLifecycle.current?.state)).toBe('COMPLETED');
    const reply=page.locator('#feed .msg.a').last();
    await expect(reply).toContainText(timeline?(language==='bg'?'по-безопасен срок':'safer timeline'):
      (language==='bg'?'Записаната ти цел':'Your saved goal'));
    await expect(reply.locator('.workout-protocol,.nutri,.start-workout')).toHaveCount(0);
    await expect(reply).not.toContainText(/2580|Daily Total|Общо в плана|не мога да предоставя пълен дневен/i);
    expect(sent).toBe(1);
    expect(await page.evaluate(()=>pfLoad().goal)).toBe('strength');
    expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
    await expect(page.locator('#user-in')).toBeVisible();
  });
}
