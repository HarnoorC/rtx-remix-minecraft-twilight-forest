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
    ATMOSPHERIC(null),
    // Vanilla end_sky.png chroma under its vertex tint and fog factor.
    END(new float[]{0.0275f, 0.0210f, 0.0372f}),
    // Publish a black dome so escaped rays do not use Remix's undrawn sky matte.
    SKYLESS(new float[]{0.0f, 0.0f, 0.0f}),
    // Authored blue twilight radiance, independent of time and vanilla's lightmap ambient.
    TWILIGHT_FOREST(new float[]{0.04f, 0.055f, 0.09f});

    private static final Identifier TWILIGHT_FOREST_EFFECTS =
            Identifier.of("twilightforest", "renderer");

    private final float[] fixedRadiance;

    SkyProfile(float[] fixedRadiance) {
        this.fixedRadiance = fixedRadiance;
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

    public boolean hasCelestialLighting() {
        return this == ATMOSPHERIC;
    }

    /** Constant dome radiance, or null for the generated atmospheric sky. Treat as read-only. */
    float[] fixedRadiance() {
        return fixedRadiance;
    }

    float ambientMultiplier(float twilightStrength) {
        return this == TWILIGHT_FOREST ? twilightStrength : 1.0f;
    }
}
