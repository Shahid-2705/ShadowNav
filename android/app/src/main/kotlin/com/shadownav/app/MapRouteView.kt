package com.shadownav.app

import android.content.Context
import android.graphics.RectF
import android.os.SystemClock
import android.util.AttributeSet
import android.view.Gravity
import android.view.MotionEvent
import android.widget.FrameLayout
import com.google.gson.JsonObject
import com.shadownav.core.GnssMode
import org.maplibre.android.MapLibre
import org.maplibre.android.camera.CameraPosition
import org.maplibre.android.camera.CameraUpdateFactory
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
import org.maplibre.geojson.MultiLineString
import org.maplibre.geojson.Point
import java.io.File
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.sqrt

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
    private var flyInInProgress = false

    private val trackAided = ArrayList<DoubleArray>() // [lat, lon]
    private val trackDr = ArrayList<DoubleArray>()

    /** Last real (or debug-synthetic) position pushed, used as the fly-in's
     *  target once one exists, and by [followMode] each update. Starts at
     *  the bundled tileset's own centre so a fly-in triggered before any fix
     *  still lands somewhere meaningful. */
    private var lastKnownLatLng = LatLng(PLACEHOLDER_LAT, PLACEHOLDER_LON)

    /** Recentres the camera on [lastKnownLatLng] after every push, preserving
     *  whatever zoom/tilt/bearing the user has gestured to -- a driving app's
     *  ordinary default. Suspended automatically during [flyIn] so the two
     *  camera movements never fight each other. Public so a future control
     *  could let the user toggle it; the task only asked that the capability
     *  exist, not that it default off. */
    var followMode = true

    /** Same conformal inflation as [TrackView.conformalLambda] -- set to the
     *  same loaded value by [MainActivity], since only one of the two views
     *  is visible at a time but both compute the identical calibrated ring. */
    var conformalLambda = 1.0

    init {
        MapLibre.getInstance(context)
        mapView = MapView(context)
        addView(mapView, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT))
        mapView.getMapAsync(::onMapReady)
        addView(buildFlyInButton())

        // MainActivity's whole screen is one ScrollView (Ui.kt), and a
        // ScrollView intercepts touch sequences from any nested child by
        // default -- real-device testing found this made pinch-zoom "really
        // hard" (a two-finger pinch reads as ambiguous drag input, which the
        // ScrollView grabs before MapLibre's own gesture detector sees it).
        // The standard fix: tell every ancestor not to intercept for as long
        // as a touch sequence is happening on the map, and hand control back
        // on release so normal page scrolling still works everywhere else.
        mapView.setOnTouchListener { _, event ->
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN, MotionEvent.ACTION_POINTER_DOWN ->
                    parent?.requestDisallowInterceptTouchEvent(true)
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL ->
                    parent?.requestDisallowInterceptTouchEvent(false)
            }
            false // never consume: MapLibre's own touch handling still runs
        }
    }

    private fun onMapReady(m: MapLibreMap) {
        map = m

        // Gestures: pinch-zoom, pan, rotate and tilt, per this step's task --
        // none of these were enabled before (MapLibre's own default has zoom
        // and scroll on but rotate/tilt off), so the map was previously
        // lookable-at but not truly explorable in 3D.
        m.uiSettings.apply {
            isZoomGesturesEnabled = true
            isScrollGesturesEnabled = true
            isRotateGesturesEnabled = true
            isTiltGesturesEnabled = true
            isDoubleTapGesturesEnabled = true
            isQuickZoomGesturesEnabled = true
        }
        // Zoom is bounded: below ~10 the whole placeholder region is a
        // speck, above 19 vector tiles are so overzoomed past the tileset's
        // native maxzoom (14) that geometry visibly chunks. A hard pan-bounds
        // clamp (setLatLngBoundsForCameraTarget) was tried here and removed:
        // real-device testing found it made the map feel like "only one
        // specific area is visible" -- Monaco's bundled extent is small
        // enough that a firm wall was reached almost immediately, which
        // reads as broken rather than as "no data past here." Panning past
        // the bundled tiles now just shows blank background, a softer and
        // more honest failure mode than a wall the user can't explain.
        m.setMinZoomPreference(10.0)
        m.setMaxZoomPreference(19.0)

        val mbtiles = ensureMbtilesCopied(context)
        android.util.Log.i("ShadowNavMap", "mbtiles at ${mbtiles.absolutePath}, exists=${mbtiles.exists()}, size=${mbtiles.length()}")
        val json = MapStyle.buildJson(mbtiles.absolutePath)
        android.util.Log.i("ShadowNavMap", "style json: $json")
        m.setStyle(Style.Builder().fromJson(json)) { style ->
            android.util.Log.i("ShadowNavMap", "style loaded callback fired, layers=${style.layers.size}")
            val source = GeoJsonSource("route", FeatureCollection.fromFeatures(emptyList()))
            style.addSource(source)
            routeSource = source

            // Width scales with zoom so the route reads as a legible line
            // whether the camera is at the wide fly-in start (where a fixed
            // pixel width would vanish) or street level (where the same
            // fixed width would become a fat blob relative to a building).
            val widthByZoom = Expression.interpolate(
                Expression.linear(), Expression.zoom(),
                Expression.stop(10, 1.5f), Expression.stop(16, 4f), Expression.stop(19, 7f),
            )
            style.addLayer(
                LineLayer("trail-aided", "route").withProperties(
                    PropertyFactory.lineColor(hex(Palette.CYAN)),
                    PropertyFactory.lineWidth(widthByZoom),
                    PropertyFactory.lineJoin(Property.LINE_JOIN_ROUND),
                    PropertyFactory.lineCap(Property.LINE_CAP_ROUND),
                ).withFilter(Expression.eq(Expression.get("kind"), Expression.literal("aided"))),
            )
            style.addLayer(
                LineLayer("trail-dr", "route").withProperties(
                    PropertyFactory.lineColor(hex(Palette.MAGENTA)),
                    PropertyFactory.lineWidth(widthByZoom),
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

        // Cinematic fly-in on demo start: begin wide and top-down (the route
        // reads as a line on the Earth) and ease down to a tilted
        // street-level framing. moveCamera (instant) then easeCamera
        // (animated) rather than starting already at the wide position via
        // the style/XML default, so there is only ever one camera-placement
        // code path -- flyIn() -- for both the automatic first run and the
        // manual re-trigger.
        m.moveCamera(
            CameraUpdateFactory.newCameraPosition(
                CameraPosition.Builder().target(lastKnownLatLng).zoom(FLY_IN_WIDE_ZOOM).tilt(FLY_IN_WIDE_TILT).build(),
            ),
        )
        flyIn()
    }

    /**
     * Eases the camera from wherever it currently is to a street-level,
     * tilted framing of [lastKnownLatLng]. Safe to call repeatedly (the
     * re-trigger button does exactly that) -- [followMode] is suspended for
     * the duration so the two never fight over the camera.
     */
    fun flyIn() {
        val m = map ?: return
        flyInInProgress = true
        val target = CameraPosition.Builder()
            .target(lastKnownLatLng)
            .zoom(FLY_IN_STREET_ZOOM)
            .tilt(FLY_IN_STREET_TILT)
            .build()
        m.easeCamera(
            CameraUpdateFactory.newCameraPosition(target),
            FLY_IN_DURATION_MS,
            object : MapLibreMap.CancelableCallback {
                override fun onFinish() { flyInInProgress = false }
                override fun onCancel() { flyInInProgress = false }
            },
        )
    }

    private fun buildFlyInButton() = context.actionButton(
        text = "▲ FLY-IN",
        filled = false,
        colour = Palette.CYAN,
        description = "Replay the cinematic camera fly-in to the current route",
    ).apply {
        // actionButton() lays itself out for a LinearLayout row (weight=1,
        // marginEnd); this is a single button floating over a map instead,
        // so only its colour/ripple/focus/touch-target behaviour is reused --
        // the layout params are replaced outright.
        layoutParams = LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT).apply {
            gravity = Gravity.TOP or Gravity.END
            topMargin = context.dp(10f)
            marginEnd = context.dp(10f)
        }
        setPadding(context.dp(14f), context.dp(8f), context.dp(14f), context.dp(8f))
        minimumHeight = context.dp(MIN_TOUCH_DP)
        setOnClickListener { flyIn() }
    }

    /**
     * Fed from the same 10 Hz call site as [TrackView.push] -- no second
     * data path. `lat`/`lon` come from the same `estimateLatLon()` call
     * [MainActivity] already makes for the trip recorder; `NaN` means no fix
     * yet, matching [TrackView]'s own "waiting for first fix" treatment.
     */
    fun push(snapshot: NavigationEngine.Snapshot, lat: Double, lon: Double) {
        if (lat.isNaN() || lon.isNaN()) return
        pushPoint(lat, lon, snapshot.mode, snapshot.sigmaM)
    }

    /** Everything a synthetic demo tick produced, so [MainActivity] can
     *  mirror it into the KM/H, HEADING and 90% RADIUS readouts -- those
     *  only ever read the real filter snapshot, which stays empty for the
     *  whole synthetic demo (no real fix), so without this the map would
     *  show a moving vehicle while the headline metrics stayed blank. */
    data class SyntheticFix(val speedMs: Double, val headingRad: Double, val sigmaM: Double)

    private var lastSyntheticPoint: LatLng? = null
    private var lastSyntheticMode: GnssMode? = null
    private var drStartElapsedMs = 0L

    /**
     * The SIMULATE TUNNEL button and the chip long-press debug harness
     * (never a live fix, so [push] can't be used -- see [MainActivity]'s
     * `pushMapRoute`) drive this instead. Walks a real road pulled from the
     * bundled tileset's own "roads" layer, back and forth, rather than an
     * arbitrary shape: real-device testing asked for the simulated path to
     * actually depict the product -- a vehicle following a real street,
     * losing GNSS, continuing by dead reckoning, and reacquiring -- not a
     * mathematical curve floating over the map that happens to move.
     */
    fun pushSynthetic(mode: GnssMode, baseSigmaM: Double = 4.0): SyntheticFix {
        val point = demoPathPoint()
        val previous = lastSyntheticPoint
        val heading = if (previous != null) bearingRad(previous, point) else 0.0
        lastSyntheticPoint = point

        val dr = mode == GnssMode.DEAD_RECKONING || mode == GnssMode.REACQUIRING
        val now = SystemClock.elapsedRealtime()
        if (dr) {
            val wasDr = lastSyntheticMode == GnssMode.DEAD_RECKONING || lastSyntheticMode == GnssMode.REACQUIRING
            if (!wasDr) drStartElapsedMs = now
        }
        lastSyntheticMode = mode
        // Growing like sqrt(elapsed time) is the real qualitative shape of a
        // random-walk position error (variance accumulates linearly with
        // time under pure integration, so standard deviation grows with its
        // square root) -- realistic in shape, not just an arbitrary ramp,
        // even though the exact rate is tuned for a demo held for seconds
        // rather than the minutes the real filter models. Aided stays tight.
        val sigmaM = if (dr) {
            val elapsedS = (now - drStartElapsedMs) / 1000.0
            (baseSigmaM + 7.0 * sqrt(elapsedS)).coerceAtMost(85.0)
        } else {
            baseSigmaM
        }

        pushPoint(point.latitude, point.longitude, mode, sigmaM)
        return SyntheticFix(demoSpeedMps, heading, sigmaM)
    }

    /** Standard bearing formula: radians clockwise from north, matching
     *  [NavigationEngine.Snapshot.headingRad]'s convention exactly (see
     *  MainActivity.render()'s `Math.toDegrees(s.headingRad)`), so the
     *  synthetic HEADING readout uses the same units as the real one. */
    private fun bearingRad(from: LatLng, to: LatLng): Double {
        val lat1 = Math.toRadians(from.latitude)
        val lat2 = Math.toRadians(to.latitude)
        val dLon = Math.toRadians(to.longitude - from.longitude)
        val y = sin(dLon) * cos(lat2)
        val x = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dLon)
        return atan2(y, x)
    }

    private fun pushPoint(lat: Double, lon: Double, mode: GnssMode, sigmaM: Double) {
        val point = doubleArrayOf(lat, lon)
        val dr = mode == GnssMode.DEAD_RECKONING || mode == GnssMode.REACQUIRING
        if (dr) trackDr.add(point) else trackAided.add(point)
        if (trackAided.size > 4000) trackAided.subList(0, 1000).clear()
        if (trackDr.size > 4000) trackDr.subList(0, 1000).clear()
        lastKnownLatLng = LatLng(lat, lon)
        rebuildGeoJson(mode, sigmaM, point)

        // This call is on MainActivity's existing 10 Hz UI-thread Handler
        // loop, never the sensor thread (task constraint: map updates must
        // not perturb the measured IMU rate) -- see MainActivity.render()'s
        // call site, which reads NavigationEngine.snapshot() once per tick
        // exactly as it always has; nothing here adds a second engine touch.
        //
        // An instant moveCamera, not an animated easeCamera: real-device
        // testing found the camera looked nearly static while the position
        // was genuinely updating underneath it, because a new 350ms ease
        // fired every 100ms and kept interrupting the previous one before it
        // could get anywhere -- ten un-eased snaps per second already reads
        // as smooth motion to the eye, and can't fight itself this way.
        if (followMode && !flyInInProgress) {
            map?.moveCamera(CameraUpdateFactory.newLatLng(lastKnownLatLng))
        }
    }

    private fun rebuildGeoJson(mode: GnssMode, sigmaM: Double, current: DoubleArray) {
        val features = ArrayList<Feature>()
        if (trackAided.size >= 2) features.add(lineFeature(trackAided, "aided"))
        if (trackDr.size >= 2) features.add(lineFeature(trackDr, "dr"))

        val vehicleColour = when (mode) {
            GnssMode.AIDED -> Palette.CYAN
            GnssMode.DEGRADED, GnssMode.REACQUIRING -> Palette.AMBER
            else -> Palette.MAGENTA
        }
        features.add(pointFeature(current, "vehicle", hex(vehicleColour)))

        if (!sigmaM.isNaN() && sigmaM.isFinite()) {
            val radiusM = sigmaM * conformalLambda * 2.146
            features.add(ringFeature(current[0], current[1], radiusM))
        }
        routeSource?.setGeoJson(FeatureCollection.fromFeatures(features))
    }

    // ------------------------------------------------------- demo road path

    /** Lazily populated from the bundled tileset's own "roads" layer the
     *  first time a synthetic demo needs it (by then the map has definitely
     *  rendered at least one frame, unlike immediately in [onMapReady]).
     *  Empty means "not found yet," not "no roads exist." */
    private var demoRoadPath: List<LatLng> = emptyList()
    private var demoRoadLengthM: Double = 0.0

    /** Roughly a brisk city driving speed -- fast enough that the demo
     *  path is unmistakably animating within a second or two of holding
     *  SIMULATE TUNNEL, not so fast it looks like noise. */
    private val demoSpeedMps = 12.0

    private fun demoPathPoint(): LatLng {
        if (demoRoadPath.size < 2) ensureDemoRoadPath()
        val path = demoRoadPath
        if (path.size < 2) {
            // No road geometry rendered yet (e.g. called before the map has
            // drawn a single frame) -- a small moving point beats nothing
            // while a later call retries the real query.
            val t = SystemClock.elapsedRealtime() / 1000.0
            return LatLng(PLACEHOLDER_LAT + 0.0025 * sin(t * 0.9), PLACEHOLDER_LON + 0.0025 * cos(t * 0.9))
        }
        val t = SystemClock.elapsedRealtime() / 1000.0
        val cycle = 2 * demoRoadLengthM
        val phase = (t * demoSpeedMps).mod(cycle)
        // Ping-pongs along the road (drive to the end, then back) instead of
        // teleporting from the last point to the first -- continuous motion
        // is what makes this read as a car on a street, not a diagram.
        val distanceAlong = if (phase <= demoRoadLengthM) phase else cycle - phase
        return pointAtDistance(path, distanceAlong)
    }

    /** Queries the "roads" layer for whatever is currently on screen and
     *  keeps the single longest LineString found -- a real street, not a
     *  shape this app invented. Safe to call repeatedly; it's a no-op once
     *  a path has been found. */
    private fun ensureDemoRoadPath() {
        val m = map ?: return
        if (mapView.width <= 0 || mapView.height <= 0) return
        val box = RectF(0f, 0f, mapView.width.toFloat(), mapView.height.toFloat())
        val features = runCatching { m.queryRenderedFeatures(box, "roads") }.getOrNull() ?: return
        var longest: List<LatLng> = emptyList()
        for (feature in features) {
            val coords = when (val geometry = feature.geometry()) {
                is LineString -> geometry.coordinates().map { LatLng(it.latitude(), it.longitude()) }
                is MultiLineString -> geometry.lineStrings()
                    .maxByOrNull { it.coordinates().size }
                    ?.coordinates()?.map { LatLng(it.latitude(), it.longitude()) }
                    ?: emptyList()
                else -> emptyList()
            }
            if (coords.size > longest.size) longest = coords
        }
        if (longest.size < 2) return
        demoRoadPath = longest
        demoRoadLengthM = pathLengthM(longest)
        android.util.Log.i(
            "ShadowNavMap",
            "demo road path: ${longest.size} points, ${"%.0f".format(demoRoadLengthM)} m",
        )
    }

    private fun pathLengthM(path: List<LatLng>): Double {
        var total = 0.0
        for (i in 0 until path.size - 1) total += distanceM(path[i], path[i + 1])
        return total
    }

    private fun pointAtDistance(path: List<LatLng>, distanceM: Double): LatLng {
        var remaining = distanceM
        for (i in 0 until path.size - 1) {
            val a = path[i]
            val b = path[i + 1]
            val segLen = distanceM(a, b)
            if (remaining <= segLen) {
                val f = if (segLen > 0) remaining / segLen else 0.0
                return LatLng(
                    a.latitude + (b.latitude - a.latitude) * f,
                    a.longitude + (b.longitude - a.longitude) * f,
                )
            }
            remaining -= segLen
        }
        return path.last()
    }

    /** Same small-scale equirectangular approximation as [GeoCircle] -- fine
     *  for a road-length demo path, never used past a few kilometres. */
    private fun distanceM(a: LatLng, b: LatLng): Double {
        val latRad = Math.toRadians((a.latitude + b.latitude) / 2)
        val dLat = Math.toRadians(b.latitude - a.latitude)
        val dLon = Math.toRadians(b.longitude - a.longitude)
        val x = dLon * cos(latRad)
        val y = dLat
        return sqrt(x * x + y * y) * 6_371_000.0
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

        // Fly-in camera tuning -- named constants per this step's own task
        // list ("duration and easing configurable constants, not magic
        // numbers buried in a call"), not because any of them are exposed
        // as user settings.
        private const val FLY_IN_WIDE_ZOOM = 12.0
        private const val FLY_IN_WIDE_TILT = 0.0
        private const val FLY_IN_STREET_ZOOM = 17.5
        private const val FLY_IN_STREET_TILT = 55.0
        private const val FLY_IN_DURATION_MS = 3500

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
