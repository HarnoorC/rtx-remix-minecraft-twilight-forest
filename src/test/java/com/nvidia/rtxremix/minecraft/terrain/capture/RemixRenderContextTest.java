/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.terrain.capture;

import net.fabricmc.fabric.api.renderer.v1.mesh.Mesh;
import net.fabricmc.fabric.api.renderer.v1.mesh.QuadEmitter;
import net.fabricmc.fabric.impl.client.indigo.renderer.IndigoRenderer;
import net.fabricmc.fabric.impl.client.indigo.renderer.mesh.MeshBuilderImpl;
import net.minecraft.Bootstrap;
import net.minecraft.SharedConstants;
import net.minecraft.util.math.BlockPos;
import net.minecraft.util.math.Direction;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SuppressWarnings("deprecation")
class RemixRenderContextTest {

    @BeforeAll
    static void bootstrapMinecraft() {
        SharedConstants.createGameVersion();
        Bootstrap.initialize();
    }

    @Test
    void consumesIndigoMeshThroughCaptureEmitterWithVertexDataIntact() {
        MeshBuilderImpl builder = new MeshBuilderImpl();
        QuadEmitter emitter = builder.getEmitter();
        emitter.square(Direction.UP, 0, 0, 1, 1, 0);
        for (int vertex = 0; vertex < 4; vertex++) {
            emitter.color(vertex, 0xFF123456 + vertex);
            emitter.uv(vertex, vertex * 0.125f, vertex * 0.25f);
            emitter.lightmap(vertex, 0x00F000A0 + vertex);
            emitter.normal(vertex, 0, 1, 0);
        }
        emitter.colorIndex(3).tag(42).emit();
        Mesh mesh = builder.build();
        RemixRenderContext context = context();
        int[] visits = {0};
        context.pushTransform(quad -> {
            visits[0]++;
            assertSame(IndigoRenderer.MATERIAL_STANDARD, quad.material());
            assertEquals(Direction.UP, quad.cullFace());
            assertEquals(Direction.UP, quad.nominalFace());
            assertEquals(3, quad.colorIndex());
            assertEquals(42, quad.tag());
            for (int vertex = 0; vertex < 4; vertex++) {
                assertEquals(0xFF123456 + vertex, quad.color(vertex));
                assertEquals(0x00F000A0 + vertex, quad.lightmap(vertex));
                assertTrue(quad.hasNormal(vertex));
                assertEquals(1.0f, quad.normalY(vertex));
            }
            return true;
        });

        context.meshConsumer().accept(mesh);

        assertEquals(1, visits[0]);
        assertEquals(1, context.harvest().size());
        SectionBlockData.BlockQuad captured = context.harvest().getFirst();
        assertArrayEquals(new float[]{0, 1, 0, 0, 1, 1, 1, 1, 1, 1, 1, 0},
                captured.positions());
        assertArrayEquals(new float[]{0, 0, 0.125f, 0.25f, 0.25f, 0.5f, 0.375f, 0.75f},
                captured.uvs());
        assertEquals(0xFF123456, captured.color());
        assertEquals(1.0f, captured.ny());
    }

    @Test
    void meshQuadsFollowTransformStackFilteringAndFaceCulling() {
        MeshBuilderImpl builder = new MeshBuilderImpl();
        QuadEmitter emitter = builder.getEmitter();
        for (int tag = 0; tag < 3; tag++) {
            emitter.square(Direction.UP, 0, 0, 1, 1, 0).tag(tag).emit();
        }
        Mesh mesh = builder.build();
        RemixRenderContext context = context();
        context.prepare(null, null, BlockPos.ORIGIN, face -> face == Direction.NORTH);
        context.pushTransform(quad -> {
            // Transforms run in reverse push order: tag 0 has already been rejected.
            assertTrue(quad.tag() > 0);
            if (quad.tag() == 1) {
                quad.cullFace(Direction.NORTH);
            }
            for (int vertex = 0; vertex < 4; vertex++) {
                quad.pos(vertex, quad.x(vertex) + 2, quad.y(vertex), quad.z(vertex));
            }
            return true;
        });
        context.pushTransform(quad -> quad.tag() != 0);

        context.meshConsumer().accept(mesh);

        assertEquals(1, context.harvest().size());
        assertEquals(2.0f, context.harvest().getFirst().positions()[0]);
        context.popTransform();
        context.popTransform();
        assertFalse(context.hasTransform());
    }

    @Test
    void repeatedMeshConsumptionClearsStaleEmitterStateAndKeepsEarlierCaptures() {
        MeshBuilderImpl builder = new MeshBuilderImpl();
        builder.getEmitter().square(Direction.UP, 0, 0, 1, 1, 0).emit();
        Mesh mesh = builder.build();
        RemixRenderContext context = context();
        context.getEmitter().normal(0, 1, 0, 0).tag(99);
        context.pushTransform(quad -> {
            assertFalse(quad.hasNormal(0));
            assertEquals(0, quad.tag());
            return true;
        });

        context.meshConsumer().accept(mesh);
        context.meshConsumer().accept(mesh);

        assertEquals(2, context.harvest().size());
        context.prepare(null, null, BlockPos.ORIGIN, null);
        context.meshConsumer().accept(mesh);
        assertEquals(1, context.harvest().size());
        assertFalse(context.hasTransform());
    }

    private static RemixRenderContext context() {
        RemixRenderContext context = new RemixRenderContext();
        context.prepare(null, null, BlockPos.ORIGIN, null);
        return context;
    }
}
