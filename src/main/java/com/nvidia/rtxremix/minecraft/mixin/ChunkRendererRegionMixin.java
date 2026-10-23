/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.mixin;

import com.nvidia.rtxremix.minecraft.terrain.capture.RegionSnapshotRelease;
import net.minecraft.client.render.chunk.ChunkRendererRegion;
import net.minecraft.client.render.chunk.RenderedChunk;
import net.minecraft.world.World;
import org.spongepowered.asm.mixin.Final;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

import java.util.concurrent.atomic.AtomicBoolean;

/**
 * A render region holds one reference on each of its nine chunk snapshots from construction
 * until {@link #rtxremix$release}, which the rebuild task that consumed it calls exactly once;
 * see {@link RebuildTaskMixin}.
 */
@Mixin(ChunkRendererRegion.class)
public abstract class ChunkRendererRegionMixin implements RegionSnapshotRelease {

    @Shadow
    @Final
    protected RenderedChunk[] chunks;

    private final AtomicBoolean rtxremix$released = new AtomicBoolean();

    @Inject(method = "<init>", at = @At("RETURN"))
    private void rtxremix$retainSnapshots(World world, int chunkX, int chunkZ, RenderedChunk[] renderedChunks, CallbackInfo ci) {
        for (RenderedChunk snapshot : chunks) {
            ((RegionSnapshotRelease) snapshot).rtxremix$retain();
        }
    }

    @Override
    public void rtxremix$retain() {
        throw new UnsupportedOperationException("regions are held by exactly one rebuild task");
    }

    @Override
    public void rtxremix$release() {
        if (!rtxremix$released.compareAndSet(false, true)) {
            return;
        }
        for (RenderedChunk snapshot : chunks) {
            ((RegionSnapshotRelease) snapshot).rtxremix$release();
        }
    }
}
