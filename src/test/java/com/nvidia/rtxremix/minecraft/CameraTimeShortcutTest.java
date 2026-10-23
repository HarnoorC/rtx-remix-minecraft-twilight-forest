/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft;

import com.nvidia.rtxremix.minecraft.camera.CameraController;
import org.junit.jupiter.api.Test;
import org.lwjgl.glfw.GLFW;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class CameraTimeShortcutTest {

    @Test
    void cameraTimeShortcutRecognizesEqualMinusAndFastModifier() {
        assertEquals(1, RtxRemixMod.cameraTimeAdjustmentDirection(GLFW.GLFW_KEY_EQUAL, 0));
        assertEquals(1, RtxRemixMod.cameraTimeAdjustmentDirection(
                GLFW.GLFW_KEY_EQUAL, GLFW.GLFW_MOD_SHIFT));
        assertEquals(-1, RtxRemixMod.cameraTimeAdjustmentDirection(GLFW.GLFW_KEY_MINUS, 0));
        assertEquals(0, RtxRemixMod.cameraTimeAdjustmentDirection(GLFW.GLFW_KEY_KP_ADD, 0));
        assertEquals(0, RtxRemixMod.cameraTimeAdjustmentDirection(GLFW.GLFW_KEY_KP_SUBTRACT, 0));
        assertEquals(10, RtxRemixMod.cameraTimeAdjustmentStep(0));
        assertEquals(250, RtxRemixMod.cameraTimeAdjustmentStep(GLFW.GLFW_MOD_CONTROL));
    }

    @Test
    void cameraTimeShortcutInactiveWithoutRecording() {
        assertFalse(RtxRemixMod.isCameraTimeShortcutActive(null));
        assertFalse(RtxRemixMod.isCameraTimeShortcutActive(new CameraController()));
    }
}
