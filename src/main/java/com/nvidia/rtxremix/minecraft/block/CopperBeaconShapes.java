/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.block;

import net.minecraft.block.Block;
import net.minecraft.util.math.Direction;
import net.minecraft.util.shape.VoxelShape;
import net.minecraft.util.shape.VoxelShapes;

/** Selection and collision envelopes for the six mounting directions. */
final class CopperBeaconShapes {

    private static final VoxelShape HEAD =
            Block.createCuboidShape(3.0, 3.0, 3.0, 13.0, 13.0, 13.0);
    private static final VoxelShape UP = VoxelShapes.union(
            Block.createCuboidShape(6.0, 0.0, 6.0, 10.0, 2.0, 10.0),
            Block.createCuboidShape(7.0, 2.0, 7.0, 9.0, 6.0, 9.0),
            HEAD);
    private static final VoxelShape DOWN = VoxelShapes.union(
            Block.createCuboidShape(6.0, 14.0, 6.0, 10.0, 16.0, 10.0),
            Block.createCuboidShape(7.0, 10.0, 7.0, 9.0, 14.0, 9.0),
            HEAD);
    private static final VoxelShape NORTH = VoxelShapes.union(
            Block.createCuboidShape(6.0, 6.0, 14.0, 10.0, 10.0, 16.0),
            Block.createCuboidShape(7.0, 7.0, 10.0, 9.0, 9.0, 14.0),
            HEAD);
    private static final VoxelShape SOUTH = VoxelShapes.union(
            Block.createCuboidShape(6.0, 6.0, 0.0, 10.0, 10.0, 2.0),
            Block.createCuboidShape(7.0, 7.0, 2.0, 9.0, 9.0, 6.0),
            HEAD);
    private static final VoxelShape EAST = VoxelShapes.union(
            Block.createCuboidShape(0.0, 6.0, 6.0, 2.0, 10.0, 10.0),
            Block.createCuboidShape(2.0, 7.0, 7.0, 6.0, 9.0, 9.0),
            HEAD);
    private static final VoxelShape WEST = VoxelShapes.union(
            Block.createCuboidShape(14.0, 6.0, 6.0, 16.0, 10.0, 10.0),
            Block.createCuboidShape(10.0, 7.0, 7.0, 14.0, 9.0, 9.0),
            HEAD);

    private CopperBeaconShapes() {}

    static VoxelShape forMount(Direction mount) {
        return switch (mount) {
            case UP -> UP;
            case DOWN -> DOWN;
            case NORTH -> NORTH;
            case SOUTH -> SOUTH;
            case EAST -> EAST;
            case WEST -> WEST;
        };
    }
}
