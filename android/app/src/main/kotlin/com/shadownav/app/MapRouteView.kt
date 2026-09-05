package com.shadownav.app

import android.content.Context
import android.util.AttributeSet
import android.widget.FrameLayout
import com.google.gson.JsonObject
import com.shadownav.core.GnssMode
import org.maplibre.android.MapLibre
import org.maplibre.android.camera.CameraPosition
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.MapView
import org.maplibre.android.maps.Style
import org.maplibre.android.style.expressions.Expression
import org.maplibre.android.style.layers.CircleLayer
import org.maplibre.android.style.layers.LineLayer
import org.maplibre.android.style.layers.Property
import org.maplibre.android.style.layers.PropertyFactory
import org.maplibre.android.style.sources.GeoJsonSource
import org.maplibre.geojson.Feature
import org.maplibre.geojson.FeatureCollection
import org.maplibre.geojson.LineString
import org.maplibre.geojson.Point
import java.io.File

/**
 * The real-world map route scene (blueprint Step 3): the aided/dead-reckoned
 * trails, the calibrated confidence ring, and the vehicle position, drawn as
 * MapLibre style layers over a bundled, fully offline vector basemap --
 * never a separate Filament 3D scene composited with the map (see
 * `plans/shadownav-3d-mvp-web-deck.md`'s FIX-2: two independent GL engines
 * don't cheaply composite on Android, so this view uses MapLibre's own
 * camera pitch/layers for its look, and [FilamentOrbView] stays a completely
 * separate, self-contained widget that never needs to sit over a map).
 *
 * **This is a rendering feature, not [com.shadownav.core] map-matching.**
 * `PLAN.md` §2.2 item #12 (a not-started, filter-level map constraint) is a
 * different layer of the system; this view never touches the estimator.
 *
 * **Offline by construction.** The bundled `assets/maps/monaco.mbtiles`
 * (currently a placeholder region -- see `PLAN.md`'s Step 0/3 notes for
 * swapping in the real demo route) is copied to internal storage once and
 * referenced by an absolute `mbtiles://<path>` URL, not accessed directly
 * from inside the APK: MapLibre Native's in-APK-asset mbtiles path has had
 * open reliability reports (maplibre-native#3559). See `MapStyle`'s file
 * comment for the exact URL format this needs, confirmed against
 * maplibre-native's own C++ source after an on-device test of a plausible
 * but wrong `mbtiles://file://` nesting rendered zero features.
 * `AndroidManifest.xml` has no
 * `INTERNET` permission (deliberately stripped from MapLibre's own merged
 * manifest default), so there is no live-fetch fallback if this fails --
 * it either renders from the bundled file or it doesn't render at all,
 * which is the honest behaviour for an "on-device, no cloud" pitch.
 *
 * Ground truth / error-vector-style indicators are deliberately absent:
 * the demo (`demo/gnss-demo.html`) can draw those because it has simulated
 * ground truth; this view only has real data, which has none.
 */
class MapRouteView @JvmOverloads constructor(
    context: Context, attrs: AttributeSet? = null,
) : FrameLayout(context, attrs) {

    private val mapView: MapView
    private var map: MapLibreMap? = null
    private var routeSource: GeoJsonSource? = null

    private val trackAided = ArrayList<DoubleArray>() // [lat, lon]
    private val trackDr = ArrayList<DoubleArray>()

    /** Same conformal inflation as [TrackView.conformalLambda] -- set to the
     *  same loaded value by [MainActivity], since only one of the two views
     *  is visible at a time but both compute the identical calibrated ring. */
    var conformalLambda = 1.0

    init {
        MapLibre.getInstance(context)
        mapView = MapView(context)
        addView(mapView, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT))
        mapView.getMapAsync(::onMapReady)
    }

    private fun onMapReady(m: MapLibreMap) {
        map = m
        val mbtiles = ensureMbtilesCopied(context)
        android.util.Log.i("ShadowNavMap", "mbtiles at ${mbtiles.absolutePath}, exists=${mbtiles.exists()}, size=${mbtiles.length()}")
        val json = MapStyle.buildJson(mbtiles.absolutePath)
        android.util.Log.i("ShadowNavMap", "style json: $json")
        m.setStyle(Style.Builder().fromJson(json)) { style ->
            android.util.Log.i("ShadowNavMap", "style loaded callback fired, layers=${style.layers.size}")
            val source = GeoJsonSource("route", FeatureCollection.fromFeatures(emptyList()))
            style.addSource(source)
            routeSource = source

            style.addLayer(
                LineLayer("trail-aided", "route").withProperties(
                    PropertyFactory.lineColor(hex(Palette.CYAN)),
                    PropertyFactory.lineWidth(3f),
                    PropertyFactory.lineJoin(Property.LINE_JOIN_ROUND),
                    PropertyFactory.lineCap(Property.LINE_CAP_ROUND),
                ).withFilter(Expression.eq(Expression.get("kind"), Expression.literal("aided"))),
            )
            style.addLayer(
                LineLayer("trail-dr", "route").withProperties(
                    PropertyFactory.lineColor(hex(Palette.MAGENTA)),
                    PropertyFactory.lineWidth(3f),
                    PropertyFactory.lineJoin(Property.LINE_JOIN_ROUND),
                    PropertyFactory.lineCap(Property.LINE_CAP_ROUND),
                ).withFilter(Expression.eq(Expression.get("kind"), Expression.literal("dr"))),
            )
            style.addLayer(
                // The calibrated ring (sigmaM * conformalLambda * 2.146) drawn
                // as a real geographic polygon outline (GeoCircle), not a
                // screen-space `circle-radius` -- see GeoCircle's file
                // comment for why that distinction is load-bearing here.
                LineLayer("ring", "route").withProperties(
                    PropertyFactory.lineColor(hex(Palette.AMBER)),
                    PropertyFactory.lineWidth(2f),
                    PropertyFactory.lineOpacity(0.6f),
                ).withFilter(Expression.eq(Expression.get("kind"), Expression.literal("ring"))),
            )
            style.addLayer(
                CircleLayer("vehicle", "route").withProperties(
                    PropertyFactory.circleRadius(7f),
                    PropertyFactory.circleColor(Expression.toColor(Expression.get("colour"))),
                    PropertyFactory.circleStrokeWidth(1.5f),
                    PropertyFactory.circleStrokeColor(hex(Palette.BG)),
                ).withFilter(Expression.eq(Expression.get("kind"), Expression.literal("vehicle"))),
            )
        }
        // Centred on the bundled tileset's own region regardless of any live
        // fix, so the basemap itself is always verifiable independent of
        // GPS -- important while the bundled region is still a placeholder
        // (PLAN.md Step 0/3) rather than wherever the device actually is.
        m.cameraPosition = CameraPosition.Builder()
            .target(LatLng(PLACEHOLDER_LAT, PLACEHOLDER_LON))
            .zoom(14.5)
            .build()
    }

    /**
     * Fed from the same 10 Hz call site as [TrackView.push] -- no second
     * data path. `lat`/`lon` come from the same `estimateLatLon()` call
     * [MainActivity] already makes for the trip recorder; `NaN` means no fix
     * yet, matching [TrackView]'s own "waiting for first fix" treatment.
     */
    fun push(snapshot: NavigationEngine.Snapshot, lat: Double, lon: Double) {
        if (lat.isNaN() || lon.isNaN()) return
        val point = doubleArrayOf(lat, lon)
        val dr = snapshot.mode == GnssMode.DEAD_RECKONING || snapshot.mode == GnssMode.REACQUIRING
        if (dr) trackDr.add(point) else trackAided.add(point)
        if (trackAided.size > 4000) trackAided.subList(0, 1000).clear()
        if (trackDr.size > 4000) trackDr.subList(0, 1000).clear()
        rebuildGeoJson(snapshot, point)
    }

    private fun rebuildGeoJson(snapshot: NavigationEngine.Snapshot, current: DoubleArray) {
        val features = ArrayList<Feature>()
        if (trackAided.size >= 2) features.add(lineFeature(trackAided, "aided"))
        if (trackDr.size >= 2) features.add(lineFeature(trackDr, "dr"))

        val vehicleColour = when (snapshot.mode) {
            GnssMode.AIDED -> Palette.CYAN
            GnssMode.DEGRADED, GnssMode.REACQUIRING -> Palette.AMBER
            else -> Palette.MAGENTA
        }
        features.add(pointFeature(current, "vehicle", hex(vehicleColour)))

        if (!snapshot.sigmaM.isNaN() && snapshot.sigmaM.isFinite()) {
            val radiusM = snapshot.sigmaM * conformalLambda * 2.146
            features.add(ringFeature(current[0], current[1], radiusM))
        }
        routeSource?.setGeoJson(FeatureCollection.fromFeatures(features))
    }

    private fun lineFeature(points: List<DoubleArray>, kind: String): Feature {
        val line = LineString.fromLngLats(points.map { Point.fromLngLat(it[1], it[0]) })
        return Feature.fromGeometry(line, JsonObject().apply { addProperty("kind", kind) })
    }

    private fun ringFeature(lat: Double, lon: Double, radiusM: Double): Feature {
        val ring = GeoCircle.ring(lat, lon, radiusM)
        val line = LineString.fromLngLats(ring.map { Point.fromLngLat(it[1], it[0]) })
        return Feature.fromGeometry(line, JsonObject().apply { addProperty("kind", "ring") })
    }

    private fun pointFeature(p: DoubleArray, kind: String, colourHex: String): Feature {
        val point = Point.fromLngLat(p[1], p[0])
        return Feature.fromGeometry(
            point,
            JsonObject().apply { addProperty("kind", kind); addProperty("colour", colourHex) },
        )
    }

    private fun hex(argb: Int): String = "#%06X".format(argb and 0xFFFFFF)

    // ---------------------------------------------------------- lifecycle
    // MapLibre's MapView needs every Activity lifecycle callback forwarded
    // to it (unlike FilamentOrbView's SurfaceView, which only needed
    // onAttachedToWindow/onDetachedFromWindow) -- see MainActivity's
    // matching overrides.

    fun onStart() = mapView.onStart()
    fun onResume() = mapView.onResume()
    fun onPause() = mapView.onPause()
    fun onStop() = mapView.onStop()
    fun onLowMemory() = mapView.onLowMemory()
    fun onDestroy() = mapView.onDestroy()

    companion object {
        // Monaco, matching the bundled placeholder tileset -- see PLAN.md's
        // Step 0/3 notes. Swap alongside assets/maps/*.mbtiles when the real
        // demo route is chosen. Non-private so MainActivity's debug harness
        // (no live GPS fix reaches this room) can synthesize a path near it.
        const val PLACEHOLDER_LAT = 43.7384
        const val PLACEHOLDER_LON = 7.4246
        const val ATTRIBUTION = "© OpenMapTiles © OpenStreetMap contributors"

        private fun ensureMbtilesCopied(context: Context): File {
            val dest = File(File(context.filesDir, "maps"), "monaco.mbtiles")
            if (!dest.exists()) {
                dest.parentFile?.mkdirs()
                context.assets.open("maps/monaco.mbtiles").use { input ->
                    dest.outputStream().use { output -> input.copyTo(output) }
                }
            }
            return dest
        }
    }
}
