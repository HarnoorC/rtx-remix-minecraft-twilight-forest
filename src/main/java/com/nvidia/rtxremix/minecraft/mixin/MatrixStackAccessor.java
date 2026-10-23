/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.mixin;

import net.minecraft.client.util.math.MatrixStack;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

import java.util.Deque;

/** Exposes the backing deque so the Remix capture stack can recycle entries. */
@Mixin(MatrixStack.class)
public interface MatrixStackAccessor {

    @Accessor("stack")
    Deque<MatrixStack.Entry> rtxremix$getStack();
}
