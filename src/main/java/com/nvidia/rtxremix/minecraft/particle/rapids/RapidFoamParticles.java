/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.particle.rapids;

import com.nvidia.rtxremix.minecraft.RtxRemixCommonMod;
import net.fabricmc.fabric.api.client.particle.v1.ParticleFactoryRegistry;
import net.fabricmc.fabric.api.particle.v1.FabricParticleTypes;
import net.minecraft.particle.SimpleParticleType;
import net.minecraft.registry.Registries;
import net.minecraft.registry.Registry;
import net.minecraft.util.Identifier;

public final class RapidFoamParticles {
    public static final SimpleParticleType RAPID_FOAM = FabricParticleTypes.simple(false);
    public static final SimpleParticleType RAPID_FOAM_DOT = FabricParticleTypes.simple(false);
    public static final SimpleParticleType RAPID_MIST = FabricParticleTypes.simple(false);

    private RapidFoamParticles() {}

    public static void register() {
        Registry.register(Registries.PARTICLE_TYPE, Identifier.of(RtxRemixCommonMod.MOD_ID, "rapid_foam"), RAPID_FOAM);
        Registry.register(Registries.PARTICLE_TYPE, Identifier.of(RtxRemixCommonMod.MOD_ID, "rapid_foam_dot"), RAPID_FOAM_DOT);
        Registry.register(Registries.PARTICLE_TYPE, Identifier.of(RtxRemixCommonMod.MOD_ID, "rapid_mist"), RAPID_MIST);
        ParticleFactoryRegistry.getInstance().register(RAPID_FOAM, RapidFoamParticle.Factory::new);
        ParticleFactoryRegistry.getInstance().register(RAPID_FOAM_DOT, RapidFoamDotParticle.Factory::new);
        ParticleFactoryRegistry.getInstance().register(RAPID_MIST, RapidMistParticle.Factory::new);
    }
}
