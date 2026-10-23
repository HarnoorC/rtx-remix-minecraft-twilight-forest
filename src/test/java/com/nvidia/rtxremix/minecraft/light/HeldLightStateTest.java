/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.light;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** Truth table for whether a held item's lit element is burning. */
class HeldLightStateTest {

    private static final boolean LOCAL = true;
    private static final boolean REMOTE = false;
    private static final boolean OFF = true;
    private static final boolean ON = false;
    private static final boolean FLAME = true;
    private static final boolean GLOW = false;
    private static final boolean UNDER = true;
    private static final boolean DRY = false;

    @Test
    void everythingBurnsByDefault() {
        assertTrue(HeldLightState.isLit(LOCAL, ON, FLAME, DRY, false));
        assertTrue(HeldLightState.isLit(LOCAL, ON, GLOW, DRY, false));
        assertTrue(HeldLightState.isLit(REMOTE, ON, FLAME, DRY, false));
    }

    @Test
    void theSwitchPutsOutOnlyTheLocalPlayersHands() {
        assertFalse(HeldLightState.isLit(LOCAL, OFF, FLAME, DRY, false));
        assertFalse(HeldLightState.isLit(LOCAL, OFF, GLOW, DRY, false));
        // No packet carries the switch, so another player's torch stays lit.
        assertTrue(HeldLightState.isLit(REMOTE, OFF, FLAME, DRY, false));
        assertTrue(HeldLightState.isLit(REMOTE, OFF, GLOW, DRY, false));
    }

    @Test
    void waterPutsOutOpenFlamesInAnyHand() {
        assertFalse(HeldLightState.isLit(LOCAL, ON, FLAME, UNDER, false));
        assertFalse(HeldLightState.isLit(REMOTE, ON, FLAME, UNDER, false));
        // A glowing block is not a flame: a sea lantern keeps shining.
        assertTrue(HeldLightState.isLit(LOCAL, ON, GLOW, UNDER, false));
        assertTrue(HeldLightState.isLit(REMOTE, ON, GLOW, UNDER, false));
    }

    @Test
    void allowingFlamesUnderwaterLiftsOnlyTheWaterRule() {
        assertTrue(HeldLightState.isLit(LOCAL, ON, FLAME, UNDER, true));
        assertTrue(HeldLightState.isLit(REMOTE, ON, FLAME, UNDER, true));
        assertFalse(HeldLightState.isLit(LOCAL, OFF, FLAME, UNDER, true));
    }
}
