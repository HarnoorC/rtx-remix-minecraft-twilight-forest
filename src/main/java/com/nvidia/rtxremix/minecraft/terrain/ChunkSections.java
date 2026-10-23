/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.terrain;

import net.minecraft.block.BlockState;
import net.minecraft.world.chunk.Chunk;

/** A chunk's sections as {@link SeededSurfaceScan} reads them. */
public record ChunkSections(Chunk chunk) implements SeededSurfaceScan.Sections<BlockState> {

    @Override
    public boolean isEmpty(int index) {
        return chunk.getSection(index).isEmpty();
    }

    @Override
    public BlockState state(int index, int localX, int localY, int localZ) {
        return chunk.getSection(index).getBlockState(localX, localY, localZ);
    }
}
