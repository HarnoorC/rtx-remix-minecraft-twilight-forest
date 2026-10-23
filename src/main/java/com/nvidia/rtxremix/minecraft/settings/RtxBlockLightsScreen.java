/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.settings;

import com.nvidia.rtxremix.minecraft.RtxRemixMod;
import java.util.ArrayList;
import java.util.List;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.gui.screen.ConfirmScreen;
import net.minecraft.client.gui.screen.Screen;
import net.minecraft.client.gui.screen.option.GameOptionsScreen;
import net.minecraft.client.gui.tooltip.Tooltip;
import net.minecraft.client.gui.widget.ButtonWidget;
import net.minecraft.client.gui.widget.DirectionalLayoutWidget;
import net.minecraft.client.gui.widget.TextWidget;
import net.minecraft.screen.ScreenTexts;
import net.minecraft.text.Text;
import net.minecraft.util.Formatting;

/** Two-column editor for built-in block-light intensity multipliers. */
final class RtxBlockLightsScreen extends GameOptionsScreen {

    private final RtxSettings settings;
    private final Runnable saveSettings;
    private final List<BlockLightMultiplierSlider> sliders = new ArrayList<>();

    RtxBlockLightsScreen(Screen parent, RtxSettings settings, Runnable saveSettings) {
        super(
                parent,
                MinecraftClient.getInstance().options,
                Text.translatable("rtxremix.settings.blockLights.title"));
        this.settings = settings;
        this.saveSettings = saveSettings;
    }

    @Override
    @SuppressWarnings("unchecked")
    protected void addOptions() {
        sliders.clear();
        this.body.addWidgetEntry(
                new TextWidget(
                        150,
                        20,
                        Text.translatable("rtxremix.settings.blockLights.block")
                                .formatted(Formatting.BOLD),
                        this.textRenderer),
                new TextWidget(
                        150,
                        20,
                        Text.translatable("rtxremix.settings.blockLights.intensity")
                                .formatted(Formatting.BOLD),
                        this.textRenderer));

        for (RtxSetting<?> raw : settings.group(SettingGroup.BLOCK_LIGHTS)) {
            RtxSetting<Double> setting = (RtxSetting<Double>) raw;
            TextWidget name =
                    new TextWidget(150, 20, Text.translatable(setting.labelKey()), this.textRenderer);
            name.setTooltip(Tooltip.of(Text.translatable(setting.tooltipKey())));
            BlockLightMultiplierSlider slider = new BlockLightMultiplierSlider(setting);
            sliders.add(slider);
            this.body.addWidgetEntry(name, slider);
        }
    }

    @Override
    protected void initFooter() {
        DirectionalLayoutWidget footer = DirectionalLayoutWidget.horizontal().spacing(8);
        footer.add(ButtonWidget.builder(
                        Text.translatable("rtxremix.settings.reset"), button -> confirmReset())
                .tooltip(Tooltip.of(Text.translatable("rtxremix.settings.reset.tip")))
                .width(98)
                .build());
        footer.add(ButtonWidget.builder(ScreenTexts.DONE, button -> close()).width(98).build());
        this.layout.addFooter(footer);
    }

    private boolean commitPendingValues() {
        boolean changed = false;
        for (BlockLightMultiplierSlider slider : sliders) {
            changed |= slider.commit();
        }
        return changed;
    }

    private void confirmReset() {
        boolean pendingChanged = commitPendingValues();
        this.client.setScreen(new ConfirmScreen(confirmed -> {
            boolean rebuild = pendingChanged;
            if (confirmed) {
                rebuild |= settings.hasOverrides(SettingGroup.BLOCK_LIGHTS);
                settings.resetGroup(SettingGroup.BLOCK_LIGHTS);
            }
            if (saveSettings != null) {
                saveSettings.run();
            }
            if (rebuild) {
                RtxRemixMod.rebuildLoadedTerrain();
            }
            this.client.setScreen(new RtxBlockLightsScreen(this.parent, settings, saveSettings));
        }, Text.translatable(
                        "rtxremix.settings.reset.confirm.title",
                        Text.translatable("rtxremix.settings.blockLights.title")),
                Text.translatable(
                        "rtxremix.settings.reset.confirm.message",
                        Text.translatable("rtxremix.settings.blockLights.title"))));
    }

    @Override
    public void close() {
        boolean changed = commitPendingValues();
        if (saveSettings != null) {
            saveSettings.run();
        }
        if (changed) {
            RtxRemixMod.rebuildLoadedTerrain();
        }
        this.client.setScreen(this.parent);
    }
}
