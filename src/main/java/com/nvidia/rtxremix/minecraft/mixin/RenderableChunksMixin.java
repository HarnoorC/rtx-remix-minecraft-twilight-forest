/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.mixin;

import com.nvidia.rtxremix.minecraft.terrain.visibility.VisibilityGraphBuffers;
import com.nvidia.rtxremix.minecraft.terrain.visibility.RenderableChunksBuffers;
import com.nvidia.rtxremix.minecraft.terrain.visibility.ChunkInfoPool;
import it.unimi.dsi.fastutil.longs.Long2ObjectOpenHashMap;
import net.minecraft.client.render.ChunkRenderingDataPreparer.ChunkInfo;
import net.minecraft.client.render.ChunkRenderingDataPreparer.ChunkInfoList;
import net.minecraft.client.render.ChunkRenderingDataPreparer.RenderableChunks;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Redirect;

import java.util.LinkedHashSet;

/**
 * Builds vanilla's visibility state on the buffers {@link VisibilityGraphBuffers} keeps
 * across walks instead of three fresh collections sized to the whole storage. Vanilla's
 * fields and readers are unchanged; they see a {@code LinkedHashSet}, a {@code ChunkInfoList}
 * and a map, as before.
 */
@Mixin(RenderableChunks.class)
public abstract class RenderableChunksMixin implements RenderableChunksBuffers {

    private ChunkInfoPool rtxremix$infoPool;

    @Redirect(
            method = "<init>",
            at = @At(value = "NEW", target = "(I)Lnet/minecraft/client/render/ChunkRenderingDataPreparer$ChunkInfoList;"))
    private ChunkInfoList rtxremix$reusedInfoList(int chunkCount) {
        VisibilityGraphBuffers.Buffers buffers = VisibilityGraphBuffers.current();
        rtxremix$infoPool = buffers.infoPool;
        return buffers.infos;
    }

    @Redirect(
            method = "<init>",
            at = @At(value = "NEW", target = "(I)Ljava/util/LinkedHashSet;"))
    private LinkedHashSet<ChunkInfo> rtxremix$reusedChunkSet(int chunkCount) {
        return VisibilityGraphBuffers.current().chunks;
    }

    @Redirect(
            method = "<init>",
            at = @At(value = "NEW", target = "()Lit/unimi/dsi/fastutil/longs/Long2ObjectOpenHashMap;"))
    private Long2ObjectOpenHashMap<?> rtxremix$reusedUnbuiltNeighbours() {
        return VisibilityGraphBuffers.current().unbuiltNeighbours;
    }

    @Override
    public ChunkInfoPool rtxremix$infoPool() {
        return rtxremix$infoPool;
    }
}
