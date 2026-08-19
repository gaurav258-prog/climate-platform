#!/bin/bash

# Download background videos for Risk Map pages
# Uses free stock video sources

set -e

echo "🎬 Downloading background videos..."

# Create videos directory
mkdir -p public/videos

cd public/videos

# Define video sources (Pexels free videos - no authentication needed)
# These are direct MP4 download links from publicly available videos

echo "Downloading flood video..."
curl -L -o flood-background.mp4 "https://videos.pexels.com/video-files/3571937/3571937-sd_640_360_30fps.mp4" 2>/dev/null || echo "⚠️  Flood video download failed"

echo "Downloading wildfire video..."
curl -L -o wildfire-background.mp4 "https://videos.pexels.com/video-files/4159260/4159260-sd_640_360_25fps.mp4" 2>/dev/null || echo "⚠️  Wildfire video download failed"

echo "Downloading heat video..."
curl -L -o heat-background.mp4 "https://videos.pexels.com/video-files/3129750/3129750-sd_640_360_24fps.mp4" 2>/dev/null || echo "⚠️  Heat video download failed"

echo "Downloading seismic video..."
curl -L -o seismic-background.mp4 "https://videos.pexels.com/video-files/2144862/2144862-sd_640_360_25fps.mp4" 2>/dev/null || echo "⚠️  Seismic video download failed"

cd ../..

echo ""
echo "✅ Video download complete!"
echo ""
echo "Videos saved to: public/videos/"
ls -lh public/videos/ 2>/dev/null || echo "No videos found"

echo ""
echo "💡 Tip: If downloads failed, you can:"
echo "   1. Visit https://www.pexels.com/search/videos/"
echo "   2. Download water/flood, fire, sun/heat, earthquake videos"
echo "   3. Save them to public/videos/ with the names above"
