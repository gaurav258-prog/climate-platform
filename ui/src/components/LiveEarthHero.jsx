import { useEffect, useRef, useState } from 'react'
import { Info } from 'lucide-react'

// Full-bleed LIVE Earth from the ISS (Sen SpaceTV-1, 4K, downlinked via NASA).
// The channel live-stream URL survives video-id rotation, so it always shows
// whatever Sen is streaming right now.
//
// Live-state: we attach the YouTube IFrame API to detect whether the channel is
// actually streaming. PLAYING → live (red dot); error/timeout → offline (green
// dot + "begin soon"), and we show a fallback loop instead of a dead black frame.
// Detection is best-effort (an embedded cross-origin player exposes limited
// signal); if the API never loads we optimistically show the stream.
const SEN_CHANNEL = 'UCkvW_7kp9LJrztmgA4q4bJQ'
const IFRAME_ID = 'iss-live-frame'
const SRC = `https://www.youtube.com/embed/live_stream?channel=${SEN_CHANNEL}` +
  '&enablejsapi=1&autoplay=1&mute=1&controls=0&playsinline=1&rel=0&modestbranding=1'
// Drop a short PUBLIC-DOMAIN NASA/ESA Earth clip here and it plays during outages.
// (We can't lawfully splice Sen's live feed.) Absent/failed → animated fallback.
const FALLBACK_VIDEO = '/earth-loop.mp4'

function loadYT() {
  return new Promise((resolve) => {
    if (window.YT && window.YT.Player) return resolve(window.YT)
    const prev = window.onYouTubeIframeAPIReady
    if (!document.getElementById('yt-iframe-api')) {
      const s = document.createElement('script')
      s.id = 'yt-iframe-api'
      s.src = 'https://www.youtube.com/iframe_api'
      document.head.appendChild(s)
    }
    window.onYouTubeIframeAPIReady = () => { if (prev) prev(); resolve(window.YT) }
  })
}

export default function LiveEarthHero({ children, showBadge = true, height = '78vh' }) {
  const ref = useRef(null)
  const apiReady = useRef(false)
  const [dim, setDim] = useState({ w: 0, h: 0 })
  const [status, setStatus] = useState('connecting') // connecting | live | offline
  const [attempt, setAttempt] = useState(0)           // remount key to retry the stream
  const [fallbackOk, setFallbackOk] = useState(true)  // false once the clip 404s/errors

  // Size the 16:9 iframe to COVER the container (crop YouTube's chrome).
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
    const ro = new ResizeObserver(fit)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // Attach the YT player to detect live vs offline (re-runs on retry).
  useEffect(() => {
    let player, offlineTimer, cancelled = false
    loadYT().then((YT) => {
      if (cancelled || !document.getElementById(IFRAME_ID)) return
      apiReady.current = true
      try {
        player = new YT.Player(IFRAME_ID, {
          events: {
            onReady: () => {
              try { player.playVideo() } catch { /* autoplay */ }
              offlineTimer = setTimeout(
                () => setStatus((s) => (s === 'live' ? s : 'offline')), 9000)
            },
            onStateChange: (e) => {
              if (e.data === YT.PlayerState.PLAYING) { clearTimeout(offlineTimer); setStatus('live') }
              else if (e.data === YT.PlayerState.ENDED) { setStatus('offline') }
            },
            onError: () => { clearTimeout(offlineTimer); setStatus('offline') },
          },
        })
      } catch { /* leave as connecting; safety timer handles it */ }
    })
    // Safety: if the API never loads (blocked), don't hide the stream forever.
    const safety = setTimeout(() => { if (!apiReady.current) setStatus('live') }, 12000)
    return () => {
      cancelled = true
      clearTimeout(offlineTimer); clearTimeout(safety)
      try { player && player.destroy && player.destroy() } catch { /* noop */ }
    }
  }, [attempt])

  // While offline, retry the stream every 90s (a stream can come back).
  useEffect(() => {
    if (status !== 'offline') return
    const t = setTimeout(() => { setStatus('connecting'); setAttempt((a) => a + 1) }, 90000)
    return () => clearTimeout(t)
  }, [status])

  const isLive = status === 'live'
  const tip = isLive ? 'live · Earth from the ISS · powered by Sen' : 'Live video will begin soon'

  return (
    <section ref={ref} className="relative overflow-hidden"
      style={{ height, minHeight: 540, background: '#04070f' }}>
      {/* live stream (bottom layer; kept mounted so we can detect state) */}
      <iframe
        id={IFRAME_ID} key={attempt} src={SRC}
        title="Live Earth from the ISS — Sen SpaceTV-1"
        allow="autoplay; encrypted-media; picture-in-picture"
        style={{
          position: 'absolute', top: '50%', left: '50%',
          transform: 'translate(-50%, -50%)', width: dim.w, height: dim.h,
          border: 0, pointerEvents: 'none',
        }}
      />

      {/* fallback layer — shown until the stream is confirmed live */}
      <div className="absolute inset-0 transition-opacity duration-700"
        style={{ opacity: isLive ? 0 : 1, pointerEvents: 'none' }}>
        {fallbackOk ? (
          <video
            src={FALLBACK_VIDEO} autoPlay muted loop playsInline
            onError={() => setFallbackOk(false)}
            className="h-full w-full object-cover"
          />
        ) : (
          // Graceful animated fallback (no asset needed): drifting Earth-glow.
          <div className="h-full w-full" style={{ background: '#04070f' }}>
            <div className="absolute inset-0 tl-drift" style={{
              background:
                'radial-gradient(60% 55% at 50% 78%, rgba(23,86,168,0.55) 0%, rgba(10,40,90,0.22) 42%, rgba(4,7,15,0) 72%)',
            }} />
            <div className="absolute inset-0" style={{
              background:
                'radial-gradient(38% 30% at 62% 40%, rgba(120,180,255,0.10) 0%, rgba(4,7,15,0) 70%)',
            }} />
          </div>
        )}
      </div>

      {/* legibility gradient */}
      <div className="absolute inset-0" style={{
        background: 'linear-gradient(180deg, rgba(4,7,15,0.60) 0%, rgba(4,7,15,0.12) 34%, ' +
          'rgba(4,7,15,0.30) 66%, rgba(4,7,15,0.88) 100%)',
      }} />

      {/* live/offline badge — dot + info; text revealed on hover/focus of the i */}
      {showBadge && (
        <div className="group absolute left-6 top-6 z-20">
          <div className="flex items-center gap-1.5 rounded-full bg-black/40 px-2.5 py-1.5 backdrop-blur">
            <span className={`h-2 w-2 rounded-full ${isLive ? 'bg-red-500' : 'bg-emerald-400'} animate-pulse`} />
            <button type="button" aria-label={tip}
              className="flex items-center text-white/70 outline-none hover:text-white focus-visible:text-white">
              <Info size={12} strokeWidth={2.2} />
            </button>
          </div>
          <div className="pointer-events-none absolute left-0 top-full mt-1.5 whitespace-nowrap rounded-md bg-black/70 px-2.5 py-1 text-[11px] font-medium text-white/90 opacity-0 backdrop-blur transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100">
            {tip}
          </div>
        </div>
      )}

      {/* content */}
      <div className="relative z-10 flex h-full flex-col items-center justify-center px-8 text-center">
        {children}
      </div>

      {/* provenance caption */}
      <div className="absolute bottom-4 right-6 z-10 text-[10px] tracking-wide text-white/55">
        Sen SpaceTV-1 · 4K · downlinked via NASA · {isLive ? 'live' : 'standby'}
      </div>
    </section>
  )
}
