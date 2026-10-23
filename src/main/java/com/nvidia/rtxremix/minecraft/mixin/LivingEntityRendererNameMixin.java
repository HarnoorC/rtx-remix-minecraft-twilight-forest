/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.mixin;

import com.nvidia.rtxremix.minecraft.entity.PlayerNameText;
import net.minecraft.client.render.entity.LivingEntityRenderer;
import net.minecraft.entity.LivingEntity;
import net.minecraft.text.Text;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Redirect;

/** The upside-down name check only reads the string; see {@link PlayerNameText}. */
@Mixin(LivingEntityRenderer.class)
public abstract class LivingEntityRendererNameMixin {
    @Redirect(
            method = "shouldFlipUpsideDown",
            at = @At(value = "INVOKE", target = "Lnet/minecraft/entity/LivingEntity;getName()Lnet/minecraft/text/Text;"))
    private static Text rtxremix$cachedName(LivingEntity entity) {
        return entity instanceof PlayerNameText cached ? cached.rtxremix$nameText() : entity.getName();
    }
}
