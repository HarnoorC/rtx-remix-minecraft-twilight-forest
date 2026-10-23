/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.mixin;

import com.llamalad7.mixinextras.injector.wrapoperation.Operation;
import com.llamalad7.mixinextras.injector.wrapoperation.WrapOperation;
import net.minecraft.client.world.ClientWorld;
import net.minecraft.util.math.BlockPos;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;

/**
 * Vanilla's {@code calculateColor} averages the biome colour over the blend radius and
 * allocates a {@code BlockPos.Mutable} to walk it. It runs once per block position per colour
 * type on every section build, on the shared workers, so the position is kept per thread
 * instead. It never escapes the method: the colour resolver receives its coordinates as ints.
 */
@Mixin(ClientWorld.class)
public abstract class ClientWorldColorMixin {

    private static final ThreadLocal<BlockPos.Mutable> rtxremix$blendPos =
            ThreadLocal.withInitial(BlockPos.Mutable::new);

    @WrapOperation(
            method = "calculateColor",
            at = @At(value = "NEW", target = "()Lnet/minecraft/util/math/BlockPos$Mutable;"))
    private BlockPos.Mutable rtxremix$reuseBlendPos(Operation<BlockPos.Mutable> original) {
        return rtxremix$blendPos.get();
    }
}
