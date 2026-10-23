/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.block;

import net.minecraft.network.RegistryByteBuf;
import net.minecraft.network.codec.PacketCodec;
import net.minecraft.util.math.BlockPos;

/** Additional data needed to bind the client-side handler to its block entity. */
public record CopperBeaconScreenData(BlockPos pos) {
    public static final PacketCodec<RegistryByteBuf, CopperBeaconScreenData> PACKET_CODEC =
            new PacketCodec<>() {
                @Override
                public CopperBeaconScreenData decode(RegistryByteBuf buffer) {
                    return new CopperBeaconScreenData(buffer.readBlockPos());
                }

                @Override
                public void encode(RegistryByteBuf buffer, CopperBeaconScreenData data) {
                    buffer.writeBlockPos(data.pos);
                }
            };
}
