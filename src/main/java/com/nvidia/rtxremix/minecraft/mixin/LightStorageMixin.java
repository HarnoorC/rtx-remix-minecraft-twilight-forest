/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.mixin;

import com.nvidia.rtxremix.minecraft.terrain.VanillaSectionBuilds;
import com.nvidia.rtxremix.minecraft.terrain.SkippedSectionRebuilds;
import com.nvidia.rtxremix.minecraft.terrain.ServerLightSnapshot;
import com.nvidia.rtxremix.minecraft.terrain.LightStorageSnapshotAccess;
import com.nvidia.rtxremix.minecraft.terrain.ClientLightSnapshotPolicy;
import com.nvidia.rtxremix.minecraft.terrain.ClientLightSnapshotPolicy.Decision;
import com.nvidia.rtxremix.minecraft.RtxRemixMod;
import it.unimi.dsi.fastutil.longs.Long2ObjectOpenHashMap;
import it.unimi.dsi.fastutil.longs.LongIterator;
import it.unimi.dsi.fastutil.longs.LongSet;
import net.minecraft.client.world.ClientWorld;
import net.minecraft.util.math.ChunkSectionPos;
import net.minecraft.world.LightType;
import net.minecraft.world.chunk.ChunkNibbleArray;
import net.minecraft.world.chunk.ChunkProvider;
import net.minecraft.world.chunk.ChunkToNibbleArrayMap;
import net.minecraft.world.chunk.light.BlockLightStorage;
import net.minecraft.world.chunk.light.LightStorage;
import net.minecraft.world.chunk.light.SkyLightStorage;
import org.spongepowered.asm.mixin.Final;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * Replaces how a light storage publishes its thread-safe snapshot in {@code notifyChanges},
 * the only place vanilla writes {@code uncachedStorage}; it runs once per storage per
 * {@code doLightUpdates}.
 *
 * <p>Client engines publish the live section map itself while RTX capture is on, in place of
 * vanilla's per-pass clone; {@link ClientLightSnapshotPolicy} holds the reasoning and the
 * invariant this depends on. When the live map is published, the pass's pending
 * {@code onLightUpdate} notifications are counted as skipped light-only rebuilds and
 * dropped, which is what {@link ClientChunkManagerMixin} does to each of them while capture
 * is on, so {@code Chunk.LightRebuildsSkipped} keeps its meaning. {@code dirtySections} is
 * cleared as vanilla clears it after a clone: it drives the copy-on-write that protects a
 * separate snapshot, there is none while the live map is published, and the alias ends with
 * an unconditional real copy rather than a dirty check.
 *
 * <p>The integrated server's engines have real readers on other threads, so they keep a
 * separate snapshot, published as {@link ServerLightSnapshot}'s overlay view instead of a
 * whole-map clone. Its notifications run exactly as vanilla's do.
 */
@Mixin(LightStorage.class)
public abstract class LightStorageMixin<M extends ChunkToNibbleArrayMap<M>> implements LightStorageSnapshotAccess {

    @Shadow
    @Final
    protected ChunkProvider chunkProvider;

    @Shadow
    @Final
    protected M storage;

    @Shadow
    protected volatile M uncachedStorage;

    @Shadow
    @Final
    protected LongSet dirtySections;

    @Shadow
    @Final
    protected LongSet notifySections;

    @Shadow
    @Final
    private LightType lightType;

    /** Created on the first pass: classifying the engine needs the chunk provider's world. */
    private ClientLightSnapshotPolicy rtxremix$snapshotPolicy;

    /** Integrated-server engines only; null for client engines and while the kill switch is set. */
    private ServerLightSnapshot rtxremix$serverSnapshot;

    private boolean rtxremix$classified;

    @Inject(method = "notifyChanges", at = @At("HEAD"), cancellable = true)
    private void rtxremix$publishSnapshotForCapture(CallbackInfo ci) {
        rtxremix$classify();
        if (rtxremix$serverSnapshot != null) {
            rtxremix$publishServerOverlay();
            ci.cancel();
            return;
        }
        Decision decision = rtxremix$snapshotPolicy.onNotifyChanges(
                RtxRemixMod.isRtxEnabled(), VanillaSectionBuilds.anyInFlight());
        switch (decision) {
            case ALIAS_LIVE_MAP -> {
                uncachedStorage = storage;
                dirtySections.clear();
                SkippedSectionRebuilds.recordLightOnly(notifySections.size());
                notifySections.clear();
                ci.cancel();
            }
            case REPUBLISH_THEN_VANILLA -> rtxremix$publishRealCopy();
            case VANILLA -> {
            }
        }
    }

    @Override
    public void rtxremix$publishRealSnapshot() {
        if (rtxremix$snapshotPolicy != null && rtxremix$snapshotPolicy.releaseLiveMap()) {
            rtxremix$publishRealCopy();
        }
    }

    /** Vanilla's publication sequence; the copy runs without its lookup cache because workers share it. */
    private void rtxremix$publishRealCopy() {
        M copy = storage.copy();
        copy.disableCache();
        uncachedStorage = copy;
        dirtySections.clear();
    }

    /** Vanilla's sequence with the clone replaced by the overlay view; notifications unchanged. */
    @SuppressWarnings("unchecked")
    private void rtxremix$publishServerOverlay() {
        if (!dirtySections.isEmpty()) {
            M snapshot;
            if (storage instanceof SkyLightStorage.Data sky) {
                ServerLightSnapshot.Published published =
                        rtxremix$serverSnapshot.publish(storage.arrays, sky.columnToTopSection, dirtySections);
                snapshot = (M) new SkyLightStorage.Data(published.sections(), published.columns(), sky.minSectionY);
            } else {
                ServerLightSnapshot.Published published =
                        rtxremix$serverSnapshot.publish(storage.arrays, null, dirtySections);
                snapshot = (M) new BlockLightStorage.Data(published.sections());
            }
            snapshot.disableCache();
            uncachedStorage = snapshot;
            dirtySections.clear();
        }
        if (!notifySections.isEmpty()) {
            for (LongIterator sections = notifySections.iterator(); sections.hasNext(); ) {
                chunkProvider.onLightUpdate(lightType, ChunkSectionPos.from(sections.nextLong()));
            }
            notifySections.clear();
        }
    }

    private void rtxremix$classify() {
        if (rtxremix$classified) {
            return;
        }
        rtxremix$classified = true;
        boolean clientEngine = chunkProvider.getWorld() instanceof ClientWorld;
        rtxremix$snapshotPolicy = new ClientLightSnapshotPolicy(
                clientEngine, ClientLightSnapshotPolicy.ALIAS_ALLOWED);
        if (!clientEngine && ClientLightSnapshotPolicy.ALIAS_ALLOWED) {
            rtxremix$serverSnapshot = new ServerLightSnapshot();
        }
    }
}
