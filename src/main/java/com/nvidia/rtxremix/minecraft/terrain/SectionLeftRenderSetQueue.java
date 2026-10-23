/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.terrain;

import java.util.Objects;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicReference;

/**
 * Queue of sections whose published vanilla chunk data is empty. The render
 * thread validates the live world section before removing Remix terrain.
 */
public final class SectionLeftRenderSetQueue {

    private static final AtomicReference<QueueState> STATE =
            new AtomicReference<>(new QueueState());

    private static final class QueueState {
        final ConcurrentLinkedQueue<SectionCoord> candidates = new ConcurrentLinkedQueue<>();
        final Set<SectionCoord> queued = ConcurrentHashMap.newKeySet();
    }

    private SectionLeftRenderSetQueue() {}

    public static void enqueueEmptyCandidate(int sectionX, int sectionY, int sectionZ) {
        enqueueEmptyCandidate(new SectionCoord(sectionX, sectionY, sectionZ));
    }

    public static void enqueueEmptyCandidate(SectionCoord section) {
        Objects.requireNonNull(section, "section");
        QueueState state = STATE.get();
        if (state.queued.add(section)) {
            state.candidates.add(section);
        }
    }

    public static SectionCoord pollEmptyCandidate() {
        QueueState state = STATE.get();
        SectionCoord section = state.candidates.poll();
        if (section == null) return null;

        state.queued.remove(section);
        return STATE.get() == state ? section : null;
    }

    public static void clear() {
        STATE.set(new QueueState());
    }

    public record SectionCoord(int x, int y, int z) {}
}
