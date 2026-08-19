import { useEffect, useRef, useState } from 'react'
import * as Cesium from 'cesium'

/**
 * 3D Cesium Globe Component
 * - Rotating 3D globe at zoom out
 * - Transitions to flat map at zoom in
 * - Risk visualization with color overlay
 */
export default function CesiumGlobe({ hazardType = 'flood' }) {
  const containerRef = useRef(null)
  const viewerRef = useRef(null)
  const [isGlobe, setIsGlobe] = useState(true)

  useEffect(() => {
    if (!containerRef.current) return

    // Initialize Cesium Viewer
    const viewer = new Cesium.Viewer(containerRef.current, {
      // Globe & Camera
      baseLayerPicker: false,
      fullscreenButton: false,
      homeButton: false,
      infoBox: false,
      timeline: false,
      animation: false,
      selectionIndicator: false,
      navigationHelpButton: false,
      geocoder: false,

      // Imagery
      imageryProvider: Cesium.ArcGisMapServerImageryProvider.fromUrl(
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer'
      ),

      // Scene
      terrainProvider: Cesium.ArcGisTerrainProvider.fromUrl(
        'https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/ImageServer'
      ),

      // Camera
      requestRenderMode: false,
      maximumRenderTimeChange: Infinity,
    })

    // Configure viewer
    viewer.scene.globe.enableLighting = true
    viewer.scene.globe.showGroundAtmosphere = true
    viewer.scene.shadows = Cesium.ShadowMode.ENABLED

    // Set initial camera position (globe view)
    viewer.camera.setView({
      destination: Cesium.Cartesian3.fromDegrees(0, 0, 20000000),
      orientation: {
        heading: 0,
        pitch: -90,
        roll: 0,
      },
    })

    // Enable rotation
    viewer.scene.screenSpaceCameraController.inertiaZoom = 0.3
    viewer.scene.screenSpaceCameraController.enableRotate = true
    viewer.scene.screenSpaceCameraController.enableTilt = true

    viewerRef.current = viewer

    // Handle zoom level changes
    const onCameraChanged = () => {
      const cartographic = Cesium.Cartographic.fromCartesian(viewer.camera.position)
      const height = cartographic.height

      // Switch to flat map view at certain zoom level (when close to surface)
      const shouldBeGlobe = height > 5000000 // ~5,000 km altitude

      if (shouldBeGlobe !== isGlobe) {
        setIsGlobe(shouldBeGlobe)

        if (!shouldBeGlobe) {
          // Smooth transition to flat map
          viewer.scene.morphToMap(Cesium.SceneMode.SCENE2D, 1000)
        } else if (viewer.scene.mode === Cesium.SceneMode.SCENE2D) {
          // Smooth transition back to 3D globe
          viewer.scene.morphTo3D(1000)
        }
      }
    }

    viewer.camera.changed.addEventListener(onCameraChanged)

    // Add risk visualization layer
    addRiskLayer(viewer, hazardType)

    // Cleanup
    return () => {
      viewer.camera.changed.removeEventListener(onCameraChanged)
      if (!viewer.isDestroyed()) {
        viewer.destroy()
      }
    }
  }, [hazardType, isGlobe])

  return (
    <div
      ref={containerRef}
      className="w-full h-full relative"
      style={{ background: '#000' }}
    >
      <div className="absolute bottom-4 left-4 text-white text-xs z-10 bg-black/50 px-3 py-2 rounded">
        {isGlobe ? '🌍 Globe View' : '🗺️ Map View'} • Scroll to zoom
      </div>
    </div>
  )
}

/**
 * Add risk visualization layer to globe
 */
function addRiskLayer(viewer, hazardType) {
  // Risk data by region (simplified)
  const riskRegions = {
    flood: [
      { name: 'Rhine Basin', lat: 50.5, lon: 6.5, risk: 0.78 },
      { name: 'Po Valley', lat: 45.5, lon: 11.5, risk: 0.72 },
      { name: 'Danube Basin', lat: 47.0, lon: 18.0, risk: 0.65 },
      { name: 'Thames', lat: 51.5, lon: 0.0, risk: 0.42 },
    ],
    wildfire: [
      { name: 'Mediterranean', lat: 40.0, lon: 15.0, risk: 0.92 },
      { name: 'Iberia', lat: 40.0, lon: -5.0, risk: 0.85 },
      { name: 'Balkans', lat: 42.0, lon: 21.0, risk: 0.72 },
      { name: 'Central Europe', lat: 50.0, lon: 12.0, risk: 0.58 },
    ],
    heat: [
      { name: 'Mediterranean', lat: 38.0, lon: 15.0, risk: 0.89 },
      { name: 'Iberia', lat: 40.0, lon: -5.0, risk: 0.85 },
      { name: 'Greece', lat: 39.0, lon: 22.0, risk: 0.78 },
      { name: 'Central Europe', lat: 50.0, lon: 12.0, risk: 0.52 },
    ],
    seismic: [
      { name: 'Mediterranean Belt', lat: 40.0, lon: 15.0, risk: 0.85 },
      { name: 'Alpine', lat: 47.0, lon: 10.0, risk: 0.72 },
      { name: 'Iceland', lat: 65.0, lon: -19.0, risk: 0.92 },
      { name: 'Eastern Europe', lat: 50.0, lon: 40.0, risk: 0.58 },
    ],
  }

  const regions = riskRegions[hazardType] || riskRegions.flood

  // Add risk circles to globe
  regions.forEach((region) => {
    const color = getRiskColor(region.risk)
    const radius = 100000 + region.risk * 200000 // Radius based on risk

    // Add circle at location
    viewer.entities.add({
      position: Cesium.Cartesian3.fromDegrees(region.lon, region.lat),
      ellipse: {
        semiMinorAxis: radius,
        semiMajorAxis: radius,
        material: color.withAlpha(0.5),
        outline: true,
        outlineColor: color,
        outlineWidth: 2,
      },
      label: {
        text: `${region.name}\n${Math.round(region.risk * 100)}%`,
        font: '12px sans-serif',
        fillColor: Cesium.Color.WHITE,
        showBackground: true,
        backgroundColor: new Cesium.Color(0, 0, 0, 0.7),
        pixelOffset: new Cesium.Cartesian2(0, -20),
        heightReference: Cesium.HeightReference.NONE,
      },
    })
  })
}

/**
 * Get color based on risk level
 */
function getRiskColor(riskLevel) {
  if (riskLevel >= 0.8) return Cesium.Color.RED
  if (riskLevel >= 0.6) return Cesium.Color.ORANGE
  if (riskLevel >= 0.4) return Cesium.Color.YELLOW
  return Cesium.Color.GREEN
}
