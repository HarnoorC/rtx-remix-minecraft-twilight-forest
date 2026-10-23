/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.mixin;

import com.nvidia.rtxremix.minecraft.entity.PlayerNameText;
import net.minecraft.entity.player.PlayerEntity;
import net.minecraft.text.Text;
import org.spongepowered.asm.mixin.Mixin;

/** Caches the player's name text, rebuilt only when the profile name changes; see {@link PlayerNameText}. */
@Mixin(PlayerEntity.class)
public abstract class PlayerEntityNameMixin implements PlayerNameText {
    private String rtxremix$cachedName;
    private Text rtxremix$cachedText;

    @Override
    public Text rtxremix$nameText() {
        PlayerEntity self = (PlayerEntity) (Object) this;
        String name = self.getGameProfile().getName();
        if (rtxremix$cachedText == null || !name.equals(rtxremix$cachedName)) {
            rtxremix$cachedName = name;
            rtxremix$cachedText = self.getName();
        }
        return rtxremix$cachedText;
    }
}
