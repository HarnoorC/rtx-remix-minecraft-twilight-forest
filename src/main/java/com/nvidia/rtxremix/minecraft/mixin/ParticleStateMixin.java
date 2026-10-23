/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.mixin;

import com.nvidia.rtxremix.minecraft.profiling.ParticleTickProfiler;
import com.nvidia.rtxremix.minecraft.particle.RemixParticleStateAccess;
import com.nvidia.rtxremix.minecraft.RtxRemixMod;
import net.minecraft.block.BlockState;
import net.minecraft.entity.Entity;
import net.minecraft.client.particle.Particle;
import net.minecraft.util.math.BlockPos;
import net.minecraft.util.math.Box;
import net.minecraft.util.math.MathHelper;
import net.minecraft.util.math.Vec3d;
import net.minecraft.util.shape.VoxelShape;
import net.minecraft.world.World;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Redirect;

import java.util.List;

@Mixin(Particle.class)
public abstract class ParticleStateMixin implements RemixParticleStateAccess {
    private static final boolean rtxremix$FAST_AIR_COLLISION =
            Boolean.parseBoolean(System.getProperty("rtxremix.particles.fastAirCollision", "true"));
    private static final int rtxremix$FAST_AIR_COLLISION_MAX_BLOCKS = Math.max(1,
            Integer.getInteger("rtxremix.particles.fastAirCollisionMaxBlocks", 8));
    private static final double rtxremix$COLLISION_EPSILON = 1.0E-7D;
    private static final ThreadLocal<BlockPos.Mutable> rtxremix$COLLISION_POS =
            ThreadLocal.withInitial(BlockPos.Mutable::new);

    private Object rtxremix$particleBucket;
    private int rtxremix$particleSlot = -1;

    @Redirect(
        method = "move(DDD)V",
        at = @At(
            value = "INVOKE",
            target = "Lnet/minecraft/entity/Entity;adjustMovementForCollisions(Lnet/minecraft/entity/Entity;Lnet/minecraft/util/math/Vec3d;Lnet/minecraft/util/math/Box;Lnet/minecraft/world/World;Ljava/util/List;)Lnet/minecraft/util/math/Vec3d;"
        )
    )
    private Vec3d rtxremix$adjustMovementForParticleCollision(
            Entity entity,
            Vec3d movement,
            Box box,
            World world,
            List<VoxelShape> collisions) {
        if (rtxremix$canFastPathAirCollision(world, box, movement, collisions)) {
            ParticleTickProfiler.recordSkippedCollisionCheck();
            return movement;
        }

        ParticleTickProfiler.beginCollisionCheck();
        try {
            return Entity.adjustMovementForCollisions(entity, movement, box, world, collisions);
        } finally {
            ParticleTickProfiler.endCollisionCheck();
        }
    }

    @Override
    public Object rtxremix$getParticleBucket() {
        return rtxremix$particleBucket;
    }

    @Override
    public void rtxremix$setParticleBucket(Object bucket) {
        rtxremix$particleBucket = bucket;
    }

    @Override
    public int rtxremix$getParticleSlot() {
        return rtxremix$particleSlot;
    }

    @Override
    public void rtxremix$setParticleSlot(int slot) {
        rtxremix$particleSlot = slot;
    }

    private static boolean rtxremix$canFastPathAirCollision(
            World world,
            Box box,
            Vec3d movement,
            List<VoxelShape> collisions) {
        if (!rtxremix$FAST_AIR_COLLISION
                || !rtxremix$isRtxParticleOptimizationActive()
                || !collisions.isEmpty()) {
            return false;
        }

        double minX = movement.x < 0.0D ? box.minX + movement.x : box.minX;
        double maxX = movement.x > 0.0D ? box.maxX + movement.x : box.maxX;
        double minY = movement.y < 0.0D ? box.minY + movement.y : box.minY;
        double maxY = movement.y > 0.0D ? box.maxY + movement.y : box.maxY;
        double minZ = movement.z < 0.0D ? box.minZ + movement.z : box.minZ;
        double maxZ = movement.z > 0.0D ? box.maxZ + movement.z : box.maxZ;

        int blockMinX = MathHelper.floor(minX - rtxremix$COLLISION_EPSILON);
        int blockMaxX = MathHelper.floor(maxX + rtxremix$COLLISION_EPSILON);
        int blockMinY = MathHelper.floor(minY - rtxremix$COLLISION_EPSILON);
        int blockMaxY = MathHelper.floor(maxY + rtxremix$COLLISION_EPSILON);
        int blockMinZ = MathHelper.floor(minZ - rtxremix$COLLISION_EPSILON);
        int blockMaxZ = MathHelper.floor(maxZ + rtxremix$COLLISION_EPSILON);

        int checked = 0;
        BlockPos.Mutable pos = rtxremix$COLLISION_POS.get();
        for (int x = blockMinX; x <= blockMaxX; x++) {
            for (int y = blockMinY; y <= blockMaxY; y++) {
                for (int z = blockMinZ; z <= blockMaxZ; z++) {
                    if (++checked > rtxremix$FAST_AIR_COLLISION_MAX_BLOCKS) {
                        return false;
                    }
                    pos.set(x, y, z);
                    BlockState state = world.getBlockState(pos);
                    if (!state.getCollisionShape(world, pos).isEmpty()) {
                        return false;
                    }
                }
            }
        }

        return checked > 0;
    }

    private static boolean rtxremix$isRtxParticleOptimizationActive() {
        if (!RtxRemixMod.isRtxEnabled()
                || !RtxRemixMod.isWorldEnabled()
                || !RtxRemixMod.isParticlesEnabled()) {
            return false;
        }
        RtxRemixMod mod = RtxRemixMod.getInstance();
        return mod != null
                && mod.getRenderer() != null
                && mod.getRenderer().isInitialized();
    }
}
