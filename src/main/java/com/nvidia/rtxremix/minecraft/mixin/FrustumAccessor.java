/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.mixin;

import net.minecraft.client.render.Frustum;
import org.joml.FrustumIntersection;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

@Mixin(Frustum.class)
public interface FrustumAccessor {
    @Accessor("frustumIntersection")
    FrustumIntersection rtxremix$getFrustumIntersection();

    @Accessor("x")
    double rtxremix$getX();

    @Accessor("y")
    double rtxremix$getY();

    @Accessor("z")
    double rtxremix$getZ();
}
