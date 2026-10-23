/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.camera;

import java.util.Objects;

/**
 * One marked pose for a documentation screenshot: where the player stood, what
 * they looked at, and the scene state a camera waypoint cannot carry.
 *
 * <p>A shot is a pose store, not a flythrough. The capture pass teleports to it,
 * applies the scene, holds the pose until the world settles, and captures.
 *
 * @param name       single file name, which is also the image name
 * @param x          player position
 * @param y          player position
 * @param z          player position
 * @param yaw        player yaw in degrees
 * @param pitch      player pitch in degrees
 * @param timeOfDay  world time of day in ticks, {@code 0} to {@code 23999}
 * @param weather    one of {@link Weather}
 * @param rtxEnabled whether path tracing was on
 * @param proceduralClouds whether the procedural cloud style was selected
 */
public record StillShot(
        String name,
        double x,
        double y,
        double z,
        float yaw,
        float pitch,
        long timeOfDay,
        Weather weather,
        boolean rtxEnabled,
        boolean proceduralClouds
) {
    /** Vanilla's three weather states. */
    public enum Weather {
        CLEAR("clear"),
        RAIN("rain"),
        THUNDER("thunder");

        private final String wireName;

        Weather(String wireName) {
            this.wireName = wireName;
        }

        public String wireName() {
            return wireName;
        }

        public static Weather fromWireName(String name) {
            for (Weather weather : values()) {
                if (weather.wireName.equals(name)) {
                    return weather;
                }
            }
            throw new IllegalArgumentException("unknown weather: " + name);
        }

        public static Weather of(boolean raining, boolean thundering) {
            if (thundering) {
                return THUNDER;
            }
            return raining ? RAIN : CLEAR;
        }
    }

    public StillShot {
        Objects.requireNonNull(weather, "weather");
        // The name becomes <name>.png and <name>.jpg, so a value read from a
        // file is held to the file-name rule, not only one typed in chat.
        if (!CameraNames.isValid(name)) {
            throw new IllegalArgumentException("shot name is not a file name: " + name + ". " + CameraNames.RULE);
        }
        if (!Double.isFinite(x) || !Double.isFinite(y) || !Double.isFinite(z)) {
            throw new IllegalArgumentException("shot position must be finite");
        }
        if (!Float.isFinite(yaw) || !Float.isFinite(pitch)) {
            throw new IllegalArgumentException("shot rotation must be finite");
        }
        if (timeOfDay < 0 || timeOfDay >= 24_000L) {
            throw new IllegalArgumentException("shot timeOfDay must be within one day: " + timeOfDay);
        }
    }
}
