/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.terrain;

import com.nvidia.rtxremix.minecraft.terrain.LightStorageSnapshotAccess;
import com.nvidia.rtxremix.minecraft.mixin.ChunkLightProviderAccessor;
import net.minecraft.client.world.ClientWorld;
import net.minecraft.world.LightType;
import net.minecraft.world.chunk.light.LightingProvider;

/** Render-thread control over the client light engine's published snapshots. */
public final class ClientLightSnapshots {
    private ClientLightSnapshots() {
    }

    /**
     * Replaces an aliased snapshot of the block and sky light storages with a real copy.
     * Must run on the render thread before RTX capture switches off, because the section
     * rebuilds that follow read light on worker threads. A storage whose snapshot is already
     * a real copy is left alone.
     */
    public static void publishRealSnapshots(ClientWorld world) {
        LightingProvider provider = world.getLightingProvider();
        for (LightType type : LightType.values()) {
            if (provider.get(type) instanceof ChunkLightProviderAccessor access
                    && access.rtxremix$getLightStorage() instanceof LightStorageSnapshotAccess storage) {
                storage.rtxremix$publishRealSnapshot();
            }
        }
    }
}
