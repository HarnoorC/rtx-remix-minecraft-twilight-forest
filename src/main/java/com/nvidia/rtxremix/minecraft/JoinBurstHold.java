/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Keeps vanilla's terrain-download screen up until the world-join frame burst has settled.
 *
 * <p>The first frames after a join pay Remix's first-sight costs: entity mesh creation,
 * pipeline compiles, first BLAS builds, deferred task flushes. Vanilla closes
 * {@code DownloadingTerrainScreen} as soon as the player's own section has built, which is
 * while that burst is under way, so the player feels the hitches right as they gain control.
 * {@code DownloadingTerrainScreenMixin} begins a hold at vanilla's first close attempt and
 * keeps cancelling the close while {@link #keepScreen(long)} says so.
 *
 * <p>The hold ends after {@link #SETTLE_STREAK} consecutive frames shorter than
 * {@link #SLOW_FRAME_NANOS}, or at {@link #MAX_HOLD_NANOS} so nobody is ever trapped. The
 * frame threshold sits above steady frame times on slow hardware and below the burst's own
 * frames, which measure 130 to 630 ms: a threshold near the steady frame time would send
 * every join on a slow machine to the cap.
 *
 * <p>Frames are sampled where the renderer submits and the screen asks from the client tick,
 * both on the render thread, so the state needs no synchronization. Kill switch:
 * {@code -Drtxremix.joinHold=false}.
 */
public final class JoinBurstHold {
    private static final Logger LOGGER = LoggerFactory.getLogger(JoinBurstHold.class);

    public static final String PROPERTY = "rtxremix.joinHold";
    /** Read once: the switch is a launch decision, not a per-join one. */
    public static final boolean ENABLED = Boolean.parseBoolean(System.getProperty(PROPERTY, "true"));

    /** A frame at least this long belongs to the burst. */
    static final long SLOW_FRAME_NANOS = 100_000_000L;
    /** Consecutive fast frames that end the hold. */
    static final int SETTLE_STREAK = 8;
    /** Longest the screen stays up beyond vanilla's close. */
    static final long MAX_HOLD_NANOS = 6_000_000_000L;

    private final boolean enabled;
    private boolean holding;
    private long holdStartNanos;
    private long lastFrameNanos;
    private int fastStreak;

    public JoinBurstHold(boolean enabled) {
        this.enabled = enabled;
    }

    /** Starts a hold at {@code nowNanos}; the screen calls this on vanilla's first close attempt. */
    public void begin(long nowNanos) {
        if (!enabled) {
            return;
        }
        holding = true;
        holdStartNanos = nowNanos;
        lastFrameNanos = 0L;
        fastStreak = 0;
    }

    /** Records a rendered frame that ended at {@code nowNanos}. */
    public void onFrame(long nowNanos) {
        if (!holding) {
            return;
        }
        if (lastFrameNanos != 0L) {
            fastStreak = nowNanos - lastFrameNanos < SLOW_FRAME_NANOS ? fastStreak + 1 : 0;
            if (fastStreak >= SETTLE_STREAK) {
                holding = false;
                LOGGER.info("World-join burst settled after {} ms ({} consecutive frames under {} ms)",
                        (nowNanos - holdStartNanos) / 1_000_000L, SETTLE_STREAK, SLOW_FRAME_NANOS / 1_000_000L);
            }
        }
        lastFrameNanos = nowNanos;
    }

    /**
     * Decides vanilla's close attempt at {@code nowNanos}.
     *
     * @return true to cancel the close and keep the screen up
     */
    public boolean keepScreen(long nowNanos) {
        if (holding && nowNanos - holdStartNanos >= MAX_HOLD_NANOS) {
            holding = false;
            LOGGER.info("World-join burst did not settle within {} s; releasing the terrain-download screen",
                    MAX_HOLD_NANOS / 1_000_000_000L);
        }
        return holding;
    }
}
