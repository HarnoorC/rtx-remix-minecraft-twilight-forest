# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import struct
from pathlib import Path

import numpy as np

from rtx_tools import water_normals as wn

SMALL = wn.WaterParams(frame_size=32, cols=4, rows=3, fps=4, tile_metres=2.0, swell_metres=0.5, ripple_metres=0.004)


def test_splitmix64_matches_the_reference_generator():
    assert [int(v) for v in wn.splitmix64(0, 3)] == [0xE220A8397B1DCDAF, 0x6E789E6AA1B965F4, 0x06C45D188009454F]
    assert int(wn.splitmix64(1234567, 1)[0]) == 0x599ED017FB08FC85


def test_the_frame_after_the_last_is_the_first():
    ocean = wn.build_ocean(SMALL)

    assert np.allclose(wn.slopes(ocean, SMALL.frames), wn.slopes(ocean, 0))
    assert not np.allclose(wn.slopes(ocean, 1), wn.slopes(ocean, 0))


def test_the_slopes_belong_to_one_tiling_surface():
    slope = wn.slopes(wn.build_ocean(SMALL), 5)
    n = SMALL.frame_size
    f = np.fft.fftfreq(n)
    kx, ky = np.meshgrid(f, f)
    sx, sy = np.fft.fft2(slope[..., 0]), np.fft.fft2(slope[..., 1])
    along = np.abs(kx * sx + ky * sy) ** 2
    across = np.abs(-ky * sx + kx * sy) ** 2

    # A height that tiles climbs as much as it falls across a frame, and a surface's slope has no curl.
    assert np.allclose(slope.mean((0, 1)), 0.0)
    assert across.sum() < 1e-6 * along.sum()


def test_the_slope_has_the_requested_strength():
    ocean = wn.build_ocean(SMALL)
    mean_square = np.mean([np.mean(wn.slopes(ocean, frame) ** 2) for frame in range(SMALL.frames)])

    assert abs(np.sqrt(mean_square) / SMALL.slope_rms - 1) < 0.1


def test_octahedral_encoding_points_y_down_the_image():
    # A surface rising towards the right of the image and towards its top tilts the normal left and down the image,
    # which is +Y. The octahedral projection divides the normal by |x| + |y| + |z|.
    slope = np.array([[[0.1, -0.1]]])

    assert np.allclose(wn.octahedral(slope)[0, 0], [-0.1 / 1.2, 0.1 / 1.2])


def test_bc5_round_trip_stays_within_half_a_step():
    xy = wn.octahedral(wn.slopes(wn.build_ocean(SMALL), 3))
    decoded = wn.decode_bc5(wn.encode_bc5(xy), SMALL.frame_size, SMALL.frame_size)

    assert np.sqrt(np.mean((decoded - xy) ** 2)) * 127.5 < 0.5


def test_the_flipbook_is_a_bc5_sheet_with_a_full_mip_chain(tmp_path: Path):
    path = tmp_path / "water.dds"
    wn.write_flipbook(path, SMALL)
    data = path.read_bytes()
    width, height = SMALL.cols * SMALL.frame_size, SMALL.rows * SMALL.frame_size

    assert data[:4] == b"DDS "
    assert struct.unpack_from("<2I", data, 12) == (height, width)
    assert struct.unpack_from("<I", data, 28)[0] == 8
    assert data[84:88] == b"DX10"
    assert struct.unpack_from("<I", data, 128)[0] == wn.DXGI_FORMAT_BC5_UNORM
    level_bytes = [-(-w // 4) * -(-h // 4) * 16 for w, h in wn.mip_dims(width, height)]
    assert len(data) == 148 + sum(level_bytes)


def test_frames_fill_the_sheet_row_by_row(tmp_path: Path):
    path = tmp_path / "water.dds"
    wn.write_flipbook(path, SMALL)
    n, cols = SMALL.frame_size, SMALL.cols
    blocks = np.frombuffer(path.read_bytes()[148 : 148 + cols * SMALL.rows * n * n], np.uint8)
    sheet = wn.decode_bc5(blocks.reshape(SMALL.rows * n // 4, cols * n // 4, 16), cols * n, SMALL.rows * n)
    ocean = wn.build_ocean(SMALL)

    frame = cols + 1
    tile = sheet[n : 2 * n, n : 2 * n]
    assert np.sqrt(np.mean((tile - wn.octahedral(wn.slopes(ocean, frame))) ** 2)) * 127.5 < 0.5


def test_a_seed_always_writes_the_same_file(tmp_path: Path):
    first, second = tmp_path / "a.dds", tmp_path / "b.dds"
    wn.write_flipbook(first, SMALL)
    wn.write_flipbook(second, SMALL)

    assert first.read_bytes() == second.read_bytes()
