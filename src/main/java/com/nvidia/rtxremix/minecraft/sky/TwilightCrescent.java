/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.sky;

/**
 * A deterministic, anti-aliased crescent moon texture for Twilight Forest's sky.
 *
 * <p>The crescent is a lit disk minus an equal shadow disk shifted away from the lit
 * limb. Colour is premultiplied by coverage over a black background, because celestial
 * meshes blend additively.
 */
final class TwilightCrescent {
    static final int SIZE = 128;
    /** Disk radius as a fraction of the texture's half-size, leaving room for the edge ramp. */
    static final float DISK_RADIUS = 0.92f;
    /** Shadow disk offset as a fraction of the disk radius; smaller is a thinner crescent. */
    static final float SHADOW_OFFSET = 0.5f;
    /** Direction of the lit limb in texture space, counter-clockwise from +U, with V up. */
    static final float LIT_LIMB_ANGLE_DEGREES = -35.0f;
    private static final float TINT_R = 0.92f;
    private static final float TINT_G = 0.95f;
    private static final float TINT_B = 1.0f;
    /** Brightness at the disk's rim relative to its centre. */
    private static final float LIMB_DARKENING = 0.75f;

    private TwilightCrescent() {}

    /** Returns {@code size * size} RGBA8 texels, top row first. */
    static byte[] create(int size) {
        if (size <= 0) {
            throw new IllegalArgumentException("Crescent size must be positive: " + size);
        }
        double angle = Math.toRadians(LIT_LIMB_ANGLE_DEGREES);
        double shadowX = -Math.cos(angle) * SHADOW_OFFSET * DISK_RADIUS;
        double shadowY = -Math.sin(angle) * SHADOW_OFFSET * DISK_RADIUS;
        double texel = 2.0 / size;

        byte[] pixels = new byte[size * size * 4];
        for (int y = 0; y < size; y++) {
            double v = 1.0 - (y + 0.5) * texel;
            for (int x = 0; x < size; x++) {
                double u = (x + 0.5) * texel - 1.0;
                double distance = Math.sqrt(u * u + v * v);
                double shadowDistance = Math.hypot(u - shadowX, v - shadowY);
                double coverage = edgeCoverage(distance, texel)
                        * (1.0 - edgeCoverage(shadowDistance, texel));
                double rho = Math.min(1.0, distance / DISK_RADIUS);
                double shade = LIMB_DARKENING
                        + (1.0 - LIMB_DARKENING) * Math.sqrt(1.0 - rho * rho);
                int index = (y * size + x) * 4;
                pixels[index] = toByte(TINT_R * shade * coverage);
                pixels[index + 1] = toByte(TINT_G * shade * coverage);
                pixels[index + 2] = toByte(TINT_B * shade * coverage);
                pixels[index + 3] = toByte(coverage);
            }
        }
        return pixels;
    }

    /** Fraction of a texel inside a disk of {@link #DISK_RADIUS}, ramped over one texel. */
    private static double edgeCoverage(double distanceFromCentre, double texel) {
        return Math.clamp(0.5 - (distanceFromCentre - DISK_RADIUS) / texel, 0.0, 1.0);
    }

    private static byte toByte(double value) {
        return (byte) Math.round(Math.clamp(value, 0.0, 1.0) * 255.0);
    }
}
