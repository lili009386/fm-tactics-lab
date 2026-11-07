const $=id=>document.getElementById(id);let current=null,snapshotKey='',tacticKey='';
const defaults=['Beta 4-1-4-1 believe it.fmf','GYR - BEAST 4231 FM27.fmf','fm27.0 shaolin 41230.fmf','343米兰.fmf','朱指导无敌高位压迫352炸.fmf'];
function text(tag,value){const e=document.createElement(tag);e.textContent=value;return e}
function error(value){$('error').textContent=value||'';$('error').hidden=!value}
async function api(path,data){const r=await fetch(path,data?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}:{});const result=await r.json();if(!r.ok)throw Error(result.error||r.status);return result}
function selected(){return [...document.querySelectorAll('[data-candidate]:checked')].map(e=>e.value)}
function excluded(){return [...document.querySelectorAll('[data-player]:not(:checked)')].map(e=>Number(e.value))}
function opponentValues(){return [...document.querySelectorAll('[data-opponent]')].filter(e=>e.querySelector('input').checked).map(e=>({club_uid:Number(e.dataset.opponent),tactic:e.querySelector('select').value}))}
function count(){if(!current)return;const total=selected().length*opponentValues().length*2*Number($('perLeg').value);$('count').textContent=`${selected().length} 套候选 × ${opponentValues().length} 支对手 × 主客场 × ${$('perLeg').value} 场 = ${total} 场`}
function populateOptions(select,values,pick){select.replaceChildren(...values.map(v=>{let o=text('option',v);o.value=v;o.selected=v===pick;return o}))}
function renderSnapshot(s,tactics){
 if(!s){$('snapshot').textContent='尚未导入';return}
 const own=s.managed[0];$('snapshot').textContent=`${own.club_name} · ${s.info.game_date} · ${s.players.length} 名一线队球员 · ${s.info.build}${s.info.known_build?'':'（解析器未验证的构建）'}`;
 $('players').replaceChildren(...s.players.map(p=>{let tr=document.createElement('tr'),td=document.createElement('td'),check=document.createElement('input');check.type='checkbox';check.checked=true;check.value=p.uid;check.dataset.player='1';check.setAttribute('aria-label','使用 '+p.name);td.append(check);tr.append(td,...[p.name,p.age,p.positions.join(' / '),p.condition==null?'未知':(p.condition/100).toFixed(1)+'%'].map(v=>text('td',v)));return tr}));
 const mapping={1135:defaults[4],1139:defaults[3],1150:defaults[1],1100:defaults[3],990:defaults[1]};
 $('opponents').replaceChildren(...s.teams.filter(t=>t.uid!==own.club_uid).map(t=>{let row=document.createElement('div');row.dataset.opponent=t.uid;let label=text('label',t.name+' · '+t.count+' 人'),check=document.createElement('input');check.type='checkbox';check.checked=true;check.onchange=count;label.prepend(check);let select=document.createElement('select');select.setAttribute('aria-label',t.name+'的测试战术');populateOptions(select,tactics,mapping[t.uid]||defaults[1]);row.append(label,select);return row}));count()
}
async function refresh(){try{const state=await api('/api/state');current=state;
 if(!$('save').options.length)populateOptions($('save'),state.saves,state.saves[0]);
 if(tacticKey!==state.tactics.join('|')){const prior=selected();tacticKey=state.tactics.join('|');$('candidates').replaceChildren(...state.tactics.map(name=>{let label=text('label',name),check=document.createElement('input');check.type='checkbox';check.value=name;check.dataset.candidate='1';check.checked=(prior.length?prior:defaults).includes(name);check.onchange=count;label.prepend(check);return label}))}
 const key=state.snapshot?state.snapshot.source_sha256+'|'+state.snapshot.teams.map(t=>t.uid).join(','):'';
 if(key!==snapshotKey){snapshotKey=key;renderSnapshot(state.snapshot,state.tactics)}
 if(!$('limits').children.length)$('limits').replaceChildren(...state.limitations.map(v=>text('li',v)));
 const run=state.run,busy=run.status==='running'||state.import_status==='running';$('import').disabled=busy;$('run').disabled=busy||!state.snapshot;$('preview').disabled=!state.snapshot;
 $('import').textContent=state.import_status==='running'?'正在读取存档…':'读取阵容';
 $('status').textContent={idle:'等待测试',running:'正在模拟',completed:'测试完成',error:'需要处理',interrupted:'运行已中断'}[run.status]||run.status;
 $('progress').max=run.total||1;$('progress').value=run.completed||0;$('progressText').textContent=`已完成 ${run.completed||0} / ${run.total||0} 场`;
 $('export').disabled=run.status!=='completed';$('download').hidden=run.status!=='completed';
 $('ranking').replaceChildren(...(run.ranking||[]).map(r=>{let tr=document.createElement('tr');tr.append(...[r.tactic,r.matches,`${r.wins} / ${r.draws} / ${r.losses}`,(100*r.win_rate).toFixed(1)+'%',r.points_per_game.toFixed(2),`${r.goals_for} / ${r.goals_against}`].map(v=>text('td',v)));return tr}));
 if(state.error||run.error)error(state.error||run.error);count()
 }catch(e){error(e.message)}}
async function action(fn){error('');try{await fn();await refresh()}catch(e){error(e.message)}}
$('import').onclick=()=>action(()=>api('/api/import-save',{save_name:$('save').value,opponents:$('clubNames').value.split(/[,，]/).map(x=>x.trim()).filter(Boolean)}));
$('run').onclick=()=>action(()=>api('/api/compare',{candidates:selected(),opponents:opponentValues(),excluded:excluded(),per_leg:Number($('perLeg').value),seed:Number($('seed').value)}));
$('preview').onclick=()=>action(async()=>{if(!selected().length)throw Error('请至少选择一套候选战术');$('lineup').textContent='正在匹配首发…';let r=await api('/api/preview',{candidate:selected()[0],excluded:excluded()});$('lineup').replaceChildren(text('h3','建议首发 · '+selected()[0]),...r.lineup.map(p=>text('div',`${p.positions.join(' → ')} · ${p.name}`)),text('p','替补：'+r.bench.join('、')))});
$('export').onclick=()=>action(async()=>{let r=await api('/api/export-winner',{});$('exported').textContent='已保存并通过原版回读校验：'+r.path});
$('perLeg').oninput=count;refresh();setInterval(refresh,3000);
