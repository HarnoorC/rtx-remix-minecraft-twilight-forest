/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.mixin;

import com.nvidia.rtxremix.minecraft.profiling.ProfileScope;
import net.minecraft.util.thread.ThreadExecutor;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * Brackets each {@code ThreadExecutor} task with a profiling scope so the work a
 * client task drain performs is attributed to the task rather than to the frame
 * around it. Runs on whichever thread owns the executor, and does nothing unless
 * a client task drain is already open on that thread.
 */
@Mixin(ThreadExecutor.class)
public abstract class ThreadExecutorMixin {
    @Shadow
    public abstract String getName();

    @Shadow
    public abstract int getTaskCount();

    @Inject(method = "executeTask", at = @At("HEAD"))
    private void rtxremix$beforeExecuteTask(Runnable task, CallbackInfo ci) {
        // This fires for every task on every ThreadExecutor, the integrated
        // server's included. getTaskCount() is ConcurrentLinkedQueue.size(), so
        // it walks the whole backlog: computing it for a hook that is about to
        // return makes draining n tasks O(n^2) for nothing. Ask first.
        if (!ProfileScope.isClientTaskDrainActive()) {
            return;
        }
        ProfileScope.beginThreadExecutorTask(getName(), getTaskCount(), task);
    }

    @Inject(method = "executeTask", at = @At("RETURN"))
    private void rtxremix$afterExecuteTask(Runnable task, CallbackInfo ci) {
        ProfileScope.endThreadExecutorTask();
    }
}
