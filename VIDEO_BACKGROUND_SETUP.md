# Video Background Setup Guide

## Overview
All risk map pages (Flood, Wildfire, Heat, Seismic) are now configured to use video backgrounds. This guide explains how to add the video files.

---

## File Structure

Create the following directory and add video files:

```
climate-platform/
└── ui/
    └── public/
        └── videos/
            ├── flood-background.mp4
            ├── flood-background.webm
            ├── wildfire-background.mp4
            ├── wildfire-background.webm
            ├── heat-background.mp4
            ├── heat-background.webm
            ├── seismic-background.mp4
            └── seismic-background.webm
```

---

## Video Requirements

### Recommended Specs
- **Duration**: 5-15 seconds (will loop)
- **Format**: MP4 (H.264) + WebM (VP8/VP9)
- **Resolution**: 1920×1080 or higher
- **Aspect Ratio**: 16:9
- **File Size**: 2-8 MB per format (8-16 MB total per hazard)
- **Frame Rate**: 24-30 fps

### Why Two Formats?
- **MP4**: Supported on all browsers, mobile
- **WebM**: Better compression, modern browsers

---

## Getting Free Videos

### Option 1: Pexels Video (Recommended)
Free, high-quality, no attribution needed.

**Flood videos:**
- https://www.pexels.com/search/videos/flood/
- Search: "water", "rain", "river"

**Wildfire videos:**
- https://www.pexels.com/search/videos/fire/
- Search: "flame", "burn", "smoke"

**Heat videos:**
- https://www.pexels.com/search/videos/sun/
- Search: "desert", "heat", "summer", "hot"

**Seismic videos:**
- https://www.pexels.com/search/videos/earthquake/
- Search: "ground", "wave", "vibration"

### Option 2: Pixabay Video
https://pixabay.com/videos/
Similar to Pexels, free videos.

### Option 3: Unsplash Video
https://videos.unsplash.com/
Large selection of free videos.

---

## Converting Videos

### Using FFmpeg (Free)

**Install FFmpeg:**
```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get install ffmpeg

# Windows
choco install ffmpeg
```

**Convert MOV/AVI to MP4:**
```bash
ffmpeg -i input-video.mov -c:v libx264 -c:a aac output.mp4
```

**Convert MP4 to WebM:**
```bash
ffmpeg -i output.mp4 -c:v libvpx-vp9 -crf 30 output.webm
```

**Compress MP4 (reduce file size):**
```bash
ffmpeg -i input.mp4 -vcodec libx264 -crf 28 output.mp4
```

---

## Implementation

### Step 1: Create Videos Directory
```bash
mkdir -p ui/public/videos
```

### Step 2: Add Video Files
- Download or record videos for each hazard
- Convert to MP4 + WebM format
- Place in `ui/public/videos/`
- Name exactly as specified above

### Step 3: Test
1. Start the dev server: `npm run dev`
2. Navigate to Risk Map pages
3. Verify videos autoplay with no audio
4. Check each hazard type loads its video

### Step 4: Fallback
If a video file is missing or fails to load:
- The gradient overlay is still visible
- Page continues to work normally
- User sees gradient background instead

---

## Video Specifications Per Hazard

### Flood
- **Content**: Water, rain, rivers, flowing water
- **Colors**: Blues, cyans, light blues
- **Filter**: `brightness(0.8) saturate(1.2)`
- **Mood**: Calm to active water flow

### Wildfire
- **Content**: Fire, flames, smoke, burning
- **Colors**: Reds, oranges, yellows
- **Filter**: `brightness(0.85) saturate(1.3) hue-rotate(-10deg)`
- **Mood**: Intense, dangerous, urgent

### Heat
- **Content**: Sun, desert, heat shimmer, hot landscape
- **Colors**: Yellows, oranges, reds
- **Filter**: `brightness(0.9) saturate(1.4) hue-rotate(20deg)`
- **Mood**: Bright, intense, extreme

### Seismic
- **Content**: Ground movement, earthquakes, waves, tremors
- **Colors**: Grays, earth tones, dark tones
- **Filter**: `brightness(0.85) saturate(1.2) hue-rotate(-20deg)`
- **Mood**: Serious, powerful, ground-focused

---

## Performance Tips

1. **File Size**: Keep videos under 8 MB each for faster loading
2. **Compression**: Use WebM for better compression (40-50% smaller)
3. **Preload**: Videos start on page load, preload in background
4. **Bandwidth**: Consider user bandwidth on mobile
5. **Caching**: Videos are cached by browsers after first load

---

## Troubleshooting

### Video Won't Play
- Check file is in correct path: `ui/public/videos/`
- Verify filename matches exactly (case-sensitive)
- Check file is valid MP4/WebM format
- Try different video source

### Video is Too Slow/Stutters
- Reduce video resolution to 1280×720
- Re-encode with lower bitrate
- Check system performance

### Audio Playing
- Ensure `muted` attribute is in HTML
- Video should have no audio stream

### File Size Too Large
- Reduce duration to 8-10 seconds
- Lower resolution to 1280×720
- Increase compression (FFmpeg `-crf` parameter)

---

## Browser Support

| Browser | MP4 | WebM |
|---------|-----|------|
| Chrome  | ✅  | ✅   |
| Firefox | ✅  | ✅   |
| Safari  | ✅  | ❌   |
| Edge    | ✅  | ✅   |
| Mobile  | ✅  | ~    |

**Note**: MP4 format ensures broad compatibility. WebM is optional but recommended for better compression.

---

## Quick Start

1. **Get videos from Pexels** (easiest)
2. **Convert to MP4 + WebM** using FFmpeg
3. **Place in `ui/public/videos/`**
4. **Refresh browser** to see videos

That's it! Videos will autoplay with gradient overlay on top. ✅
