import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Info } from 'lucide-react'

// Full-bleed LIVE Earth from the ISS (Sen SpaceTV-1, downlinked via NASA). The channel
// live_stream URL survives video-id rotation, so it always shows whatever Sen streams now.
// We attach the YouTube IFrame API to detect live vs offline; on outage we cross-fade to an
// animated Earth-glow fallback (no asset needed) rather than a dead black frame.
const SEN_CHANNEL = 'UCkvW_7kp9LJrztmgA4q4bJQ'
const IFRAME_ID = 'iss-live-frame'
const SRC = `https://www.youtube.com/embed/live_stream?channel=${SEN_CHANNEL}` +
  '&enablejsapi=1&autoplay=1&mute=1&controls=0&playsinline=1&rel=0&modestbranding=1'

declare global {
  interface Window { YT?: any; onYouTubeIframeAPIReady?: () => void }
}

function loadYT(): Promise<any> {
  return new Promise((resolve) => {
    if (window.YT && window.YT.Player) return resolve(window.YT)
    const prev = window.onYouTubeIframeAPIReady
    if (!document.getElementById('yt-iframe-api')) {
      const s = document.createElement('script')
      s.id = 'yt-iframe-api'; s.src = 'https://www.youtube.com/iframe_api'
      document.head.appendChild(s)
    }
    window.onYouTubeIframeAPIReady = () => { if (prev) prev(); resolve(window.YT) }
  })
}

export default function LiveEarthHero({ children, height = '78vh', showBadge = true }:
  { children?: ReactNode; height?: string; showBadge?: boolean }) {
  const ref = useRef<HTMLElement | null>(null)
  const apiReady = useRef(false)
  const [dim, setDim] = useState({ w: 0, h: 0 })
  const [status, setStatus] = useState<'connecting' | 'live' | 'offline'>('connecting')
  const [attempt, setAttempt] = useState(0)

  // Size the 16:9 iframe to COVER the container (crop YouTube chrome).
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const OVERSCAN = 1.4
    const fit = () => {
      const W = el.clientWidth, H = el.clientHeight, ar = 16 / 9
      const [w, h] = W / H > ar ? [W, W / ar] : [H * ar, H]
      setDim({ w: Math.ceil(w * OVERSCAN), h: Math.ceil(h * OVERSCAN) })
    }
    fit()
    const ro = new ResizeObserver(fit); ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // Detect live vs offline via the YT player.
  useEffect(() => {
    let player: any, offlineTimer: ReturnType<typeof setTimeout>, cancelled = false
    loadYT().then((YT) => {
      if (cancelled || !document.getElementById(IFRAME_ID)) return
      apiReady.current = true
      try {
        player = new YT.Player(IFRAME_ID, {
          events: {
            onReady: () => {
              try { player.playVideo() } catch { /* autoplay */ }
              offlineTimer = setTimeout(() => setStatus((s) => (s === 'live' ? s : 'offline')), 9000)
            },
            onStateChange: (e: any) => {
              if (e.data === YT.PlayerState.PLAYING) { clearTimeout(offlineTimer); setStatus('live') }
              else if (e.data === YT.PlayerState.ENDED) { setStatus('offline') }
            },
            onError: () => { clearTimeout(offlineTimer); setStatus('offline') },
          },
        })
      } catch { /* safety timer handles it */ }
    })
    const safety = setTimeout(() => { if (!apiReady.current) setStatus('live') }, 12000)
    return () => {
      cancelled = true; clearTimeout(offlineTimer); clearTimeout(safety)
      try { player && player.destroy && player.destroy() } catch { /* noop */ }
    }
  }, [attempt])

  // Retry the stream every 90s while offline.
  useEffect(() => {
    if (status !== 'offline') return
    const t = setTimeout(() => { setStatus('connecting'); setAttempt((a) => a + 1) }, 90000)
    return () => clearTimeout(t)
  }, [status])

  const isLive = status === 'live'
  const tip = isLive ? 'live · Earth from the ISS · powered by Sen' : 'Live video will begin soon'

  return (
    <section ref={ref} className="relative overflow-hidden rounded-2xl border border-[var(--color-line)]"
      style={{ height, minHeight: 320, background: '#04070f' }}>
      <iframe id={IFRAME_ID} key={attempt} src={SRC} title="Live Earth from the ISS — Sen SpaceTV-1"
        allow="autoplay; encrypted-media; picture-in-picture"
        style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
          width: dim.w, height: dim.h, border: 0, pointerEvents: 'none' }} />

      {/* animated Earth-glow fallback until confirmed live */}
      <div className="absolute inset-0 transition-opacity duration-700" style={{ opacity: isLive ? 0 : 1, pointerEvents: 'none' }}>
        <div className="absolute inset-0 drift" style={{ background: 'radial-gradient(60% 55% at 50% 78%, rgba(23,86,168,0.55) 0%, rgba(10,40,90,0.22) 42%, rgba(4,7,15,0) 72%)' }} />
        <div className="absolute inset-0" style={{ background: 'radial-gradient(38% 30% at 62% 40%, rgba(120,180,255,0.10) 0%, rgba(4,7,15,0) 70%)' }} />
      </div>

      {/* legibility gradient */}
      <div className="absolute inset-0" style={{ background: 'linear-gradient(180deg, rgba(4,7,15,0.55) 0%, rgba(4,7,15,0.10) 34%, rgba(4,7,15,0.30) 66%, rgba(4,7,15,0.90) 100%)' }} />

      {showBadge && (
        <div className="group absolute left-4 top-4 z-20">
          <div className="flex items-center gap-1.5 rounded-full bg-black/40 px-2.5 py-1.5 backdrop-blur">
            <span className={`h-2 w-2 rounded-full ${isLive ? 'bg-red-500' : 'bg-emerald-400'} animate-pulse`} />
            <span className="mono text-[10px] uppercase tracking-widest text-white/70">{isLive ? 'live' : 'connecting'}</span>
            <button type="button" aria-label={tip} className="flex items-center text-white/60 hover:text-white outline-none"><Info size={11} strokeWidth={2.2} /></button>
          </div>
        </div>
      )}

      <div className="relative z-10 h-full flex flex-col items-center justify-center text-center px-6">{children}</div>
    </section>
  )
}
