/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.texture;

import org.junit.jupiter.api.Test;

import java.util.Arrays;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DustSssAtlasTest {
    @Test
    void sharedSssAtlasDisablesScatteringOnlyForUnauthoredDustRegions() {
        for (String name : new String[] {"redstone_dust_dot", "redstone_dust_line0", "redstone_dust_line1",
                "redstone_dust_overlay", "stone"}) {
            for (boolean sss : new boolean[] {false, true}) {
                var sprite = TerrainSpriteFixtures.sprite(name, 16, true, sss);
                byte[] atlas = new byte[64 * 64 * 4];
                Arrays.fill(atlas, (byte) 191);
                BlockTextureManager.clearUnauthoredDustSss(atlas, 64, sprite);
                for (int y = 0; y < 64; y++) {
                    for (int x = 0; x < 64; x++) {
                        boolean cleared = !sss && !name.equals("stone") && x >= 16 && x < 32 && y >= 16 && y < 32;
                        for (int channel = 0; channel < 4; channel++) {
                            assertEquals(cleared && channel < 3 ? 0 : 191, atlas[(y * 64 + x) * 4 + channel] & 255,
                                    name + ", sss=" + sss + ", x=" + x + ", y=" + y);
                        }
                    }
                }
            }
        }
    }
}
