/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.particle.rapids;

import net.fabricmc.api.EnvType;
import net.fabricmc.api.Environment;
import net.minecraft.client.particle.Particle;
import net.minecraft.client.particle.ParticleFactory;
import net.minecraft.client.particle.ParticleTextureSheet;
import net.minecraft.client.particle.SpriteBillboardParticle;
import net.minecraft.client.particle.SpriteProvider;
import net.minecraft.client.world.ClientWorld;
import net.minecraft.particle.SimpleParticleType;

@Environment(EnvType.CLIENT)
public class RapidMistParticle extends SpriteBillboardParticle {
    private RapidMistParticle(ClientWorld world, double x, double y, double z,
                              double velocityX, double velocityY, double velocityZ,
                              SpriteProvider spriteProvider) {
        super(world, x, y, z);
        this.setSprite(spriteProvider);
        this.setBoundingBoxSpacing(0.05f, 0.05f);
        this.scale *= this.random.nextFloat() * 0.42f + 0.32f;
        this.maxAge = 18 + this.random.nextInt(19);
        this.gravityStrength = -0.012f;
        this.velocityMultiplier = 0.82f;
        this.collidesWithWorld = false;
        this.velocityX = velocityX;
        this.velocityY = velocityY;
        this.velocityZ = velocityZ;
        this.setColor(0.62f, 0.68f, 0.72f);
        this.setAlpha(0.28f);
    }

    @Override
    public ParticleTextureSheet getType() {
        return ParticleTextureSheet.PARTICLE_SHEET_TRANSLUCENT;
    }

    @Override
    public void tick() {
        super.tick();
        if (!this.dead) {
            float life = (float) this.age / (float) this.maxAge;
            this.scale *= 1.002f;
            this.setAlpha(0.28f * (1.0f - life));
        }
    }

    @Environment(EnvType.CLIENT)
    public static final class Factory implements ParticleFactory<SimpleParticleType> {
        private final SpriteProvider spriteProvider;

        public Factory(SpriteProvider spriteProvider) {
            this.spriteProvider = spriteProvider;
        }

        @Override
        public Particle createParticle(SimpleParticleType type, ClientWorld world,
                                       double x, double y, double z,
                                       double velocityX, double velocityY, double velocityZ) {
            return new RapidMistParticle(world, x, y, z, velocityX, velocityY, velocityZ, spriteProvider);
        }
    }
}
