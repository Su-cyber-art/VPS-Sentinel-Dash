'use strict';
const $ = (s, root = document) => root.querySelector(s);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const names = {snapshot:'系统快照',network:'网络检测',logs:'读取日志',google:'区域访问实验',trust:'本地站点访问实验',quality:'IP 质量检测'};
const pageNames = {overview:'运行概览',nodes:'节点管理',jobs:'任务记录',events:'事件日志',settings:'控制台设置'};
const paths = {
  grid:'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  server:'M4 3h16v7H4z M4 14h16v7H4z M7 6.5h.01 M7 17.5h.01 M16 6.5h1 M16 17.5h1',
  globe:'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M3 12h18 M12 3c5 5 5 13 0 18-5-5-5-13 0-18',
  activity:'M3 12h4l3-8 4 16 3-8h4',
  clock:'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M12 7v5l3 2',
  list:'M8 5h13 M8 12h13 M8 19h13 M3 5h.01 M3 12h.01 M3 19h.01',
  settings:'M12 8a4 4 0 1 1 0 8 4 4 0 0 1 0-8 M12 2v3 M12 19v3 M2 12h3 M19 12h3 M5 5l2 2 M17 17l2 2 M5 19l2-2 M17 7l2-2',
  plus:'M12 5v14 M5 12h14',refresh:'M20 7v5h-5 M4 17v-5h5 M6.1 6a8 8 0 0 1 13.1 3 M17.9 18a8 8 0 0 1-13.1-3',
  arrow:'m9 5 7 7-7 7',close:'m6 6 12 12 M18 6 6 18',check:'m5 12 4 4L19 6',
  search:'M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0 m-2 5 6 6',logout:'M9 3H4v18h5 M9 12h12 m-5-5 5 5-5 5',
  copy:'M8 8h12v13H8z M16 8V3H3v13h5',shield:'m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6z',play:'m8 4 12 8-12 8z',bell:'M5 17h14l-2-3V9a5 5 0 0 0-10 0v5z M10 21h4'
};
const icon = name => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[name] || paths.server}"/></svg>`;
const brand = '<img src="/favicon.svg" alt=""><div><strong>IP Sentinel</strong><small>CONTROL PLANE</small></div>';
const state = {csrf:'',data:null,view:'overview',regions:[],settings:null,filter:'',status:'all',modalJob:null,loading:false};
let toastTimer, poll;
function toast(message) { const el=$('#toast'); el.textContent=message; el.classList.add('visible'); clearTimeout(toastTimer); toastTimer=setTimeout(()=>el.classList.remove('visible'),3500); }
function when(timestamp) { return timestamp ? new Date(timestamp*1000).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}) : '尚未上报'; }
function ago(timestamp) { if(!timestamp) return '等待首次心跳'; const t=Math.max(0,Math.floor(Date.now()/1000-timestamp)); return t<5?'刚刚':t<60?`${t} 秒前`:t<3600?`${Math.floor(t/60)} 分钟前`:`${Math.floor(t/3600)} 小时前`; }
function statusPill(status) { const labels={online:'在线',offline:'离线',queued:'待执行',running:'执行中',succeeded:'已完成',failed:'失败'}; return `<span class="status ${esc(status)}"><span class="dot ${['offline','queued'].includes(status)?'off':''}"></span>${labels[status]||esc(status)}</span>`; }
async function api(path, method='GET', body) {
  const options={method,headers:{}};
  if(method!=='GET') {options.headers={'Content-Type':'application/json','X-CSRF-Token':state.csrf};options.body=JSON.stringify(body||{});}
  const response=await fetch('/api'+path,options);
  const value=await response.json();
  if(!response.ok) {if(response.status===401 && !['/login','/session'].includes(path)) {clearInterval(poll);$('#modal').close();renderLogin(true);} throw new Error(value.error||'请求失败');}
  return value;
}
function renderLogin(configured) {
  state.data=null;
  $('#app').innerHTML=`<main class="login-shell"><section class="login-intro"><div class="brand">${brand}</div><h1>每一个节点，<br>都在掌控之中。</h1><p>连接分散各地的服务器。<br>在一个清晰的控制台中，了解状态、安排任务、追踪结果。</p><div class="login-caption">YOUR INFRASTRUCTURE. ONE CLEAR VIEW.</div><div class="login-orbit"></div></section><section class="login-form-wrap"><form id="login-form" class="login-form"><h2>${configured?'欢迎回来':'创建你的控制台'}</h2><p>${configured?'登录 IP Sentinel，查看节点运行状况。':'首次使用，请输入主控启动终端中的初始化密钥，并设置管理密码。'}</p>${configured?'':`<div class="field"><label for="setup-token">初始化密钥</label><input id="setup-token" name="setup_token" type="password" required autocomplete="off"></div>`}<div class="field"><label for="password">${configured?'管理密码':'设置管理密码'}</label><input id="password" name="password" type="password" required ${configured?'':'minlength="12"'} maxlength="256" placeholder="${configured?'输入管理密码':'至少 12 个字符'}" autocomplete="${configured?'current-password':'new-password'}"></div><div class="form-error" role="alert"></div><button class="btn primary" type="submit">${configured?'进入控制台':'创建并进入控制台'} ${icon('arrow')}</button><div class="login-foot">私有部署 · 数据由你掌控</div></form></section></main>`;
  $('#login-form').addEventListener('submit',async event=>{
    event.preventDefault(); const form=event.currentTarget,button=$('button',form);button.disabled=true;
    try { const value=await api(configured?'/login':'/setup','POST',Object.fromEntries(new FormData(form)));state.csrf=value.csrf;await start(); }
    catch(error){$('.form-error',form).textContent=error.message;button.disabled=false;}
  });
}
function shell() {
  const nav=[['overview','grid'],['nodes','server'],['jobs','clock'],['events','list'],['settings','settings']];
  $('#app').innerHTML=`<div class="shell"><aside class="sidebar"><a class="brand" href="#overview">${brand}</a><div class="nav-label">WORKSPACE</div><nav aria-label="主导航">${nav.map(([key,i])=>`<a class="nav-link ${state.view===key?'active':''}" href="#${key}" ${state.view===key?'aria-current="page"':''}>${icon(i)}<span>${pageNames[key]}</span>${key==='nodes'?`<span class="count">${state.data.nodes.length}</span>`:''}</a>`).join('')}</nav><div class="sidebar-bottom"><div class="system-status"><span class="dot"></span>主控已连接</div><small>IP SENTINEL / v${esc(state.data.version)}</small></div></aside><div><header class="topbar"><div class="breadcrumb">工作空间 ${icon('arrow')} <strong>${pageNames[state.view]}</strong></div><a href="#overview" class="mobile-brand"><img src="/favicon.svg" alt="">IP Sentinel</a><div class="top-right"><span class="live"><span class="dot"></span>实时同步</span><span class="avatar" title="管理员">AD</span><button class="btn plain" data-action="logout" aria-label="退出登录" title="退出登录">${icon('logout')}</button></div></header><main class="page" id="page"></main></div></div>`;
  renderPage();
}
function head(title,subtitle,add=true) {return `<div class="page-head"><div><h1>${title}</h1><p>${subtitle}</p></div><div class="actions"><button class="btn" data-action="refresh" aria-label="刷新数据">${icon('refresh')}<span class="refresh-text">刷新</span></button>${add?`<button class="btn primary" data-action="enroll">${icon('plus')} 接入节点</button>`:''}</div></div>`;}
function empty(title,description,add=false) {return `<div class="empty">${icon('server')}<h3>${title}</h3><p>${description}</p>${add?`<button class="btn primary" data-action="enroll">${icon('plus')} 接入第一个节点</button>`:''}</div>`;}
function nodeRows(nodes) {return nodes.map(n=>`<tr><td><div class="node-name"><span class="node-symbol">${icon('server')}</span><div><strong>${esc(n.name)}</strong><small>${esc(n.hostname||'等待 Agent 上报')}</small></div></div></td><td><span class="mono">${esc(n.metrics.public_ip||'尚未检测')}</span><small style="display:block;margin-top:6px;font-size:10px">${esc(n.region||n.metrics.country||'地区未设置')}</small></td><td>${statusPill(n.online?'online':'offline')}</td><td class="muted">${ago(n.seen)}</td><td><button class="btn plain" data-action="node" data-id="${n.id}" aria-label="管理 ${esc(n.name)}">${icon('arrow')}</button></td></tr>`).join('');}
function nodeTable(nodes) {return nodes.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>节点 / 主机</th><th>出口 IP / 地区</th><th>连接状态</th><th>最近心跳</th><th></th></tr></thead><tbody>${nodeRows(nodes)}</tbody></table></div>`:empty(state.filter||state.status!=='all'?'没有匹配的节点':'从第一个节点开始',state.filter||state.status!=='all'?'尝试调整搜索词或状态筛选。':'生成接入令牌，让服务器连接到你的控制台。',!state.filter&&state.status==='all');}
function jobTable(jobs) {return jobs.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>任务</th><th>节点</th><th>状态</th><th>创建时间</th><th></th></tr></thead><tbody>${jobs.map(j=>`<tr><td><strong style="font-weight:500">${names[j.action]||esc(j.action)}</strong><small style="display:block;font-size:10px;margin-top:6px">${j.source==='schedule'?'定时任务':'手动任务'}</small></td><td>${esc(j.node_name||'已移除节点')}</td><td>${statusPill(j.status)}</td><td class="muted mono">${when(j.created)}</td><td><button class="btn plain" data-action="job" data-id="${j.id}" aria-label="查看任务结果">${icon('arrow')}</button></td></tr>`).join('')}</tbody></table></div>`:empty('还没有任务记录','在节点详情中运行检测，结果会保存在这里。');}
function eventList(events) {return events.length?`<div class="events">${events.map(e=>`<div class="event"><span class="event-indicator">${icon(e.kind.includes('failed')||e.kind.includes('offline')?'bell':'check')}</span><div><p>${esc(e.message)}</p><small>${when(e.created)}</small></div></div>`).join('')}</div>`:empty('一切准备就绪','节点接入、策略调整和任务结果会记录在这里。');}
function overview() {
  const d=state.data, online=d.nodes.filter(n=>n.online).length, total=d.nodes.length;
  const countries=new Set(d.nodes.map(n=>n.region||n.metrics.country).filter(Boolean)).size;
  const jobs=Object.values(d.counts).reduce((a,b)=>a+b,0),pending=d.pending_count;
  const metrics=[['在线节点',online,`/ ${total}`,total?'当前已连接 Agent':'等待节点接入','server'],['覆盖地区',countries,'',countries?'按节点地区统计':'设置地区以追踪分布','globe'],['24h 任务',jobs,'',`${d.counts.succeeded||0} 项完成 · ${d.counts.failed||0} 项失败`,'activity'],['待处理任务',pending,'',pending?'任务将由 Agent 领取':'所有任务已处理','clock']];
  const pct=total?Math.round(online/total*100):0,max=Math.max(1,...d.hours);
  return head('运行概览','随时了解你的服务器，以及正在发生的事。')+`<div class="metrics">${metrics.map(([name,value,unit,sub,i])=>`<section class="metric"><div class="metric-top">${name}<span class="metric-icon">${icon(i)}</span></div><div class="metric-value">${value}<span>${unit}</span></div><div class="metric-bottom">${sub}</div></section>`).join('')}</div><div class="grid-two"><div class="stack"><section class="card"><div class="card-head"><div><h2>我的节点 <span class="pill-count">${total}</span></h2><p>所有服务器的最新连接状态</p></div><a href="#nodes" class="btn plain">管理节点 ${icon('arrow')}</a></div>${nodeTable(d.nodes.slice(0,6))}<div class="table-footer"><span>每 15 秒自动同步</span><span>${total} 个节点</span></div></section><section class="card"><div class="card-head"><h2>最近任务</h2><a href="#jobs" class="btn plain">全部记录 ${icon('arrow')}</a></div>${jobTable(d.jobs.slice(0,4))}</section></div><div class="stack side-stack"><section class="card health"><h2>连接健康度</h2><div class="health-number"><strong>${total?pct:'—'}</strong><small>${total?'% 节点在线':'尚无节点'}</small></div><div class="health-meter" aria-label="节点在线率 ${pct}%">${Array.from({length:24},(_,i)=>`<span class="${i<Math.round(pct/100*24)?'on':''}"></span>`).join('')}</div><div class="legend"><span>${online} 在线</span><span>${total-online} 离线</span></div><div class="tip"><strong>${total&&online===total?'所有节点连接正常':'Agent 主动连接主控'}</strong>${total&&online===total?'主控持续接收心跳，任务结果会自动同步到这里。':'安装 Agent 后即可在此查看状态，无需开放节点入站端口。'}</div></section><section class="card activity"><div class="activity-title"><h2>任务活动</h2><small>过去 24 小时</small></div><div class="chart" role="img" aria-label="过去 24 小时共 ${jobs} 个任务">${d.hours.map((n,i)=>`<span class="chart-bar" style="height:${Math.max(3,n/max*100)}%" title="${23-i} 小时前：${n} 项"></span>`).join('')}</div><div class="chart-labels"><span>24h 前</span><span>12h 前</span><span>现在</span></div></section><section class="card"><div class="card-head"><h2>最新动态</h2><a href="#events" class="btn plain" aria-label="全部事件">${icon('arrow')}</a></div>${eventList(d.events.slice(0,3))}</section></div></div>`;
}
function renderPage() {
  if(!state.data||!$('#page'))return;
  let content='';
  if(state.view==='overview')content=overview();
  if(state.view==='nodes')content=head('节点管理','连接、查看和配置你的全部 Agent。')+`<section class="card"><div class="filters"><div class="search">${icon('search')}<input id="node-search" aria-label="搜索节点" placeholder="搜索名称、IP、主机或分组…" value="${esc(state.filter)}"></div><select id="node-status" aria-label="筛选连接状态"><option value="all">全部状态</option><option value="online" ${state.status==='online'?'selected':''}>在线</option><option value="offline" ${state.status==='offline'?'selected':''}>离线</option></select></div><div id="node-list"></div></section>`;
  if(state.view==='jobs')content=head('任务记录','查看执行进度、检测结果和失败原因。',false)+`<section class="card"><div class="card-head"><h2>最近 200 个任务</h2><small>记录保留 30 天</small></div>${jobTable(state.data.jobs)}</section>`;
  if(state.view==='events')content=head('事件日志','节点连接、配置调整与操作记录。',false)+`<section class="card"><div class="card-head"><h2>最近 200 条事件</h2><small>记录保留 30 天</small></div>${eventList(state.data.events)}</section>`;
  if(state.view==='settings')content=settingsPage();
  $('#page').innerHTML=content+`<footer class="footer"><span>IP Sentinel · 你的基础设施，由你掌控</span><a href="https://github.com/hotyue/IP-Sentinel" target="_blank" rel="noopener">基于 IP-Sentinel · AGPL-3.0</a></footer>`;
  if(state.view==='nodes')filterNodes();
}
function filterNodes() {if(!$('#node-list'))return;const q=state.filter.toLowerCase();const nodes=state.data.nodes.filter(n=>(state.status==='all'||n.online===(state.status==='online'))&&[n.name,n.hostname,n.region,n.group_name,n.metrics.public_ip].join(' ').toLowerCase().includes(q));$('#node-list').innerHTML=nodeTable(nodes);}
function settingsPage() {
  const s=state.settings;if(!s)return head('控制台设置','管理通知与访问凭证。',false)+empty('正在读取设置','');
  return head('控制台设置','管理通知与访问凭证。',false)+`<div class="settings-grid"><section class="card"><div class="card-head"><h2>${icon('bell')} Telegram 通知</h2><span class="status ${s.telegram_configured?'':'offline'}">${s.telegram_configured?'已配置':'未配置'}</span></div><form id="notification-form" class="settings-body"><p>在节点离线、恢复连接或任务失败时收到通知。节点管理和任务操作均在网页中完成。</p><label class="toggle-line"><span><strong>启用 Telegram 通知</strong><small>${s.telegram_configured?'主控已读取通知凭证':'在主控环境变量中设置 TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID 后重启'}</small></span><input name="enabled" type="checkbox" ${s.telegram_enabled?'checked':''} ${s.telegram_configured?'':'disabled'}></label><button class="btn primary" type="submit">保存通知设置</button></form></section><section class="card"><div class="card-head"><h2>${icon('shield')} 访问管理</h2></div><form id="password-form" class="settings-body"><p>修改管理密码后，所有已登录的会话将退出。</p><div class="field"><label for="old-password">当前密码</label><input id="old-password" name="current_password" type="password" required autocomplete="current-password"></div><div class="field"><label for="new-password">新密码</label><input id="new-password" name="new_password" type="password" minlength="12" maxlength="256" required autocomplete="new-password" placeholder="至少 12 个字符"></div><button class="btn" type="submit">更新密码</button></form></section><section class="card"><div class="card-head"><h2>主控信息</h2></div><div class="settings-body"><div class="settings-row"><span class="muted">版本</span><span class="mono">${esc(s.version)}</span></div><div class="settings-row"><span class="muted">接入地址</span><span class="mono">${esc(s.public_url||location.origin)}</span></div><div class="settings-row"><span class="muted">部署方式</span><span>私有主控 · SQLite</span></div></div></section></div>`;
}
function showModal(title,subtitle,body,footer='',drawer=false) {const el=$('#modal');state.modalJob=null;el.className=drawer?'drawer':'';el.innerHTML=`<div class="dialog-head"><div><h2>${title}</h2><small>${subtitle}</small></div><button class="btn plain" data-action="close" aria-label="关闭">${icon('close')}</button></div><div class="dialog-content">${body}</div>${footer?`<div class="dialog-footer">${footer}</div>`:''}`;if(!el.open)el.showModal();}
function enrollment() {showModal('接入新节点','通过一次性令牌，将 Agent 连接到主控。',`<form id="enroll-form"><div class="field"><label for="enroll-name">节点名称</label><input id="enroll-name" name="name" maxlength="80" placeholder="例如 Tokyo · Production 01" required autofocus></div><p>令牌有效期为 15 分钟，只能使用一次。接入后将为该节点签发独立凭证。</p><div class="form-error" role="alert"></div><button class="btn primary" type="submit" style="margin-top:20px">生成接入令牌 ${icon('arrow')}</button></form>`);}
async function enrolled(data) {
  const origin=data.master_url||location.origin;
  const script=`curl -fsS '${origin}/download/install-agent.sh' -o install-agent.sh\nsudo bash install-agent.sh '${origin}'`;
  showModal('节点接入准备就绪','在目标 Linux 服务器上完成以下步骤。',`<div class="section-label" style="margin-top:0">01 / 保存并运行安装程序</div><pre id="install-command">${esc(script)}</pre><button class="btn" data-action="copy" data-target="install-command">${icon('copy')} 复制安装命令</button><div class="section-label">02 / 在安装程序提示时粘贴令牌</div><div class="token-box"><code id="enroll-token">${esc(data.token)}</code><button class="btn icon-only" data-action="copy" data-target="enroll-token" aria-label="复制接入令牌">${icon('copy')}</button></div><p style="margin-top:12px">有效期至 ${when(data.expires)}。Agent 启动后，节点会自动出现。</p>${origin.startsWith('http:')?'<div class="note">当前使用本机预览地址。远程服务器接入前，请为主控配置 HTTPS 域名与 SENTINEL_PUBLIC_URL。开发环境可按 README 使用本机 Agent。</div>':''}<div class="section-label">03 / 返回节点列表</div><p>首次心跳通常在 15 秒内到达。原版养护模块可在安装时选装，默认关闭。</p>`,`<button class="btn primary" data-action="enroll-done">查看节点</button>`);
}
async function nodeDetail(id) {
  const n=state.data.nodes.find(n=>n.id===id);if(!n)return;
  if(!state.regions.length)state.regions=(await api('/regions')).regions;
  const p=n.policy,m=n.metrics;
  showModal(esc(n.name),`${esc(n.platform||'等待系统信息')} · ${esc(n.id)}`,`<div class="detail-metrics"><div class="detail-metric"><small>连接状态</small><strong>${statusPill(n.online?'online':'offline')}</strong></div><div class="detail-metric"><small>一分钟负载</small><strong>${esc(m.load_1m??'—')}</strong></div><div class="detail-metric"><small>磁盘使用率</small><strong>${m.disk_used_percent!=null?esc(m.disk_used_percent)+'%':'—'}</strong></div></div><h3>运行任务</h3><div class="task-buttons" style="margin-top:13px">${Object.entries(names).map(([key,name])=>`<button class="btn" data-action="run" data-id="${id}" data-task="${key}" ${!n.capabilities.includes(key)||(['google','trust'].includes(key)&&!p[key])?'disabled':''}>${icon(key==='logs'?'list':'play')}${name}</button>`).join('')}</div><div class="section-label">节点信息与策略</div><form id="node-form" data-id="${id}"><div class="form-grid"><div class="field"><label for="node-name">节点名称</label><input id="node-name" name="name" value="${esc(n.name)}" required maxlength="80"></div><div class="field"><label for="node-group">分组</label><input id="node-group" name="group_name" value="${esc(n.group_name)}" required maxlength="80"></div><div class="field"><label for="node-region">地区标签</label><input id="node-region" name="region" value="${esc(n.region)}" maxlength="80" placeholder="例如 日本 · 东京"></div><div class="field"><label for="target-region">实验目标地区</label><select id="target-region" name="region_path">${state.regions.map(r=>`<option value="${esc(r.path)}" ${r.path===p.region_path?'selected':''}>${esc(r.name)}</option>`).join('')}</select></div></div><label class="toggle-line"><span><strong>区域访问实验</strong><small>运行原版 Google 访问模块，定位改善效果未经验证。</small></span><input type="checkbox" name="google" ${p.google?'checked':''}></label><label class="toggle-line"><span><strong>本地站点访问实验</strong><small>运行原版 Trust 模块，HTTP 成功不代表信誉提升。</small></span><input type="checkbox" name="trust" ${p.trust?'checked':''}></label><div class="form-grid"><div class="field"><label for="scheduled-action">定时执行</label><select id="scheduled-action" name="scheduled_action">${Object.entries(names).filter(([key])=>key!=='logs').map(([key,name])=>`<option value="${key}" ${p.scheduled_action===key?'selected':''}>${name}</option>`).join('')}</select></div><div class="field"><label for="interval">周期（分钟）</label><input id="interval" type="number" name="interval_minutes" min="0" max="1440" step="1" value="${p.interval_minutes}" required><small>0 为关闭；开启后最少 5 分钟。</small></div></div><div class="form-error" role="alert"></div><button class="btn primary" type="submit">保存节点配置</button></form><div class="section-label">节点凭证</div><p>移除后将撤销 Agent 的连接凭证。正在执行的本地进程可能继续完成。</p><button class="btn danger" style="margin-top:12px" data-action="remove" data-id="${id}">移除节点</button>`,'',true);
}
async function jobDetail(id) {
  const j=await api('/jobs/'+id);
  showModal(names[j.action]||esc(j.action),`${esc(j.node_name)} · ${when(j.created)}`,`<div style="display:flex;align-items:center;justify-content:space-between">${statusPill(j.status)}<span class="mono muted">${esc(j.id.slice(0,12))}</span></div><div class="section-label">执行结果</div>${j.result?`<pre>${esc(j.result.text??JSON.stringify(j.result,null,2))}</pre>`:`<div class="empty">${icon('clock')}<p>${j.status==='queued'?'等待 Agent 领取任务。离线节点将在恢复连接后领取。':'Agent 正在执行，结果会自动更新。'}</p></div>`}`,`<button class="btn" data-action="job" data-id="${j.id}">${icon('refresh')} 更新结果</button><button class="btn primary" data-action="close">完成</button>`);
  state.modalJob=['queued','running'].includes(j.status)?id:null;
}
async function refresh(manual=false) {
  if(state.loading)return;state.loading=true;
  try {
    state.data=await api('/overview');
    if(state.view==='settings')state.settings=await api('/settings');
    const editing=$('#page')?.contains(document.activeElement)&&['INPUT','SELECT'].includes(document.activeElement.tagName);
    if(!editing)renderPage();
    if($('#modal').open&&state.modalJob){const job=state.data.jobs.find(j=>j.id===state.modalJob);if(job&&['succeeded','failed'].includes(job.status))await jobDetail(state.modalJob);}
    const count=$('.nav-link .count');if(count)count.textContent=state.data.nodes.length;
    $('.banner-error')?.remove();if(manual)toast('已同步最新状态');
  }catch(error){if(state.data&&$('#page')&&!$('.banner-error')){const el=document.createElement('div');el.className='banner-error';el.textContent='同步失败：'+error.message;$('#page').prepend(el);}if(manual)toast(error.message);}
  finally{state.loading=false;}
}
async function start() {state.data=await api('/overview');state.settings=await api('/settings');state.view=Object.hasOwn(pageNames,location.hash.slice(1))?location.hash.slice(1):'overview';shell();clearInterval(poll);poll=setInterval(()=>refresh(),15000);}
document.addEventListener('input',e=>{if(e.target.id==='node-search'){state.filter=e.target.value;filterNodes();}});
document.addEventListener('change',e=>{if(e.target.id==='node-status'){state.status=e.target.value;filterNodes();}});
window.addEventListener('hashchange',()=>{if(!state.data)return;state.view=Object.hasOwn(pageNames,location.hash.slice(1))?location.hash.slice(1):'overview';shell();});
$('#modal').addEventListener('close',()=>{state.modalJob=null;});
document.addEventListener('click',async event=>{
  const button=event.target.closest('[data-action]');if(!button)return;
  const {action,id,task,target}=button.dataset;
  try {
    if(action==='reload')location.reload();
    if(action==='refresh')await refresh(true);
    if(action==='enroll')enrollment();
    if(action==='close')$('#modal').close();
    if(action==='enroll-done'){$('#modal').close();location.hash='nodes';await refresh();}
    if(action==='node')await nodeDetail(id);
    if(action==='job')await jobDetail(id);
    if(action==='copy'){await navigator.clipboard.writeText(document.getElementById(target).textContent);toast('已复制');}
    if(action==='logout'){await api('/logout','POST');clearInterval(poll);renderLogin(true);}
    if(action==='run'){button.disabled=true;const job=await api('/nodes/'+id+'/jobs','POST',{action:task});toast('任务已提交');await refresh();await jobDetail(job.id);}
    if(action==='remove'){const node=state.data.nodes.find(n=>n.id===id);showModal('移除节点',esc(node.name),'<p>节点将从面板移除，其连接凭证将立即失效。若需重新接入，需要生成新的令牌。</p>',`<button class="btn" data-action="node" data-id="${id}">返回</button><button class="btn danger" data-action="remove-confirm" data-id="${id}">确认移除</button>`);}
    if(action==='remove-confirm'){await api('/nodes/'+id,'DELETE');$('#modal').close();toast('节点已移除，凭证已撤销');await refresh();}
  }catch(error){toast(error.message);button.disabled=false;}
});
document.addEventListener('submit',async event=>{
  const form=event.target;if(form.id==='login-form')return;event.preventDefault();
  const values=Object.fromEntries(new FormData(form));const submit=$('button[type=submit]',form);if(submit)submit.disabled=true;
  try {
    if(form.id==='enroll-form')await enrolled(await api('/enrollments','POST',values));
    if(form.id==='node-form'){
      const policy={google:!!values.google,trust:!!values.trust,interval_minutes:Number(values.interval_minutes),scheduled_action:values.scheduled_action,region_path:values.region_path};
      await api('/nodes/'+form.dataset.id,'PATCH',{name:values.name,group_name:values.group_name,region:values.region,policy});toast('配置已保存，将在下次心跳同步');await refresh();await nodeDetail(form.dataset.id);
    }
    if(form.id==='notification-form'){await api('/settings','POST',{telegram_enabled:!!values.enabled});toast('通知设置已保存');await refresh();}
    if(form.id==='password-form'){await api('/password','POST',values);clearInterval(poll);renderLogin(true);toast('密码已修改，请重新登录');}
  }catch(error){const el=$('.form-error',form);if(el)el.textContent=error.message;else toast(error.message);}
  finally{if(submit)submit.disabled=false;}
});
(async()=>{try{const session=await api('/session');if(session.authenticated){state.csrf=session.csrf;await start();}else renderLogin(session.configured);}catch(error){$('#app').innerHTML=`<div class="boot">无法连接主控：${esc(error.message)}<br><button class="btn" data-action="reload">请刷新页面重试</button></div>`;}})();
