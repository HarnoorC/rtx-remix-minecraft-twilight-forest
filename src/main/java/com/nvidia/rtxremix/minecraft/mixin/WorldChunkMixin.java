/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.mixin;

import com.nvidia.rtxremix.minecraft.terrain.SkyLightSurfaceScanPolicy;
import com.nvidia.rtxremix.minecraft.terrain.SkyLightSurfaceAccess;
import com.nvidia.rtxremix.minecraft.RtxRemixMod;
import com.llamalad7.mixinextras.injector.wrapoperation.Operation;
import com.llamalad7.mixinextras.injector.wrapoperation.WrapOperation;
import net.minecraft.nbt.NbtCompound;
import net.minecraft.nbt.NbtElement;
import net.minecraft.network.PacketByteBuf;
import net.minecraft.network.packet.s2c.play.ChunkData;
import net.minecraft.world.Heightmap;
import net.minecraft.world.chunk.WorldChunk;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;

import java.util.function.Consumer;

/**
 * Seeds the sky-light surface scan of a chunk the client receives from the packet's
 * {@code WORLD_SURFACE} heightmap. {@code loadFromPacket} is the client chunk apply; the
 * server's refresh during chunk generation is untouched.
 */
@Mixin(WorldChunk.class)
public abstract class WorldChunkMixin {

    @WrapOperation(
            method = "loadFromPacket",
            at = @At(value = "INVOKE", target = "Lnet/minecraft/world/chunk/WorldChunk;refreshSurfaceY()V"))
    private void rtxremix$seedSurfaceScan(
            WorldChunk self,
            Operation<Void> original,
            PacketByteBuf buf,
            NbtCompound nbt,
            Consumer<ChunkData.BlockEntityVisitor> consumer) {
        boolean worldSurfaceInPacket = nbt.contains(Heightmap.Type.WORLD_SURFACE.getName(), NbtElement.LONG_ARRAY_TYPE);
        if (!SkyLightSurfaceScanPolicy.seedFromHeightmap(SkyLightSurfaceScanPolicy.SEED_ALLOWED, worldSurfaceInPacket)) {
            if (SkyLightSurfaceScanPolicy.SEED_ALLOWED) {
                SkyLightSurfaceScanPolicy.noteMissingHeightmap();
            }
            original.call(self);
            return;
        }
        ((SkyLightSurfaceAccess) self.getChunkSkyLight())
                .rtxremix$refreshSurfaceY(self, self.getHeightmap(Heightmap.Type.WORLD_SURFACE));
        // Counted only while capture is on, like the paced-chunk counters: the terrain
        // counters that drain it run only while capture and world rendering are on, and
        // seeding itself depends on neither toggle.
        if (RtxRemixMod.isRtxEnabled()) {
            SkyLightSurfaceScanPolicy.recordSeeded();
        }
    }
}
