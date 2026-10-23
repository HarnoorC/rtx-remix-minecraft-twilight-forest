/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft;

import com.nvidia.rtxremix.minecraft.sky.SkyRenderer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Field;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Truth-table coverage for the master/sub-flag "active" predicates.
 * The master flag (rtxEnabled) gates every sub-flag: a subsystem is only
 * "active" when RTX is on AND its own sub-flag is on.
 */
class RtxToggleStateTest {

    @AfterEach
    void resetFlags() throws Exception {
        setFlag("rtxEnabled", true);
        setFlag("worldEnabled", true);
        setFlag("entitiesEnabled", true);
        setFlag("skyEnabled", true);
        setFlag("blockEntitiesEnabled", true);
        setFlag("particlesEnabled", true);
    }

    @Test
    void everyActivePredicateIsFalseWhenTheMasterToggleIsOff() throws Exception {
        setFlag("rtxEnabled", false);
        // All sub-flags remain true (defaults), but master off => nothing active.
        assertFalse(RtxRemixMod.isWorldActive(), "world");
        assertFalse(RtxRemixMod.isEntitiesActive(), "entities");
        assertFalse(RtxRemixMod.isBlockEntitiesActive(), "blockEntities");
        assertFalse(RtxRemixMod.isSkyActive(), "sky");
        assertFalse(RtxRemixMod.isParticlesActive(), "particles");
    }

    @Test
    void anActivePredicateIsTrueWhenTheMasterAndItsSubFlagAreOn() throws Exception {
        setFlag("rtxEnabled", true);
        assertTrue(RtxRemixMod.isWorldActive(), "world");
        assertTrue(RtxRemixMod.isEntitiesActive(), "entities");
        assertTrue(RtxRemixMod.isBlockEntitiesActive(), "blockEntities");
        assertTrue(RtxRemixMod.isSkyActive(), "sky");
        assertTrue(RtxRemixMod.isParticlesActive(), "particles");
    }

    @Test
    void eachActivePredicateIsolatesItsOwnSubFlagWhenTheMasterIsOn() throws Exception {
        setFlag("rtxEnabled", true);
        setFlag("entitiesEnabled", false);
        assertTrue(RtxRemixMod.isRtxEnabled());
        assertFalse(RtxRemixMod.isEntitiesActive(), "entities off");
        // A different sub-flag is unaffected.
        assertTrue(RtxRemixMod.isWorldActive(), "world still active");
    }

    @Test
    void settingSkyEnabledKeepsBothGatesInSync() {
        RtxRemixMod.setSkyEnabled(false);
        assertFalse(RtxRemixMod.isSkyEnabled());
        assertFalse(SkyRenderer.isEnabled());

        RtxRemixMod.setSkyEnabled(true);
        assertTrue(RtxRemixMod.isSkyEnabled());
        assertTrue(SkyRenderer.isEnabled());
    }

    private static void setFlag(String name, boolean value) throws Exception {
        Field f = RtxRemixMod.class.getDeclaredField(name);
        f.setAccessible(true);
        f.setBoolean(null, value);
    }
}
