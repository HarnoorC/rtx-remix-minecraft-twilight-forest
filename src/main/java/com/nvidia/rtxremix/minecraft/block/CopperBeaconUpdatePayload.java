/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.block;

import com.nvidia.rtxremix.minecraft.RtxRemixCommonMod;
import net.fabricmc.fabric.api.networking.v1.PayloadTypeRegistry;
import net.fabricmc.fabric.api.networking.v1.ServerPlayNetworking;
import net.minecraft.network.RegistryByteBuf;
import net.minecraft.network.codec.PacketCodec;
import net.minecraft.network.packet.CustomPayload;
import net.minecraft.util.Identifier;

/** One validated control edit from an open Copper Beacon screen. */
public record CopperBeaconUpdatePayload(int syncId, Field field, float value)
        implements CustomPayload {

    public static final Id<CopperBeaconUpdatePayload> ID = new Id<>(
            Identifier.of(RtxRemixCommonMod.MOD_ID, "copper_beacon_update"));
    public static final PacketCodec<RegistryByteBuf, CopperBeaconUpdatePayload> PACKET_CODEC =
            new PacketCodec<>() {
                @Override
                public CopperBeaconUpdatePayload decode(RegistryByteBuf buffer) {
                    return new CopperBeaconUpdatePayload(
                            buffer.readVarInt(),
                            Field.byId(buffer.readVarInt()),
                            buffer.readFloat());
                }

                @Override
                public void encode(
                        RegistryByteBuf buffer, CopperBeaconUpdatePayload payload) {
                    buffer.writeVarInt(payload.syncId);
                    buffer.writeVarInt(payload.field.ordinal());
                    buffer.writeFloat(payload.value);
                }
            };

    public static void register() {
        PayloadTypeRegistry.playC2S().register(ID, PACKET_CODEC);
        ServerPlayNetworking.registerGlobalReceiver(ID, (payload, context) ->
                context.server().execute(() -> {
                    if (context.player().currentScreenHandler
                                    instanceof CopperBeaconScreenHandler handler
                            && handler.syncId == payload.syncId
                            && handler.canUse(context.player())) {
                        handler.applyUpdate(payload.field, payload.value);
                    }
                }));
    }

    @Override
    public Id<? extends CustomPayload> getId() {
        return ID;
    }

    public enum Field {
        INTENSITY,
        CONE_ANGLE,
        REDSTONE_CONTROLLED,
        YAW_POSITION,
        YAW_MODE,
        YAW_ROTATION_SPEED,
        YAW_MINIMUM_OFFSET,
        YAW_MAXIMUM_OFFSET,
        YAW_CYCLE_SECONDS,
        YAW_PATROL_SECONDS,
        PITCH_POSITION,
        PITCH_MODE,
        PITCH_ROTATION_SPEED,
        PITCH_MINIMUM_OFFSET,
        PITCH_MAXIMUM_OFFSET,
        PITCH_CYCLE_SECONDS,
        PITCH_PATROL_SECONDS,
        SATURATION;

        private static Field byId(int id) {
            Field[] values = values();
            return id >= 0 && id < values.length ? values[id] : INTENSITY;
        }
    }
}
