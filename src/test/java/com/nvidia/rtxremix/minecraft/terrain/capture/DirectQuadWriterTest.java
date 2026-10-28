/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.terrain.capture;

import com.nvidia.rtxremix.HardcodedVertex;
import com.nvidia.rtxremix.minecraft.terrain.ChunkManager;
import com.nvidia.rtxremix.minecraft.texture.BlockTextureManager;
import com.nvidia.rtxremix.minecraft.texture.RedstoneEmission;
import net.minecraft.util.Identifier;
import org.junit.jupiter.api.Test;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DirectQuadWriterTest {

    @Test
    void dustLineAndCoplanarOverlayStayTogetherInEveryPowerState() {
        DirectQuadWriter writer = new DirectQuadWriter();
        for (int power = 0; power <= 15; power++) {
            writer.beginSection();
            for (String texture : new String[] {"redstone_dust_line0", "redstone_dust_overlay"}) {
                Identifier sprite = Identifier.ofVanilla("block/" + texture);
                writer.stageQuad(FRONT_POSITIONS, FRONT_UVS, 0, 0, 1,
                        texture.endsWith("overlay") ? 0xFFFFFFFF : 0xFF660000,
                        sprite, 0, 0, 1, 1, "cutout",
                        BlockQuadEmitter.dustEmissionPower(power, sprite));
            }
            writer.flushBlock(null);
            SectionMeshData mesh = writer.buildMeshData();
            try {
                assertEquals(1, mesh.surfaces().size(), "Coplanar layers must not become separate surfaces");
                assertEquals(RedstoneEmission.bucketKey("cutout", power),
                        mesh.surfaces().get(0).bucketKey());
                assertEquals(8, mesh.surfaces().get(0).vertexCount());
                assertEquals(ChunkManager.CAT_CUTOUT, mesh.surfaces().get(0).category());
            } finally {
                mesh.release();
            }
        }
    }

    @Test
    void allPowerTransitionsPreserveVerticesButChangeTheMeshFingerprint() {
        DirectQuadWriter writer = new DirectQuadWriter();
        SectionMeshData powered = dustMesh(writer, 15);
        try {
            assertEquals("cutout", powered.surfaces().get(0).bucketKey());
            long previousHash = powered.contentHash();
            long previousCategoryHash = powered.categoryContentHash(ChunkManager.CAT_CUTOUT);
            for (int power = 0; power < 15; power++) {
                SectionMeshData mesh = dustMesh(writer, power);
                try {
                    assertEquals(RedstoneEmission.bucketKey("cutout", power), mesh.surfaces().get(0).bucketKey());
                    assertEquals(powered.surfaces().get(0).vertexBuffer(), mesh.surfaces().get(0).vertexBuffer());
                    assertNotEquals(previousHash, mesh.contentHash());
                    assertNotEquals(previousCategoryHash, mesh.categoryContentHash(ChunkManager.CAT_CUTOUT));
                    previousHash = mesh.contentHash();
                    previousCategoryHash = mesh.categoryContentHash(ChunkManager.CAT_CUTOUT);
                } finally {
                    mesh.release();
                }
            }
        } finally {
            powered.release();
        }
    }

    @Test
    void powerBucketsCoexistWithOrdinaryGeometryAndStillRemoveDuplicateBackfaces() {
        DirectQuadWriter writer = new DirectQuadWriter();
        writer.beginSection();
        for (int power = 0; power <= 15; power++) {
            writer.stageQuad(FRONT_POSITIONS, FRONT_UVS, 0, 0, 1, 0xFF660000,
                    CUTOUT_SPRITE, 0, 0, 1, 1, "cutout", power);
            writer.stageQuad(BACK_POSITIONS, DISTINCT_BACK_UVS, 0, 0, -1, 0xFF660000,
                    CUTOUT_SPRITE, 0, 0, 1, 1, "cutout", power);
            writer.flushBlock(null);
        }
        writer.stageQuad(FRONT_POSITIONS, FRONT_UVS, 0, 0, 1, 0xFF660000,
                CUTOUT_SPRITE, 0, 0, 1, 1, "cutout");
        writer.flushBlock(null);
        SectionMeshData mesh = writer.buildMeshData();
        try {
            assertEquals(16, mesh.surfaces().size());
            for (SectionMeshData.Surface surface : mesh.surfaces()) {
                assertEquals(surface.bucketKey().equals("cutout") ? 8 : 4, surface.vertexCount());
            }
        } finally {
            mesh.release();
        }
    }

    @Test
    void oppositeFacesWithDifferentEmissionDoNotCollapse() {
        DirectQuadWriter writer = new DirectQuadWriter();
        writer.beginSection();
        writer.stageQuad(FRONT_POSITIONS, FRONT_UVS, 0, 0, 1, 0xFF660000,
                CUTOUT_SPRITE, 0, 0, 1, 1, "cutout", 1);
        writer.stageQuad(BACK_POSITIONS, DISTINCT_BACK_UVS, 0, 0, -1, 0xFF660000,
                CUTOUT_SPRITE, 0, 0, 1, 1, "cutout", 2);
        writer.flushBlock(null);
        SectionMeshData mesh = writer.buildMeshData();
        try {
            assertEquals(2, mesh.surfaces().size());
            assertEquals(8, mesh.surfaces().stream().mapToInt(SectionMeshData.Surface::vertexCount).sum());
        } finally {
            mesh.release();
        }
    }

    private static SectionMeshData dustMesh(DirectQuadWriter writer, int emissionPower) {
        writer.beginSection();
        writer.stageQuad(FRONT_POSITIONS, FRONT_UVS, 0, 0, 1, 0xFF660000,
                CUTOUT_SPRITE, 0, 0, 1, 1, "cutout", emissionPower);
        writer.flushBlock(null);
        return writer.buildMeshData();
    }

    private static final Identifier CUTOUT_SPRITE = Identifier.ofVanilla("test/cutout");
    private static final float[] FRONT_POSITIONS = {
            0.0f, 0.0f, 0.0f,
            1.0f, 0.0f, 0.0f,
            1.0f, 1.0f, 0.0f,
            0.0f, 1.0f, 0.0f
    };
    private static final float[] BACK_POSITIONS = {
            0.0f, 1.0f, 0.0f,
            1.0f, 1.0f, 0.0f,
            1.0f, 0.0f, 0.0f,
            0.0f, 0.0f, 0.0f
    };
    private static final float[] FRONT_UVS = {
            0.0f, 0.0f,
            1.0f, 0.0f,
            1.0f, 1.0f,
            0.0f, 1.0f
    };
    private static final float[] DISTINCT_BACK_UVS = {
            0.25f, 0.75f,
            0.75f, 0.75f,
            0.75f, 0.25f,
            0.25f, 0.25f
    };

    @Test
    void precomputedHashMatchesSectionMeshDataHash() {
        DirectQuadWriter writer = new DirectQuadWriter();
        writer.beginSection();

        writeQuad(writer, 0.0f, 0xFF00AA55);
        writeQuad(writer, 1.0f, 0xFF00AA55);

        SectionMeshData meshData = writer.buildMeshData();
        SectionMeshData recomputedHashMeshData = new SectionMeshData(meshData.surfaces());

        assertEquals(recomputedHashMeshData.contentHash(), meshData.contentHash());
    }

    @Test
    void resetClearsPrecomputedHashState() {
        DirectQuadWriter writer = new DirectQuadWriter();

        writer.beginSection();
        writeQuad(writer, 0.0f, 0xFF00AA55);
        int firstHash = writer.buildMeshData().contentHash();

        writer.beginSection();
        writeQuad(writer, 0.0f, 0xFF00AA55);
        int repeatedHash = writer.buildMeshData().contentHash();

        writer.beginSection();
        writeQuad(writer, 0.0f, 0xFF00AA56);
        int changedHash = writer.buildMeshData().contentHash();

        assertEquals(firstHash, repeatedHash);
        assertNotEquals(firstHash, changedHash);
    }

    @Test
    void beginSectionKeepsVerticesSectionLocalAndMarksCanonicalIndices() {
        DirectQuadWriter writer = new DirectQuadWriter();
        writer.beginSection(16, 32, 48);

        writeQuad(writer, 0.0f, 0xFF00AA55);

        SectionMeshData.Surface surface = writer.buildMeshData().surfaces().get(0);
        ByteBuffer vertices = surface.vertexBuffer().duplicate().order(ByteOrder.LITTLE_ENDIAN);

        assertTrue(surface.canonicalQuadIndices());
        assertEquals(0.0f, vertices.getFloat(0));
        assertEquals(0.0f, vertices.getFloat(4));
        assertEquals(0.0f, vertices.getFloat(8));
        assertEquals(1.0f, vertices.getFloat(2 * 64));
        assertEquals(1.0f, vertices.getFloat(2 * 64 + 4));
        assertEquals(0.0f, vertices.getFloat(2 * 64 + 8));
    }

    @Test
    void builtSurfacesExposeExactlyTheirPayload() {
        // Surface buffers come from DirectBufferPool, which rounds up to a size class,
        // so a buffer is larger than its payload; the hash and the upload both read
        // position..limit and depend on that window being exactly the vertices.
        DirectQuadWriter writer = new DirectQuadWriter();
        writer.beginSection();
        for (int i = 0; i < 5; i++) {
            writeQuad(writer, i, 0xFF00AA55);
        }

        SectionMeshData meshData = writer.buildMeshData();
        try {
            assertEquals(1, meshData.surfaces().size());
            SectionMeshData.Surface surface = meshData.surfaces().get(0);
            ByteBuffer vertices = surface.vertexBuffer();
            assertTrue(vertices.isDirect());
            assertEquals(0, vertices.position());
            assertEquals(20, surface.vertexCount());
            assertEquals(20 * HardcodedVertex.STRIDE, vertices.limit());
            assertTrue(vertices.capacity() >= vertices.limit());
        } finally {
            meshData.release();
        }
    }

    @Test
    void oppositeCutoutFacesCollapseToFirstPlaneAndUvs() {
        DirectQuadWriter writer = new DirectQuadWriter();
        writer.beginSection();

        stageCutoutQuad(writer, FRONT_POSITIONS, FRONT_UVS, 1.0f, CUTOUT_SPRITE, 0xFFFFFFFF);
        stageCutoutQuad(writer, BACK_POSITIONS, DISTINCT_BACK_UVS, -1.0f, CUTOUT_SPRITE, 0xFFFFFFFF);
        writer.flushBlock(null);

        SectionMeshData.Surface surface = writer.buildMeshData().surfaces().get(0);
        ByteBuffer vertices = surface.vertexBuffer().duplicate().order(ByteOrder.LITTLE_ENDIAN);

        assertEquals(4, surface.vertexCount());
        assertEquals(6, surface.indexCount());
        for (int vertex = 0; vertex < 4; vertex++) {
            assertEquals(FRONT_UVS[vertex * 2], vertices.getFloat(vertex * 64 + 24));
            assertEquals(FRONT_UVS[vertex * 2 + 1], vertices.getFloat(vertex * 64 + 28));
        }
    }

    @Test
    void sameFacingAndDifferentMaterialCutoutLayersRemainSeparate() {
        DirectQuadWriter writer = new DirectQuadWriter();
        writer.beginSection();

        stageCutoutQuad(writer, FRONT_POSITIONS, FRONT_UVS, 1.0f, CUTOUT_SPRITE, 0xFFFFFFFF);
        stageCutoutQuad(writer, BACK_POSITIONS, DISTINCT_BACK_UVS, 1.0f, CUTOUT_SPRITE, 0xFFFFFFFF);
        stageCutoutQuad(writer, BACK_POSITIONS, DISTINCT_BACK_UVS, -1.0f,
                Identifier.ofVanilla("test/cutout_overlay"), 0xFFFFFFFF);
        writer.flushBlock(null);

        assertEquals(12, totalVertices(writer.buildMeshData()));
    }

    @Test
    void displacedAndNonCutoutBackfacesRemainSeparate() {
        DirectQuadWriter writer = new DirectQuadWriter();
        writer.beginSection();

        float[] displacedBack = BACK_POSITIONS.clone();
        for (int vertex = 0; vertex < 4; vertex++) {
            displacedBack[vertex * 3 + 2] = 0.001f;
        }
        stageCutoutQuad(writer, FRONT_POSITIONS, FRONT_UVS, 1.0f, CUTOUT_SPRITE, 0xFFFFFFFF);
        stageCutoutQuad(writer, displacedBack, DISTINCT_BACK_UVS, -1.0f, CUTOUT_SPRITE, 0xFFFFFFFF);
        writer.flushBlock(null);

        stageQuad(writer, FRONT_POSITIONS, FRONT_UVS, 1.0f, CUTOUT_SPRITE, 0xFFFFFFFF, "solid");
        stageQuad(writer, BACK_POSITIONS, DISTINCT_BACK_UVS, -1.0f, CUTOUT_SPRITE, 0xFFFFFFFF, "solid");
        writer.flushBlock(null);

        assertEquals(16, totalVertices(writer.buildMeshData()));
    }

    @Test
    void clearGlassBlendsInItsOwnBucket() {
        // Clear glass refracts: it must blend like vanilla's translucent
        // layer, yet never share a surface with it, because the two take different
        // materials (constant transmission with a diffuse frame vs. tinted transmittance).
        DirectQuadWriter writer = new DirectQuadWriter();
        writer.beginSection();
        stageQuad(writer, FRONT_POSITIONS, FRONT_UVS, 1.0f, CUTOUT_SPRITE, 0xFFFFFFFF, "glass");
        writer.flushBlock(null);
        stageQuad(writer, BACK_POSITIONS, DISTINCT_BACK_UVS, -1.0f, CUTOUT_SPRITE, 0xFFFFFFFF, "translucent");
        writer.flushBlock(null);
        stageQuad(writer, FRONT_POSITIONS, FRONT_UVS, 1.0f, CUTOUT_SPRITE, 0xFFFFFFFF, "cutout");
        writer.flushBlock(null);

        SectionMeshData meshData = writer.buildMeshData();
        SectionMeshData.Surface glass = surface(meshData, "glass");
        SectionMeshData.Surface translucent = surface(meshData, "translucent");
        assertEquals(ChunkManager.CAT_TRANSLUCENT, glass.category());
        assertEquals(ChunkManager.CAT_TRANSLUCENT, translucent.category());
        assertEquals(4, glass.vertexCount());
        assertEquals(ChunkManager.CAT_CUTOUT, surface(meshData, "cutout").category());

        assertNotEquals(BlockTextureManager.layerType("translucent"), BlockTextureManager.layerType("glass"),
                "glass needs its own atlas material slot");
        assertTrue(BlockTextureManager.layerType("glass") < BlockTextureManager.LAYER_COUNT);
    }

    private static SectionMeshData.Surface surface(SectionMeshData meshData, String bucketKey) {
        return meshData.surfaces().stream()
                .filter(s -> bucketKey.equals(s.bucketKey()))
                .findFirst()
                .orElseThrow(() -> new AssertionError("no surface for bucket " + bucketKey));
    }

    private static int totalVertices(SectionMeshData meshData) {
        return meshData.surfaces().stream().mapToInt(SectionMeshData.Surface::vertexCount).sum();
    }

    private static void stageCutoutQuad(DirectQuadWriter writer, float[] positions, float[] uvs,
                                        float normalZ, Identifier sprite, int color) {
        stageQuad(writer, positions, uvs, normalZ, sprite, color, "cutout");
    }

    private static void stageQuad(DirectQuadWriter writer, float[] positions, float[] uvs,
                                  float normalZ, Identifier sprite, int color, String layer) {
        writer.stageQuad(positions, uvs,
                0.0f, 0.0f, normalZ,
                color, sprite,
                0.0f, 0.0f, 1.0f, 1.0f,
                layer);
    }

    private static void writeQuad(DirectQuadWriter writer, float xOffset, int color) {
        float[] positions = {
                xOffset, 0.0f, 0.0f,
                xOffset + 1.0f, 0.0f, 0.0f,
                xOffset + 1.0f, 1.0f, 0.0f,
                xOffset, 1.0f, 0.0f
        };
        float[] uvs = {
                0.0f, 0.0f,
                1.0f, 0.0f,
                1.0f, 1.0f,
                0.0f, 1.0f
        };
        writer.writeFluidQuad(positions, uvs,
                0.0f, 0.0f, 1.0f,
                color, null,
                0.0f, 0.0f, 1.0f, 1.0f,
                "solid", null);
    }
}
