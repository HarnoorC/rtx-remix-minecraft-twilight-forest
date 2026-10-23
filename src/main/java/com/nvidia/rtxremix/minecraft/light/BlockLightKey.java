/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.light;

import net.minecraft.util.Identifier;
import net.minecraft.util.math.BlockPos;

/**
 * Stable identity for one block-attached Remix light.
 */
public record BlockLightKey(BlockPos pos, Identifier ruleId, int lightIndex) {}
