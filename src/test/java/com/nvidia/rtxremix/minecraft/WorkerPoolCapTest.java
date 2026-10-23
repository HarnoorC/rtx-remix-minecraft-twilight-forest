/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class WorkerPoolCapTest {

    @Test
    void capsLargeMachinesAtEight() {
        assertEquals(8, WorkerPoolCap.choose(32));
        assertEquals(8, WorkerPoolCap.choose(16));
        assertEquals(8, WorkerPoolCap.choose(9));
    }

    @Test
    void mirrorsVanillaBelowTheCap() {
        assertEquals(7, WorkerPoolCap.choose(8));
        assertEquals(3, WorkerPoolCap.choose(4));
        assertEquals(1, WorkerPoolCap.choose(2));
        assertEquals(1, WorkerPoolCap.choose(1));
    }
}
