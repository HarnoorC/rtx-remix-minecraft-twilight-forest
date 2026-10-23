/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.mixin;

import com.nvidia.rtxremix.minecraft.terrain.ChunkHolderTickEntry;
import net.minecraft.server.world.ChunkHolder;
import net.minecraft.server.world.ServerChunkManager;
import net.minecraft.world.chunk.WorldChunk;
import org.spongepowered.asm.mixin.Mixin;

/**
 * Keeps one {@code ChunkWithHolder} per holder for the server's per-tick chunk list. The
 * holder's world chunk is stable while it is loaded, so the entry is remade only when the
 * chunk changes; see {@link ServerChunkManagerMixin}.
 */
@Mixin(ChunkHolder.class)
public abstract class ChunkHolderMixin implements ChunkHolderTickEntry {

    private ServerChunkManager.ChunkWithHolder rtxremix$tickEntry;

    @Override
    public ServerChunkManager.ChunkWithHolder rtxremix$tickEntry(WorldChunk chunk) {
        ServerChunkManager.ChunkWithHolder entry = rtxremix$tickEntry;
        if (entry == null || entry.chunk != chunk) {
            entry = new ServerChunkManager.ChunkWithHolder(chunk, (ChunkHolder) (Object) this);
            rtxremix$tickEntry = entry;
        }
        return entry;
    }
}
