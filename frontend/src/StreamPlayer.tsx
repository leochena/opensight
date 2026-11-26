import { useEffect, useRef, useState } from 'react'

/** go2rtc WebRTC 播放器：通过 /rtc/ 反代连本机 go2rtc，浏览器直接解码 H.264。 */
export default function StreamPlayer({ stream, enabled }: { stream: string; enabled: boolean }) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [status, setStatus] = useState<'idle' | 'connecting' | 'playing' | 'error'>('idle')
  const [error, setError] = useState('')

  useEffect(() => {
    if (!enabled || !stream) return
    let disposed = false
    let pc: RTCPeerConnection | null = null
    let ws: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null

    const start = async () => {
      setStatus('connecting')
      setError('')
      try {
        // 纯本地预览：go2rtc 与浏览器在同一主机/内网，不需要公网 STUN。
        // 留空可避免向外部 STUN 服务器暴露本机候选地址。
        pc = new RTCPeerConnection({ iceServers: [] })
        // 与 go2rtc 官方 webrtc.html 一致：先建立 recvonly transceiver，
        // 再直接把 receiver.track 挂到 <video>，不依赖 ontrack 的 stream 分组。
        const tracks = ['video', 'audio'].map((kind) =>
          pc!.addTransceiver(kind, { direction: 'recvonly' }).receiver.track,
        )
        if (videoRef.current) {
          videoRef.current.srcObject = new MediaStream(tracks)
          videoRef.current.onplaying = () => {
            if (!disposed) setStatus('playing')
          }
        }

        pc.onicecandidate = (ev) => {
          if (ev.candidate && ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
              type: 'webrtc/candidate',
              value: ev.candidate.candidate,
            }))
          }
        }
        pc.onconnectionstatechange = () => {
          if (disposed || !pc) return
          if (pc.connectionState === 'connected') setStatus('playing')
          else if (pc.connectionState === 'failed' || pc.connectionState === 'disconnected') {
            setStatus('error')
            setError('连接中断，正在重试…')
            scheduleReconnect()
          }
        }

        // WebSocket 信令通道：接收 answer 与远端 ICE candidate
        const proto = location.protocol === 'https:' ? 'wss' : 'ws'
        ws = new WebSocket(`${proto}://${location.host}/rtc/api/ws?src=${encodeURIComponent(stream)}`)
        ws.onopen = async () => {
          try {
            const offer = await pc!.createOffer()
            await pc!.setLocalDescription(offer)
            ws!.send(JSON.stringify({
              type: 'webrtc/offer',
              value: pc!.localDescription?.sdp || offer.sdp,
            }))
          } catch (e: any) {
            setError('创建连接失败：' + e.message)
            setStatus('error')
          }
        }
        ws.onmessage = async (ev) => {
          if (disposed || !pc) return
          try {
            const msg = JSON.parse(ev.data)
            if (msg.type === 'webrtc/answer' && msg.value) {
              await pc.setRemoteDescription({ type: 'answer', sdp: msg.value })
            } else if (msg.type === 'webrtc/candidate' && msg.value) {
              await pc.addIceCandidate({
                candidate: msg.value,
                sdpMid: '0',
              }).catch(() => {})
            } else if (msg.type === 'error') {
              setError(typeof msg.error === 'string' ? msg.error : JSON.stringify(msg.error))
              setStatus('error')
            }
          } catch (e) { /* 忽略畸形信令 */ }
        }
        ws.onerror = () => {
          if (disposed) return
          setStatus('error')
          setError('信令连接失败，请确认 go2rtc 正常')
          scheduleReconnect()
        }
        ws.onclose = () => {
          if (!disposed) scheduleReconnect()
        }
      } catch (e: any) {
        setStatus('error')
        setError(e.message || String(e))
      }
    }

    const scheduleReconnect = () => {
      if (disposed || reconnectTimer) return
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null
        cleanup()
        start()
      }, 3000)
    }

    const cleanup = () => {
      try { ws?.close() } catch { /* ignore */ }
      try { pc?.close() } catch { /* ignore */ }
      ws = null
      pc = null
      if (videoRef.current) videoRef.current.srcObject = null
    }

    start()
    return () => {
      disposed = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      cleanup()
    }
  }, [stream, enabled])

  if (!enabled) return null

  return (
    <div className="stream-player">
      <video ref={videoRef} autoPlay playsInline muted controls className="stream-video" />
      {status !== 'playing' && (
        <div className="stream-status">
          <span>{status === 'connecting' ? '正在连接预览…' : status === 'error' ? '预览不可用' : ''}</span>
          {error && <small>{error}</small>}
        </div>
      )}
    </div>
  )
}
