/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.texture;

import org.junit.jupiter.api.Test;

import java.util.HashSet;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class RedstoneEmissionTest {
    @Test
    void everyLayerAndPowerHasAStableDistinctBucketWithTheOriginalMaterialProperties() {
        Set<String> keys = new HashSet<>();
        for (String base : new String[] {"solid", "cutout", "cutout_mipped", "translucent", "glass",
                "solid_sss", "cutout_sss", "cutout_mipped_sss"}) {
            for (int power = 0; power <= 15; power++) {
                String key = RedstoneEmission.bucketKey(base, power);
                assertSame(key, RedstoneEmission.bucketKey(base, power));
                assertTrue(keys.add(key), "Every power/layer pair must be distinct");
                if (power == 15) {
                    assertEquals(base, key);
                    assertNull(RedstoneEmission.resolve(key));
                } else {
                    assertEquals(new RedstoneEmission.Bucket(base, power), RedstoneEmission.resolve(key));
                }
            }
            assertEquals(base, RedstoneEmission.bucketKey(base, -1));
        }
    }

    @Test
    void emissionRangesFromSoftLowPowerToTheExistingMaximum() {
        assertEquals(0f, RedstoneEmission.multiplier(0));
        assertEquals(1f / 15, RedstoneEmission.multiplier(1));
        assertEquals(1f, RedstoneEmission.multiplier(15));
        for (int power = 1; power <= 15; power++) {
            assertTrue(RedstoneEmission.multiplier(power) > RedstoneEmission.multiplier(power - 1));
        }
    }
}
