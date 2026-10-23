/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.settings;

import com.mojang.serialization.Codec;
import com.nvidia.rtxremix.minecraft.UnfocusedFramerateLimit;
import net.minecraft.client.gui.tooltip.Tooltip;
import net.minecraft.client.option.SimpleOption;
import net.minecraft.screen.ScreenTexts;
import net.minecraft.text.Text;
import net.minecraft.util.Formatting;

import java.util.Locale;
import java.util.Optional;
import java.util.function.Function;

/** Converts an RtxSetting into a vanilla SimpleOption for OptionListWidget. */
final class RtxOptionFactory {

    static final String ENTITY_DISTANCE_ID = "dist.entity";
    static final String LIGHT_DISTANCE_ID = "dist.light";
    static final String SUN_INTENSITY_ID = "sky.sunIntensity";
    static final String PROCEDURAL_CLOUDS_ID = "clouds.procedural";
    static final String TERRAIN_EMISSION_MULTIPLIER_ID =
            "materials.terrainEmissionMultiplier";
    static final double SUN_MIN_NONZERO_INTENSITY = 0.01;
    static final double SUN_ZERO_SENTINEL_END = 0.02;
    static final double MULTIPLIER_MIN_NONZERO_VALUE = 0.02;
    static final double MULTIPLIER_ZERO_SENTINEL_END = 0.04;
    /**
     * Slider position above the shared 0..32 range that encodes the runtime
     * value 0.
     *
     * <p>Zero means Auto to these setters, which reads backwards
     * at the left edge of a distance slider, so it is drawn at the right edge
     * instead. That needs a slider-space value of its own: persistence and
     * default comparisons stay in runtime-value space, and only the widget sees
     * this position. Another sentinel-backed slider must preserve the same
     * separation.
     */
    static final int SENTINEL_SLIDER_VALUE = 33;
    static final String UNFOCUSED_FRAMERATE_ID = "framerate.unfocused";

    private RtxOptionFactory() {}

    @SuppressWarnings("unchecked")
    public static SimpleOption<?> toOption(RtxSetting<?> setting) {
        switch (setting.kind()) {
            case BOOL -> {
                RtxSetting<Boolean> s = (RtxSetting<Boolean>) setting;
                return SimpleOption.ofBoolean(
                        setting.labelKey(),
                        v -> tooltip(s, v),
                        buttonValueText(value -> booleanValueText(s.id(), value)),
                        s.get(),
                        s::apply);
            }
            case INT -> {
                RtxSetting<Integer> s = (RtxSetting<Integer>) setting;
                int sentinelSliderValue = sentinelSliderValue(s.id());
                int sliderMin = sentinelSliderValue > 0 ? 1 : (int) s.min() / s.step();
                int sliderMax = sentinelSliderValue > 0 ? sentinelSliderValue : (int) s.max() / s.step();
                var callbacks =
                        sliderApplyPolicy(
                                new SimpleOption.ValidatingIntSliderCallbacks(
                                        sliderMin, sliderMax, true).withModifier(
                                                value -> intValueFromSlider(s, value),
                                                value -> sliderValueFromInt(s, value)),
                                s.applySliderValueImmediately());
                return new SimpleOption<>(
                        setting.labelKey(),
                        v -> tooltip(s, v),
                        (optionText, value) -> optionText.copy()
                                .append(": ").append(intValueText(s.id(), value)),
                        callbacks,
                        s.get(),
                        s::apply);
            }
            case FLOAT -> {
                RtxSetting<Double> s = (RtxSetting<Double>) setting;
                double min = s.min();
                double max = s.max();
                var callbacks =
                        sliderApplyPolicy(
                                SimpleOption.DoubleSliderCallbacks.INSTANCE.withModifier(
                                        progress -> floatValueFromSlider(
                                                s.id(), progress, min, max),
                                        value -> sliderValueFromFloat(
                                                s.id(), value, min, max)),
                                s.applySliderValueImmediately());
                return new SimpleOption<>(
                        setting.labelKey(),
                        v -> tooltip(s, v),
                        (optionText, value) -> optionText.copy()
                                .append(": ").append(floatValueText(s.id(), value)),
                        callbacks,
                        s.get(),
                        s::apply);
            }
            default -> throw new IllegalStateException("Unknown kind: " + setting.kind());
        }
    }

    /**
     * The value text for a button, without its label.
     *
     * <p>Buttons render as a
     * {@link net.minecraft.client.gui.widget.CyclingButtonWidget}, which
     * composes {@code "<label>: <value>"} from the option text itself, so
     * prefixing the label here renders it twice. Sliders instead set their
     * message straight from the getter, which is why the slider kinds include it.
     */
    private static <T> SimpleOption.ValueTextGetter<T> buttonValueText(
            Function<T, Text> valueText) {
        return (optionText, value) -> valueText.apply(value);
    }

    static <T> SimpleOption.SliderCallbacks<T> sliderApplyPolicy(
            SimpleOption.SliderCallbacks<T> callbacks, boolean applyImmediately) {
        if (applyImmediately) {
            return callbacks;
        }
        return new SimpleOption.SliderCallbacks<>() {
            @Override
            public double toSliderProgress(T value) {
                return callbacks.toSliderProgress(value);
            }

            @Override
            public T toValue(double sliderProgress) {
                return callbacks.toValue(sliderProgress);
            }

            @Override
            public Optional<T> validate(T value) {
                return callbacks.validate(value);
            }

            @Override
            public Codec<T> codec() {
                return callbacks.codec();
            }

            @Override
            public boolean applyValueImmediately() {
                return false;
            }
        };
    }

    private static <T> Tooltip tooltip(RtxSetting<T> setting, T value) {
        Text defaultValue = switch (setting.kind()) {
            case BOOL -> booleanValueText(
                    setting.id(), (Boolean) setting.defaultValue());
            case INT -> intValueText(setting.id(), (Integer) setting.defaultValue());
            case FLOAT -> floatValueText(
                    setting.id(), (Double) setting.defaultValue());
        };
        Text defaultLine = Text.translatable("rtxremix.settings.tooltip.default", defaultValue);
        if (!setting.isDefaultValue(value)) {
            defaultLine = defaultLine.copy()
                    .append(Text.literal(" "))
                    .append(Text.translatable("rtxremix.settings.tooltip.overridden")
                            .formatted(Formatting.YELLOW));
        }
        return Tooltip.of(ScreenTexts.joinLines(
                Text.translatable(setting.tooltipKey()), defaultLine));
    }

    static int intValueFromSlider(RtxSetting<Integer> setting, int sliderValue) {
        int sentinelSliderValue = sentinelSliderValue(setting.id());
        if (sentinelSliderValue > 0 && sliderValue == sentinelSliderValue) {
            return 0;
        }
        return sliderValue * setting.step();
    }

    static int sliderValueFromInt(RtxSetting<Integer> setting, int value) {
        int sentinelSliderValue = sentinelSliderValue(setting.id());
        if (sentinelSliderValue < 0) {
            return value / setting.step();
        }
        if (value == 0) {
            return sentinelSliderValue;
        }
        return Math.max(1, Math.min(sentinelSliderValue - 1, value));
    }

    static double floatValueFromSlider(
            String settingId, double progress, double min, double max) {
        if (SUN_INTENSITY_ID.equals(settingId)) {
            return exponentialValueFromSlider(
                    progress, max, SUN_MIN_NONZERO_INTENSITY,
                    SUN_ZERO_SENTINEL_END);
        }
        if (TERRAIN_EMISSION_MULTIPLIER_ID.equals(settingId)) {
            return exponentialValueFromSlider(
                    progress, max, MULTIPLIER_MIN_NONZERO_VALUE,
                    MULTIPLIER_ZERO_SENTINEL_END);
        }
        return min + progress * (max - min);
    }

    static double sliderValueFromFloat(
            String settingId, double value, double min, double max) {
        if (SUN_INTENSITY_ID.equals(settingId)) {
            return sliderValueFromExponential(
                    value, max, SUN_MIN_NONZERO_INTENSITY,
                    SUN_ZERO_SENTINEL_END);
        }
        if (TERRAIN_EMISSION_MULTIPLIER_ID.equals(settingId)) {
            return sliderValueFromExponential(
                    value, max, MULTIPLIER_MIN_NONZERO_VALUE,
                    MULTIPLIER_ZERO_SENTINEL_END);
        }
        return (value - min) / (max - min);
    }

    private static double exponentialValueFromSlider(
            double progress, double max, double minNonzero, double zeroSentinelEnd) {
        if (progress < zeroSentinelEnd) {
            return 0.0;
        }
        double logarithmicProgress =
                (progress - zeroSentinelEnd) / (1.0 - zeroSentinelEnd);
        return minNonzero * Math.pow(max / minNonzero, logarithmicProgress);
    }

    private static double sliderValueFromExponential(
            double value, double max, double minNonzero, double zeroSentinelEnd) {
        if (value <= 0.0) {
            return 0.0;
        }
        double clamped = Math.max(minNonzero, Math.min(max, value));
        double logarithmicProgress = Math.log(clamped / minNonzero)
                / Math.log(max / minNonzero);
        return zeroSentinelEnd
                + logarithmicProgress * (1.0 - zeroSentinelEnd);
    }

    private static Text floatValueText(String settingId, double value) {
        String formatted = String.format(Locale.ROOT, "%.2f", value);
        if (!TERRAIN_EMISSION_MULTIPLIER_ID.equals(settingId)) {
            return Text.literal(formatted);
        }
        if (value <= 0.0) {
            return Text.translatable("rtxremix.settings.value.off");
        }
        return Text.translatable("rtxremix.settings.value.multiplier", formatted);
    }

    static Text booleanValueText(String settingId, boolean value) {
        if (PROCEDURAL_CLOUDS_ID.equals(settingId)) {
            return Text.translatable(value
                    ? "rtxremix.settings.value.procedural"
                    : "rtxremix.settings.value.classic");
        }
        return ScreenTexts.onOrOff(value);
    }

    static Text intValueText(String settingId, int value) {
        if (UNFOCUSED_FRAMERATE_ID.equals(settingId)) {
            // Vanilla's own Max Framerate wording, so the two read alike.
            return value == UnfocusedFramerateLimit.UNLIMITED
                    ? Text.translatable("options.framerateLimit.max")
                    : Text.translatable("options.framerate", value);
        }
        if (value == 0 && sentinelSliderValue(settingId) > 0) {
            return Text.translatable("rtxremix.settings.value.auto");
        }
        return Text.literal(Integer.toString(value));
    }

    private static int sentinelSliderValue(String settingId) {
        boolean hasSentinel = ENTITY_DISTANCE_ID.equals(settingId)
                || LIGHT_DISTANCE_ID.equals(settingId);
        return hasSentinel ? SENTINEL_SLIDER_VALUE : -1;
    }
}
