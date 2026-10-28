/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.texture;

import com.nvidia.rtxremix.MaterialInfo;
import com.nvidia.rtxremix.minecraft.asset.RemixTexture;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.concurrent.CompletableFuture;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

import org.junit.jupiter.api.Test;

class BlockTextureManagerEmissionTest {

    @Test
    void workerMaterialLookupNeverCreatesResources() {
        BlockTextureManager manager = new BlockTextureManager(null);
        CompletableFuture.runAsync(() -> {
            for (int layer = 0; layer < BlockTextureManager.LAYER_COUNT; layer++) {
                for (int power = 0; power < 15; power++) {
                    assertNull(manager.getRedstoneAtlasMaterial(layer, false, power));
                    assertNull(manager.getRedstoneAtlasMaterial(layer, true, power));
                }
            }
        }).join();
    }

    @Test
    void dustPowerScalesOnlyEmissionAndSharesTheAnimatedAtlasTextures() throws Exception {
        BlockTextureManager manager = new BlockTextureManager(null);
        String[] textures = {"atlasAlbedo", "atlasNormalTex", "atlasHeightTex", "atlasRoughnessTex",
                "atlasMetallicTex", "atlasEmissive", "atlasSssTex", "atlasSssAlbedoTex"};
        for (int i = 0; i < textures.length; i++) {
            Field field = BlockTextureManager.class.getDeclaredField(textures[i]);
            field.setAccessible(true);
            field.set(manager, new TestTexture(i + 1));
        }
        Method build = BlockTextureManager.class.getDeclaredMethod(
                "redstoneAtlasMaterialInfo", int.class, boolean.class, int.class);
        build.setAccessible(true);
        manager.setTerrainEmissionMultiplier(0.25f);
        manager.commitTerrainEmissionMultiplier();
        for (int layer = 0; layer < BlockTextureManager.LAYER_COUNT; layer++) {
            for (boolean sss : new boolean[] {false, true}) {
                for (int power = 0; power <= 15; power++) {
                    MaterialInfo info = (MaterialInfo) build.invoke(manager, layer, sss, power);
                    assertEquals(1L, info.albedoTexture);
                    assertEquals(2L, info.normalTexture);
                    assertEquals(0, info.filterMode);
                    assertEquals(power == 0 ? 0L : 6L, info.emissiveTexture);
                    assertEquals(25f * power / 15, info.emissiveIntensity, 0.00001f);
                    if (layer == BlockTextureManager.L_TRANS || layer == BlockTextureManager.L_GLASS) {
                        assertNull(info.opaqueExt);
                        assertEquals(layer == BlockTextureManager.L_GLASS ? 1 : 0, info.translucentExt.useDiffuseLayer);
                    } else {
                        assertNull(info.translucentExt);
                        assertEquals(3L, info.opaqueExt.heightTexture);
                        assertEquals(4L, info.opaqueExt.roughnessTexture);
                        assertEquals(5L, info.opaqueExt.metallicTexture);
                        assertEquals(1, info.opaqueExt.useDrawCallAlphaState);
                        if (sss) assertNotNull(info.opaqueExt.subsurfaceExt);
                        else assertNull(info.opaqueExt.subsurfaceExt);
                    }
                }
            }
        }
    }

    private static final class TestTexture extends RemixTexture {
        TestTexture(long textureHandle) {
            super(1, 1, 0, 0, null);
            handle = textureHandle;
        }
    }

    @Test
    void terrainEmissionMultiplierScalesTheAuthoredMaterialIntensity() {
        BlockTextureManager manager = new BlockTextureManager(null);

        assertEquals(1.0f, manager.getTerrainEmissionMultiplier());
        assertEquals(100.0f, manager.terrainEmissionIntensity());

        manager.setTerrainEmissionMultiplier(0.25f);
        assertEquals(0.25f, manager.getTerrainEmissionMultiplier());
        assertEquals(100.0f, manager.terrainEmissionIntensity());
        assertTrue(manager.commitTerrainEmissionMultiplier());
        assertEquals(25.0f, manager.terrainEmissionIntensity());
        assertFalse(manager.commitTerrainEmissionMultiplier());

        manager.setTerrainEmissionMultiplier(0.0f);
        assertEquals(25.0f, manager.terrainEmissionIntensity());
        assertTrue(manager.commitTerrainEmissionMultiplier());
        assertEquals(0.0f, manager.terrainEmissionIntensity());
    }

    @Test
    void terrainEmissionMultiplierStaysWithinItsSettingsRange() {
        BlockTextureManager manager = new BlockTextureManager(null);

        manager.setTerrainEmissionMultiplier(-1.0f);
        assertEquals(0.0f, manager.getTerrainEmissionMultiplier());

        manager.setTerrainEmissionMultiplier(100.0f);
        assertEquals(
                BlockTextureManager.MAX_TERRAIN_EMISSION_MULTIPLIER,
                manager.getTerrainEmissionMultiplier());
    }

    @Test
    void lensMaterialScalesItsEmissionIndependently() {
        assertEquals(0.0f, BlockTextureManager.scaledEmissionIntensity(100.0f, 0.0f));
        assertEquals(100.0f, BlockTextureManager.scaledEmissionIntensity(100.0f, 1.0f));
        assertEquals(
                100_000.0f,
                BlockTextureManager.scaledEmissionIntensity(100.0f, 1000.0f));
        assertEquals(0.0f, BlockTextureManager.scaledEmissionIntensity(100.0f, -1.0f));
    }
}
