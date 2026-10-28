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

class DustLayerGroupingTest {
    private static final float[] POSITIONS = {0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0};
    private static final int TINT = 0xFF660000;
    private final BlockTextureManager previousTextures = BlockTextureManager.get();

    @AfterEach
    void restoreTextureManager() throws Exception {
        Field instance = BlockTextureManager.class.getDeclaredField("INSTANCE");
        instance.setAccessible(true);
        instance.set(null, previousTextures);
    }

    @Test
    void mixedSpriteMetadataKeepsDustInOneOrderedSurfaceAcrossAllPowerStates() {
        DirectQuadWriter writer = new DirectQuadWriter();
        try {
            for (String dustName : new String[] {"redstone_dust_dot", "redstone_dust_line0", "redstone_dust_line1"}) {
                for (int metadata = 0; metadata < 16; metadata++) {
                    boolean dustTransparent = (metadata & 1) != 0;
                    boolean overlayTransparent = (metadata & 2) != 0;
                    boolean dustSss = (metadata & 4) != 0;
                    boolean overlaySss = (metadata & 8) != 0;
                    var dust = TerrainSpriteFixtures.sprite(dustName, 0, dustTransparent, dustSss);
                    var overlay = TerrainSpriteFixtures.sprite("redstone_dust_overlay", 16, overlayTransparent, overlaySss);
                    assertEquals(dustTransparent, dust.hasTransparency);
                    assertEquals(overlayTransparent, overlay.hasTransparency);
                    BlockTextureManager textures = new TestTextures(dust, overlay);
                    for (String layer : new String[] {"cutout", "cutout_mipped"}) {
                        for (int power = 0; power <= 15; power++) {
                            writer.beginSection();
                            stage(writer, dust, POSITIONS, layer, power, TINT);
                            stage(writer, overlay, POSITIONS, layer, power, 0xFFFFFFFF);
                            writer.flushBlock(textures);
                            SectionMeshData mesh = writer.buildMeshData();
                            try {
                                assertEquals(1, mesh.surfaces().size(), dustName + ": metadata=" + metadata
                                        + ", layer=" + layer + ", power=" + power);
                                var surface = mesh.surfaces().getFirst();
                                assertEquals(dustTransparent || overlayTransparent
                                        ? ChunkManager.CAT_CUTOUT : ChunkManager.CAT_SOLID, surface.category());
                                String base = dustSss || overlaySss ? layer + "_sss"
                                        : dustTransparent || overlayTransparent ? layer : "solid";
                                assertEquals(RedstoneEmission.bucketKey(base, power), surface.bucketKey());
                                assertEquals(8, surface.vertexCount());
                                assertVertex(surface.vertexBuffer(), 0, dust, TINT);
                                assertVertex(surface.vertexBuffer(), 4, overlay, 0xFFFFFFFF);
                            } finally {
                                mesh.release();
                            }
                        }
                    }
                }
            }
        } finally {
            writer.releaseBuffers();
        }
    }

    @Test
    void disconnectedDustFacesRetainTheirOwnClassificationAndSss() {
        var dust = TerrainSpriteFixtures.sprite("redstone_dust_line0", 0, false, true);
        var overlay = TerrainSpriteFixtures.sprite("redstone_dust_overlay", 16, true, false);
        DirectQuadWriter writer = new DirectQuadWriter();
        try {
            for (float[] separateFace : new float[][] {
                    {2, 0, 0, 3, 0, 0, 3, 1, 0, 2, 1, 0},
                    {0, 0, 1, 1, 0, 1, 1, 1, 1, 0, 1, 1}}) {
                writer.beginSection();
                stage(writer, dust, POSITIONS, "cutout", 0, TINT);
                stage(writer, overlay, separateFace, "cutout", 0, 0xFFFFFFFF);
                writer.flushBlock(new TestTextures(dust, overlay));
                SectionMeshData mesh = writer.buildMeshData();
                try {
                    assertEquals(2, mesh.surfaces().size());
                    assertSurface(mesh, "cutout_sss_redstone_0", ChunkManager.CAT_SOLID, 4);
                    assertSurface(mesh, "cutout_redstone_0", ChunkManager.CAT_CUTOUT, 4);
                } finally {
                    mesh.release();
                }
            }
        } finally {
            writer.releaseBuffers();
        }
    }

    @Test
    void connectedOverlapsShareOneSurfaceInOriginalPaintOrder() {
        var first = TerrainSpriteFixtures.sprite("redstone_dust_line0", 0, false, false);
        var last = TerrainSpriteFixtures.sprite("redstone_dust_line1", 16, false, true);
        var bridge = TerrainSpriteFixtures.sprite("redstone_dust_overlay", 32, true, false);
        DirectQuadWriter writer = new DirectQuadWriter();
        try {
            writer.beginSection();
            stage(writer, first, POSITIONS, "cutout_mipped", 8, TINT);
            stage(writer, last, new float[] {1.5f, 0, 0, 2.5f, 0, 0, 2.5f, 1, 0, 1.5f, 1, 0},
                    "cutout_mipped", 8, TINT);
            stage(writer, bridge, new float[] {0.75f, 0, 0, 1.75f, 0, 0, 1.75f, 1, 0, 0.75f, 1, 0},
                    "cutout_mipped", 8, 0xFFFFFFFF);
            writer.flushBlock(new TestTextures(first, last, bridge));
            SectionMeshData mesh = writer.buildMeshData();
            try {
                assertEquals(1, mesh.surfaces().size());
                assertSurface(mesh, "cutout_mipped_sss_redstone_8", ChunkManager.CAT_CUTOUT, 12);
                ByteBuffer vertices = mesh.surfaces().getFirst().vertexBuffer();
                assertVertex(vertices, 0, first, TINT);
                assertVertex(vertices, 4, last, TINT);
                assertVertex(vertices, 8, bridge, 0xFFFFFFFF);
            } finally {
                mesh.release();
            }
        } finally {
            writer.releaseBuffers();
        }
    }

    @Test
    void groupingPreservesOtherSpritesAndDoesNotLeakIntoTheNextBlock() {
        var dust = TerrainSpriteFixtures.sprite("redstone_dust_line0", 0, false, false);
        var overlay = TerrainSpriteFixtures.sprite("redstone_dust_overlay", 16, true, true);
        var stone = TerrainSpriteFixtures.sprite("stone", 32, false, false);
        DirectQuadWriter writer = new DirectQuadWriter();
        TestTextures textures = new TestTextures(dust, overlay, stone);
        try {
            writer.beginSection();
            stage(writer, dust, POSITIONS, "cutout", 1, TINT);
            stage(writer, overlay, POSITIONS, "cutout", 1, 0xFFFFFFFF);
            stage(writer, stone, POSITIONS, "solid", 1, 0xFFFFFFFF);
            writer.flushBlock(textures);
            // The same sprites on an unrelated block must retain ordinary capture behavior.
            stage(writer, dust, POSITIONS, "cutout", -1, TINT);
            stage(writer, overlay, POSITIONS, "cutout", -1, 0xFFFFFFFF);
            writer.flushBlock(textures);
            SectionMeshData mesh = writer.buildMeshData();
            try {
                assertSurface(mesh, "solid", ChunkManager.CAT_SOLID, 8);
                assertSurface(mesh, "cutout_sss", ChunkManager.CAT_OVERLAY, 4);
                assertSurface(mesh, "cutout_sss_redstone_1", ChunkManager.CAT_OVERLAY, 8);
                assertEquals(3, mesh.surfaces().size());
            } finally {
                mesh.release();
            }
        } finally {
            writer.releaseBuffers();
        }
    }

    @Test
    void groupingKeepsDuplicateBackfaceRemovalWithMixedMetadata() {
        var dust = TerrainSpriteFixtures.sprite("redstone_dust_line0", 0, false, true);
        var overlay = TerrainSpriteFixtures.sprite("redstone_dust_overlay", 16, true, false);
        DirectQuadWriter writer = new DirectQuadWriter();
        try {
            for (int power = 0; power <= 15; power++) {
                writer.beginSection();
                for (var sprite : new BlockTextureManager.SpriteEntry[] {dust, overlay}) {
                    stage(writer, sprite, POSITIONS, "cutout", power, TINT);
                    writer.stageQuad(new float[] {0, 1, 0, 1, 1, 0, 1, 0, 0, 0, 0, 0},
                            new float[] {sprite.u0, sprite.v1, sprite.u1, sprite.v1,
                                    sprite.u1, sprite.v0, sprite.u0, sprite.v0},
                            0, 0, -1, TINT, sprite.id, sprite.u0, sprite.v0, sprite.u1, sprite.v1,
                            "cutout", power);
                }
                writer.flushBlock(new TestTextures(dust, overlay));
                SectionMeshData mesh = writer.buildMeshData();
                try {
                    assertEquals(1, mesh.surfaces().size());
                    assertSurface(mesh, RedstoneEmission.bucketKey("cutout_sss", power), ChunkManager.CAT_CUTOUT, 8);
                } finally {
                    mesh.release();
                }
            }
        } finally {
            writer.releaseBuffers();
        }
    }

    private static void assertSurface(SectionMeshData mesh, String key, int category, int vertexCount) {
        var surface = mesh.surfaces().stream()
                .filter(candidate -> candidate.bucketKey().equals(key) && candidate.category() == category)
                .findFirst().orElseThrow();
        assertEquals(vertexCount, surface.vertexCount());
    }

    private static void stage(DirectQuadWriter writer, BlockTextureManager.SpriteEntry sprite,
                              float[] positions, String layer, int power, int color) {
        float[] uv = {sprite.u0, sprite.v0, sprite.u1, sprite.v0,
                sprite.u1, sprite.v1, sprite.u0, sprite.v1};
        writer.stageQuad(positions, uv, 0, 0, 1, color, sprite.id,
                sprite.u0, sprite.v0, sprite.u1, sprite.v1, layer,
                BlockQuadEmitter.dustEmissionPower(power, sprite.id));
    }

    private static void assertVertex(ByteBuffer vertices, int vertex,
                                      BlockTextureManager.SpriteEntry sprite, int color) {
        int offset = vertex * HardcodedVertex.STRIDE;
        assertEquals(sprite.u0, vertices.getFloat(offset + 24));
        assertEquals(sprite.v0, vertices.getFloat(offset + 28));
        assertEquals(color, vertices.getInt(offset + 32));
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
