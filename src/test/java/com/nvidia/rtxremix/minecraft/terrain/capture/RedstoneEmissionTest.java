/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.terrain.capture;

import net.minecraft.util.Identifier;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class RedstoneEmissionTest {
    @Test
    void onlyWireDustSurfacesReceivePowerDependentEmission() {
        for (int power = 0; power <= 15; power++) {
            for (String texture : new String[] {"redstone_dust_dot", "redstone_dust_line0",
                    "redstone_dust_line1", "redstone_dust_overlay"}) {
                Identifier dust = Identifier.ofVanilla("block/" + texture);
                assertEquals(power, BlockQuadEmitter.dustEmissionPower(power, dust));
                assertEquals(-1, BlockQuadEmitter.dustEmissionPower(-1, dust));
            }
            assertEquals(-1, BlockQuadEmitter.dustEmissionPower(power, Identifier.ofVanilla("block/stone")));
            assertEquals(-1, BlockQuadEmitter.dustEmissionPower(power, null));
        }
    }
}
