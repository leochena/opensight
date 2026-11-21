import { useCallback, useEffect, useState } from 'react'
import { Camera as CameraIcon, Images, Bell, ShieldCheck, Activity, Plus, Trash2, Play, Square, RefreshCw, Search, AlertTriangle } from 'lucide-react'
import { api } from './api'
import type { Camera, Config, Gallery, SightEvent } from './types'

type Tab = 'dashboard' | 'galleries' | 'events' | 'privacy'

export default function App() {
  const [tab, setTab] = useState<Tab>('dashboard')
  const [config, setConfig] = useState<Config | null>(null)
  const [online, setOnline] = useState(false)

  useEffect(() => {
    api.config().then(setConfig).catch(() => {})
    const t = setInterval(() => {
      api.health().then(() => setOnline(true)).catch(() => setOnline(false))
    }, 5000)
    api.health().then(() => setOnline(true)).catch(() => setOnline(false))
    return () => clearInterval(t)
  }, [])

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><Activity size={22} /></div>
          <div>
            <div className="brand-name">OpenSight</div>
            <div className="brand-sub">本地人脸辅助识别</div>
          </div>
        </div>
        <nav>
          <NavItem active={tab === 'dashboard'} onClick={() => setTab('dashboard')} icon={<CameraIcon size={18} />} label="实时预览" />
          <NavItem active={tab === 'galleries'} onClick={() => setTab('galleries')} icon={<Images size={18} />} label="比对库" />
          <NavItem active={tab === 'events'} onClick={() => setTab('events')} icon={<Bell size={18} />} label="事件记录" />
          <NavItem active={tab === 'privacy'} onClick={() => setTab('privacy')} icon={<ShieldCheck size={18} />} label="合规与隐私" />
        </nav>
        <div className="sidebar-foot">
          <div className={`dot ${online ? 'on' : 'off'}`} />
          <span>{online ? '服务在线' : '服务离线'}</span>
          {config && <span className="engine-tag">{config.engine}</span>}
        </div>
      </aside>

      <main className="main">
        <div className="notice-banner">
          <AlertTriangle size={16} />
          <span>{config?.notice_text || 'AI 辅助识别区域 · 结果仅供人工复核，不作为身份认定'}</span>
        </div>
        {tab === 'dashboard' && <Dashboard />}
        {tab === 'galleries' && <Galleries />}
        {tab === 'events' && <Events />}
        {tab === 'privacy' && <Privacy />}
      </main>
    </div>
  )
}

function NavItem({ active, onClick, icon, label }: any) {
  return <button className={`nav-item ${active ? 'active' : ''}`} onClick={onClick}>{icon}<span>{label}</span></button>
}

/* ---------------- 实时预览 / 摄像头 ---------------- */
function Dashboard() {
  const [cameras, setCameras] = useState<Camera[]>([])
  const [showAdd, setShowAdd] = useState(false)
  const [name, setName] = useState('')
  const [source, setSource] = useState('')
  const [kind, setKind] = useState('rtsp')
  const [err, setErr] = useState('')

  const load = useCallback(() => api.cameras().then(setCameras).catch(e => setErr(e.message)), [])
  useEffect(() => { load(); const t = setInterval(load, 10000); return () => clearInterval(t) }, [load])

  const add = async () => {
    if (!name || !source) return
    try { await api.createCamera({ name, source, kind }); setName(''); setSource(''); setShowAdd(false); load() }
    catch (e: any) { setErr(e.message) }
  }

  return (
    <section>
      <div className="page-head">
        <div><h1>实时预览</h1><p className="muted">摄像头画面在本地处理，不会上传到任何云端</p></div>
        <button className="btn primary" onClick={() => setShowAdd(!showAdd)}><Plus size={16} />添加摄像头</button>
      </div>

      {showAdd && (
        <div className="card form-card">
          <h3>添加摄像头</h3>
          <div className="form-row">
            <label>名称<input value={name} onChange={e => setName(e.target.value)} placeholder="例如：前门" /></label>
            <label>协议
              <select value={kind} onChange={e => setKind(e.target.value)}>
                <option value="rtsp">RTSP</option>
                <option value="onvif">ONVIF</option>
                <option value="usb">USB 摄像头</option>
              </select>
            </label>
          </div>
          <label>地址 / 流<input value={source} onChange={e => setSource(e.target.value)} placeholder="rtsp://user:pass@192.168.1.64:554/stream1 或 USB 序号 0" /></label>
          <div className="form-actions"><button className="btn" onClick={() => setShowAdd(false)}>取消</button><button className="btn primary" onClick={add}>保存</button></div>
        </div>
      )}

      {err && <div className="error">{err}</div>}

      {cameras.length === 0 ? (
        <div className="empty">
          <CameraIcon size={40} />
          <h3>还没有摄像头</h3>
          <p className="muted">添加一个 RTSP / ONVIF 摄像头，或点击上方按钮开始。</p>
        </div>
      ) : (
        <div className="cam-grid">
          {cameras.map(c => (
            <div className="cam-card" key={c.id}>
              <div className="cam-head">
                <span className={`status ${c.enabled ? 'on' : 'off'}`}>{c.enabled ? '运行中' : '已暂停'}</span>
                <strong>{c.name}</strong>
              </div>
              <div className="cam-preview">
                <div className="cam-placeholder">
                  <Play size={28} />
                  <span>实时画面由 go2rtc / WebRTC 提供</span>
                  <code>{c.source}</code>
                </div>
              </div>
              <div className="cam-foot">
                <button className="btn sm" onClick={() => api.toggleCamera(c.id).then(load)}>
                  {c.enabled ? <><Square size={14} />暂停</> : <><Play size={14} />启动</>}
                </button>
                <button className="btn sm danger" onClick={() => api.deleteCamera(c.id).then(load)}><Trash2 size={14} />删除</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

/* ---------------- 比对库 ---------------- */
function Galleries() {
  const [galleries, setGalleries] = useState<Gallery[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [persons, setPersons] = useState<any[]>([])
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [err, setErr] = useState('')

  const load = useCallback(() => api.galleries().then(setGalleries).catch(e => setErr(e.message)), [])
  useEffect(() => { load() }, [load])
  useEffect(() => { if (selected) api.persons(selected).then(setPersons) }, [selected])

  const create = async () => {
    if (!newName) return
    try { await api.createGallery(newName, newDesc); setNewName(''); setNewDesc(''); load() }
    catch (e: any) { setErr(e.message) }
  }

  return (
    <section>
      <div className="page-head"><div><h1>比对库</h1><p className="muted">照片与特征全部保存在本地，可随时删除</p></div></div>
      <div className="two-col">
        <div className="card">
          <h3>新建比对库</h3>
          <label>库名称<input value={newName} onChange={e => setNewName(e.target.value)} placeholder="例如：家人 / 员工" /></label>
          <label>说明<input value={newDesc} onChange={e => setNewDesc(e.target.value)} placeholder="可选" /></label>
          <button className="btn primary" onClick={create}><Plus size={16} />创建</button>
          <div className="divider" />
          <h3>所有比对库</h3>
          <div className="list">
            {galleries.map(g => (
              <div className={`list-item ${selected === g.id ? 'sel' : ''}`} key={g.id} onClick={() => setSelected(g.id)}>
                <div><strong>{g.name}</strong><div className="muted small">{g.person_count} 人 · {g.description}</div></div>
                <button className="icon-btn" onClick={e => { e.stopPropagation(); api.deleteGallery(g.id).then(() => { if (selected === g.id) setSelected(null); load() }) }}><Trash2 size={15} /></button>
              </div>
            ))}
            {galleries.length === 0 && <p className="muted">还没有比对库</p>}
          </div>
        </div>

        <div className="card">
          <h3>{selected ? `${galleries.find(g => g.id === selected)?.name} · 人员` : '选择左侧比对库'}</h3>
          {selected && <AddPerson gid={selected} onAdded={() => { api.persons(selected).then(setPersons); load() }} />}
          {err && <div className="error">{err}</div>}
          <div className="person-grid">
            {persons.map(p => (
              <div className="person-card" key={p.id}>
                <img src={`/api/persons/${p.id}/image`} alt={p.name} />
                <div className="person-name">{p.name}</div>
                <div className="muted small">{p.note}</div>
                <button className="btn sm danger" onClick={() => { if (selected != null) api.deletePerson(p.id).then(() => { api.persons(selected).then(setPersons); load() }) }}><Trash2 size={13} />删除</button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

function AddPerson({ gid, onAdded }: any) {
  const [name, setName] = useState('')
  const [note, setNote] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  const submit = async () => {
    if (!name || !file) return
    setBusy(true); setMsg('')
    try { await api.addPerson(gid, name, note, file); setName(''); setNote(''); setFile(null); onAdded() }
    catch (e: any) { setMsg(e.message) }
    finally { setBusy(false) }
  }

  return (
    <div className="add-person">
      <div className="form-row">
        <label>姓名<input value={name} onChange={e => setName(e.target.value)} placeholder="姓名或称呼" /></label>
        <label>备注<input value={note} onChange={e => setNote(e.target.value)} placeholder="可选" /></label>
      </div>
      <label>照片（清晰正面照）<input type="file" accept="image/*" onChange={e => setFile(e.target.files?.[0] || null)} /></label>
      <button className="btn primary" disabled={busy || !name || !file} onClick={submit}>{busy ? '处理中…' : '添加到比对库'}</button>
      {msg && <div className="error">{msg}</div>}
    </div>
  )
}

/* ---------------- 事件 ---------------- */
function Events() {
  const [events, setEvents] = useState<SightEvent[]>([])
  const load = useCallback(() => api.events().then(setEvents).catch(() => {}), [])
  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t) }, [load])

  return (
    <section>
      <div className="page-head">
        <div><h1>事件记录</h1><p className="muted">所有命中均为"候选提示"，必须由人工复核确认</p></div>
        <button className="btn" onClick={() => api.cleanup().then(load)}><RefreshCw size={16} />清理过期</button>
      </div>
      {events.length === 0 ? (
        <div className="empty"><Bell size={40} /><h3>暂无事件</h3><p className="muted">当摄像头画面与比对库产生相似候选时，会在此显示。</p></div>
      ) : (
        <div className="event-list">
          {events.map(e => (
            <div className="event-item" key={e.id}>
              <div className="event-thumb">
                {e.snapshot_url ? <img src={e.snapshot_url} alt="snapshot" /> : <CameraIcon size={24} />}
              </div>
              <div className="event-body">
                <div className="event-title"><strong>{e.person_name}</strong><span className="sim">相似度 {(e.similarity * 100).toFixed(1)}%</span></div>
                <div className="muted small">摄像头：{e.camera_name} · {e.created_at ? new Date(e.created_at).toLocaleString() : ''}</div>
                <div className="muted small warn-note">AI 辅助提示 · 仅供人工复核，非身份认定</div>
              </div>
              <div className="event-actions">
                <button className="btn sm" onClick={() => api.setEventStatus(e.id, 'acknowledged').then(load)}>已复核</button>
                <button className="btn sm" onClick={() => api.setEventStatus(e.id, 'dismissed').then(load)}>忽略</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

/* ---------------- 合规与隐私 ---------------- */
const NOTIFIER_LABELS: Record<string, string> = {
  telegram: 'Telegram Bot（出站，无需域名）',
  custom_bot: '企业微信 / 钉钉 / 飞书群机器人（出站）',
  local_bridge: '本地长连接桥接器 OpenClaw / QQ / 微信',
  webhook: '传统 HTTP Webhook（接收方需公网可达）',
  mqtt: 'MQTT',
}

function Privacy() {
  const [audit, setAudit] = useState<any[]>([])
  const [msg, setMsg] = useState('')
  const [notifiers, setNotifiers] = useState<string[]>([])
  const [testResult, setTestResult] = useState<Record<string, string>>({})
  useEffect(() => {
    api.audit().then(setAudit).catch(() => {})
    api.config().then(c => setNotifiers(c.notifiers || [])).catch(() => {})
  }, [])

  const sendTest = () => {
    setTestResult({})
    api.testNotifications().then(setTestResult).catch(e => setMsg(e.message))
  }

  const purge = () => {
    if (!window.confirm('此操作将永久删除所有比对库、照片、特征与事件记录，且不可恢复。确认继续？')) return
    api.purgeAll().then(() => { setMsg('所有本地数据已清除'); api.audit().then(setAudit) }).catch(e => setMsg(e.message))
  }

  return (
    <section>
      <div className="page-head"><div><h1>合规与隐私</h1><p className="muted">工具中立，责任在使用者。请依法合规使用。</p></div></div>
      <div className="card">
        <h3>使用原则</h3>
        <ul className="principles">
          <li>仅处理你有权处理的照片；导入他人照片前取得必要授权</li>
          <li>在采集区域设置显著告知标识，系统已在预览叠加提示</li>
          <li>识别结果仅为候选提示，必须由人工复核，不得作为身份认定或执法依据</li>
          <li>不得用于秘密监控、人肉搜索或非法的身份辨识</li>
          <li>遵守所在司法辖区法规：中国《个人信息保护法》/《人脸识别技术应用安全管理办法》、欧盟 GDPR、美国各州 BIPA 等</li>
        </ul>
      </div>
      <div className="card">
        <h3>告警通道</h3>
        <p className="muted small">通道在 <code>config/config.yaml</code> 的 <code>notifications</code> 段配置，密钥不会显示在界面上。除 Webhook 外均由本机主动连出，不需要域名或内网穿透。</p>
        {notifiers.length === 0 ? (
          <p className="muted">当前未启用任何告警通道，命中只会在“事件记录”页显示。配置方法见 docs/NOTIFICATIONS.md。</p>
        ) : (
          <ul className="principles">
            {notifiers.map(n => <li key={n}><strong>{n}</strong> — {NOTIFIER_LABELS[n] || '自定义通道'}</li>)}
          </ul>
        )}
        <div className="form-actions">
          <button className="btn" onClick={sendTest} disabled={notifiers.length === 0}><Bell size={15} />发送测试通知</button>
        </div>
        {Object.keys(testResult).length > 0 && (
          <div className="ok-msg">
            {Object.entries(testResult).map(([k, v]) => <div key={k}><code>{k}</code>：{v}</div>)}
          </div>
        )}
        {msg && <div className="error">{msg}</div>}
      </div>
      <div className="card">
        <h3>审计日志</h3>
        <div className="audit-list">
          {audit.slice(0, 30).map((a, i) => (
            <div key={i} className="audit-row"><code>{a.action}</code><span className="muted small">{a.detail}</span><span className="muted small">{a.time}</span></div>
          ))}
          {audit.length === 0 && <p className="muted">暂无操作记录</p>}
        </div>
      </div>
      <div className="card danger-zone">
        <h3>数据清除</h3>
        <p className="muted">一键删除本机所有比对库、照片、特征向量、快照与事件记录。</p>
        <button className="btn danger" onClick={purge}><Trash2 size={16} />清除所有本地数据</button>
        {msg && <div className="ok-msg">{msg}</div>}
      </div>
    </section>
  )
}
