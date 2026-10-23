/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.mixin;

import com.nvidia.rtxremix.minecraft.terrain.BuiltChunkNeighbourhoodAccess;
import com.nvidia.rtxremix.minecraft.terrain.ChunkBuilderBlockEntityAccess;
import com.nvidia.rtxremix.minecraft.terrain.NeighbourReflagFilter;
import com.nvidia.rtxremix.minecraft.terrain.SectionLeftRenderSetQueue;
import com.nvidia.rtxremix.minecraft.terrain.visibility.ChunkSlotMoveLog;
import net.minecraft.client.render.chunk.ChunkBuilder;
import net.minecraft.client.render.chunk.ChunkRendererRegionBuilder;
import net.minecraft.util.math.BlockPos;
import org.spongepowered.asm.mixin.Final;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/**
 * Hooks into vanilla's BuiltChunk lifecycle.
 *
 * <ul>
 *   <li><b>setOrigin:</b> Resets per-slot block-entity and snapshot state when
 *       vanilla reuses a BuiltChunk for a new section, and logs the move so the
 *       frustum index can re-bucket exactly the slots that moved.
 *   <li><b>createRebuildTask:</b> Records which neighbour columns the region
 *       snapshot contained, so a later chunk-load re-flag from a column the
 *       capture already read can be dropped.
 *   <li><b>method_60908:</b> Tracks whether the section contains block
 *       entities and flags empty render data as a removal candidate. The
 *       render thread validates the live world section before removing
 *       Remix terrain because vanilla can publish temporary empty data.
 * </ul>
 */
@Mixin(ChunkBuilder.BuiltChunk.class)
public abstract class BuiltChunkMixin implements ChunkBuilderBlockEntityAccess, BuiltChunkNeighbourhoodAccess {

    @Shadow
    @Final
    public int index;

    @Shadow
    @Final
    BlockPos.Mutable origin;

    @Shadow
    protected abstract double getSquaredCameraDistance();

    @Shadow
    protected abstract boolean isChunkNonEmpty(BlockPos pos);

    @Shadow
    public abstract ChunkBuilder.ChunkData getData();

    /**
     * Shared by every slot: createRebuildTask runs only on the render thread
     * (updateChunks, ChunkBuilder.rebuild, the Remix recapture queue), so one
     * scratch position serves all of them.
     */
    private static final BlockPos.Mutable rtxremix$neighbourProbe = new BlockPos.Mutable();

    private boolean rtxremix$hasBlockEntities;

    /** Bit k set iff neighbour column (DX[k], DZ[k]) was loaded when the last region snapshot was taken. */
    private int rtxremix$snapshotMask;

    @Override
    public boolean rtxremix$hasBlockEntities() {
        return rtxremix$hasBlockEntities;
    }

    @Override
    public int rtxremix$snapshotMask() {
        return rtxremix$snapshotMask;
    }

    @Override
    public void rtxremix$clearSnapshotBit(int bit) {
        rtxremix$snapshotMask &= ~bit;
    }

    @Inject(method = "setOrigin(III)V", at = @At("HEAD"))
    private void rtxremix$onSetOrigin(int x, int y, int z, CallbackInfo ci) {
        rtxremix$hasBlockEntities = false;
        rtxremix$snapshotMask = 0;
    }

    @Inject(method = "setOrigin(III)V", at = @At("RETURN"))
    private void rtxremix$afterSetOrigin(int x, int y, int z, CallbackInfo ci) {
        ChunkSlotMoveLog.RENDER_THREAD.record(index);
    }

    /**
     * The probe sees exactly the columns the snapshot holds: ChunkRendererRegionBuilder.build
     * reads ClientChunkManager.getChunk(x, z, FULL, true), which returns the shared EmptyChunk
     * precisely when this create=false probe returns null, and nothing interleaves on the
     * render thread between the two. A null region (empty own section) is recorded too: it
     * has no geometry that a neighbour could make wrong.
     */
    @Inject(
            method = "createRebuildTask(Lnet/minecraft/client/render/chunk/ChunkRendererRegionBuilder;)"
                    + "Lnet/minecraft/client/render/chunk/ChunkBuilder$BuiltChunk$Task;",
            at = @At("RETURN"))
    private void rtxremix$recordSnapshotNeighbourhood(
            ChunkRendererRegionBuilder regionBuilder, CallbackInfoReturnable<?> cir) {
        // RETURN precedes the synchronous task.run in BuiltChunk.rebuild, so a first build still reads EMPTY here.
        boolean firstBuild = getData() == ChunkBuilder.ChunkData.EMPTY;
        int mask = 0;
        for (int k = 0; k < NeighbourReflagFilter.NEIGHBOUR_COUNT; k++) {
            rtxremix$neighbourProbe.set(
                    origin.getX() + NeighbourReflagFilter.DX[k] * 16,
                    origin.getY(),
                    origin.getZ() + NeighbourReflagFilter.DZ[k] * 16);
            if (isChunkNonEmpty(rtxremix$neighbourProbe)) {
                mask |= NeighbourReflagFilter.bit(k);
            }
        }
        rtxremix$snapshotMask = mask;
        if (NeighbourReflagFilter.isIncompleteFirstBuild(firstBuild, getSquaredCameraDistance(), mask)) {
            NeighbourReflagFilter.recordIncompleteFirstBuild();
        }
    }

    @Inject(method = "method_60908(Lnet/minecraft/client/render/chunk/ChunkBuilder$ChunkData;)V", at = @At("HEAD"))
    private void rtxremix$onChunkDataSet(ChunkBuilder.ChunkData chunkData, CallbackInfo ci) {
        rtxremix$hasBlockEntities = !chunkData.getBlockEntities().isEmpty();

        if (!chunkData.isEmpty()) {
            return;
        }
        int x = origin.getX();
        int y = origin.getY();
        int z = origin.getZ();
        if (x == -1 && y == -1 && z == -1) {
            return;
        }
        SectionLeftRenderSetQueue.enqueueEmptyCandidate(x >> 4, y >> 4, z >> 4);
    }

    @Inject(method = "clear()V", at = @At("HEAD"), require = 0)
    private void rtxremix$onClear(CallbackInfo ci) {
        rtxremix$hasBlockEntities = false;
        rtxremix$snapshotMask = 0;
    }
}
