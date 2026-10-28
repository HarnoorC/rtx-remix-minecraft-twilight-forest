/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.texture;

import java.util.HashMap;
import java.util.Map;

/** Power-specific atlas buckets shared by terrain capture and material resolution. */
public final class RedstoneEmission {
    public static final int MAX_POWER = 15;
    private static final Map<String, String[]> KEYS = buildKeys();
    private static final Map<String, Bucket> BUCKETS = buildBuckets();

    private RedstoneEmission() {}

    public record Bucket(String baseKey, int power) {}

    /** Returns a cached key; negative power denotes an unrelated surface. */
    public static String bucketKey(String baseKey, int power) {
        if (power < 0 || power == MAX_POWER) return baseKey;
        return KEYS.get(baseKey)[power];
    }

    /** Returns the material variant described by a key, or null for an ordinary bucket. */
    public static Bucket resolve(String key) {
        return BUCKETS.get(key);
    }

    /** Scales emission in addition to vanilla's vertex tint, leaving full power unchanged. */
    public static float multiplier(int power) {
        return power / (float) MAX_POWER;
    }

    private static Map<String, String[]> buildKeys() {
        Map<String, String[]> keys = new HashMap<>();
        for (String base : new String[] {"solid", "cutout", "cutout_mipped", "translucent", "glass",
                "solid_sss", "cutout_sss", "cutout_mipped_sss"}) {
            String[] levels = new String[MAX_POWER];
            for (int power = 0; power < MAX_POWER; power++) {
                levels[power] = base + "_redstone_" + power;
            }
            keys.put(base, levels);
        }
        return Map.copyOf(keys);
    }

    private static Map<String, Bucket> buildBuckets() {
        Map<String, Bucket> buckets = new HashMap<>();
        KEYS.forEach((base, levels) -> {
            for (int power = 0; power < levels.length; power++) {
                buckets.put(levels[power], new Bucket(base, power));
            }
        });
        return Map.copyOf(buckets);
    }
}
