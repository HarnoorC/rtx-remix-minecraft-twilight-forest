/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.cloud;

import java.util.function.Consumer;

/** Stateless placement of streamed chunks from vanilla's repeating cloud texture. */
final class VanillaCloudPlacement {
    static final int PARTITIONS_PER_AXIS = 8;
    static final double WORLD_PERIOD = 256.0 * VanillaCloudMeshGenerator.CELL_SIZE;
    static final double VIEW_DISTANCE = CloudPlacement.VIEW_DISTANCE;
    static final double DRIFT_PER_TICK = 0.03;
    static final double Z_PHASE = 0.33;

    private VanillaCloudPlacement() {
    }

    /**
     * Calls {@code consumer} once per visible placement with one reused cursor: the
     * traversal runs every frame over hundreds of cells, and a record per cell was a
     * visible share of the render thread's allocation. The cursor is valid only during the
     * callback; {@link Cursor#snapshot()} copies it for anything that outlives the call.
     */
    static void forEachVisible(
            double cameraX,
            double cameraZ,
            double worldTime,
            int textureWidth,
            int textureHeight,
            Consumer<Cursor> consumer) {
        if (textureWidth <= 0 || textureHeight <= 0) {
            throw new IllegalArgumentException("Cloud texture dimensions must be positive");
        }
        double driftX = worldTime * DRIFT_PER_TICK;
        double phaseZ = Z_PHASE * VanillaCloudMeshGenerator.CELL_SIZE;
        int partitionsX = Math.min(PARTITIONS_PER_AXIS, textureWidth);
        int partitionsZ = Math.min(PARTITIONS_PER_AXIS, textureHeight);
        double cellSizeX = WORLD_PERIOD / textureWidth;
        double cellSizeZ = WORLD_PERIOD / textureHeight;
        int minRepeatX = floorRepeat(cameraX + driftX - VIEW_DISTANCE);
        int maxRepeatX = floorRepeat(cameraX + driftX + VIEW_DISTANCE);
        int minRepeatZ = floorRepeat(cameraZ + phaseZ - VIEW_DISTANCE);
        int maxRepeatZ = floorRepeat(cameraZ + phaseZ + VIEW_DISTANCE);
        Cursor cursor = new Cursor();

        for (int repeatZ = minRepeatZ; repeatZ <= maxRepeatZ; repeatZ++) {
            for (int partitionZ = 0; partitionZ < partitionsZ; partitionZ++) {
                int textureZ = partitionBoundary(partitionZ, textureHeight, partitionsZ);
                int nextTextureZ =
                        partitionBoundary(partitionZ + 1, textureHeight, partitionsZ);
                int windowHeight = nextTextureZ - textureZ;
                double worldZ = repeatZ * WORLD_PERIOD + textureZ * cellSizeZ - phaseZ;
                double worldDepth = windowHeight * cellSizeZ;

                for (int repeatX = minRepeatX; repeatX <= maxRepeatX; repeatX++) {
                    for (int partitionX = 0; partitionX < partitionsX; partitionX++) {
                        int textureX =
                                partitionBoundary(partitionX, textureWidth, partitionsX);
                        int nextTextureX =
                                partitionBoundary(partitionX + 1, textureWidth, partitionsX);
                        int windowWidth = nextTextureX - textureX;
                        double worldX =
                                repeatX * WORLD_PERIOD + textureX * cellSizeX - driftX;
                        double worldWidth = windowWidth * cellSizeX;
                        if (!intersectsView(
                                worldX,
                                worldZ,
                                worldWidth,
                                worldDepth,
                                cameraX,
                                cameraZ)) {
                            continue;
                        }
                        cursor.textureKey = key(partitionX, partitionZ);
                        cursor.textureX = textureX;
                        cursor.textureZ = textureZ;
                        cursor.windowWidth = windowWidth;
                        cursor.windowHeight = windowHeight;
                        cursor.cellSizeX = (float) cellSizeX;
                        cursor.cellSizeZ = (float) cellSizeZ;
                        cursor.x = worldX;
                        cursor.z = worldZ;
                        consumer.accept(cursor);
                    }
                }
            }
        }
    }

    private static boolean intersectsView(
            double chunkX,
            double chunkZ,
            double chunkWidth,
            double chunkDepth,
            double cameraX,
            double cameraZ) {
        double nearestX = Math.max(chunkX, Math.min(cameraX, chunkX + chunkWidth));
        double nearestZ = Math.max(chunkZ, Math.min(cameraZ, chunkZ + chunkDepth));
        double dx = nearestX - cameraX;
        double dz = nearestZ - cameraZ;
        return dx * dx + dz * dz <= VIEW_DISTANCE * VIEW_DISTANCE;
    }

    private static int floorRepeat(double coordinate) {
        return (int) Math.floor(coordinate / WORLD_PERIOD);
    }

    private static int partitionBoundary(int partition, int textureSize, int partitionCount) {
        return partition * textureSize / partitionCount;
    }

    private static long key(int x, int z) {
        return ((long) x << 32) ^ (z & 0xffff_ffffL);
    }

    /** A visible placement, as a value. */
    record Placement(
            long textureKey,
            int textureX,
            int textureZ,
            int windowWidth,
            int windowHeight,
            float cellSizeX,
            float cellSizeZ,
            double x,
            double z) {
    }

    /** The traversal's reused view of the current placement. */
    static final class Cursor {
        long textureKey;
        int textureX;
        int textureZ;
        int windowWidth;
        int windowHeight;
        float cellSizeX;
        float cellSizeZ;
        double x;
        double z;

        Placement snapshot() {
            return new Placement(textureKey, textureX, textureZ, windowWidth, windowHeight,
                    cellSizeX, cellSizeZ, x, z);
        }
    }
}
