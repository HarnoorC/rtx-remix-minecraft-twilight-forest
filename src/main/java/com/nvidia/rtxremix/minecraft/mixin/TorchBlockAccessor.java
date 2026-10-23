/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.mixin;

import net.minecraft.block.TorchBlock;
import net.minecraft.particle.SimpleParticleType;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

/** Exposes the particle a torch block spawns from its display tick. */
@Mixin(TorchBlock.class)
public interface TorchBlockAccessor {
    @Accessor("particle")
    SimpleParticleType getParticle();
}
