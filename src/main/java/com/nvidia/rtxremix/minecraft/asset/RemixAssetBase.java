/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.asset;

import com.nvidia.rtxremix.RemixAPI;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.lang.ref.Cleaner;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.locks.ReentrantReadWriteLock;
import java.util.function.BiConsumer;

/**
 * Abstract base for all stateful Remix asset types (mesh, material, texture,
 * light, instance). Owns the {@link ReentrantReadWriteLock} that guards all
 * mutable state, the Cleaner-based leak detector, and the common lifecycle
 * transitions (NOT_CREATED -> ALIVE -> DELETED).
 *
 * <p>Subclasses implement {@link #doCreate}, {@link #doDestroy}, and
 * {@link #doDisposeData} to interact with the concrete Remix C API calls.
 *
 * <p>Thread safety: write lock for {@code create/update/destroy}, read lock
 * for {@code isAlive/isDeleted/getHandle/draw}. The RWLock provides
 * happens-before guarantees, so all fields are plain (no volatile).
 */
public abstract class RemixAssetBase {

    private static final Logger LOGGER = LoggerFactory.getLogger(RemixAssetBase.class);
    private static final Cleaner CLEANER = Cleaner.create();

    protected final ReentrantReadWriteLock rwLock = new ReentrantReadWriteLock();

    protected long handle;
    protected long hash;
    protected DeletionReason deletionFlag = DeletionReason.NOT_DELETED;
    protected boolean dataDisposed;
    protected RemixAPI api;

    private final AtomicInteger cleanerDeletionOrdinal = new AtomicInteger(DeletionReason.NOT_DELETED.ordinal());
    private final AtomicLong cleanerHandleRef = new AtomicLong();
    private Cleaner.Cleanable cleanable;
    private BiConsumer<Long, RemixAssetBase> deletionReporter;

    /**
     * Registers this asset's leak detector with the Cleaner. Called by the
     * store after the hash is known and the asset is registered in the map.
     * The cleanup action captures only atomics and the store-lookup lambda
     * (never a reference to {@code this}).
     */
    void registerCleaner(BiConsumer<Long, Long> leakReporter,
                         BiConsumer<Long, RemixAssetBase> deletionReporter) {
        rwLock.writeLock().lock();
        try {
            long capturedHash = this.hash;
            AtomicInteger delOrd = this.cleanerDeletionOrdinal;
            AtomicLong hRef = this.cleanerHandleRef;
            this.deletionReporter = deletionReporter;

            this.cleanable = CLEANER.register(this, () -> {
                if (delOrd.get() == DeletionReason.NOT_DELETED.ordinal()) {
                    long leaked = hRef.get();
                    LOGGER.error("MEMORY LEAK: {}(hash=0x{}) was GC'd without destroy()!",
                            leaked != 0 ? "Asset" : "UninitialisedAsset",
                            Long.toHexString(capturedHash));
                    if (leakReporter != null && leaked != 0) {
                        leakReporter.accept(capturedHash, leaked);
                    }
                }
            });
            if (this.deletionFlag != DeletionReason.NOT_DELETED) {
                this.cleanable.clean();
                this.cleanable = null;
                reportDeletion();
            }
        } finally {
            rwLock.writeLock().unlock();
        }
    }

    /**
     * Package-private. Only the owning store calls this after claiming a hash.
     *
     * @param api         the Remix API instance
     * @param hash        the unique 64-bit hash assigned by the store
     * @param disposeData if true, native buffers are freed after creation
     */
    void create(RemixAPI api, long hash, boolean disposeData) {
        rwLock.writeLock().lock();
        try {
            if (this.handle != 0) {
                throw new IllegalStateException(typeName() + " already created (hash=0x"
                        + Long.toHexString(this.hash) + ")");
            }
            this.api = api;
            this.hash = hash;
            this.handle = doCreate(api, hash);
            cleanerHandleRef.set(this.handle);
            if (disposeData) {
                doDisposeData();
                dataDisposed = true;
            }
        } catch (RuntimeException e) {
            this.handle = 0;
            cleanerHandleRef.set(0);
            if (disposeData && !dataDisposed) {
                try {
                    doDisposeData();
                    dataDisposed = true;
                } catch (RuntimeException cleanupError) {
                    e.addSuppressed(cleanupError);
                    LOGGER.warn("Failed to dispose {} creation data after create failure",
                            typeName(), cleanupError);
                }
            }
            throw e;
        } finally {
            rwLock.writeLock().unlock();
        }
    }

    public void destroy() {
        destroy(DeletionReason.DIRECT_REQUEST);
    }

    public void destroy(DeletionReason reason) {
        rwLock.writeLock().lock();
        try {
            if (deletionFlag != DeletionReason.NOT_DELETED) {
                LOGGER.warn("Thread '{}' tried to destroy already-deleted {}(hash=0x{}, reason={})",
                        Thread.currentThread().getName(), typeName(),
                        Long.toHexString(hash), deletionFlag);
                return;
            }

            // Keep the asset live if the native destroy fails. Marking it
            // deleted first lets store GC remove the last Java owner while the
            // native handle is still allocated.
            if (handle != 0 && api != null) {
                doDestroy(api, handle);
            }
            handle = 0;
            cleanerHandleRef.set(0);

            deletionFlag = reason;
            cleanerDeletionOrdinal.set(reason.ordinal());
            Cleaner.Cleanable registeredCleaner = cleanable;
            cleanable = null;
            if (registeredCleaner != null) {
                registeredCleaner.clean();
            }
            reportDeletion();

            if (!dataDisposed) {
                doDisposeData();
                dataDisposed = true;
            }
        } finally {
            rwLock.writeLock().unlock();
        }
    }

    private void reportDeletion() {
        BiConsumer<Long, RemixAssetBase> reporter = deletionReporter;
        deletionReporter = null;
        if (reporter != null) {
            reporter.accept(hash, this);
        }
    }

    // --- read-locked queries ---

    public boolean isDeleted() {
        rwLock.readLock().lock();
        try {
            return deletionFlag != DeletionReason.NOT_DELETED;
        } finally {
            rwLock.readLock().unlock();
        }
    }

    /**
     * Lock-free deletion check for render-thread-only hot paths.
     * Only safe when caller is guaranteed to be on the same thread as
     * {@link #destroy(DeletionReason)}.
     */
    public boolean isDeletedFast() {
        return deletionFlag != DeletionReason.NOT_DELETED;
    }

    public boolean isAlive() {
        rwLock.readLock().lock();
        try {
            return handle != 0 && deletionFlag == DeletionReason.NOT_DELETED;
        } finally {
            rwLock.readLock().unlock();
        }
    }

    public long getHandle() {
        rwLock.readLock().lock();
        try {
            return handle;
        } finally {
            rwLock.readLock().unlock();
        }
    }

    /**
     * Lock-free handle lookup for render-thread-only hot paths.
     * Only safe when creation, replacement, and destruction are confined to the caller's thread.
     */
    public long getHandleFast() {
        return handle;
    }

    public long getHash() {
        return hash;
    }

    public DeletionReason getDeletionFlag() {
        rwLock.readLock().lock();
        try {
            return deletionFlag;
        } finally {
            rwLock.readLock().unlock();
        }
    }

    // --- subclass hooks ---

    protected abstract long doCreate(RemixAPI api, long hash);

    protected abstract void doDestroy(RemixAPI api, long handle);

    /** Free any native buffers held for creation. Called under write lock. */
    protected abstract void doDisposeData();

    /** Replaces the native handle after an in-place recreate/update. Called under write lock. */
    protected final void replaceNativeHandle(long newHandle) {
        handle = newHandle;
        cleanerHandleRef.set(newHandle);
    }

    /** Human-readable type name for logging (e.g. "RemixMesh"). */
    protected abstract String typeName();
}
