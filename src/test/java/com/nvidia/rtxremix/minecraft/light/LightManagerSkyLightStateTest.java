/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.light;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class LightManagerSkyLightStateTest {

    @ParameterizedTest
    @CsvSource({
            "1.0, -1.0, 3.0",
            "-1.0, 1.0, 0.06"
    })
    void weatherDomeRadiancePreservesAuthoredSourceScale(
            float sunHeight, float moonHeight, float expected) {
        LightManager.SkyLightState state = state(
                new float[]{0.0f, sunHeight, 0.0f},
                new float[]{0.0f, moonHeight, 0.0f},
                new float[]{30.0f, 30.0f, 30.0f},
                new float[]{0.6f, 0.6f, 0.6f});

        assertEquals(expected, state.weatherDomeRadiance(), 1.0e-6f);
    }

    @Test
    void weatherInterpolatesDirectLightsWithoutReducingDomeSource() {
        float clearSun = LightManager.weatherSunDirectScale(0.0f, 0.0f);
        float rainSun = LightManager.weatherSunDirectScale(1.0f, 0.0f);
        float thunderSun = LightManager.weatherSunDirectScale(1.0f, 1.0f);
        float clearMoon = LightManager.weatherMoonDirectScale(0.0f, 0.0f);
        float rainMoon = LightManager.weatherMoonDirectScale(1.0f, 0.0f);
        float thunderMoon = LightManager.weatherMoonDirectScale(1.0f, 1.0f);

        assertEquals(1.0f, clearSun, 1.0e-6f);
        assertEquals(0.0025f, rainSun, 1.0e-6f);
        assertEquals(0.001f, thunderSun, 1.0e-6f);
        assertEquals(1.0f, clearMoon, 1.0e-6f);
        assertEquals(0.375f, rainMoon, 1.0e-6f);
        assertEquals(0.625f, thunderMoon, 1.0e-6f);
        assertEquals(
                (clearSun + rainSun) * 0.5f,
                LightManager.weatherSunDirectScale(0.5f, 0.0f),
                1.0e-6f);
        assertEquals(
                (rainSun + thunderSun) * 0.5f,
                LightManager.weatherSunDirectScale(1.0f, 0.5f),
                1.0e-6f);
        assertEquals(
                (clearMoon + rainMoon) * 0.5f,
                LightManager.weatherMoonDirectScale(0.5f, 0.0f),
                1.0e-6f);
        assertEquals(
                (rainMoon + thunderMoon) * 0.5f,
                LightManager.weatherMoonDirectScale(1.0f, 0.5f),
                1.0e-6f);
    }

    @Test
    void fixedMoonLightsFromItsDirectionWithNoSun() {
        float[] direction = {0.6f, 0.8f, 0.0f};

        LightManager.SkyLightState state = LightManager.fixedMoonSkyLightState(direction, 1.0f);

        assertArrayEquals(direction, state.moonPosition());
        assertArrayEquals(new float[]{-0.6f, -0.8f, 0.0f}, state.sunPosition(), 1.0e-6f);
        assertArrayEquals(new float[3], state.sunDirectRadiance());
        assertArrayEquals(new float[3], state.sunSourceRadiance());
        float[] moon = state.moonDirectRadiance();
        assertTrue(moon[2] > 0.0f);
        assertTrue(moon[2] >= moon[1] && moon[1] >= moon[0], "moonlight is cool");
        direction[0] = 0.0f;
        assertEquals(0.6f, state.moonPosition()[0], "state keeps its own copy");
    }

    @Test
    void fixedMoonRadianceIsLinearInIntensityAndOffAtZero() {
        float[] direction = {0.0f, 1.0f, 0.0f};
        float[] one = LightManager.fixedMoonSkyLightState(direction, 1.0f).moonDirectRadiance();
        float[] three = LightManager.fixedMoonSkyLightState(direction, 3.0f).moonDirectRadiance();

        for (int channel = 0; channel < 3; channel++) {
            assertEquals(one[channel] * 3.0f, three[channel], 1.0e-6f);
        }
        assertArrayEquals(new float[3],
                LightManager.fixedMoonSkyLightState(direction, 0.0f).moonDirectRadiance());
    }

    @Test
    void twilightMoonIntensityClampsToItsSliderRange() {
        float original = LightManager.getTwilightMoonIntensity();
        try {
            LightManager.setTwilightMoonIntensity(-1.0f);
            assertEquals(0.0f, LightManager.getTwilightMoonIntensity());
            LightManager.setTwilightMoonIntensity(100.0f);
            assertEquals(LightManager.MAX_TWILIGHT_MOON_INTENSITY, LightManager.getTwilightMoonIntensity());
        } finally {
            LightManager.setTwilightMoonIntensity(original);
        }
    }

    private static LightManager.SkyLightState state(
            float[] sunPosition,
            float[] moonPosition,
            float[] sunSource,
            float[] moonSource) {
        return new LightManager.SkyLightState(
                sunPosition,
                moonPosition,
                sunSource,
                moonSource,
                new float[3],
                new float[3],
                0.0f,
                0.0f);
    }
}
