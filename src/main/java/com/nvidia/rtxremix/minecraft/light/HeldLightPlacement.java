/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.light;

import net.minecraft.client.render.Camera;
import net.minecraft.client.world.ClientWorld;
import net.minecraft.entity.Entity;
import net.minecraft.entity.EquipmentSlot;
import net.minecraft.util.math.Box;
import net.minecraft.util.math.Vec3d;
import net.minecraft.util.shape.VoxelShape;

import java.util.EnumMap;

/**
 * Places local first-person item lights on the camera centerline while keeping
 * their emitter sphere out of nearby block collision geometry.
 */
final class HeldLightPlacement {

    static final double PREFERRED_DISTANCE = 0.72;
    static final double WALL_CLEARANCE = 0.02;
    static final double OUTWARD_SPEED = 3.0;
    static final float MAX_FRAME_DT_SECONDS = 0.1f;

    private static final double PARALLEL_EPSILON = 1.0e-12;

    private final EnumMap<EquipmentSlot, Double> previousDistances =
            new EnumMap<>(EquipmentSlot.class);

    Vec3d resolve(ClientWorld world, Camera camera, Entity source,
                  EquipmentSlot slot, double emitterRadius, float dtSeconds) {
        Vec3d origin = camera.getPos();
        Vec3d forward = horizontalForward(camera.getYaw());
        double expansion = Math.max(0.0, emitterRadius) + WALL_CLEARANCE;
        double targetDistance = collisionLimitedDistance(
                world,
                source,
                origin,
                forward,
                PREFERRED_DISTANCE,
                expansion);
        Double previousDistance = previousDistances.get(slot);
        double distance = previousDistance == null
                ? targetDistance
                : advanceDistance(previousDistance, targetDistance, dtSeconds);
        previousDistances.put(slot, distance);
        return origin.add(forward.multiply(distance));
    }

    void reset(EquipmentSlot slot) {
        previousDistances.remove(slot);
    }

    void clear() {
        previousDistances.clear();
    }

    static Vec3d horizontalForward(float yawDegrees) {
        double yawRadians = Math.toRadians(yawDegrees);
        return new Vec3d(-Math.sin(yawRadians), 0.0, Math.cos(yawRadians));
    }

    static double collisionLimitedDistance(
            ClientWorld world,
            Entity source,
            Vec3d origin,
            Vec3d direction,
            double preferredDistance,
            double expansion) {
        Vec3d preferredPosition = origin.add(direction.multiply(preferredDistance));
        Box queryBox = new Box(
                Math.min(origin.x, preferredPosition.x) - expansion,
                Math.min(origin.y, preferredPosition.y) - expansion,
                Math.min(origin.z, preferredPosition.z) - expansion,
                Math.max(origin.x, preferredPosition.x) + expansion,
                Math.max(origin.y, preferredPosition.y) + expansion,
                Math.max(origin.z, preferredPosition.z) + expansion);
        return collisionLimitedDistance(
                origin,
                direction,
                preferredDistance,
                world.getBlockCollisions(source, queryBox),
                expansion);
    }

    static double collisionLimitedDistance(
            Vec3d origin,
            Vec3d direction,
            double preferredDistance,
            Iterable<VoxelShape> collisions,
            double expansion) {
        double nearest = Math.max(0.0, preferredDistance);
        for (VoxelShape collision : collisions) {
            for (Box box : collision.getBoundingBoxes()) {
                double entry = rayBoxEntryDistance(
                        origin,
                        direction,
                        nearest,
                        box.expand(Math.max(0.0, expansion)));
                if (entry < nearest) {
                    nearest = entry;
                }
            }
        }
        return nearest;
    }

    static double advanceDistance(double previous, double target, float dtSeconds) {
        if (target <= previous) {
            return target;
        }
        float clampedDt = Math.clamp(dtSeconds, 0.0f, MAX_FRAME_DT_SECONDS);
        return Math.min(target, previous + OUTWARD_SPEED * clampedDt);
    }

    static double rayBoxEntryDistance(
            Vec3d origin,
            Vec3d direction,
            double maxDistance,
            Box box) {
        double tMin = 0.0;
        double tMax = Math.max(0.0, maxDistance);

        if (Math.abs(direction.x) < PARALLEL_EPSILON) {
            if (origin.x < box.minX || origin.x > box.maxX) return Double.POSITIVE_INFINITY;
        } else {
            double t1 = (box.minX - origin.x) / direction.x;
            double t2 = (box.maxX - origin.x) / direction.x;
            if (t1 > t2) {
                double swap = t1;
                t1 = t2;
                t2 = swap;
            }
            tMin = Math.max(tMin, t1);
            tMax = Math.min(tMax, t2);
            if (tMin > tMax) return Double.POSITIVE_INFINITY;
        }

        if (Math.abs(direction.y) < PARALLEL_EPSILON) {
            if (origin.y < box.minY || origin.y > box.maxY) return Double.POSITIVE_INFINITY;
        } else {
            double t1 = (box.minY - origin.y) / direction.y;
            double t2 = (box.maxY - origin.y) / direction.y;
            if (t1 > t2) {
                double swap = t1;
                t1 = t2;
                t2 = swap;
            }
            tMin = Math.max(tMin, t1);
            tMax = Math.min(tMax, t2);
            if (tMin > tMax) return Double.POSITIVE_INFINITY;
        }

        if (Math.abs(direction.z) < PARALLEL_EPSILON) {
            if (origin.z < box.minZ || origin.z > box.maxZ) return Double.POSITIVE_INFINITY;
        } else {
            double t1 = (box.minZ - origin.z) / direction.z;
            double t2 = (box.maxZ - origin.z) / direction.z;
            if (t1 > t2) {
                double swap = t1;
                t1 = t2;
                t2 = swap;
            }
            tMin = Math.max(tMin, t1);
            tMax = Math.min(tMax, t2);
            if (tMin > tMax) return Double.POSITIVE_INFINITY;
        }

        return tMin <= maxDistance ? Math.max(0.0, tMin) : Double.POSITIVE_INFINITY;
    }
}
