/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.mixin;

import net.minecraft.client.particle.Particle;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

@Mixin(Particle.class)
public interface ParticleAccessor {
    @Accessor("x") double getX();
    @Accessor("y") double getY();
    @Accessor("z") double getZ();
    @Accessor("prevPosX") double getPrevPosX();
    @Accessor("prevPosY") double getPrevPosY();
    @Accessor("prevPosZ") double getPrevPosZ();
    @Accessor("red") float getRed();
    @Accessor("green") float getGreen();
    @Accessor("blue") float getBlue();
    @Accessor("alpha") float getAlpha();
    @Accessor("angle") float getAngle();
    @Accessor("prevAngle") float getPrevAngle();
    @Accessor("dead") boolean getDead();
}
