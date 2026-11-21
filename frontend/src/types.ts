export interface Gallery {
  id: number
  name: string
  description: string
  created_at?: string
  person_count: number
}

export interface Person {
  id: number
  gallery_id: number
  name: string
  note: string
  created_at?: string
}

export interface Camera {
  id: number
  name: string
  source: string
  kind: string
  enabled: boolean
  zone: number[] | null
  gallery_ids: number[]
}

export interface SightEvent {
  id: number
  camera_id: number
  camera_name: string
  person_id: number
  person_name: string
  gallery_id: number
  similarity: number
  snapshot_url: string
  status: string
  note: string
  created_at?: string
}

export interface Config {
  name: string
  notice_text: string
  overlay_notice: boolean
  threshold: number
  engine: string
  notifiers: string[]
}
