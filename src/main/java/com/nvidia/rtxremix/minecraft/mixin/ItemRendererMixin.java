/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.mixin;

import com.nvidia.rtxremix.minecraft.entity.EntityRenderContext;
import com.nvidia.rtxremix.minecraft.entity.HeldItemEffectsRenderer;
import com.nvidia.rtxremix.minecraft.terrain.capture.BlockQuadEmitter;
import com.nvidia.rtxremix.minecraft.texture.BlockTextureManager;
import net.minecraft.client.render.VertexConsumerProvider;
import net.minecraft.client.render.item.ItemRenderer;
import net.minecraft.client.render.model.BakedModel;
import net.minecraft.client.render.model.json.ModelTransformationMode;
import net.minecraft.client.util.math.MatrixStack;
import net.minecraft.item.BlockItem;
import net.minecraft.item.ItemStack;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * Records the terrain layer of the block item being rendered, and adds the lit
 * element of a hand-held item.
 *
 * <p>Minecraft routes ordinary opaque items through its translucent item layer,
 * and clear glass through its cutout one, so the render layer alone cannot tell
 * a pane of stained glass from an apple, or clear glass from a torch. The
 * {@code ItemStack} can, and this is the last point at which it is in scope
 * before the geometry reaches capture.
 */
@Mixin(ItemRenderer.class)
public class ItemRendererMixin {

    @Inject(
        method = "renderItem(Lnet/minecraft/item/ItemStack;Lnet/minecraft/client/render/model/json/ModelTransformationMode;ZLnet/minecraft/client/util/math/MatrixStack;Lnet/minecraft/client/render/VertexConsumerProvider;IILnet/minecraft/client/render/model/BakedModel;)V",
        at = @At("HEAD")
    )
    private void rtxremix$beginItem(ItemStack stack, ModelTransformationMode mode, boolean leftHanded,
                                    MatrixStack matrices, VertexConsumerProvider vertexConsumers,
                                    int light, int overlay, BakedModel model, CallbackInfo ci) {
        EntityRenderContext context = EntityRenderContext.get();
        if (context.isRemixPass()) {
            context.setBlockItemLayer(rtxremix$blockLayer(stack));
        }
    }

    /**
     * Adds the item's lit element right after its baked model, while the matrix
     * stack still holds the item's block-space pose. Running here rather than in
     * a hand-specific renderer covers every hand-held render with one hook.
     */
    @Inject(
        method = "renderItem(Lnet/minecraft/item/ItemStack;Lnet/minecraft/client/render/model/json/ModelTransformationMode;ZLnet/minecraft/client/util/math/MatrixStack;Lnet/minecraft/client/render/VertexConsumerProvider;IILnet/minecraft/client/render/model/BakedModel;)V",
        at = @At(
            value = "INVOKE",
            target = "Lnet/minecraft/client/render/item/ItemRenderer;renderBakedItemModel(Lnet/minecraft/client/render/model/BakedModel;Lnet/minecraft/item/ItemStack;IILnet/minecraft/client/util/math/MatrixStack;Lnet/minecraft/client/render/VertexConsumer;)V",
            shift = At.Shift.AFTER
        )
    )
    private void rtxremix$renderHeldFlame(ItemStack stack, ModelTransformationMode mode, boolean leftHanded,
                                          MatrixStack matrices, VertexConsumerProvider vertexConsumers,
                                          int light, int overlay, BakedModel model, CallbackInfo ci) {
        HeldItemEffectsRenderer.render(stack, mode, matrices, vertexConsumers, model);
    }

    @Inject(
        method = "renderItem(Lnet/minecraft/item/ItemStack;Lnet/minecraft/client/render/model/json/ModelTransformationMode;ZLnet/minecraft/client/util/math/MatrixStack;Lnet/minecraft/client/render/VertexConsumerProvider;IILnet/minecraft/client/render/model/BakedModel;)V",
        at = @At("RETURN")
    )
    private void rtxremix$endItem(ItemStack stack, ModelTransformationMode mode, boolean leftHanded,
                                  MatrixStack matrices, VertexConsumerProvider vertexConsumers,
                                  int light, int overlay, BakedModel model, CallbackInfo ci) {
        EntityRenderContext context = EntityRenderContext.get();
        if (context.isRemixPass()) {
            context.setBlockItemLayer(EntityRenderContext.NO_BLOCK_ITEM);
        }
    }

    /**
     * Asks the question terrain asks of a placed block, through the same
     * classifier, so a held block is classified exactly as its placed
     * counterpart is.
     */
    private static int rtxremix$blockLayer(ItemStack stack) {
        return stack.getItem() instanceof BlockItem blockItem
                ? BlockTextureManager.layerType(
                        BlockQuadEmitter.classifyBlockLayer(blockItem.getBlock().getDefaultState()))
                : EntityRenderContext.NO_BLOCK_ITEM;
    }
}
