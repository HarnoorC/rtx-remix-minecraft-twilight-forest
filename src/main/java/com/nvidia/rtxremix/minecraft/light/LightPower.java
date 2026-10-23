/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.light;

/**
 * Emitted-power proxy for a block light: shape area times pi times the
 * luminance of its radiance, the same quantity the Remix sampler weights a
 * light by before dividing by distance squared.
 */
public final class LightPower {

    private static final float PI = (float) Math.PI;
    /** Vanilla's torch light level, the calibration point for {@link #torchReference()}. */
    private static final int TORCH_LIGHT_LEVEL = 14;

    private LightPower() {}

    /** BT.709 luminance of a linear RGB radiance. */
    public static float luminance(float r, float g, float b) {
        return 0.2126f * r + 0.7152f * g + 0.0722f * b;
    }

    /**
     * @param shape      light shape
     * @param radius     sphere or cylinder radius
     * @param axisLength cylinder length
     * @param xSize      rect width or disk x radius
     * @param ySize      rect height or disk y radius
     * @param radianceR  linear RGB radiance after every multiplier
     * @param radianceG  linear RGB radiance after every multiplier
     * @param radianceB  linear RGB radiance after every multiplier
     * @return the emitted-power proxy
     */
    public static float of(LightShape shape, float radius, float axisLength, float xSize, float ySize,
                           float radianceR, float radianceG, float radianceB) {
        float area = switch (shape) {
            case SPHERE -> 4f * PI * radius * radius;
            case CYLINDER -> 2f * PI * radius * axisLength;
            case RECT -> xSize * ySize;
            case DISK -> PI * xSize * ySize;
        };
        return area * PI * luminance(radianceR, radianceG, radianceB);
    }

    public static float of(LightEntry light, float radianceR, float radianceG, float radianceB) {
        return of(light.shape(), light.radius(), light.axisLength(), light.xSize(), light.ySize(),
                radianceR, radianceG, radianceB);
    }

    /**
     * Power of the shipped torch rule, the unit the light reach setting is
     * expressed in. Computed from the rule's constants rather than by resolving
     * the rule, so it needs no block registry.
     */
    public static float torchReference() {
        float intensity = TORCH_LIGHT_LEVEL
                * BlockLightRuleManager.RADIANCE_PER_LIGHT_LEVEL
                * BlockLightDefaults.THIN_SPHERE_INTENSITY_SCALE
                * BlockLightDefaults.TORCH_AUTHORED_INTENSITY_MULTIPLIER;
        float radius = BlockLightDefaults.TORCH_RADIUS * BlockLightDefaults.THIN_SPHERE_RADIUS_SCALE;
        LightEntry.ColorOverride color = BlockLightDefaults.TORCH_COLOR;
        return of(LightShape.SPHERE, radius, 0f, 0f, 0f,
                color.r() * intensity, color.g() * intensity, color.b() * intensity);
    }
}
