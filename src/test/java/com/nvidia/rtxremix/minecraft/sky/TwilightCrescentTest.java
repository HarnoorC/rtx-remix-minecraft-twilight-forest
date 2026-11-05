/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.sky;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TwilightCrescentTest {
    private static final int SIZE = TwilightCrescent.SIZE;
    private static final byte[] PIXELS = TwilightCrescent.create(SIZE);

    @Test
    void textureIsStableAndSized() {
        assertEquals(SIZE * SIZE * 4, PIXELS.length);
        assertArrayEquals(PIXELS, TwilightCrescent.create(SIZE));
        assertThrows(IllegalArgumentException.class, () -> TwilightCrescent.create(0));
    }

    @Test
    void cornersAreTransparentBlack() {
        for (int[] corner : new int[][]{{0, 0}, {SIZE - 1, 0}, {0, SIZE - 1}, {SIZE - 1, SIZE - 1}}) {
            for (int channel = 0; channel < 4; channel++) {
                assertEquals(0, texel(corner[0], corner[1], channel));
            }
        }
    }

    @Test
    void litLimbIsBrightAndTheBittenCentreIsDark() {
        double angle = Math.toRadians(TwilightCrescent.LIT_LIMB_ANGLE_DEGREES);
        double rim = TwilightCrescent.DISK_RADIUS * 0.9;
        int litX = toPixel(Math.cos(angle) * rim);
        int litY = toPixelRow(Math.sin(angle) * rim);
        assertEquals(255, texel(litX, litY, 3));
        assertTrue(texel(litX, litY, 2) > 160, "the lit limb is bright");

        int centre = SIZE / 2;
        assertEquals(0, texel(centre, centre, 3), "the shadow disk covers the moon's centre");
        assertEquals(0, texel(centre, centre, 2));
    }

    @Test
    void colourIsPremultipliedAndEdgesAreSoft() {
        int partial = 0;
        for (int index = 0; index < PIXELS.length; index += 4) {
            int alpha = PIXELS[index + 3] & 0xFF;
            for (int channel = 0; channel < 3; channel++) {
                assertTrue((PIXELS[index + channel] & 0xFF) <= alpha, "colour is premultiplied");
            }
            if (alpha > 0 && alpha < 255) partial++;
        }
        assertTrue(partial > SIZE, "edges are anti-aliased");
    }

    private static int texel(int x, int y, int channel) {
        return PIXELS[(y * SIZE + x) * 4 + channel] & 0xFF;
    }

    private static int toPixel(double u) {
        return (int) Math.floor((u + 1.0) * 0.5 * SIZE);
    }

    private static int toPixelRow(double v) {
        return (int) Math.floor((1.0 - v) * 0.5 * SIZE);
    }
}
