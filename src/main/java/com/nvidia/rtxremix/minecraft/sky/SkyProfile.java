/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.sky;

import net.minecraft.client.render.DimensionEffects;
import net.minecraft.client.world.ClientWorld;
import net.minecraft.util.Identifier;

/** Shared dimension policy for the sky dome, ambient light, and celestial lighting. */
public enum SkyProfile {
    ATMOSPHERIC(null, null),
    // Vanilla end_sky.png chroma under its vertex tint and fog factor.
    END(new float[]{0.0275f, 0.0210f, 0.0372f}, null),
    // Publish a black dome so escaped rays do not use Remix's undrawn sky matte.
    SKYLESS(new float[]{0.0f, 0.0f, 0.0f}, null),
    // Authored deep blue twilight radiance, independent of time and vanilla's lightmap ambient.
    // The dimension pins its time at dusk, which would park a clock-driven moon on the
    // horizon, so its crescent moon hangs at an authored direction instead.
    TWILIGHT_FOREST(new float[]{0.002f, 0.005f, 0.03f}, moonDirection(50.0f, 120.0f));

    private static final Identifier TWILIGHT_FOREST_EFFECTS =
            Identifier.of("twilightforest", "renderer");

    private final float[] fixedRadiance;
    private final float[] fixedMoonDirection;

    SkyProfile(float[] fixedRadiance, float[] fixedMoonDirection) {
        this.fixedRadiance = fixedRadiance;
        this.fixedMoonDirection = fixedMoonDirection;
    }

    /**
     * A unit direction toward a point in the sky, from its elevation above the horizon and
     * its azimuth clockwise from north (-Z) toward east (+X).
     */
    static float[] moonDirection(float elevationDegrees, float azimuthDegrees) {
        double elevation = Math.toRadians(elevationDegrees);
        double azimuth = Math.toRadians(azimuthDegrees);
        double horizontal = Math.cos(elevation);
        return new float[]{
                (float) (horizontal * Math.sin(azimuth)),
                (float) Math.sin(elevation),
                (float) (-horizontal * Math.cos(azimuth))
        };
    }

    public static SkyProfile forWorld(ClientWorld world) {
        return resolve(world.getDimension().effects(), world.getDimensionEffects().getSkyType());
    }

    /** Custom effects can draw a sky despite reporting NONE to disable vanilla's sky. */
    static SkyProfile resolve(Identifier effects, DimensionEffects.SkyType skyType) {
        if (TWILIGHT_FOREST_EFFECTS.equals(effects)) {
            return TWILIGHT_FOREST;
        }
        return switch (skyType) {
            case NORMAL -> ATMOSPHERIC;
            case END -> END;
            case NONE -> SKYLESS;
        };
    }

    /** Whether the sun and moon follow the world clock, as in the overworld. */
    public boolean hasCelestialLighting() {
        return this == ATMOSPHERIC;
    }

    /**
     * Unit direction toward a moon that stays put regardless of time, or null when the
     * profile has none. Treat as read-only.
     */
    public float[] fixedMoonDirection() {
        return fixedMoonDirection;
    }

    /** Constant dome radiance, or null for the generated atmospheric sky. Treat as read-only. */
    float[] fixedRadiance() {
        return fixedRadiance;
    }

    float ambientMultiplier(float twilightStrength) {
        return this == TWILIGHT_FOREST ? twilightStrength : 1.0f;
    }
}
