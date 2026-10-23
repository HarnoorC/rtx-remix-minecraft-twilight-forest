/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.entity;

import net.minecraft.client.texture.NativeImage;
import net.minecraft.client.texture.Sprite;
import net.minecraft.client.texture.SpriteContents;
import net.minecraft.client.texture.SpriteDimensions;
import net.minecraft.resource.metadata.ResourceMetadata;
import net.minecraft.util.Identifier;

/** Real {@link Sprite}s for key and UV-remap tests, with the atlas rectangle chosen by the test. */
final class SpriteFixtures {

    private static final Identifier ATLAS = Identifier.of("minecraft", "textures/atlas/test.png");

    private SpriteFixtures() {}

    /**
     * A {@code size}-pixel square sprite at ({@code x}, {@code y}) in a square atlas of
     * {@code atlasSize} pixels. Every call allocates a new sprite, so two calls with the
     * same arguments are two identities, as two atlas stitches would be.
     */
    static Sprite sprite(int x, int y, int size, int atlasSize) {
        SpriteContents contents = new SpriteContents(
                Identifier.of("minecraft", "test/" + x + "_" + y),
                new SpriteDimensions(size, size),
                new NativeImage(size, size, false),
                ResourceMetadata.NONE);
        // The constructor is protected; an anonymous subclass reaches it without
        // widening access for the sake of a test.
        Sprite sprite = new Sprite(ATLAS, contents, atlasSize, atlasSize, x, y) {};
        // The rectangle is fixed at construction and no test reads pixels, so the
        // off-heap image is released at once.
        contents.close();
        return sprite;
    }
}
