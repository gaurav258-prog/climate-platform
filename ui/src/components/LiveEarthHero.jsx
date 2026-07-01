import { useEffect, useRef, useState } from 'react'

// Full-bleed LIVE Earth from the ISS (Sen SpaceTV-1, 4K, downlinked via NASA).
// The channel live-stream URL survives video-id rotation, so it always shows
// whatever Sen is streaming right now. On-brand: the platform runs on live space
// data — here is the Earth we watch, in real time.
const SEN_CHANNEL = 'UCkvW_7kp9LJrztmgA4q4bJQ'
const SRC = `https://www.youtube.com/embed/live_stream?channel=${SEN_CHANNEL}` +
  '&autoplay=1&mute=1&controls=0&playsinline=1&rel=0&modestbranding=1'

export default function LiveEarthHero({ children, showBadge = true, height = '78vh' }) {
  const ref = useRef(null)
  const [dim, setDim] = useState({ w: 0, h: 0 })

  // Size the 16:9 iframe to COVER the container (crop, never letterbox).
  useEffect(() => {
    const el = ref.current
    if (!el) return
    // Overscan past cover so YouTube's own chrome (title bar top, live UI bottom)
    // is cropped outside the container — leaving just clean Earth.
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

  return (
    <section ref={ref} className="relative overflow-hidden"
      style={{ height, minHeight: 540, background: '#04070f' }}>
      <iframe
        src={SRC} title="Live Earth from the ISS — Sen SpaceTV-1"
        allow="autoplay; encrypted-media; picture-in-picture"
        style={{
          position: 'absolute', top: '50%', left: '50%',
          transform: 'translate(-50%, -50%)', width: dim.w, height: dim.h,
          border: 0, pointerEvents: 'none',
        }}
      />
      {/* legibility gradient */}
      <div className="absolute inset-0" style={{
        background: 'linear-gradient(180deg, rgba(4,7,15,0.60) 0%, rgba(4,7,15,0.12) 34%, ' +
          'rgba(4,7,15,0.30) 66%, rgba(4,7,15,0.88) 100%)',
      }} />
      {/* live badge */}
      {showBadge && (
        <div className="absolute left-6 top-6 z-10 flex items-center gap-2 rounded-full bg-black/40 px-3 py-1.5 text-[11px] font-medium text-white/90 backdrop-blur">
          <span className="h-2 w-2 rounded-full bg-red-500 animate-pulse" />
          LIVE · EARTH FROM THE ISS · powered by Sen
        </div>
      )}
      {/* content */}
      <div className="relative z-10 flex h-full flex-col items-center justify-center px-8 text-center">
        {children}
      </div>
      {/* provenance caption */}
      <div className="absolute bottom-4 right-6 z-10 text-[10px] tracking-wide text-white/55">
        Sen SpaceTV-1 · 4K · downlinked via NASA · live
      </div>
    </section>
  )
}
