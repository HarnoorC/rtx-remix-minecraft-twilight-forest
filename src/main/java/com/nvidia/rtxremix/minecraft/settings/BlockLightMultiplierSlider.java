/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.settings;

import com.nvidia.rtxremix.minecraft.light.BlockLightIntensityControls;
import java.util.Locale;
import net.minecraft.client.gui.tooltip.Tooltip;
import net.minecraft.client.gui.widget.SliderWidget;
import net.minecraft.text.Text;

/** Deferred exponential slider used by the block-light intensity table. */
class BlockLightMultiplierSlider extends SliderWidget {

    static final double MIN_NONZERO_MULTIPLIER = 0.02;
    static final double ZERO_SENTINEL_END = 0.04;

    private final RtxSetting<Double> setting;
    private double pendingMultiplier;

    BlockLightMultiplierSlider(RtxSetting<Double> setting) {
        super(0, 0, 150, 20, Text.empty(), positionFromMultiplier(setting.get()));
        this.setting = setting;
        this.pendingMultiplier = setting.get();
        setTooltip(Tooltip.of(Text.translatable(setting.tooltipKey())));
        updateMessage();
    }

    @Override
    protected void updateMessage() {
        pendingMultiplier = multiplierFromPosition(value);
        setMessage(pendingMultiplier == 0.0
                ? Text.translatable("rtxremix.settings.value.off")
                : Text.translatable(
                        "rtxremix.settings.value.multiplier",
                        Text.literal(String.format(Locale.ROOT, "%.2f", pendingMultiplier))));
    }

    @Override
    protected void applyValue() {
        pendingMultiplier = multiplierFromPosition(value);
    }

    boolean commit() {
        if (Float.compare(setting.get().floatValue(), (float) pendingMultiplier) == 0) {
            return false;
        }
        setting.apply(pendingMultiplier);
        return true;
    }

    static double multiplierFromPosition(double position) {
        if (position < ZERO_SENTINEL_END) {
            return 0.0;
        }
        double progress = (position - ZERO_SENTINEL_END) / (1.0 - ZERO_SENTINEL_END);
        double ratio =
                BlockLightIntensityControls.MAX_MULTIPLIER / MIN_NONZERO_MULTIPLIER;
        return MIN_NONZERO_MULTIPLIER * Math.pow(ratio, progress);
    }

    static double positionFromMultiplier(double multiplier) {
        if (multiplier <= 0.0) {
            return 0.0;
        }
        double clamped = Math.max(
                MIN_NONZERO_MULTIPLIER,
                Math.min(BlockLightIntensityControls.MAX_MULTIPLIER, multiplier));
        double ratio =
                BlockLightIntensityControls.MAX_MULTIPLIER / MIN_NONZERO_MULTIPLIER;
        double progress = Math.log(clamped / MIN_NONZERO_MULTIPLIER) / Math.log(ratio);
        return ZERO_SENTINEL_END + progress * (1.0 - ZERO_SENTINEL_END);
    }
}
