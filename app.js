const $=s=>document.querySelector(s),el=(t,c,x)=>{const e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e};
let me=null,mode='login',cur=null,sig={},drafts={},open=new Set(),timer=null,D={feed:[],ev:[],users:[],dm:[]};
const col=id=>{let h=0;for(const c of String(id))h=(h*31+c.charCodeAt(0))%360;return`hsl(${h} 55% 45%)`};
const ago=t=>{const s=(Date.now()-t)/1e3;return s<60?'agora':s<3600?Math.floor(s/60)+' min':s<86400?Math.floor(s/3600)+' h':new Date(t).toLocaleDateString('pt-BR')};
async function api(m,p,b){try{const r=await fetch(p,{method:m,headers:{'Content-Type':'application/json','X-Requested-With':'fetch'},body:b?JSON.stringify(b):undefined});let d={};try{d=await r.json()}catch(e){}return{ok:r.ok,s:r.status,d}}catch(e){return{ok:false,d:{error:'sem conexão'}}}}
const av=(id,n)=>{const a=el('div','av',(n[0]||'C').toUpperCase());a.style.background=col(id);return a};
function setMode(m){mode=m;$('#m1').classList.toggle('on',m==='login');$('#m2').classList.toggle('on',m==='reg');document.querySelectorAll('.reg').forEach(e=>e.hidden=m!=='reg');$('#sub').textContent=m==='reg'?'Criar conta':'Entrar';$('#am').textContent=''}
$('#m1').onclick=()=>setMode('login');$('#m2').onclick=()=>setMode('reg');
$('#sub').onclick=async()=>{const b={username:$('#un').value,password:$('#pw').value};$('#am').textContent='';
 if(mode==='reg'){b.name=$('#nm').value;b.invite=$('#iv').value;const r=await api('POST','/api/register',b);if(!r.ok){$('#am').textContent=r.d.error||'erro';return}}
 const r=await api('POST','/api/login',{username:b.username,password:b.password});if(!r.ok){$('#am').textContent=r.d.error||'erro';return}$('#pw').value='';boot()};
$('#pw').onkeydown=e=>{if(e.key==='Enter')$('#sub').click()};
async function boot(){const r=await api('GET','/api/me');if(!r.ok){$('#auth').hidden=false;$('#app').hidden=true;return}
 me=r.d;$('#auth').hidden=true;$('#app').hidden=false;sig={};tick();clearInterval(timer);timer=setInterval(tick,4000)}
$('#out').onclick=async()=>{await api('POST','/api/logout');clearInterval(timer);me=null;cur=null;$('#app').hidden=true;$('#auth').hidden=false};
document.querySelectorAll('header .tab').forEach(b=>b.onclick=()=>{document.querySelectorAll('header .tab').forEach(x=>x.classList.toggle('on',x===b));for(const t of['feed','dm','ev'])$('#'+t).hidden=t!==b.dataset.t});
async function tick(){if(!me)return;const [f,e,u]=await Promise.all([api('GET','/api/feed'),api('GET','/api/events'),api('GET','/api/users')]);
 if(f.s===401){boot();return}
 if(f.ok&&chg('f',f.d))rfeed(f.d.posts);if(e.ok&&chg('e',e.d))rev(e.d.events);if(u.ok&&chg('u',u.d))rfl(u.d.users);
 if(cur){const d=await api('GET','/api/dm/'+cur.id);if(d.ok&&chg('d',d.d))rms(d.d.msgs)}}
const chg=(k,d)=>{const s=JSON.stringify(d);if(sig[k]===s)return false;sig[k]=s;return true};
function rfeed(ps){const a=document.activeElement,pid=a&&a.dataset&&a.dataset.pid,pos=a&&a.selectionStart,L=$('#list');L.textContent='';
 if(!ps.length)L.append(el('div','cnt','Nenhum post ainda. Seja o primeiro cuiudo a postar!'));
 for(const p of ps){const c=el('div','post'),top=el('div','top'),w=el('div');w.append(el('div','nm',p.name),el('div','tm',ago(p.ts)));top.append(av(p.uid,p.name),w);c.append(top,el('div','tx',p.text));
  const mine=p.likes.includes(me.id),row=el('div','row'),l=el('div');
  const b1=el('button','g'+(mine?' on':''),(mine?'♥ ':'♡ ')+p.likes.length);b1.onclick=async()=>{await api('POST','/api/posts/'+p.id+'/like');tick()};
  const b2=el('button','g','💬 '+p.comments.length);b2.onclick=()=>{open.has(p.id)?open.delete(p.id):open.add(p.id);rfeed(ps)};l.append(b1,b2);row.append(l);
  if(p.uid===me.id){const d=el('button','g','Excluir');d.onclick=async()=>{if(confirm('Excluir este post?')){await api('DELETE','/api/posts/'+p.id);tick()}};row.append(d)}c.append(row);
  if(open.has(p.id)){const cm=el('div','cm');for(const x of p.comments){const d=el('div','c');d.append(el('b','',x.name+': '),document.createTextNode(x.text));cm.append(d)}
   const i=el('input');i.placeholder='Comentar…';i.maxLength=300;i.dataset.pid=p.id;i.value=drafts[p.id]||'';i.oninput=()=>drafts[p.id]=i.value;
   i.onkeydown=async e=>{if(e.key==='Enter'&&i.value.trim()){const v=i.value.trim();drafts[p.id]='';await api('POST','/api/posts/'+p.id+'/comments',{text:v});tick()}};cm.append(i);c.append(cm)}L.append(c)}
 if(pid){const i=L.querySelector(`input[data-pid="${pid}"]`);if(i){i.focus();try{i.setSelectionRange(pos,pos)}catch(e){}}}}
$('#t').oninput=e=>$('#n').textContent=e.target.value.length+'/500';
$('#go').onclick=async()=>{const v=$('#t').value.trim();if(!v)return;const r=await api('POST','/api/posts',{text:v});if(r.ok){$('#t').value='';$('#n').textContent='0/500';tick()}};
function rfl(us){D.users=us;const L=$('#fl');L.textContent='';if(!us.length)L.append(el('div','cnt','Ninguém mais entrou ainda. Mande o link e o código de convite aos amigos.'));
 for(const u of us){const b=el('button','fr');b.append(av(u.id,u.name),el('span','',u.name));b.onclick=()=>{cur=u;sig.d='';$('#fl').hidden=true;$('#conv').hidden=false;$('#cw').textContent=u.name;$('#ms').textContent='';tick()};L.append(b)}}
$('#back').onclick=()=>{cur=null;$('#fl').hidden=false;$('#conv').hidden=true};
function rms(ms){const M=$('#ms');M.textContent='';if(!ms.length)M.append(el('div','cnt','Sem mensagens ainda. Diga oi!'));for(const m of ms)M.append(el('div','bub'+(m.frm===me.id?' me':''),m.text));M.scrollTop=M.scrollHeight}
async function send(){const v=$('#mi').value.trim();if(!v||!cur)return;$('#mi').value='';await api('POST','/api/dm/'+cur.id,{text:v});sig.d='';tick()}
$('#mg').onclick=send;$('#mi').onkeydown=e=>{if(e.key==='Enter')send()};
function rev(es){const L=$('#el');L.textContent='';const now=Date.now()-108e5;if(!es.length)L.append(el('div','cnt','Nenhum evento. Marque o primeiro rolê!'));
 const up=es.filter(e=>e.whenx>=now),pa=es.filter(e=>e.whenx<now).reverse();
 for(const e of[...up,...pa]){const c=el('div','post');if(e.whenx<now)c.style.opacity='.6';
  c.append(el('div','nm',e.title),el('div','tm',new Date(e.whenx).toLocaleString('pt-BR',{weekday:'short',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'})+(e.place?' · '+e.place:'')+' · por '+e.name));
  const mine=(e.rsvps.find(r=>r.uid===me.id)||{}).s,row=el('div','row'),l=el('div');
  for(const[s,t]of[['go','Vou'],['maybe','Talvez'],['no','Não vou']]){const b=el('button','g'+(mine===s?' on':''),t+' '+e.rsvps.filter(r=>r.s===s).length);b.onclick=async()=>{await api('POST','/api/events/'+e.id+'/rsvp',{s:mine===s?'none':s});tick()};l.append(b)}
  row.append(l);if(e.uid===me.id){const d=el('button','g','Excluir');d.onclick=async()=>{if(confirm('Excluir este evento?')){await api('DELETE','/api/events/'+e.id);tick()}};row.append(d)}c.append(row);
  const go=e.rsvps.filter(r=>r.s==='go').map(r=>r.name);if(go.length)c.append(el('div','cnt','Vão: '+go.join(', ')));L.append(c)}}
$('#eg').onclick=async()=>{const t=$('#et').value.trim(),w=new Date($('#ew').value).getTime();if(!t||isNaN(w)){alert('Informe o nome e a data/hora.');return}
 const r=await api('POST','/api/events',{title:t,when:w,place:$('#ep').value});if(r.ok){$('#et').value=$('#ep').value=$('#ew').value='';tick()}};
boot();
