/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.sky;

import java.util.Arrays;
import java.util.Random;

/** A deterministic, dense field of inward-facing star quads on a radius-100 sky. */
final class TwilightStarField {
    private TwilightStarField() {}

    static float[] create() {
        // Rejection sampling gives the field the same density as 3000 cube samples.
        Random random = new Random(10842L);
        float[] positions = new float[3000 * 12];
        int offset = 0;
        for (int sample = 0; sample < 3000; sample++) {
            double x = random.nextDouble() * 2.0 - 1.0;
            double y = random.nextDouble() * 2.0 - 1.0;
            double z = random.nextDouble() * 2.0 - 1.0;
            double lengthSquared = x * x + y * y + z * z;
            if (lengthSquared <= 0.01 || lengthSquared >= 1.0) continue;
            double inverseLength = 1.0 / Math.sqrt(lengthSquared);
            x *= inverseLength;
            y *= inverseLength;
            z *= inverseLength;

            // Use a tangent basis with a stable reference axis near either pole.
            double rx = Math.abs(y) < 0.9 ? z : 0.0;
            double ry = Math.abs(y) < 0.9 ? 0.0 : -z;
            double rz = Math.abs(y) < 0.9 ? -x : y;
            double inverseRightLength = 1.0 / Math.sqrt(rx * rx + ry * ry + rz * rz);
            rx *= inverseRightLength;
            ry *= inverseRightLength;
            rz *= inverseRightLength;
            double ux = y * rz - z * ry;
            double uy = z * rx - x * rz;
            double uz = x * ry - y * rx;
            double angle = random.nextDouble() * Math.PI * 2.0;
            double halfSize = 0.15 + random.nextDouble() * 0.1;
            double cos = Math.cos(angle) * halfSize;
            double sin = Math.sin(angle) * halfSize;
            double ax = rx * cos + ux * sin;
            double ay = ry * cos + uy * sin;
            double az = rz * cos + uz * sin;
            double bx = ux * cos - rx * sin;
            double by = uy * cos - ry * sin;
            double bz = uz * cos - rz * sin;
            for (int corner = 0; corner < 4; corner++) {
                int a = corner < 2 ? -1 : 1;
                int b = corner == 0 || corner == 3 ? -1 : 1;
                positions[offset++] = (float) (x * 100.0 + a * ax + b * bx);
                positions[offset++] = (float) (y * 100.0 + a * ay + b * by);
                positions[offset++] = (float) (z * 100.0 + a * az + b * bz);
            }
        }
        return Arrays.copyOf(positions, offset);
    }
}
