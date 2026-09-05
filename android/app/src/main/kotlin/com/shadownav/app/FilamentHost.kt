package com.shadownav.app

import com.google.android.filament.Engine
import com.google.android.filament.Filament

/**
 * Owns the single, process-wide Filament [Engine].
 *
 * Filament strongly prefers one shared `Engine` per process rather than one
 * per view. Step 2 (the status orb) is the first consumer; anything later
 * that also needs Filament must go through this object rather than calling
 * `Engine.create()` itself, or teardown ordering becomes impossible to
 * reason about. There was no such shared-ownership point before this file --
 * see `plans/shadownav-3d-mvp-web-deck.md` Step 1 (FIX-21).
 *
 * Not thread-safe by design: create/destroy from the main thread only, same
 * as every other Filament call.
 */
object FilamentHost {

    private var engineRef: Engine? = null
    private var refCount = 0

    /**
     * Call when a view starts using Filament; pairs with [release]. Loads the
     * native library and creates the engine on first use only.
     */
    fun acquire(): Engine {
        if (engineRef == null) {
            Filament.init()
            engineRef = Engine.create()
        }
        refCount++
        return requireNotNull(engineRef)
    }

    /** Call when a view stops using Filament (e.g. `onDetachedFromWindow`).
     *  Destroys the engine only once the last consumer has released it. */
    fun release() {
        if (refCount <= 0) return
        refCount--
        if (refCount == 0) {
            engineRef?.destroy()
            engineRef = null
        }
    }
}
