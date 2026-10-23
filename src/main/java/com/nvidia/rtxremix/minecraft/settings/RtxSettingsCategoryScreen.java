/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.settings;

import com.nvidia.rtxremix.minecraft.texture.BlockTextureManager;
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
import net.minecraft.client.option.SimpleOption;
import net.minecraft.screen.ScreenTexts;
import net.minecraft.text.Text;
import net.minecraft.util.Formatting;

/** Native options list for one RTX settings category. */
final class RtxSettingsCategoryScreen extends GameOptionsScreen {

    private final RtxSettings settings;
    private final Runnable saveSettings;
    private final SettingCategory category;

    RtxSettingsCategoryScreen(
            Screen parent,
            RtxSettings settings,
            Runnable saveSettings,
            SettingCategory category) {
        super(parent, MinecraftClient.getInstance().options, Text.translatable(category.labelKey()));
        this.settings = settings;
        this.saveSettings = saveSettings;
        this.category = category;
    }

    @Override
    protected void addOptions() {
        for (SettingGroup group : SettingGroup.values()) {
            if (group.category() != category) {
                continue;
            }
            List<RtxSetting<?>> groupSettings = settings.group(group);
            if (groupSettings.isEmpty()) {
                continue;
            }
            if (opensSubscreen(group)) {
                this.body.addWidgetEntry(
                        new TextWidget(
                                150,
                                20,
                                Text.translatable(group.labelKey()).formatted(Formatting.BOLD),
                                this.textRenderer),
                        ButtonWidget.builder(
                                        Text.translatable("rtxremix.settings.configure"),
                                        button -> this.client.setScreen(
                                                new RtxBlockLightsScreen(
                                                        this, settings, saveSettings)))
                                .width(150)
                                .build());
                continue;
            }

            TextWidget header = new TextWidget(
                    310,
                    20,
                    Text.translatable(group.labelKey()).formatted(Formatting.BOLD),
                    this.textRenderer);
            this.body.addWidgetEntry(header, null);

            List<SimpleOption<?>> options = new ArrayList<>();
            for (RtxSetting<?> setting : groupSettings) {
                options.add(RtxOptionFactory.toOption(setting));
            }
            if (fullWidthRows(group)) {
                options.forEach(this.body::addSingleOptionEntry);
            } else {
                this.body.addAll(options.toArray(new SimpleOption<?>[0]));
            }
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

    private void confirmReset() {
        this.client.setScreen(new ConfirmScreen(confirmed -> {
            if (confirmed) {
                resetCurrentScreen();
                if (saveSettings != null) {
                    saveSettings.run();
                }
                if (commitTerrainEmission()) {
                    RtxRemixMod.rebuildTerrainForMaterialSettings();
                }
                this.client.setScreen(
                        new RtxSettingsCategoryScreen(
                                this.parent, settings, saveSettings, category));
            } else {
                this.client.setScreen(this);
            }
        }, Text.translatable("rtxremix.settings.reset.confirm.title",
                        Text.translatable(category.labelKey())),
                Text.translatable("rtxremix.settings.reset.confirm.message",
                        Text.translatable(category.labelKey()))));
    }

    private void resetCurrentScreen() {
        for (SettingGroup group : resettableGroups(category)) {
            settings.resetGroup(group);
        }
    }

    static List<SettingGroup> resettableGroups(SettingCategory category) {
        List<SettingGroup> groups = new ArrayList<>();
        for (SettingGroup group : SettingGroup.values()) {
            if (group.category() == category && !opensSubscreen(group)) {
                groups.add(group);
            }
        }
        return List.copyOf(groups);
    }

    private static boolean opensSubscreen(SettingGroup group) {
        return group == SettingGroup.BLOCK_LIGHTS;
    }

    private static boolean fullWidthRows(SettingGroup group) {
        return group == SettingGroup.FRAMERATE;
    }

    private boolean commitTerrainEmission() {
        BlockTextureManager textures = BlockTextureManager.get();
        return category == SettingCategory.MATERIALS
                && textures != null
                && textures.commitTerrainEmissionMultiplier();
    }

    @Override
    public void close() {
        if (this.body != null) {
            this.body.applyAllPendingValues();
        }
        if (saveSettings != null) {
            saveSettings.run();
        }
        if (commitTerrainEmission()) {
            RtxRemixMod.rebuildTerrainForMaterialSettings();
        }
        this.client.setScreen(this.parent);
    }
}
