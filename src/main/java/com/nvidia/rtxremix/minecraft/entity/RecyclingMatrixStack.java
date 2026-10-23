/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.entity;

import com.nvidia.rtxremix.minecraft.mixin.MatrixStackAccessor;
import com.nvidia.rtxremix.minecraft.mixin.MatrixStackEntryAccessor;
import net.minecraft.client.util.math.MatrixStack;
import org.joml.Quaternionf;

import java.util.ArrayDeque;
import java.util.Deque;

/**
 * Matrix stack dedicated to Remix entity capture.
 *
 * <p>Vanilla allocates an entry, a position matrix, and a normal matrix for
 * every {@link #push()}. Entity models repeat that traversal every frame, so
 * popped entries are retained here and copied back into service on the next
 * push. The pool belongs to this stack and therefore never changes vanilla
 * rendering outside the capture pass.
 */
public final class RecyclingMatrixStack extends MatrixStack {

    private final Deque<Entry> recycledEntries = new ArrayDeque<>();
    private final Quaternionf modelPartRotation = new Quaternionf();

    @Override
    public void push() {
        Deque<Entry> stack = stack();
        Entry previous = stack.getLast();
        Entry next = recycledEntries.pollLast();
        if (next == null) {
            super.push();
            return;
        }

        next.getPositionMatrix().set(previous.getPositionMatrix());
        next.getNormalMatrix().set(previous.getNormalMatrix());
        boolean canSkipNormalization = ((MatrixStackEntryAccessor) (Object) previous)
                .rtxremix$getCanSkipNormalization();
        ((MatrixStackEntryAccessor) (Object) next)
                .rtxremix$setCanSkipNormalization(canSkipNormalization);
        stack.addLast(next);
    }

    @Override
    public void pop() {
        recycledEntries.addLast(stack().removeLast());
    }

    /** Restores the identity root after a normal render or renderer exception. */
    void reset() {
        Deque<Entry> stack = stack();
        while (stack.size() > 1) {
            recycledEntries.addLast(stack.removeLast());
        }
        loadIdentity();
    }

    /** Applies vanilla's {@code ModelPart.rotate} transform without allocating a quaternion. */
    public void applyModelPartTransform(float pivotX, float pivotY, float pivotZ,
                                        float pitch, float yaw, float roll,
                                        float xScale, float yScale, float zScale) {
        translate(pivotX / 16.0F, pivotY / 16.0F, pivotZ / 16.0F);
        if (pitch != 0.0F || yaw != 0.0F || roll != 0.0F) {
            multiply(modelPartRotation.rotationZYX(roll, yaw, pitch));
        }
        if (xScale != 1.0F || yScale != 1.0F || zScale != 1.0F) {
            scale(xScale, yScale, zScale);
        }
    }

    private Deque<Entry> stack() {
        return ((MatrixStackAccessor) (Object) this).rtxremix$getStack();
    }
}
