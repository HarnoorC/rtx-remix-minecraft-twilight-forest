# Built-In LabPBR Textures

The mod JAR supplies the baseline LabPBR textures through Fabric's `fabric`
resource pack, below user packs. No separate baseline pack needs enabling.

The assets include the minimum set of LabPBR sidecars this renderer needs:
`_s` for blocks that are meant to glow and `_sss` for foliage so leaves and
grass scatter light. Sky and particle base textures are included too.

The sidecars and the sun and moon textures are covered by the repository
[LICENSE](../../../LICENSE). Copy them and build on them. None of them carries
Minecraft's pixels. A glow map for a block that glows all over holds one value.
A glow map for part of a texture, such as a torch flame, is a mask drawn by
hand to line up with the vanilla texture, so a pack that redraws that texture
should ship its own `_s` too. The sun and moon are original pixel art.

The explosion particle frames are not covered by that grant yet; their
provenance is still being confirmed.
[Resource Packs](../../../docs/RESOURCE_PACKS.md) explains each channel.
