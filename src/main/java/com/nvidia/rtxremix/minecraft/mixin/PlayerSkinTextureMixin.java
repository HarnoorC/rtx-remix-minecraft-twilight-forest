/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.mixin;

import com.nvidia.rtxremix.minecraft.texture.DynamicTextureCache;
import net.minecraft.client.texture.AbstractTexture;
import net.minecraft.client.texture.NativeImage;
import net.minecraft.client.texture.PlayerSkinTexture;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * Intercepts {@link PlayerSkinTexture} upload to capture pixel data for RTX Remix.
 *
 * <p>{@code PlayerSkinTexture} extends {@code ResourceTexture} rather than
 * {@code NativeImageBackedTexture}, so {@code NativeImageBackedTextureMixin} never
 * fires for player skins. This mixin covers them at the private
 * {@code uploadTexture(NativeImage)} method, where the fully processed skin image is
 * available on the render thread just before it is uploaded to GL and freed.
 *
 * <p>The texture-to-identifier mapping is established by {@code TextureManagerMixin},
 * which registers the {@code PlayerSkinTexture} for upload tracking in
 * {@link DynamicTextureCache} at {@code registerTexture()} time.
 */
@Mixin(PlayerSkinTexture.class)
public class PlayerSkinTextureMixin {

    @Inject(method = "uploadTexture", at = @At("HEAD"))
    private void rtxremix$onUploadTexture(NativeImage image, CallbackInfo ci) {
        if (image == null) return;
        DynamicTextureCache.captureFromUpload((AbstractTexture) (Object) this, image);
    }
}
