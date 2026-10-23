/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Set;
import java.util.TreeSet;
import java.util.regex.Pattern;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RemixJavaBoundaryTest {
    private static final Pattern GAME_IMPORT = Pattern.compile(
            "(?m)^\\s*import\\s+(?:static\\s+)?net\\.(?:minecraft|fabricmc)\\.");

    @Test
    void shimSourcesDoNotImportMinecraftOrFabric() throws Exception {
        Path sourceRoot = Path.of("rtxremix-java", "src");
        assertTrue(Files.isDirectory(sourceRoot), "missing Java shim sources: " + sourceRoot);

        Set<String> offenders = new TreeSet<>();
        try (Stream<Path> sources = Files.walk(sourceRoot)) {
            var iterator = sources.filter(path -> path.toString().endsWith(".java")).iterator();
            while (iterator.hasNext()) {
                Path source = iterator.next();
                if (GAME_IMPORT.matcher(Files.readString(source)).find()) {
                    offenders.add(sourceRoot.relativize(source).toString());
                }
            }
        }

        assertEquals(Set.of(), offenders,
                "the Java shim must remain independent of Minecraft and Fabric");
    }
}
