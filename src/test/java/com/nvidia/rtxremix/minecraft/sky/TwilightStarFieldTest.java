/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.sky;

import org.junit.jupiter.api.Test;
import org.joml.Vector3f;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TwilightStarFieldTest {
    @Test
    void fieldIsStableDenseAndFacesTheCamera() {
        float[] positions = TwilightStarField.create();
        assertArrayEquals(positions, TwilightStarField.create());
        assertEquals(0, positions.length % 12);
        int stars = positions.length / 12;
        assertTrue(stars > 1400 && stars < 1700);
        for (int offset = 0; offset < positions.length; offset += 12) {
            Vector3f a = new Vector3f(positions[offset], positions[offset + 1], positions[offset + 2]);
            Vector3f b = new Vector3f(positions[offset + 3], positions[offset + 4], positions[offset + 5]);
            Vector3f c = new Vector3f(positions[offset + 6], positions[offset + 7], positions[offset + 8]);
            Vector3f d = new Vector3f(positions[offset + 9], positions[offset + 10], positions[offset + 11]);
            Vector3f center = new Vector3f(a).add(b).add(c).add(d).mul(0.25f);
            assertEquals(100.0f, center.length(), 0.001f);
            float size = a.distance(b);
            assertTrue(size >= 0.2999f && size <= 0.5001f);
            assertEquals(size, b.distance(c), 0.0001f);
            Vector3f normal = new Vector3f(b).sub(a).cross(new Vector3f(c).sub(a));
            assertTrue(normal.dot(center) < 0.0f, "Star faces inward");
        }
    }
}
