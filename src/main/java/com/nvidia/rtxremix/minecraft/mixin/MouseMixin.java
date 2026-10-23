/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.mixin;

import com.nvidia.rtxremix.minecraft.RtxRemixMod;
import com.nvidia.rtxremix.minecraft.input.RemixMouseAccess;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.Mouse;
import org.lwjgl.glfw.GLFW;
import org.spongepowered.asm.mixin.Final;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/**
 * Applies the shared Remix overlay input policy to Minecraft's mouse callbacks.
 *
 * The gate blocks Minecraft only while the overlay capture session owns input.
 */
@Mixin(Mouse.class)
public abstract class MouseMixin implements RemixMouseAccess {
    private static final double rtxremix$HIDDEN_CURSOR_COORDINATE = -Double.MAX_VALUE;

    @Shadow @Final
    private MinecraftClient client;

    @Shadow
    private int activeButton;

    @Shadow
    private int field_1796;

    @Shadow
    private void onMouseButton(long window, int button, int action, int mods) { }

    private boolean rtxremix$releasingActiveButton;

    @Override
    public void rtxremix$releaseActiveButton() {
        if (activeButton == -1) {
            return;
        }

        // Touchscreen mode counts outstanding presses and suppresses intermediate releases.
        field_1796 = client.options.getTouchscreen().getValue() ? 1 : 0;
        rtxremix$releasingActiveButton = true;
        try {
            onMouseButton(client.getWindow().getHandle(), activeButton, GLFW.GLFW_RELEASE, 0);
        } finally {
            rtxremix$releasingActiveButton = false;
        }
    }

    @Shadow
    private double x;

    @Shadow
    private double y;

    @Shadow
    private boolean hasResolutionChanged;

    @Inject(method = "onCursorPos", at = @At("HEAD"), cancellable = true)
    private void rtxremix$blockMovementWhileMenuOpen(
            long window, double cursorX, double cursorY, CallbackInfo ci) {
        if (RtxRemixMod.getRemixInputGate().isCaptureSessionOpen()) {
            x = cursorX;
            y = cursorY;
            hasResolutionChanged = false;
            ci.cancel();
        }
    }

    /* Screen rendering derives hover state from these coordinates even without a movement event. */
    @Inject(method = "getX", at = @At("HEAD"), cancellable = true)
    private void rtxremix$hideXWhileMenuOpen(CallbackInfoReturnable<Double> cir) {
        if (RtxRemixMod.getRemixInputGate().isCaptureSessionOpen()) {
            cir.setReturnValue(rtxremix$HIDDEN_CURSOR_COORDINATE);
        }
    }

    @Inject(method = "getY", at = @At("HEAD"), cancellable = true)
    private void rtxremix$hideYWhileMenuOpen(CallbackInfoReturnable<Double> cir) {
        if (RtxRemixMod.getRemixInputGate().isCaptureSessionOpen()) {
            cir.setReturnValue(rtxremix$HIDDEN_CURSOR_COORDINATE);
        }
    }

    @Inject(method = "lockCursor", at = @At("HEAD"), cancellable = true)
    private void rtxremix$blockLockWhileMenuOpen(CallbackInfo ci) {
        if (RtxRemixMod.getRemixInputGate().isCaptureSessionOpen()) {
            ci.cancel();
        }
    }

    @Inject(method = "onMouseButton", at = @At("HEAD"), cancellable = true)
    private void rtxremix$blockClickWhileMenuOpen(long window, int button, int action, int mods, CallbackInfo ci) {
        boolean syntheticRelease = rtxremix$releasingActiveButton
                && action == GLFW.GLFW_RELEASE
                && button == activeButton;
        if (RtxRemixMod.getRemixInputGate().isCaptureSessionOpen() && !syntheticRelease) {
            ci.cancel();
        }
    }

    @Inject(method = "onMouseScroll", at = @At("HEAD"), cancellable = true)
    private void rtxremix$blockScrollWhileMenuOpen(long window, double horizontal, double vertical, CallbackInfo ci) {
        if (RtxRemixMod.getRemixInputGate().isCaptureSessionOpen()) {
            ci.cancel();
        }
    }
}
