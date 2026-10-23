/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.mixin;

import net.minecraft.client.util.math.MatrixStack;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

/** Preserves MatrixStack.Entry's normal-normalization state while recycling it. */
@Mixin(MatrixStack.Entry.class)
public interface MatrixStackEntryAccessor {

    @Accessor("canSkipNormalization")
    boolean rtxremix$getCanSkipNormalization();

    @Accessor("canSkipNormalization")
    void rtxremix$setCanSkipNormalization(boolean canSkipNormalization);
}
