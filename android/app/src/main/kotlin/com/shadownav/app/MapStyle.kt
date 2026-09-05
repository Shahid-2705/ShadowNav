package com.shadownav.app

/**
 * Builds the base-map style JSON referencing the bundled, offline
 * OpenMapTiles-schema MBTiles vector tileset (see `PLAN.md`'s Step 3 note
 * for how `assets/maps/monaco.mbtiles` was generated with Planetiler).
 *
 * Deliberately a hand-built minimal style, not the full OpenMapTiles
 * reference style (which is a much larger JSON covering dozens of layers
 * this app has no use for) -- just enough layers to make the bundled tiles
 * read as a real, legible map, in the app's own dark palette rather than a
 * default light basemap.
 *
 * [mbtilesAbsolutePath] must be a real filesystem path, not an in-APK asset
 * path (which has had reliability problems on Android -- see
 * `MapRouteView`'s file comment for why the asset is copied to internal
 * storage first). Read `MBTilesFileSource::request`/`url_to_path` in
 * maplibre-native's own source (`platform/default/src/mln/storage/
 * mbtiles_file_source.cpp`): it strips only the literal `mbtiles://` prefix
 * and passes the remainder straight to `sqlite3_open` and to its own
 * `is_absolute_path` check, so the URL must be `mbtiles://` + the absolute
 * path directly (three slashes total, since the path itself starts with
 * `/`) -- not `mbtiles://file://...`, which is a plausible-looking but
 * wrong nesting some other guidance suggests; that leaves a literal
 * `file://` inside the path string the source-code review above shows is
 * used as-is, which is unlikely to resolve correctly (confirmed on-device:
 * that form loaded a style with zero rendered features, background paint
 * only).
 */
object MapStyle {

    fun buildJson(mbtilesAbsolutePath: String): String = """
    {
      "version": 8,
      "name": "ShadowNav offline",
      "sources": {
        "basemap": {
          "type": "vector",
          "url": "mbtiles://$mbtilesAbsolutePath"
        }
      },
      "layers": [
        { "id": "background", "type": "background",
          "paint": { "background-color": "#07090C" } },
        { "id": "water", "type": "fill", "source": "basemap", "source-layer": "water",
          "paint": { "fill-color": "#0D1520" } },
        { "id": "landuse", "type": "fill", "source": "basemap", "source-layer": "landuse",
          "paint": { "fill-color": "#0E131A" } },
        { "id": "landcover", "type": "fill", "source": "basemap", "source-layer": "landcover",
          "paint": { "fill-color": "#0C1015" } },
        { "id": "buildings", "type": "fill-extrusion", "source": "basemap", "source-layer": "building",
          "paint": {
            "fill-extrusion-color": "#1B2530",
            "fill-extrusion-height": ["coalesce", ["get", "render_height"], 6.0],
            "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], 0.0],
            "fill-extrusion-opacity": 0.88
          } },
        { "id": "roads", "type": "line", "source": "basemap", "source-layer": "transportation",
          "paint": { "line-color": "#1B2530", "line-width": 1.2 },
          "layout": { "line-cap": "round", "line-join": "round" } }
      ]
    }
    """.trimIndent()
}
