/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.terrain.capture;

import com.nvidia.rtxremix.HardcodedVertex;
import com.nvidia.rtxremix.MaterialInfo;
import com.nvidia.rtxremix.minecraft.asset.RemixMaterial;
import com.nvidia.rtxremix.minecraft.terrain.ChunkManager;
import com.nvidia.rtxremix.minecraft.texture.BlockTextureManager;
import com.nvidia.rtxremix.minecraft.texture.RedstoneEmission;
import com.nvidia.rtxremix.minecraft.texture.TerrainSpriteFixtures;
import net.minecraft.util.Identifier;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DustLayerStackTest {
    /** Vanilla's redstone_dust_dot alpha. */
    private static final String[] DOT = {
            "................", "................", "................", "................",
            "................", "......#.##......", ".....######.....", "......##.###....",
            ".....######.....", ".....###.##.....", ".......##.#.....", ".........#......",
            "................", "................", "................", "................"};
    /** Vanilla's redstone_dust_line0 alpha. */
    private static final String[] LINE = {
            "........#.......", "................", "........#.......", ".......##.......",
            ".......#.#......", ".........#......", "........##......", ".......#........",
            "........#.......", ".......#........", ".......##.......", "......#.........",
            ".......##.......", "........#.......", "........#.......", ".......#........"};
    private static final String[] OVERLAY = {
            "################", "................", "................", "................",
            "................", "................", "................", "................",
            "................", "................", "................", "................",
            "................", "................", "................", "................"};
    private static final String[] FULL = {
            "################", "################", "################", "################",
            "################", "################", "################", "################",
            "################", "################", "################", "################",
            "################", "################", "################", "################"};
    /** Pack texels between the opaque and clear extremes, on the first row. */
    private static final String[] PARTLY_TRANSPARENT = {
            "+-..............", "................", "................", "................",
            "................", "................", "................", "................",
            "................", "................", "................", "................",
            "................", "................", "................", "................"};
    /** How far vanilla's bake pulls a face's UVs toward their centre on a 1024-texel atlas. */
    private static final float VANILLA_UV_INSET = 4f / 1024;
    private static final int DOT_TINT = 0xFF660000;
    private static final int LINE_TINT = 0xFF770000;
    private static final int UNTINTED = 0xFFFFFFFF;
    // Wire dust sits a quarter texel above the block below it, away from the section origin.
    private static final float X = 3, Y = 5.015625f, Z = 7;

    private final BlockTextureManager previousTextures = BlockTextureManager.get();

    @AfterEach
    void restoreTextureManager() throws Exception {
        Field instance = BlockTextureManager.class.getDeclaredField("INSTANCE");
        instance.setAccessible(true);
        instance.set(null, previousTextures);
    }

    @Test
    void aCornerDrawsEachTexelOnceFromTheTopmostOpaqueLayer() {
        var dot = TerrainSpriteFixtures.sprite("redstone_dust_dot", 0, DOT, false);
        var line = TerrainSpriteFixtures.sprite("redstone_dust_line0", 16, LINE, false);
        DirectQuadWriter writer = new DirectQuadWriter();
        try {
            for (float inset : new float[] {0, VANILLA_UV_INSET}) {
                for (RedstoneEmission emission : new RedstoneEmission[] {RedstoneEmission.UNPOWERED, RedstoneEmission.POWERED}) {
                    writer.beginSection();
                    // Vanilla's corner: the full-block dot, then a half-block line over it, each with
                    // an underside that duplicate-backface removal drops.
                    stage(writer, dot, 0, 1, 0, 1, 1, DOT_TINT, 0, 1, 0, 1, inset);
                    stage(writer, dot, 0, 1, 0, 1, -1, DOT_TINT, 0, 1, 0, 1, inset);
                    stage(writer, line, 0, 1, 0, 0.5f, 1, LINE_TINT, 0, 1, 0, 0.5f, inset);
                    stage(writer, line, 0, 1, 0, 0.5f, -1, LINE_TINT, 0, 1, 0, 0.5f, inset);
                    writer.flushBlock(new TestTextures(dot, line), emission);
                    SectionMeshData mesh = writer.buildMeshData();
                    try {
                        assertEquals(1, mesh.surfaces().size());
                        var surface = mesh.surfaces().getFirst();
                        assertEquals(ChunkManager.CAT_CUTOUT, surface.category());
                        assertEquals(emission, surface.redstoneEmission());
                        int[][] drawn = drawnTints(mesh, Map.of(DOT_TINT, dot, LINE_TINT, line));
                        for (int z = 0; z < 16; z++) {
                            for (int x = 0; x < 16; x++) {
                                int expected = z < 8 && LINE[z].charAt(x) == '#' ? LINE_TINT
                                        : DOT[z].charAt(x) == '#' ? DOT_TINT : 0;
                                assertEquals(expected, drawn[z][x], "texel " + x + "," + z);
                            }
                        }
                    } finally {
                        mesh.release();
                    }
                }
            }
        } finally {
            writer.releaseBuffers();
        }
    }

    @Test
    void aVisibleOverlayOverAnOpaqueLineIsCutRatherThanMadeADecal() {
        var line = TerrainSpriteFixtures.sprite("redstone_dust_line0", 0, false, false);
        var overlay = TerrainSpriteFixtures.sprite("redstone_dust_overlay", 16, OVERLAY, true);
        TestTextures textures = new TestTextures(line, overlay);
        DirectQuadWriter writer = new DirectQuadWriter();
        try {
            writer.beginSection();
            stage(writer, line, 0, 1, 0, 1, 1, LINE_TINT);
            stage(writer, overlay, 0, 1, 0, 1, 1, UNTINTED);
            writer.flushBlock(textures, RedstoneEmission.POWERED);
            SectionMeshData mesh = writer.buildMeshData();
            try {
                assertEquals(2, mesh.surfaces().size());
                assertTrue(mesh.surfaces().stream().noneMatch(s -> s.category() == ChunkManager.CAT_OVERLAY));
                int[][] drawn = drawnTints(mesh, Map.of(LINE_TINT, line, UNTINTED, overlay));
                for (int z = 0; z < 16; z++) {
                    for (int x = 0; x < 16; x++) {
                        assertEquals(z == 0 ? UNTINTED : LINE_TINT, drawn[z][x], "texel " + x + "," + z);
                    }
                }
                assertEquals("solid", surfaceOf(mesh, ChunkManager.CAT_SOLID).bucketKey());
                assertEquals("cutout_sss", surfaceOf(mesh, ChunkManager.CAT_CUTOUT).bucketKey());
            } finally {
                mesh.release();
            }

            // The same quads on a block that is not dust keep the ordinary overlay path.
            writer.beginSection();
            stage(writer, line, 0, 1, 0, 1, 1, LINE_TINT);
            stage(writer, overlay, 0, 1, 0, 1, 1, UNTINTED);
            writer.flushBlock(textures, RedstoneEmission.NONE);
            mesh = writer.buildMeshData();
            try {
                assertEquals(4, surfaceOf(mesh, ChunkManager.CAT_SOLID).vertexCount());
                assertEquals(4, surfaceOf(mesh, ChunkManager.CAT_OVERLAY).vertexCount());
            } finally {
                mesh.release();
            }
        } finally {
            writer.releaseBuffers();
        }
    }

    @Test
    void aStackOffTheTexelGridIsLeftAsStaged() {
        var dot = TerrainSpriteFixtures.sprite("redstone_dust_dot", 0, DOT, false);
        var line = TerrainSpriteFixtures.sprite("redstone_dust_line0", 16, LINE, false);
        DirectQuadWriter writer = new DirectQuadWriter();
        try {
            writer.beginSection();
            stage(writer, dot, 0.03f, 1.03f, 0, 1, 1, DOT_TINT);
            stage(writer, line, 0, 1, 0, 0.5f, 1, LINE_TINT);
            writer.flushBlock(new TestTextures(dot, line), RedstoneEmission.POWERED);
            SectionMeshData mesh = writer.buildMeshData();
            try {
                assertEquals(1, mesh.surfaces().size());
                assertEquals(8, mesh.surfaces().getFirst().vertexCount());
            } finally {
                mesh.release();
            }
        } finally {
            writer.releaseBuffers();
        }
    }

    @Test
    void aPartlyTransparentTexelIsOwnedWhereTheAlphaTestKeepsIt() {
        var base = TerrainSpriteFixtures.sprite("redstone_dust_dot", 0, FULL, false);
        var top = TerrainSpriteFixtures.sprite("redstone_dust_line0", 16, PARTLY_TRANSPARENT, false);
        DirectQuadWriter writer = new DirectQuadWriter();
        try {
            writer.beginSection();
            stage(writer, base, 0, 1, 0, 1, 1, DOT_TINT);
            stage(writer, top, 0, 1, 0, 1, 1, LINE_TINT);
            writer.flushBlock(new TestTextures(base, top), RedstoneEmission.POWERED);
            SectionMeshData mesh = writer.buildMeshData();
            try {
                int[][] drawn = drawnTints(mesh, Map.of(DOT_TINT, base, LINE_TINT, top));
                for (int z = 0; z < 16; z++) {
                    for (int x = 0; x < 16; x++) {
                        assertEquals(z == 0 && x == 0 ? LINE_TINT : DOT_TINT, drawn[z][x], "texel " + x + "," + z);
                    }
                }
            } finally {
                mesh.release();
            }
        } finally {
            writer.releaseBuffers();
        }
    }

    @Test
    void aStackWithAnAnimatedLayerIsLeftAsStaged() {
        var dot = TerrainSpriteFixtures.sprite("redstone_dust_dot", 0, DOT, false);
        var line = TerrainSpriteFixtures.animated(TerrainSpriteFixtures.sprite("redstone_dust_line0", 16, LINE, false));
        DirectQuadWriter writer = new DirectQuadWriter();
        try {
            writer.beginSection();
            stage(writer, dot, 0, 1, 0, 1, 1, DOT_TINT);
            stage(writer, line, 0, 1, 0, 0.5f, 1, LINE_TINT);
            writer.flushBlock(new TestTextures(dot, line), RedstoneEmission.POWERED);
            SectionMeshData mesh = writer.buildMeshData();
            try {
                assertEquals(1, mesh.surfaces().size());
                assertEquals(8, mesh.surfaces().getFirst().vertexCount());
            } finally {
                mesh.release();
            }
        } finally {
            writer.releaseBuffers();
        }
    }

    @Test
    void aSpriteScaledAcrossHalfABlockIsLeftAsStaged() {
        var dot = TerrainSpriteFixtures.sprite("redstone_dust_dot", 0, DOT, false);
        var line = TerrainSpriteFixtures.sprite("redstone_dust_line0", 16, LINE, false);
        DirectQuadWriter writer = new DirectQuadWriter();
        try {
            writer.beginSection();
            stage(writer, dot, 0, 1, 0, 1, 1, DOT_TINT);
            // A custom model squeezing the line's 16 texels into half a block, 32 to the block.
            stage(writer, line, 0, 0.5f, 0, 1, 1, LINE_TINT, 0, 1, 0, 1, 0);
            writer.flushBlock(new TestTextures(dot, line), RedstoneEmission.POWERED);
            SectionMeshData mesh = writer.buildMeshData();
            try {
                assertEquals(1, mesh.surfaces().size());
                assertEquals(8, mesh.surfaces().getFirst().vertexCount());
            } finally {
                mesh.release();
            }
        } finally {
            writer.releaseBuffers();
        }
    }

    @Test
    void aStackWithNonAffineUvsIsLeftAsStaged() {
        var dot = TerrainSpriteFixtures.sprite("redstone_dust_dot", 0, DOT, false);
        var line = TerrainSpriteFixtures.sprite("redstone_dust_line0", 16, LINE, false);
        DirectQuadWriter writer = new DirectQuadWriter();
        try {
            writer.beginSection();
            stage(writer, dot, 0, 1, 0, 1, 1, DOT_TINT);
            // A rectangle whose third UV is pulled in from the sprite's corner, so its two
            // triangles map the texture differently.
            float[] positions = {X, Y, Z, X + 1, Y, Z, X + 1, Y, Z + 1, X, Y, Z + 1};
            float du = line.u1 - line.u0, dv = line.v1 - line.v0;
            float[] uvs = {line.u0, line.v0, line.u1, line.v0, line.u0 + 0.5f * du, line.v0 + dv, line.u0, line.v1};
            writer.stageQuad(positions, uvs, 0, 1, 0, LINE_TINT, line.id,
                    line.u0, line.v0, line.u1, line.v1, "cutout");
            writer.flushBlock(new TestTextures(dot, line), RedstoneEmission.POWERED);
            SectionMeshData mesh = writer.buildMeshData();
            try {
                assertEquals(1, mesh.surfaces().size());
                assertEquals(8, mesh.surfaces().getFirst().vertexCount());
            } finally {
                mesh.release();
            }
        } finally {
            writer.releaseBuffers();
        }
    }

    /** Stages an upward or downward quad over [x0, x1] by [z0, z1] of the block, UVs following x and z. */
    private static void stage(DirectQuadWriter writer, BlockTextureManager.SpriteEntry sprite,
                              float x0, float x1, float z0, float z1, float normalY, int color) {
        stage(writer, sprite, x0, x1, z0, z1, normalY, color, x0, x1, z0, z1, 0);
    }

    /**
     * Stages an upward or downward quad over [x0, x1] by [z0, z1] of the block, sampling
     * [s0, s1] by [r0, r1] of the sprite, as fractions, pulled toward their centre by
     * {@code inset} as vanilla's bake does.
     */
    private static void stage(DirectQuadWriter writer, BlockTextureManager.SpriteEntry sprite,
                              float x0, float x1, float z0, float z1, float normalY, int color,
                              float s0, float s1, float r0, float r1, float inset) {
        float[] positions = {X + x0, Y, Z + z0, X + x1, Y, Z + z0, X + x1, Y, Z + z1, X + x0, Y, Z + z1};
        float du = sprite.u1 - sprite.u0, dv = sprite.v1 - sprite.v0;
        float sc = (s0 + s1) / 2, rc = (r0 + r1) / 2;
        float[] u = {sprite.u0 + (s0 + inset * (sc - s0)) * du, sprite.u0 + (s1 + inset * (sc - s1)) * du};
        float[] v = {sprite.v0 + (r0 + inset * (rc - r0)) * dv, sprite.v0 + (r1 + inset * (rc - r1)) * dv};
        float[] uvs = {u[0], v[0], u[1], v[0], u[1], v[1], u[0], v[1]};
        writer.stageQuad(positions, uvs, 0, normalY, 0, color, sprite.id,
                sprite.u0, sprite.v0, sprite.u1, sprite.v1, "cutout");
    }

    /**
     * Rasterizes every drawn quad onto the block's 16x16 texel grid by its tint, failing if
     * two quads cover one texel or a quad's UVs sample a texel other than the one it covers.
     */
    private static int[][] drawnTints(SectionMeshData mesh, Map<Integer, BlockTextureManager.SpriteEntry> spritesByTint) {
        int[][] drawn = new int[16][16];
        for (var surface : mesh.surfaces()) {
            ByteBuffer vertices = surface.vertexBuffer();
            for (int quad = 0; quad < surface.vertexCount() / 4; quad++) {
                float minX = Float.POSITIVE_INFINITY, maxX = Float.NEGATIVE_INFINITY;
                float minZ = Float.POSITIVE_INFINITY, maxZ = Float.NEGATIVE_INFINITY;
                float u = 0, v = 0;
                for (int corner = 0; corner < 4; corner++) {
                    int offset = (quad * 4 + corner) * HardcodedVertex.STRIDE;
                    float x = vertices.getFloat(offset), z = vertices.getFloat(offset + 8);
                    if (x <= minX && z <= minZ) {
                        u = vertices.getFloat(offset + 24);
                        v = vertices.getFloat(offset + 28);
                    }
                    minX = Math.min(minX, x); maxX = Math.max(maxX, x);
                    minZ = Math.min(minZ, z); maxZ = Math.max(maxZ, z);
                }
                int tint = vertices.getInt(quad * 4 * HardcodedVertex.STRIDE + 32);
                var sprite = spritesByTint.get(tint);
                assertFalse(sprite == null, "unexpected tint " + Integer.toHexString(tint));
                int x0 = Math.round((minX - X) * 16), x1 = Math.round((maxX - X) * 16);
                int z0 = Math.round((minZ - Z) * 16), z1 = Math.round((maxZ - Z) * 16);
                assertEquals(x0, Math.round((u - sprite.u0) / (sprite.u1 - sprite.u0) * 16));
                assertEquals(z0, Math.round((v - sprite.v0) / (sprite.v1 - sprite.v0) * 16));
                for (int z = z0; z < z1; z++) {
                    for (int x = x0; x < x1; x++) {
                        assertEquals(0, drawn[z][x], "texel " + x + "," + z + " drawn twice");
                        drawn[z][x] = tint;
                    }
                }
            }
        }
        return drawn;
    }

    private static SectionMeshData.Surface surfaceOf(SectionMeshData mesh, int category) {
        return mesh.surfaces().stream().filter(s -> s.category() == category).findFirst()
                .orElseThrow(() -> new AssertionError("no surface in category " + category));
    }

    private static final class TestTextures extends BlockTextureManager {
        private final Map<Identifier, SpriteEntry> entries;
        private final RemixMaterial sssMaterial = new RemixMaterial(new MaterialInfo());

        TestTextures(SpriteEntry... sprites) {
            super(null);
            entries = new HashMap<>();
            for (SpriteEntry sprite : sprites) entries.put(sprite.id, sprite);
        }

        @Override
        public SpriteEntry getSpriteById(Identifier id) { return entries.get(id); }

        @Override
        public RemixMaterial getAtlasMaterialSSS(int layer) { return sssMaterial; }
    }
}
