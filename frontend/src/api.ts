import type { Camera, Config, Gallery, Person, SightEvent } from './types'

const B = '/api'

async function req<T>(path: string, opts?: RequestInit): Promise<T> {
  const r = await fetch(B + path, opts)
  if (!r.ok) {
    let msg = r.statusText
    try { msg = (await r.json()).detail || msg } catch { /* ignore */ }
    throw new Error(msg)
  }
  return r.json()
}

export const api = {
  health: () => req<any>('/health'),
  config: () => req<Config>('/config'),

  galleries: () => req<Gallery[]>('/galleries'),
  createGallery: (name: string, description: string) =>
    req<Gallery>('/galleries', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, description }),
    }),
  deleteGallery: (id: number) => req<any>(`/galleries/${id}`, { method: 'DELETE' }),
  persons: (gid: number) => req<Person[]>(`/galleries/${gid}/persons`),
  addPerson: (gid: number, name: string, note: string, file: File) => {
    // 后端 name/note 是 query 参数，file 才是 multipart 字段
    const fd = new FormData()
    fd.append('file', file)
    const q = `name=${encodeURIComponent(name)}&note=${encodeURIComponent(note)}`
    return req<Person>(`/galleries/${gid}/persons?${q}`, { method: 'POST', body: fd })
  },
  deletePerson: (id: number) => req<any>(`/persons/${id}`, { method: 'DELETE' }),

  cameras: () => req<Camera[]>('/cameras'),
  createCamera: (data: { name: string; source: string; kind: string }) =>
    req<Camera>('/cameras', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),
  deleteCamera: (id: number) => req<any>(`/cameras/${id}`, { method: 'DELETE' }),
  toggleCamera: (id: number) => req<any>(`/cameras/${id}/toggle`, { method: 'POST' }),
  discoverOnvif: () => req<any[]>('/onvif/discover'),

  events: (limit = 100) => req<SightEvent[]>(`/events?limit=${limit}`),
  setEventStatus: (id: number, status: string, note = '') =>
    req<any>(`/events/${id}/status`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status, note }),
    }),
  cleanup: () => req<any>('/events/cleanup', { method: 'POST' }),
  testNotifications: () => req<Record<string, string>>('/notifications/test', { method: 'POST' }),
  audit: () => req<any[]>('/audit'),
  purgeAll: () => req<any>('/privacy/purge-all?confirm=DELETE', { method: 'POST' }),

  // go2rtc WebRTC 播放地址（由前端直接打开）
  streamUrl: (id: number) => `/api/stream/cam_${id}`,
}
