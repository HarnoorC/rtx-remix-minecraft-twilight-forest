/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.mixin;

import com.nvidia.rtxremix.minecraft.terrain.capture.RenderRegionStoragePool;
import com.nvidia.rtxremix.minecraft.terrain.capture.RegionSnapshotRelease;
import com.llamalad7.mixinextras.injector.wrapoperation.Operation;
import com.llamalad7.mixinextras.injector.wrapoperation.WrapOperation;
import net.minecraft.client.render.chunk.RenderedChunk;
import net.minecraft.world.chunk.WorldChunk;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;

/**
 * Marks the render thread as taking a region snapshot while a {@code RenderedChunk} is
 * constructed, so its block-state copies draw pooled storage, and takes the builder's
 * reference on the new snapshot; see {@link RenderedChunkMixin} and
 * {@link ChunkRendererRegionBuilderMixin}.
 */
@Mixin(targets = "net.minecraft.client.render.chunk.ChunkRendererRegionBuilder$ClientChunk")
public abstract class ClientChunkMixin {

    @WrapOperation(
            method = "getRenderedChunk",
            at = @At(value = "NEW", target = "(Lnet/minecraft/world/chunk/WorldChunk;)Lnet/minecraft/client/render/chunk/RenderedChunk;")
    )
    private RenderedChunk rtxremix$snapshotWithPooledStorage(WorldChunk chunk, Operation<RenderedChunk> original) {
        RenderRegionStoragePool.beginCopying();
        RenderedChunk snapshot;
        try {
            snapshot = original.call(chunk);
        } finally {
            RenderRegionStoragePool.endCopying();
        }
        ((RegionSnapshotRelease) snapshot).rtxremix$retain();
        return snapshot;
    }
}
